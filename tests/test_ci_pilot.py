# SPDX-License-Identifier: Apache-2.0
"""Offline shadow classification; all git repositories are local fixtures."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, UPSTREAM, NEEDS_UPSTREAM

SCRIPT = REPO / ".github/ci/pilot_scope.py"
spec = importlib.util.spec_from_file_location("pilot_scope", SCRIPT)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
REPOSITORY = "example/project-code"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   stderr=subprocess.STDOUT).decode().strip()


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


def event(base, head):
    def side(sha):
        return {"sha": sha, "repo": {"full_name": REPOSITORY}}
    return {"action": "synchronize", "pull_request": {
        "state": "open", "draft": False, "base": side(base), "head": side(head)}}


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "CI Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.filemode", "true")
    (root / "tests").mkdir()
    (root / "claude-current").write_text("#!/bin/sh\nexit 0\n")
    (root / "claude-current").chmod(0o755)
    (root / "tests/test_claude_current.py").write_text("# old\n")
    base = commit(root)
    # Explicit Git mode also works on filesystems without POSIX chmod.
    git(root, "update-index", "--chmod=+x", "claude-current")
    git(root, "commit", "--amend", "--no-edit", "-q")
    base = git(root, "rev-parse", "HEAD")
    (root / "tests/test_claude_current.py").write_text("# new\n")
    head = commit(root)
    return root, base, head


def observe(history, payload=None, kind="pull_request"):
    root, base, head = history
    return pilot.classify(kind, event(base, head) if payload is None else payload,
                          root, REPOSITORY)


def assert_full_acceptance(result):
    assert result["mode"] == "shadow"
    assert result["required_ci"] == "full"
    assert result["queue_admission"] is False


def test_narrow_shadow_candidate_still_requires_every_acceptance_gate(history):
    result = observe(history)
    assert result["candidate_scope"] == "claude-current"
    assert result["files"] == ["tests/test_claude_current.py"]
    assert (result["base"], result["head"]) == history[1:]
    assert_full_acceptance(result)


@pytest.mark.parametrize("action", sorted(pilot.OBSERVE))
def test_open_metadata_is_recomputed_not_granted_by_actor_labels_or_body(history, action):
    payload = event(*history[1:])
    payload.update(action=action, sender={"login": "unrelated-third-party"})
    payload["pull_request"].update(body="approved fast queue", labels=[{"name": "fast"}])
    result = observe(history, payload)
    assert result["candidate_scope"] == "claude-current"
    assert_full_acceptance(result)


@pytest.mark.parametrize("action", ["closed", "dequeued", "enqueued", "converted_to_draft", "unknown"])
def test_closed_dequeued_and_unknown_events_stay_full(history, action):
    payload = event(*history[1:])
    payload["action"] = action
    if action == "closed":
        payload["pull_request"].update(state="closed", merged=True)
    result = observe(history, payload)
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


@pytest.mark.parametrize("kind", ["push", "merge_group", "workflow_dispatch", "pull_request_target", ""])
def test_non_pr_events_never_claim_fast_eligibility(history, kind):
    result = observe(history, kind=kind)
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


@pytest.mark.parametrize("mutation", ["draft", "missing-draft", "missing-base", "fork", "bad-sha", "missing-object", "closed-state"])
def test_incomplete_or_foreign_context_falls_back(history, mutation):
    payload = event(*history[1:])
    pr = payload["pull_request"]
    if mutation == "draft":
        pr["draft"] = True
    elif mutation == "missing-draft":
        del pr["draft"]
    elif mutation == "missing-base":
        del pr["base"]
    elif mutation == "fork":
        pr["head"]["repo"]["full_name"] = "fork/project-code"
    elif mutation == "bad-sha":
        pr["head"]["sha"] = "--output=unexpected"
    elif mutation == "missing-object":
        pr["head"]["sha"] = "0" * 40
    else:
        pr["state"] = "closed"
    result = observe(history, payload)
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


@pytest.mark.parametrize("payload", [None, [], {}, {"pull_request": []}, {"action": []}])
def test_malformed_payload_does_not_grant_scope(history, payload):
    result = pilot.classify("pull_request", payload, history[0], REPOSITORY)
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


@pytest.mark.parametrize("path", ["lane-start", ".github/workflows/tests.yml", "README.md", "tests/test_claude_restart_check.py"])
def test_mixed_changes_keep_full_scope_even_with_fast_metadata(history, path):
    root, base, _ = history
    changed = root / path
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("# unrelated\n")
    head = commit(root)
    result = observe((root, base, head))
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


@pytest.mark.parametrize("operation", ["delete", "rename", "symlink", "executable-test"])
def test_nonregular_deleted_renamed_and_mode_changes_keep_full_scope(history, operation):
    root, base, _ = history
    target = root / "tests/test_claude_current.py"
    if operation == "delete":
        target.unlink()
    elif operation == "rename":
        target.rename(root / "tests/moved.py")
    elif operation == "symlink":
        target.unlink()
        try:
            target.symlink_to("../claude-current")
        except OSError:
            pytest.skip("filesystem does not allow symlinks")
    else:
        target.chmod(0o755)
    head = commit(root)
    result = observe((root, base, head))
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


def test_upper_pr_excludes_predecessors_changes(history):
    root, _, _ = history
    (root / "lane-start").write_text("# predecessor-only\n")
    predecessor = commit(root)
    (root / "tests/test_claude_current.py").write_text("# upper-only\n")
    head = commit(root)
    result = observe((root, predecessor, head))
    assert result["candidate_scope"] == "claude-current"
    assert result["files"] == ["tests/test_claude_current.py"]
    assert_full_acceptance(result)


def test_unrelated_history_and_empty_diff_keep_full_scope(history):
    root, base, head = history
    assert observe((root, head, head))["candidate_scope"] == "full"
    unrelated = git(root, "commit-tree", "HEAD^{tree}", "-m", "unrelated")
    result = observe((root, base, unrelated))
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


def test_cli_reads_event_as_data_and_prints_no_admission(history, tmp_path):
    root, base, head = history
    payload = event(base, head)
    payload["pull_request"]["body"] = "$(touch should-not-exist)\n::error::injection"
    event_file, summary = tmp_path / "event.json", tmp_path / "summary.md"
    event_file.write_text(json.dumps(payload))
    env = dict(os.environ, GITHUB_EVENT_PATH=str(event_file), GITHUB_EVENT_NAME="pull_request",
               GITHUB_REPOSITORY=REPOSITORY, GITHUB_STEP_SUMMARY=str(summary))
    output = subprocess.check_output([sys.executable, str(SCRIPT)], cwd=root, env=env, text=True)
    result = json.loads(output)
    assert result["candidate_scope"] == "claude-current"
    assert_full_acceptance(result)
    assert not (root / "should-not-exist").exists()
    assert "injection" not in summary.read_text()
    event_file.write_text("malformed JSON")
    output = subprocess.check_output([sys.executable, str(SCRIPT)], cwd=root, env=env, text=True)
    assert json.loads(output)["candidate_scope"] == "full"


def test_git_read_failure_keeps_full_scope(history, monkeypatch):
    def unavailable(*args):
        raise subprocess.TimeoutExpired("git", 20)
    monkeypatch.setattr(pilot, "git", unavailable)
    result = observe(history)
    assert result["candidate_scope"] == "full"
    assert_full_acceptance(result)


@NEEDS_UPSTREAM
def test_ci_pilot_workflow_is_read_only_and_cannot_replace_existing_gates():
    reader_spec = importlib.util.spec_from_file_location(
        "pilot_yaml_reader", UPSTREAM / "scripts/repo_shape.py")
    reader = importlib.util.module_from_spec(reader_spec)
    sys.modules[reader_spec.name] = reader
    reader_spec.loader.exec_module(reader)
    workflow = reader.load_yaml(REPO / ".github/workflows/ci-pilot.yml")
    ordinary = reader.load_yaml(REPO / ".github/workflows/tests.yml")
    assert workflow["permissions"] == {}
    assert "pull_request_target" not in workflow["on"]
    assert set(workflow["on"]["pull_request"]) == {"types"}
    assert {"closed", "dequeued", "edited", "labeled", "synchronize"} <= set(
        workflow["on"]["pull_request"]["types"])
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert not set(workflow["jobs"]) & set(ordinary["jobs"])
    assert workflow["jobs"]["pilot-contract"]["steps"][0]["with"]["submodules"] is True
    runs = []
    for job in workflow["jobs"].values():
        assert job["permissions"] == {"contents": "read"}
        assert not {"if", "needs", "outputs", "environment"} & set(job)
        for step in job["steps"]:
            if "uses" in step:
                assert "@" in step["uses"]
                assert len(step["uses"].rsplit("@", 1)[1]) == 40
                if step["uses"].startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] is False
            if "run" in step:
                assert "${{" not in step["run"]
                runs.append(shlex.split(step["run"]))
    assert ["python3", ".github/ci/pilot_scope.py"] in runs
    assert ["bash", "tests/run.sh", "-k", "ci_pilot", "-q"] in runs


def test_agents_share_one_code_local_reference_without_changing_root_ownership():
    agents = (REPO / "AGENTS.md").read_text()
    claude = (REPO / "CLAUDE.md").read_text()
    assert "Read AGENTS.md." in claude
    assert ".github/ci/task-set-delivery.md" in agents
    assert (REPO / ".github/ci/task-set-delivery.md").is_file()
    assert "assembly root" in agents
