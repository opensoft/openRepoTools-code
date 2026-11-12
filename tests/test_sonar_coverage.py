# SPDX-License-Identifier: Apache-2.0
"""Reject fabricated coverage, changed copies and incomplete language reports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import os

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
