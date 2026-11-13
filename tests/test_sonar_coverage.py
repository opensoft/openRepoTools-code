# SPDX-License-Identifier: Apache-2.0
"""Reject fabricated coverage, changed copies and incomplete language reports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import os
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture
def collector():
    spec = importlib.util.spec_from_file_location(
        "sonar_coverage_test", HERE / ".github/ci/sonar_coverage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source(tmp_path, name="command", language="shell"):
    content = b"#!/usr/bin/env bash\necho hello\n"
    path = tmp_path / name
    path.write_bytes(content)
    return {"schema": 1, "files": [{
        "path": name, "language": language, "test": False,
        "sha256": hashlib.sha256(content).hexdigest(), "lines": 2}]}


def test_source_verification_rejects_modified_bytes(collector, tmp_path):
    manifest = source(tmp_path)
    collector.checked_sources(tmp_path, manifest)
    (tmp_path / "command").write_bytes(b"#!/usr/bin/env bash\necho pwned\n")
    with pytest.raises(ValueError, match="source changed"):
        collector.checked_sources(tmp_path, manifest)


def test_report_rejects_incomplete_scope_out_of_bounds_and_unmeasured_language(collector, tmp_path):
    manifest = source(tmp_path)
    for measurements in ({}, {"command": {3: True}}, {"command": {2: False}}):
        with pytest.raises(ValueError):
            collector.write_report(tmp_path, manifest, measurements)
    summary = collector.write_report(tmp_path, manifest, {"command": {2: True}})
    assert summary["languages"]["shell"] == {"covered": 1, "lines": 1}
    assert 'path="command"' in (tmp_path / "coverage.xml").read_text()


def test_shell_hits_require_known_hash_and_exact_baseline_bytes(collector, tmp_path):
    root = tmp_path / "root"
    out = tmp_path / "out"
    root.mkdir(); out.mkdir()
    manifest = source(root)
    staged = out / "shell-sources"
    staged.mkdir()
    (staged / "command").write_bytes((root / "command").read_bytes())
    (out / "shell-baseline.xml").write_text(
        '<coverage version="1"><file path="' + str(staged / "command")
        + '"><lineToCover lineNumber="2" covered="false"/></file></coverage>')
    hits = out / "shell-hits"
    hits.write_text(manifest["files"][0]["sha256"] + "\t2\n")
    assert collector.shell_lines(out, manifest) == {"command": {2: True}}
    hits.write_text("0" * 64 + "\t2\n")
    with pytest.raises(ValueError, match="unknown shell hit"):
        collector.shell_lines(out, manifest)
    hits.unlink()
    (staged / "command").write_text("modified")
    with pytest.raises(ValueError, match="denominator bytes"):
        collector.shell_lines(out, manifest)


@pytest.mark.parametrize("spelling", ["copied", "copy with spaces", "control", "copy$(touch OWNED)"])
def test_bash_collector_credits_exact_copy_without_recording_arguments(tmp_path, spelling):
    manifest = source(tmp_path)
    name = "copy" + chr(92) + chr(10) + "name" if spelling == "control" else spelling
    copied = tmp_path / name
    copied.write_bytes((tmp_path / "command").read_bytes())
    env = dict(os.environ, BASH_ENV=str(HERE / ".github/ci/sonar_coverage/bash-env.sh"),
               ORT_SONAR_SHELL_HASHES=manifest["files"][0]["sha256"],
               ORT_SONAR_SHELL_HITS=str(tmp_path / "hits"))
    result = subprocess.run(["bash", str(copied), "private-argument"],
                            env=env, cwd=tmp_path, capture_output=True, text=True, check=True)
    assert result.stdout == "hello\n"
    rows = "".join(path.read_text() for path in tmp_path.glob("hits*"))
    assert manifest["files"][0]["sha256"] + "\t2\n" in rows
    assert "private-argument" not in rows
    assert "hello" not in rows
    for path in tmp_path.glob("hits*"):
        path.unlink()
    copied.write_text("#!/usr/bin/env bash\necho changed\n")
    subprocess.run(["bash", str(copied)], env=env, cwd=tmp_path, capture_output=True, check=True)
    assert not list(tmp_path.glob("hits*"))
    assert not (tmp_path / "OWNED").exists()


def test_collector_refuses_missing_coverage_before_starting_tests(collector, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "coverage", None)
    with pytest.raises(ModuleNotFoundError):
        collector.prepare(tmp_path, tmp_path, tmp_path / "not-executed")


def test_clean_python_environment_keeps_its_dependency_isolation(tmp_path):
    target = tmp_path / "isolated"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(target)],
                   check=True, capture_output=True)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = dict(os.environ,
               PYTHONPATH=str(HERE / ".github/ci/sonar_coverage"),
               ORT_SONAR_INVENTORY=str(tmp_path / "intentionally-absent"),
               COVERAGE_PROCESS_START=str(tmp_path / "intentionally-absent.rc"))
    result = subprocess.run([str(python), "-c", "print('isolation-preserved')"],
                            env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "isolation-preserved"
    assert result.stderr == ""


def test_measurement_preserves_the_applications_default_sigterm_handler(
        collector, tmp_path, monkeypatch):
    # Supervisors install cleanup only when SIGTERM retains its default.
    # Instrumentation must not take ownership of that application contract.
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    root, out = tmp_path / "checkout", tmp_path / "report"
    root.mkdir(); out.mkdir()
    (out / "inventory.json").write_text(json.dumps({"files": []}))
    env = {**os.environ, **collector.coverage_environment(root, out, [])}
    config = (out / collector.COVERAGE_CONFIG).read_text()
    assert "sigterm = false" in config
    result = subprocess.run([sys.executable, "-c",
        "import signal; assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL; "
        "print('signal-contract-preserved')"],
        env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "signal-contract-preserved"
    assert result.stderr == ""


@pytest.mark.skipif(os.name == "nt", reason="Windows cannot remove the process working directory")
def test_deleted_working_directory_remains_deleted_and_receives_no_coverage(tmp_path):
    # Coverage imports os.getcwd() at module load. Use a stub so this startup
    # boundary is exercised even in the ordinary pytest-only test environment.
    stub = tmp_path / "stub"
    stub.mkdir()
    marker = tmp_path / "measurement-started"
    (stub / "coverage.py").write_text(
        "import os\nfrom pathlib import Path\nos.getcwd()\n"
        f"Path({str(marker)!r}).write_text('started')\n")
    gone = tmp_path / "gone"
    gone.mkdir()
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join((str(HERE / ".github/ci/sonar_coverage"), str(stub))),
               ORT_SONAR_INVENTORY=str(tmp_path / "inventory.json"),
               COVERAGE_PROCESS_START=str(tmp_path / "coverage.rc"))
    command = ("import os\ntry: os.getcwd()\nexcept FileNotFoundError: "
               "print('deleted-directory-preserved')\nelse: raise AssertionError('cwd changed')")
    result = subprocess.run(
        ["sh", "-c", 'cd "$1" && rmdir "$1" && shift && exec "$@"', "sh",
         str(gone), sys.executable, "-c", command],
        env=env, capture_output=True, text=True, check=True)
    assert result.stdout == "deleted-directory-preserved\n"
    assert result.stderr == ""
    assert not marker.exists()
    assert not gone.exists()


def test_startup_still_reports_configuration_errors_from_an_existing_directory(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "coverage.py").write_text(
        "def process_startup():\n    raise RuntimeError('invalid-coverage-configuration')\n")
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join((str(HERE / ".github/ci/sonar_coverage"), str(stub))),
               ORT_SONAR_INVENTORY=str(tmp_path / "inventory.json"),
               COVERAGE_PROCESS_START=str(tmp_path / "coverage.rc"))
    result = subprocess.run([sys.executable, "-c", "pass"], cwd=tmp_path,
                            env=env, capture_output=True, text=True, check=True)
    assert "RuntimeError: invalid-coverage-configuration" in result.stderr
