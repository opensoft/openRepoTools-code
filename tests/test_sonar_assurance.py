# SPDX-License-Identifier: Apache-2.0
"""Acceptance is complete source inventory and a computed, unchanged gate."""
import importlib.util
import json
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


@pytest.mark.parametrize("conditions,ignored", [
    ([{"metricKey": "new_reliability_rating"}], False),
    ([{"metricKey": "new_coverage"}], True),
])
def test_gate_refuses_unevaluated_or_ignored_coverage(assurance, conditions, ignored):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    with pytest.raises(ValueError, match="evaluate new coverage"):
        assurance.verify_gate({"projectStatus": {
            "status": "OK", "periods": [{"index": 1}],
            "conditions": conditions, "ignoredConditions": ignored}}, thresholds)


@pytest.mark.parametrize("failure", [
    None, "wrong-project", "compute-pending", "missing-source",
    "wrong-language", "missing-coverage", "neutral-gate", "wrong-revision",
    "pr-zero-coverage", "pr-covered", "pr-no-metric",
])
def test_analysis_verifies_the_submitted_task_sources_and_coverage(
        assurance, tmp_path, monkeypatch, failure):
    manifest = {"commits": {".": "b" * 40},
                "files": [{"path": "code/lane", "language": "shell"}]}
    (tmp_path / "inventory.json").write_text(json.dumps(manifest))
    task = tmp_path / "report-task.txt"
    project = "wrong" if failure == "wrong-project" else assurance.PROJECT
    task.write_text("projectKey=" + project + "\nceTaskId=task-123\n")
    conditions = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    calls = []
    pull_request = "361" if failure and failure.startswith("pr-") else None
    positive = failure in (None, "pr-zero-coverage", "pr-covered")

    def api(endpoint, parameters):
        calls.append((endpoint, parameters))
        if endpoint == "ce/task":
            return {"task": {"status": "PENDING" if failure == "compute-pending" else "SUCCESS",
                             "analysisId": "analysis-123"}}
        if endpoint == "qualitygates/project_status":
            return {"projectStatus": {
                "status": "NONE" if failure == "neutral-gate" else "OK",
                "periods": [] if pull_request else [{"index": 1}],
                "conditions": [{"metricKey": "new_reliability_rating" if failure == "pr-zero-coverage"
                                else "new_coverage"}]}}
        if endpoint == "qualitygates/get_by_project":
            assert parameters["organization"] == "opensoft"
            return {"qualityGate": {"id": 9}}
        if endpoint == "qualitygates/show":
            assert parameters["organization"] == "opensoft"
            return {"id": 9, "conditions": conditions}
        if endpoint == "components/tree":
            files = [] if failure in ("missing-source", "pr-zero-coverage") else [{
                "path": "code/lane", "language": "py" if failure == "wrong-language" else "shell"}]
            return {"paging": {"total": len(files)}, "components": files}
        if endpoint == "measures/component":
            measures = [] if failure == "missing-coverage" else [
                {"metric": "coverage", "value": "90.0"}, {"metric": "lines_to_cover", "value": "100"}]
            if pull_request:
                measures = [] if failure == "pr-no-metric" else [{
                    "metric": "new_lines_to_cover", "periods": [
                        {"index": 1, "value": "0" if failure == "pr-zero-coverage" else "100"}]}]
                if failure == "pr-covered":
                    measures.append({"metric": "new_coverage", "periods": [{"index": 1, "value": "90.0"}]})
            return {"component": {"measures": measures}}
        if endpoint == "project_analyses/search":
            revision = "c" * 40 if failure == "wrong-revision" else "b" * 40
            return {"analyses": [{"key": "analysis-123", "revision": revision}]}
        raise AssertionError(endpoint)

    monkeypatch.setattr(assurance, "sonar_api", api)
    if not positive:
        with pytest.raises(ValueError):
            assurance.verify_analysis(tmp_path, task, pull_request)
        assert not (tmp_path / "acceptance.json").exists()
    else:
        receipt = assurance.verify_analysis(tmp_path, task, pull_request)
        assert receipt["analysisId"] == "analysis-123"
        assert receipt["indexed_sources"] == (0 if failure == "pr-zero-coverage" else 1)
        assert receipt["full_index_verified"] == (not bool(pull_request))
        assert receipt["coverage_import_verified"] == (not bool(pull_request))
        assert calls[1][1] == {"analysisId": "analysis-123"}
        assert (tmp_path / "acceptance.json").exists()
