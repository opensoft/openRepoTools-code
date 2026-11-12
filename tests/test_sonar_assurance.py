# SPDX-License-Identifier: Apache-2.0
"""Acceptance is complete source inventory and a computed, unchanged gate."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture
def assurance():
    spec = importlib.util.spec_from_file_location(
        "sonar_assurance_test", HERE / ".github/ci/sonar_assurance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo(tmp_path, files):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", *files], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test",
                    "-c", "user.email=test@invalid", "commit", "-qm", "fixture"], check=True)
    return tmp_path


def test_inventory_includes_extensionless_and_tests_and_rejects_source_drift(assurance, tmp_path):
    root = repo(tmp_path, {"command": b"#!/usr/bin/env bash\necho hello\n",
                           "index": b"#!/usr/bin/env python3\nprint(1)\n",
                           "tests/test_sample.py": b"assert True\n",
                           "README.md": b"notes\n"})
    manifest = assurance.inventory(root)
    assert {(item["path"], item["language"], item["test"]) for item in manifest["files"]} == {
        ("command", "shell", False), ("index", "py", False),
        ("tests/test_sample.py", "py", True)}
    (root / "command").write_text("changed\n")
    with pytest.raises(ValueError, match="tracked source changes"):
        assurance.inventory(root)


def test_configuration_covers_each_command_and_removes_automatic_coverage_exclusion(assurance, tmp_path):
    manifest = {"commits": {".": "a" * 40},
                "files": [{"path": "code/lane", "language": "shell", "test": False},
                          {"path": "code/lanes-index", "language": "py", "test": False},
                          {"path": "code/tests/test_sample.py", "language": "py", "test": True}]}
    config = assurance.write_configuration(tmp_path, tmp_path / "out", manifest)
    assert config["sonar.lang.patterns.shell"] == "code/lane"
    assert config["sonar.lang.patterns.py"] == "code/lanes-index,code/tests/test_sample.py"
    assert config["sonar.coverage.exclusions"] == ""
    assert config["sonar.python.version"] == "3.9"
    assert config["sonar.qualitygate.wait"] == "true"
    assert config["sonar.exclusions"] == "code/tests/test_sample.py"
    assert config["sonar.test.inclusions"] == config["sonar.exclusions"]


@pytest.mark.parametrize("status,period,conditions", [
    ("NONE", [], []), ("OK", [], [{"metricKey": "new_coverage"}]),
    ("ERROR", [{"index": 1}], [{"metricKey": "new_coverage"}]),
])
def test_gate_rejects_neutral_missing_period_and_failures(assurance, status, period, conditions):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    with pytest.raises(ValueError):
        assurance.verify_gate({"projectStatus": {
            "status": status, "periods": period, "conditions": conditions}}, thresholds)


def test_gate_rejects_relaxed_thresholds_and_accepts_computed_result(assurance):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    status = {"projectStatus": {"status": "OK", "periods": [{"index": 1}],
                                "conditions": [{"metricKey": "new_coverage", "status": "OK"}]}}
    assert assurance.verify_gate(status, thresholds)["status"] == "OK"
    thresholds[0]["error"] = "5"
    with pytest.raises(ValueError, match="thresholds"):
        assurance.verify_gate(status, thresholds)


def test_ci_paths_refuse_other_checkouts_and_arbitrary_report_paths(assurance, tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    runner = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(root))
    monkeypatch.setenv("RUNNER_TEMP", str(runner))
    assert assurance.ci_paths(root, runner / "sonar") == (root, runner / "sonar")
    with pytest.raises(ValueError, match="paths must match"):
        assurance.ci_paths(tmp_path / "other", runner / "sonar")
    with pytest.raises(ValueError, match="paths must match"):
        assurance.ci_paths(root, runner / "elsewhere")


def test_pr_gate_is_computed_without_a_main_branch_period(assurance):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    status = {"projectStatus": {"status": "OK", "periods": [],
                                "conditions": [{"metricKey": "new_coverage", "status": "OK"}]}}
    assert assurance.verify_gate(status, thresholds, require_period=False)["status"] == "OK"
