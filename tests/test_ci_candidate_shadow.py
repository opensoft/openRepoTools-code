# SPDX-License-Identifier: Apache-2.0
"""Offline shadow-caller contracts; never queue or exempt an original PR."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

from conftest import NEEDS_UPSTREAM, REPO, UPSTREAM


@pytest.fixture
def caller():
    if not (UPSTREAM / "scripts/repo_shape.py").is_file():
        pytest.skip("Pinned upstream YAML reader is not initialized")
    spec = importlib.util.spec_from_file_location(
        "candidate_shadow_yaml", UPSTREAM / "scripts/repo_shape.py")
    reader = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reader
    spec.loader.exec_module(reader)
    return reader.load_yaml(REPO / ".github/workflows/task-set-candidate-shadow.yml")


def test_ci_candidate_shadow_push_only_non_gating_graph(caller):
    assert caller["on"] == {"push": {"branches": ["mergify/merge-queue/*"]}}
    assert caller["permissions"] == {}
    assert set(caller["jobs"]) == {"probe", "candidate"}
    probe = caller["jobs"]["probe"]
    assert probe["timeout-minutes"] == 15
    assert probe["runs-on"] == "ubuntu-24.04"
    assert probe["permissions"] == {
        "contents": "read", "pull-requests": "read", "checks": "read", "actions": "read"}
    assert probe["outputs"] == {"qualify": "${{ steps.scope.outputs.qualify }}"}
    assert len(probe["steps"]) == 2
    checkout, step = probe["steps"]
    assert checkout == {
        "uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "with": {"ref": "main", "fetch-depth": 0, "persist-credentials": False}}
    assert step["id"] == "scope"
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "${{" not in step["run"]  # No payload interpolation into shell.
    call = caller["jobs"]["candidate"]
    assert call == {
        "needs": "probe",
        "if": "${{ needs.probe.result == 'success' && needs.probe.outputs.qualify == 'true' }}",
        "permissions": probe["permissions"],
        "uses": "./.github/workflows/task-set-candidate.yml"}


@pytest.mark.parametrize("policy,expected", [
    (None, False),
    ("raise SystemExit(1)\n", False),
    ("raise RuntimeError('fixture crash')\n", False),
    ("raise SystemExit(2)\n", False),
    ("raise SystemExit(0)\n", True),
    ("print('qualify=true\\n::set-output name=qualify::true')\nraise SystemExit(1)\n", False),
])
def test_ci_candidate_shadow_actual_probe_shell(caller, tmp_path, policy, expected):
    script = caller["jobs"]["probe"]["steps"][1]["run"]
    policy_dir = tmp_path / ".github/ci"
    policy_dir.mkdir(parents=True)
    if policy is not None:
        (policy_dir / "delivery_verify.py").write_text(
            "import sys\nassert sys.argv[1:] == ['candidate']\n" + policy)
    output, summary = tmp_path / "output", tmp_path / "summary"
    result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=tmp_path,
                            env=dict(os.environ, GITHUB_OUTPUT=str(output),
                                     GITHUB_STEP_SUMMARY=str(summary)),
                            capture_output=True, timeout=10)
    assert result.returncode == 0
    assert output.read_text() == f"qualify={str(expected).lower()}\n"
    assert "full CI remains required" in summary.read_text()
    assert "No queue admission" in summary.read_text()


@pytest.mark.parametrize("probe_result,output,scheduled", [
    ("success", "true", True), ("success", "false", False),
    ("success", "", False), ("success", "True", True),
    ("failure", "true", False), ("cancelled", "true", False),
    ("skipped", "true", False), ("timed_out", "true", False),
])
def test_ci_candidate_shadow_scheduling_condition_contract(caller, probe_result, output, scheduled):
    expression = caller["jobs"]["candidate"]["if"]
    assert expression == "${{ needs.probe.result == 'success' && needs.probe.outputs.qualify == 'true' }}"
    # Actions string equality ignores case. This is a bounded interpretation
    # of the asserted graph expression, not an executed hosted scheduler.
    # The actual probe-shell tests above prove it emits lowercase literals.
    assert ((probe_result.casefold() == "success") and (output.casefold() == "true")) is scheduled


@NEEDS_UPSTREAM
def test_ci_candidate_shadow_keeps_reusable_proof_and_full_coverage(caller):
    # The independently tested existing entry must remain the only heavy caller.
    assert caller["jobs"]["candidate"]["uses"] == "./.github/workflows/task-set-candidate.yml"
    assert "openrepotools-batch-heavy" not in (REPO / ".mergify.yml").read_text()
    assert "openrepotools-pr-fast" not in (REPO / ".mergify.yml").read_text()
    instructions = (REPO / ".github/ci/delivery-preparation.md").read_text()
    assert "task-set-candidate-shadow.yml" in instructions
    assert "does not save heavy runs" in instructions
    assert "separately approved merge" in instructions
