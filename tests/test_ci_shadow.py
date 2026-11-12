# SPDX-License-Identifier: Apache-2.0
"""Trusted shadow observations, with local Git fixtures and mocked read APIs."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys

import pytest

from conftest import NEEDS_UPSTREAM, REPO, UPSTREAM

SCRIPT = REPO / ".github/ci/shadow_scope.py"
WORKFLOW = REPO / ".github/workflows/ci-shadow.yml"
REPOSITORY = "opensoft/openRepoTools-code"
INTENT = "CI-Shadow: claude-current"


@pytest.fixture(scope="module")
def shadow():
    spec = importlib.util.spec_from_file_location("trusted_shadow", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   stderr=subprocess.STDOUT).decode().strip()


def commit(root, message=INTENT):
    git(root, "add", ".")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "CI Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.filemode", "true")
    (root / "tests").mkdir()
    (root / "claude-current").write_text("#!/bin/sh\nexit 0\n")
    (root / "claude-current").chmod(0o755)
    (root / "tests/test_claude_current.py").write_text("# baseline\n")
    commit(root)
    git(root, "update-index", "--chmod=+x", "claude-current")
    git(root, "commit", "--amend", "--no-edit", "-q")
    base = git(root, "rev-parse", "HEAD")
    (root / "tests/test_claude_current.py").write_text("# scoped\n")
    head = commit(root)
    git(root, "checkout", "-q", "--detach", base)
    def side(sha, ref):
        return {"sha": sha, "ref": ref, "repo": {"full_name": REPOSITORY}}
    pr = {"number": 7, "state": "open", "draft": False, "merged": False,
          "body": INTENT, "user": {"login": "writer"}, "merge_commit_sha": None,
          "head": side(head, "feature/small"), "base": side(base, "main")}
    event = {"number": 7, "action": "synchronize", "pull_request": copy.deepcopy(pr)}
    env = {"GITHUB_REPOSITORY": REPOSITORY, "GITHUB_EVENT_NAME": "pull_request",
           "GITHUB_REF": "refs/pull/7/merge", "GITHUB_SHA": head}
    return {"root": root, "main": base, "head": head, "pr": pr, "event": event, "env": env}


def api(fixture):
    def request(repo, endpoint):
        assert repo == REPOSITORY
        if endpoint == "git/ref/heads/main":
            return {"object": {"sha": fixture["main"]}}
        if endpoint == "pulls/7":
            return copy.deepcopy(fixture["pr"])
        if endpoint == "git/ref/heads/feature/small":
            return {"object": {"sha": fixture["head"]}}
        raise AssertionError("Unexpected read endpoint: " + endpoint)
    return request


def observe(shadow, fixture, request=None):
    return shadow.classify(fixture["env"], fixture["event"], fixture["root"],
                           request or api(fixture))


def full_authority(result):
    assert result["mode"] == "shadow"
    assert result["required_ci"] == "full"
    assert result["skip_ci"] is False
    assert result["queue_admission"] is False
    assert set(result) == {"mode", "required_ci", "skip_ci", "queue_admission",
                           "candidate_scope", "observation", "reason",
                           "policy_sha", "main", "head", "base"}


def test_ci_shadow_current_scoped_pr_is_observational_only(shadow, fixture):
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "claude-current"
    assert result["observation"] == "scoped-pr"
    assert result["policy_sha"] == result["main"] == fixture["main"]
    full_authority(result)


@pytest.mark.parametrize("action", [
    "opened", "reopened", "synchronize", "edited", "labeled", "unlabeled", "ready_for_review"])
def test_ci_shadow_third_party_metadata_is_reproved_not_authority(shadow, fixture, action):
    fixture["event"].update(action=action, sender={"login": "third-party"})
    fixture["event"]["pull_request"]["labels"] = [{"name": "approved fast"}]
    assert observe(shadow, fixture)["candidate_scope"] == "claude-current"
    fixture["pr"]["head"]["sha"] = "a" * 40
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("mutation", [
    "draft", "fork", "missing-sha", "bad-sha", "wrong-number", "bool-number",
    "changed-head", "changed-base", "changed-body", "missing-intent", "duplicate-intent",
    "non-main-base", "reserved-branch", "unsafe-ref", "closed", "unknown-repository"])
def test_ci_shadow_uncertain_or_unsupported_pr_context_stays_full(shadow, fixture, mutation):
    event, pr = fixture["event"], fixture["pr"]
    if mutation == "draft":
        pr["draft"] = event["pull_request"]["draft"] = True
    elif mutation == "fork":
        pr["head"]["repo"]["full_name"] = "fork/project"
    elif mutation == "missing-sha":
        del event["pull_request"]["head"]["sha"]
    elif mutation == "bad-sha":
        event["pull_request"]["head"]["sha"] = "--output=bad"
    elif mutation == "wrong-number":
        pr["number"] = 8
    elif mutation == "bool-number":
        event["number"] = True
    elif mutation == "changed-head":
        pr["head"]["sha"] = "a" * 40
    elif mutation == "changed-base":
        pr["base"]["sha"] = "a" * 40
    elif mutation == "changed-body":
        pr["body"] += "\nchanged"
    elif mutation == "missing-intent":
        pr["body"] = event["pull_request"]["body"] = ""
    elif mutation == "duplicate-intent":
        pr["body"] = event["pull_request"]["body"] = INTENT + "\n" + INTENT
    elif mutation == "non-main-base":
        pr["base"]["ref"] = event["pull_request"]["base"]["ref"] = "predecessor"
    elif mutation == "reserved-branch":
        pr["head"]["ref"] = event["pull_request"]["head"]["ref"] = "verify/task"
    elif mutation == "unsafe-ref":
        pr["head"]["ref"] = event["pull_request"]["head"]["ref"] = "feature/../../other"
    elif mutation == "closed":
        pr["state"] = event["pull_request"]["state"] = "closed"
    else:
        fixture["env"]["GITHUB_REPOSITORY"] = "another/repository"
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("action", ["closed", "dequeued", "enqueued", "converted_to_draft", "unknown"])
def test_ci_shadow_inactive_or_queue_actions_never_gain_scope(shadow, fixture, action):
    fixture["event"]["action"] = action
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("operation", ["mixed", "delete", "rename", "mode", "symlink", "empty"])
def test_ci_shadow_git_content_not_labels_controls_scope(shadow, fixture, operation):
    root = fixture["root"]
    git(root, "checkout", "-q", "--detach", fixture["head"])
    target = root / "tests/test_claude_current.py"
    if operation == "mixed":
        (root / "lane-start").write_text("# unrelated\n")
    elif operation == "delete":
        target.unlink()
    elif operation == "rename":
        target.rename(root / "tests/renamed.py")
    elif operation == "mode":
        target.chmod(0o755)
        git(root, "update-index", "--chmod=+x", "tests/test_claude_current.py")
        git(root, "commit", "-qm", INTENT)
    elif operation == "symlink":
        target.unlink()
        target.symlink_to("../claude-current")
    if operation == "empty":
        head = fixture["main"]
    elif operation == "mode":
        head = git(root, "rev-parse", "HEAD")
    else:
        head = commit(root)
    fixture["head"] = fixture["pr"]["head"]["sha"] = head
    fixture["event"]["pull_request"] = copy.deepcopy(fixture["pr"])
    git(root, "checkout", "-q", "--detach", fixture["main"])
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("failure", ["api", "git", "main-before", "main-after", "pr-after"])
def test_ci_shadow_read_failure_or_moving_identity_stays_full(shadow, fixture, monkeypatch, failure):
    original, count = api(fixture), {}
    def request(repo, endpoint):
        count[endpoint] = count.get(endpoint, 0) + 1
        if failure == "api":
            raise subprocess.TimeoutExpired("gh", 15)
        data = original(repo, endpoint)
        if endpoint == "git/ref/heads/main" and (
                failure == "main-before" or failure == "main-after" and count[endpoint] > 1):
            data["object"]["sha"] = "a" * 40
        if endpoint == "pulls/7" and failure == "pr-after" and count[endpoint] > 1:
            data["head"]["sha"] = "a" * 40
        return data
    if failure == "git":
        def unavailable(*args):
            raise subprocess.TimeoutExpired("git", 20)
        monkeypatch.setattr(shadow, "git", unavailable)
    result = observe(shadow, fixture, request)
    assert result["candidate_scope"] == "full"
    full_authority(result)


def make_merged(fixture):
    root = fixture["root"]
    git(root, "checkout", "-qb", "landed-main", fixture["main"])
    git(root, "merge", "--no-ff", "-qm", "landed", fixture["head"])
    merged = git(root, "rev-parse", "HEAD")
    fixture["main"] = merged
    fixture["pr"].update(state="closed", merged=True, merge_commit_sha=merged)
    fixture["event"]["action"] = "edited"
    # The event's base is deliberately stale: only immutable merge proof may help.
    fixture["event"]["pull_request"]["base"]["sha"] = "b" * 40
    return merged


def test_ci_shadow_merged_metadata_uses_same_head_and_immutable_merge_not_stale_base(shadow, fixture):
    make_merged(fixture)
    fixture["event"]["sender"] = {"login": "third-party-editor"}
    fixture["env"]["GITHUB_SHA"] = "c" * 40  # stale test-merge context is not executed
    result = observe(shadow, fixture)
    assert result["observation"] == "merged-scoped-metadata"
    assert result["candidate_scope"] == "claude-current"
    full_authority(result)


@pytest.mark.parametrize("mutation", ["changed-head", "unmerged", "wrong-merge", "closed-event", "dequeued"])
def test_ci_shadow_closed_metadata_needs_narrow_live_merge_proof(shadow, fixture, mutation):
    make_merged(fixture)
    if mutation == "changed-head":
        fixture["pr"]["head"]["sha"] = "a" * 40
    elif mutation == "unmerged":
        fixture["pr"]["merged"] = False
    elif mutation == "wrong-merge":
        fixture["pr"]["merge_commit_sha"] = fixture["head"]
    else:
        fixture["event"]["action"] = mutation.replace("-event", "")
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


def push_event(fixture, ref="refs/heads/feature/small"):
    fixture["env"].update(GITHUB_EVENT_NAME="push", GITHUB_REF=ref, GITHUB_SHA=fixture["head"])
    fixture["event"] = {"repository": {"full_name": REPOSITORY}, "ref": ref,
                        "after": fixture["head"], "before": fixture["main"],
                        "deleted": False, "forced": False}


def test_ci_shadow_source_push_requires_live_branch_and_intent(shadow, fixture):
    push_event(fixture)
    result = observe(shadow, fixture)
    assert result["observation"] == "scoped-source-push"
    assert result["candidate_scope"] == "claude-current"
    full_authority(result)
    def stale(repo, endpoint):
        data = api(fixture)(repo, endpoint)
        if endpoint.endswith("feature/small"):
            data["object"]["sha"] = "a" * 40
        return data
    assert observe(shadow, fixture, stale)["candidate_scope"] == "full"


def test_ci_shadow_source_branch_moving_after_scope_check_stays_full(shadow, fixture):
    push_event(fixture)
    reads = 0
    def moving(repo, endpoint):
        nonlocal reads
        data = api(fixture)(repo, endpoint)
        if endpoint.endswith("feature/small"):
            reads += 1
            if reads > 1:
                data["object"]["sha"] = "a" * 40
        return data
    result = observe(shadow, fixture, moving)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("missing", [False, True])
def test_ci_shadow_unrelated_or_missing_git_head_never_qualifies(shadow, fixture, missing):
    head = "0" * 40 if missing else git(
        fixture["root"], "commit-tree", "HEAD^{tree}", "-m", "unrelated")
    fixture["pr"]["head"]["sha"] = fixture["event"]["pull_request"]["head"]["sha"] = head
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


def test_ci_shadow_untrusted_body_is_never_executed_or_reflected(shadow, fixture):
    text = INTENT + "\n$(touch should-not-exist)\n::error::untrusted"
    fixture["pr"]["body"] = fixture["event"]["pull_request"]["body"] = text
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "claude-current"
    assert "untrusted" not in json.dumps(result)
    assert not (fixture["root"] / "should-not-exist").exists()
    full_authority(result)


def test_ci_shadow_api_adapter_is_fixed_host_read_only_bounded_and_quiet(shadow, monkeypatch):
    calls = []
    class Response:
        stdout = b'{"object":{"sha":"' + b"a" * 40 + b'"}}'
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Response()
    monkeypatch.setattr(shadow.subprocess, "run", run)
    assert shadow.github(REPOSITORY, "git/ref/heads/main")["object"]["sha"] == "a" * 40
    args, options = calls[0]
    assert args == ["gh", "api", "--hostname", "github.com",
                    "repos/" + REPOSITORY + "/git/ref/heads/main"]
    assert options == {"check": True, "stdout": subprocess.PIPE,
                       "stderr": subprocess.PIPE, "timeout": 15}


@pytest.mark.parametrize("mutation", ["deleted", "forced", "ref", "sha", "repository", "release", "verify"])
def test_ci_shadow_unverified_push_stays_full(shadow, fixture, mutation):
    push_event(fixture)
    if mutation in ("deleted", "forced"):
        fixture["event"][mutation] = True
    elif mutation == "ref":
        fixture["event"]["ref"] = "refs/heads/another"
    elif mutation == "sha":
        fixture["env"]["GITHUB_SHA"] = "a" * 40
    elif mutation == "repository":
        fixture["event"]["repository"]["full_name"] = "fork/project"
    else:
        ref = "refs/heads/" + mutation + "/task"
        fixture["env"]["GITHUB_REF"] = fixture["event"]["ref"] = ref
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("kind", ["candidate-pr", "closed-candidate", "candidate-push", "main-push"])
def test_ci_shadow_candidates_and_landings_do_not_invent_integration_evidence(shadow, fixture, kind):
    if kind.endswith("push"):
        ref = "refs/heads/main" if kind == "main-push" else "refs/heads/mergify/merge-queue/0123456789"
        push_event(fixture, ref)
    else:
        fixture["pr"]["head"]["ref"] = "mergify/merge-queue/0123456789"
        fixture["pr"]["user"]["login"] = "mergify[bot]"
        if kind == "closed-candidate":
            fixture["pr"]["state"] = "closed"
            fixture["event"]["action"] = "closed"
        fixture["event"]["pull_request"] = copy.deepcopy(fixture["pr"])
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    assert result["reason"] in {"candidate-proof-required", "landing-proof-required"}
    full_authority(result)


@pytest.mark.parametrize("payload", [None, [], {}, {"number": True}, {"pull_request": []}])
def test_ci_shadow_malformed_payloads_are_full(shadow, fixture, payload):
    fixture["event"] = payload
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


@pytest.mark.parametrize("kind", ["pull_request_target", "merge_group", "workflow_dispatch", "schedule"])
def test_ci_shadow_unsupported_event_kinds_never_gain_scope(shadow, fixture, kind):
    fixture["env"]["GITHUB_EVENT_NAME"] = kind
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


def test_ci_shadow_no_intent_in_source_commit_stays_full(shadow, fixture):
    head = git(fixture["root"], "commit-tree", fixture["head"] + "^{tree}",
               "-p", fixture["main"], "-m", "no intent")
    fixture["head"] = head
    push_event(fixture)
    result = observe(shadow, fixture)
    assert result["candidate_scope"] == "full"
    full_authority(result)


def read_workflow():
    spec = importlib.util.spec_from_file_location("shadow_yaml", UPSTREAM / "scripts/repo_shape.py")
    reader = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reader
    spec.loader.exec_module(reader)
    return reader.load_yaml(WORKFLOW)


@NEEDS_UPSTREAM
def test_ci_shadow_workflow_executes_only_trusted_main_observer():
    workflow = read_workflow()
    assert workflow["permissions"] == {}
    assert set(workflow["on"]) == {"pull_request", "push"}
    assert workflow["on"]["push"] == {"branches-ignore": ["release/**"]}
    assert {"edited", "closed", "dequeued", "synchronize"} <= set(
        workflow["on"]["pull_request"]["types"])
    assert set(workflow["jobs"]) == {"observe", "contract"}
    observe, contract = (workflow["jobs"][name] for name in ("observe", "contract"))
    assert observe["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert observe["steps"][0]["with"] == {
        "ref": "main", "fetch-depth": 0, "persist-credentials": False}
    assert contract["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert not {"if", "needs", "outputs", "environment"} & set(job)
        for step in job["steps"]:
            if "run" in step:
                assert "${{" not in step["run"]
            if "uses" in step:
                assert len(step["uses"].rsplit("@", 1)[1]) == 40
    assert all("GH_TOKEN" not in step.get("env", {}) for step in contract["steps"])
    script = observe["steps"][-1]["run"]
    assert "if [ -f .github/ci/shadow_scope.py ]" in script
    assert "policy-unavailable" in script and '"required_ci":"full"' in script
    assert "python3 .github/ci/shadow_scope.py" in script
    assert "GITHUB_OUTPUT" not in script
    assert "GITHUB_OUTPUT" not in SCRIPT.read_text()


@NEEDS_UPSTREAM
def test_ci_shadow_missing_trusted_policy_falls_back_without_running_head_code(tmp_path):
    workflow = read_workflow()
    script = workflow["jobs"]["observe"]["steps"][-1]["run"]
    tools = tmp_path / "bin"
    tools.mkdir()
    sentinel = tmp_path / "called"
    fake = tools / "python3"
    fake.write_text('#!/bin/sh\ntouch "$SHADOW_SENTINEL"\nexit 99\n')
    fake.chmod(0o755)
    summary = tmp_path / "summary"
    result = subprocess.run(["bash", "-c", script], cwd=tmp_path,
                            env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                                     SHADOW_SENTINEL=str(sentinel),
                                     GITHUB_STEP_SUMMARY=str(summary)),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    full_authority(observed)
    assert observed["reason"] == "policy-unavailable"
    assert not sentinel.exists()


def test_ci_shadow_cli_handles_missing_policy_context_without_network_or_output_grants(
        fixture, tmp_path):
    payload = tmp_path / "event.json"
    payload.write_text("malformed JSON")
    summary = tmp_path / "summary"
    env = dict(os.environ, GITHUB_EVENT_PATH=str(payload), GITHUB_EVENT_NAME="pull_request",
               GITHUB_REPOSITORY="unrelated/repository", GITHUB_STEP_SUMMARY=str(summary))
    output = subprocess.check_output([sys.executable, str(SCRIPT)], cwd=fixture["root"],
                                     env=env, text=True)
    result = json.loads(output)
    full_authority(result)
    assert result["candidate_scope"] == "full"
    assert "Full CI remains required" in summary.read_text()
