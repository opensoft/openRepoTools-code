# SPDX-License-Identifier: Apache-2.0
"""Clean-checkout, layered-protection and transient-only wait regressions."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_ci_cutover import (
    artifact, batch, base_changes, classic_clear, cutover, delivery, duplicate_fixture, git,
    request_for, route_fixture, rules, source_fixture, threads,
)


def main_checkout(batch, env, tmp_path, number=7):
    remote, checkout = batch["root"], tmp_path / "fresh"
    for branch, sha in (("main", batch["base"]), ("feature/7", batch["heads"][0]),
                        ("feature/8", batch["heads"][1])):
        git(remote, "branch", branch, sha)
    git(remote, "update-ref", f"refs/pull/{number}/merge", env["GITHUB_SHA"])
    checkout.mkdir()
    git(checkout, "init", "-q")
    git(checkout, "remote", "add", "origin", str(remote))
    # Pinned checkout's explicit-main full-history refspec excludes PR merges.
    git(checkout, "fetch", "--no-tags", "--no-write-fetch-head", "origin",
        "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*")
    git(checkout, "checkout", "-q", "--detach", batch["base"])
    policy_path = checkout / ".github/ci/delivery-policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text('{"schema_version":1,"enabled":true}')
    assert subprocess.run(["git", "-C", str(checkout), "cat-file", "-e", env["GITHUB_SHA"]],
                          capture_output=True).returncode != 0
    return checkout


def local_transport(cutover, batch, monkeypatch):
    original, fetches = cutover.policy.git, []
    def read(root, *args):
        if "fetch" in args:
            fetches.append(args)
            assert args[-2] == "https://github.com/opensoft/openRepoTools-code.git"
            assert "--no-write-fetch-head" in args
            assert "--no-tags" in args
            assert "credential.helper=" in args
            assert "credential.interactive=false" in args
            args = (*args[:-2], str(batch["root"]), args[-1])
        return original(root, *args)
    monkeypatch.setattr(cutover.policy, "git", read)
    return fetches


@pytest.mark.parametrize("mode", ["route", "gate"])
def test_ci_cutover_repair_clean_control_fetches_merge_without_checkout(cutover, batch, tmp_path, monkeypatch, mode):
    env, event = source_fixture(cutover, batch)
    batch["data"]["branches/main"] = classic_clear()
    original_proof = route_fixture(cutover, batch, env, event)
    assert original_proof["omit_full"] is True
    checkout = main_checkout(batch, env, tmp_path)
    refs = git(checkout, "for-each-ref", "--format=%(refname):%(objectname)")
    fetches = local_transport(cutover, batch, monkeypatch)
    actual_route = cutover.route
    def injected_route(current_env, current_event, root, request):
        return actual_route(current_env, current_event, root, request,
                            threads=lambda number: threads(number, batch), base_changes=base_changes)
    if mode == "route":
        assert injected_route(env, event, checkout, request_for(batch)) == original_proof
    else:
        monkeypatch.setattr(cutover, "route", injected_route)
        cutover.gate(dict(env, OMIT_FULL="true", ROUTE_MODE="source", ROUTE_PROOF=original_proof["proof"]),
                     event, checkout, request_for(batch))
    assert [args[-1] for args in fetches] == [env["GITHUB_SHA"]]
    assert git(checkout, "rev-parse", "HEAD") == batch["base"]
    assert git(checkout, "for-each-ref", "--format=%(refname):%(objectname)") == refs
    assert not (checkout / ".git/FETCH_HEAD").exists()


@pytest.mark.parametrize("legacy", ["guard-launch-mode", "tests", "tests-no-submodule", "package"])
@pytest.mark.parametrize("field", ["contexts", "checks"])
def test_ci_cutover_repair_classic_legacy_check_prevents_activation(cutover, legacy, field):
    branch = classic_clear()
    branch["protection"]["enabled"] = True
    checks = branch["protection"]["required_status_checks"]
    checks["enforcement_level"] = "non_admins"
    checks[field] = [legacy] if field == "contexts" else [{"context": legacy, "app_id": 15368}]
    def request(_repo, endpoint):
        return branch if endpoint == "branches/main" else rules((cutover.GATE, 15368))
    assert cutover.effective_gate(request) is False


def run_main(cutover, batch, env, event, tmp_path, monkeypatch, on_sleep=None):
    event_path, output = tmp_path / "event.json", tmp_path / "outputs"
    event_path.write_text(json.dumps(event))
    for key, value in dict(env, GITHUB_EVENT_PATH=str(event_path), GITHUB_OUTPUT=str(output)).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["delivery_route.py", "route"])
    monkeypatch.setattr(cutover, "__file__", str(batch["root"] / ".github/ci/delivery_route.py"))
    actual_route, sleeps, attempts = cutover.route, [], []
    def injected_route(current_env, current_event, root):
        attempts.append(True)
        return actual_route(current_env, current_event, root, request_for(batch),
                            threads=lambda number: threads(number, batch), base_changes=base_changes)
    monkeypatch.setattr(cutover, "route", injected_route)
    def sleep(value):
        sleeps.append(value)
        if on_sleep:
            on_sleep(len(sleeps))
    # Replacing the shared time module's sleep also intercepts subprocess's
    # timeout polling, contaminating retry counts and callbacks under load.
    monkeypatch.setattr(cutover, "time", SimpleNamespace(sleep=sleep))
    cutover.main()
    return sleeps, attempts, output.read_text()


def test_ci_cutover_repair_wait_stub_does_not_patch_subprocess_clock(cutover, batch, tmp_path, monkeypatch):
    import time
    original = time.sleep
    env, event = source_fixture(cutover, batch)
    batch["prs"][7]["body"] = event["pull_request"]["body"] = ""
    run_main(cutover, batch, env, event, tmp_path, monkeypatch)
    assert time.sleep is original


@pytest.mark.parametrize("kind", ["no-intent", "reusable", "old-protection", "failed-fast"])
def test_ci_cutover_repair_definitive_full_has_no_startup_delay(cutover, batch, tmp_path, monkeypatch, kind):
    env, event = source_fixture(cutover, batch)
    batch["data"]["branches/main"] = classic_clear()
    if kind == "no-intent":
        batch["prs"][7]["body"] = event["pull_request"]["body"] = "CI-Shadow: claude-current"
    elif kind == "reusable":
        batch["data"]["actions/runs/501"]["path"] = ".github/workflows/full-ci-parity.yml"
    elif kind == "old-protection":
        batch["data"]["rules/branches/main?per_page=100&page=1"] += rules(("tests", None))
    else:
        batch["data"]["actions/runs/107"]["conclusion"] = "failure"
    sleeps, attempts, output = run_main(cutover, batch, env, event, tmp_path, monkeypatch)
    assert sleeps == []
    assert len(attempts) == 1
    assert "omit_full=false" in output


@pytest.mark.parametrize("mode", ["route", "gate"])
def test_ci_cutover_repair_candidate_control_also_fetches_merge(cutover, batch, artifact, tmp_path, monkeypatch, mode):
    env, event, data = duplicate_fixture(cutover, batch, artifact)
    git(batch["root"], "branch", artifact["run"]["head_branch"], batch["candidate"])
    request = request_for(batch)
    original_proof = cutover.route(env, event, batch["root"], request, lambda _id: data,
                                   lambda number: threads(number, batch), base_changes)
    assert original_proof["omit_full"] is True
    checkout = main_checkout(batch, env, tmp_path, number=9)
    fetches = local_transport(cutover, batch, monkeypatch)
    actual_route = cutover.route
    def injected_route(current_env, current_event, root, reader):
        return actual_route(current_env, current_event, root, reader, lambda _id: data,
                            lambda number: threads(number, batch), base_changes)
    if mode == "route":
        assert injected_route(env, event, checkout, request) == original_proof
    else:
        monkeypatch.setattr(cutover, "route", injected_route)
        cutover.gate(dict(env, OMIT_FULL="true", ROUTE_MODE="candidate", ROUTE_PROOF=original_proof["proof"]),
                     event, checkout, request)
    assert [args[-1] for args in fetches] == [env["GITHUB_SHA"]]
    assert git(checkout, "rev-parse", "HEAD") == batch["base"]
    assert not (checkout / ".git/FETCH_HEAD").exists()


def test_ci_cutover_repair_unavailable_merge_retains_full_without_retries(cutover, batch, tmp_path, monkeypatch):
    env, event = source_fixture(cutover, batch)
    checkout = main_checkout(batch, env, tmp_path)
    original = cutover.policy.git
    def read(root, *args):
        if "fetch" in args:
            raise subprocess.CalledProcessError(1, args)
        return original(root, *args)
    monkeypatch.setattr(cutover.policy, "git", read)
    assert cutover.route(env, event, checkout, request_for(batch), threads=lambda number: threads(number, batch),
                          base_changes=base_changes) == cutover.FULL
    assert git(checkout, "rev-parse", "HEAD") == batch["base"]


@pytest.mark.parametrize("path,value", [
    (("protection",), None), (("name",), "other"), (("protected",), False),
    (("protection", "enabled"), None), (("protection", "enabled"), 1),
    (("protection", "required_status_checks"), {}),
    (("protection", "required_status_checks", "enforcement_level"), "unknown"),
    (("protection", "required_status_checks", "enforcement_level"), "non_admins"),
    (("protection", "required_status_checks", "contexts"), None),
    (("protection", "required_status_checks", "contexts"), [True]),
    (("protection", "required_status_checks", "checks"), {}),
    (("protection", "required_status_checks", "checks"), [{}]),
])
def test_ci_cutover_repair_incomplete_classic_evidence_is_full(cutover, path, value):
    branch = classic_clear()
    node = branch
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    def request(_repo, endpoint):
        return branch if endpoint == "branches/main" else rules((cutover.GATE, 15368))
    assert cutover.effective_gate(request) is False


def test_ci_cutover_repair_unrelated_classic_checks_remain_compatible(cutover):
    branch = classic_clear()
    branch["protection"]["enabled"] = True
    branch["protection"]["required_status_checks"].update(
        enforcement_level="everyone", contexts=["independent-security"],
        checks=[{"context": "independent-security", "app_id": 7}])
    def request(_repo, endpoint):
        return branch if endpoint == "branches/main" else rules((cutover.GATE, 15368))
    assert cutover.effective_gate(request) is True


def test_ci_cutover_repair_classic_change_during_routing_retains_full(cutover, batch):
    env, event = source_fixture(cutover, batch)
    request, reads = request_for(batch), []
    def raced(repo, endpoint):
        answer = request(repo, endpoint)
        if endpoint == "branches/main":
            reads.append(True)
            if len(reads) > 1:
                answer["protection"]["enabled"] = True
                answer["protection"]["required_status_checks"].update(
                    enforcement_level="everyone", contexts=["tests"])
        return answer
    assert cutover.route(env, event, batch["root"], raced,
                          threads=lambda number: threads(number, batch), base_changes=base_changes) == cutover.FULL
    assert len(reads) == 2


def test_ci_cutover_repair_final_gate_rechecks_classic_requirements(cutover, batch, monkeypatch):
    env, event = source_fixture(cutover, batch)
    selected = route_fixture(cutover, batch, env, event)
    assert selected["omit_full"] is True
    branch = batch["data"]["branches/main"]
    branch["protection"]["enabled"] = True
    branch["protection"]["required_status_checks"].update(enforcement_level="everyone", contexts=["tests"])
    actual_route = cutover.route
    def injected_route(current_env, current_event, root, request):
        return actual_route(current_env, current_event, root, request,
                            threads=lambda number: threads(number, batch), base_changes=base_changes)
    monkeypatch.setattr(cutover, "route", injected_route)
    with pytest.raises(ValueError, match="no longer verifies"):
        cutover.gate(dict(env, OMIT_FULL="true", ROUTE_MODE="source", ROUTE_PROOF=selected["proof"]),
                     event, batch["root"], request_for(batch))


def pending_fast(batch):
    head = batch["heads"][0]
    check = batch["data"][f"commits/{head}/check-runs?check_name=openrepotools-pr-fast&filter=latest&per_page=100"]["check_runs"][0]
    for record in (check, batch["data"]["actions/runs/107"], batch["data"]["actions/jobs/907"]):
        record.update(status="in_progress", conclusion=None)


def fast_records(batch):
    head = batch["heads"][0]
    return {
        "check": batch["data"][f"commits/{head}/check-runs?check_name=openrepotools-pr-fast&filter=latest&per_page=100"]["check_runs"][0],
        "run": batch["data"]["actions/runs/107"],
        "job": batch["data"]["actions/jobs/907"],
    }


@pytest.mark.parametrize("component", ["check", "run", "job"])
@pytest.mark.parametrize("finish", ["success", "job-head", "run-attempt"])
def test_ci_cutover_repair_pending_completion_during_reads_requires_fresh_poll(cutover, batch, component, finish):
    env, event = source_fixture(cutover, batch)
    records = fast_records(batch)
    records[component].update(status="in_progress", conclusion=None)
    reader = request_for(batch)
    def request(repo, endpoint):
        answer = reader(repo, endpoint)
        if endpoint == "actions/jobs/907":
            for record in records.values():
                record.update(status="completed", conclusion="success")
            records["run"]["updated_at"] = "2026-11-11T00:00:02Z"
            records["check"]["completed_at"] = "2026-11-11T00:00:02Z"
            if finish == "job-head":
                records["job"]["head_sha"] = batch["heads"][1]
            elif finish == "run-attempt":
                records["run"]["run_attempt"] = 2
        return answer
    first = cutover.route(env, event, batch["root"], request,
                          threads=lambda number: threads(number, batch), base_changes=base_changes)
    assert first == {**cutover.FULL, "retryable": True}
    # The completing observation returns no proof; only a fresh stable one qualifies.
    second = route_fixture(cutover, batch, env, event)
    if finish == "success":
        assert second["mode"] == "source" and second["omit_full"] is True
        assert len(second["proof"]) == 64
    else:
        assert second == cutover.FULL


@pytest.mark.parametrize("change", ["run-attempt", "run-metadata", "check-state", "check-output"])
def test_ci_cutover_repair_completed_fast_reread_stays_strict(cutover, batch, change):
    env, event = source_fixture(cutover, batch)
    records, reader = fast_records(batch), request_for(batch)
    def request(repo, endpoint):
        answer = reader(repo, endpoint)
        if endpoint == "actions/jobs/907":
            if change == "run-attempt":
                records["run"]["run_attempt"] = 2
            elif change == "run-metadata":
                records["run"]["updated_at"] = "2026-11-11T00:00:02Z"
            elif change == "check-state":
                records["check"]["conclusion"] = "failure"
            else:
                records["check"]["output"] = {"summary": "Private field must not be normalized."}
        return answer
    assert cutover.route(env, event, batch["root"], request,
        threads=lambda number: threads(number, batch), base_changes=base_changes) == cutover.FULL


@pytest.mark.parametrize("component", ["check", "run", "job"])
def test_ci_cutover_repair_admission_rejects_each_pending_component(cutover, batch, component):
    source_fixture(cutover, batch)
    fast_records(batch)[component].update(status="in_progress", conclusion=None)
    with pytest.raises(cutover.verifier.Refused) as refused:
        cutover.verifier.fast_receipt(batch["prs"][7], batch["heads"][0], request_for(batch), base_changes)
    assert not isinstance(refused.value, cutover.verifier.PendingEvidence)


def test_ci_cutover_repair_authenticated_fast_pending_waits_but_never_qualifies(cutover, batch, delivery, tmp_path, monkeypatch):
    env, event = source_fixture(cutover, batch)
    pending_fast(batch)
    assert route_fixture(cutover, batch, env, event) == {**cutover.FULL, "retryable": True}
    # Candidate admission remains success-only; only the router may wait.
    with pytest.raises(delivery.Refused) as refused:
        delivery.fast_receipt(batch["prs"][7], batch["heads"][0], request_for(batch), base_changes)
    assert not isinstance(refused.value, delivery.PendingEvidence)
    sleeps, attempts, output = run_main(cutover, batch, env, event, tmp_path, monkeypatch)
    assert sleeps == [10] * 30
    assert len(attempts) == 31
    assert "omit_full=false" in output
    assert "retryable" not in output


def test_ci_cutover_repair_pending_fast_transition_qualifies_only_after_success(cutover, batch, tmp_path, monkeypatch):
    env, event = source_fixture(cutover, batch)
    pending_fast(batch)
    def finish(_count):
        check = batch["data"][f"commits/{batch['heads'][0]}/check-runs?check_name=openrepotools-pr-fast&filter=latest&per_page=100"]["check_runs"][0]
        for record in (check, batch["data"]["actions/runs/107"], batch["data"]["actions/jobs/907"]):
            record.update(status="completed", conclusion="success")
    sleeps, attempts, output = run_main(cutover, batch, env, event, tmp_path, monkeypatch, finish)
    assert sleeps == [10]
    assert len(attempts) == 2
    assert "omit_full=true" in output


def test_ci_cutover_repair_realistic_pending_duration_is_not_limited_to_one_minute(cutover, batch, tmp_path, monkeypatch):
    env, event = source_fixture(cutover, batch)
    pending_fast(batch)
    def finish(count):
        if count != 20:
            return
        check = batch["data"][f"commits/{batch['heads'][0]}/check-runs?check_name=openrepotools-pr-fast&filter=latest&per_page=100"]["check_runs"][0]
        for record in (check, batch["data"]["actions/runs/107"], batch["data"]["actions/jobs/907"]):
            record.update(status="completed", conclusion="success")
    sleeps, attempts, output = run_main(cutover, batch, env, event, tmp_path, monkeypatch, finish)
    assert sleeps == [10] * 20
    assert len(attempts) == 21
    assert "omit_full=true" in output


@pytest.mark.parametrize("failure", ["workflow", "head", "history", "check-missing", "run-attempt", "failed"])
def test_ci_cutover_repair_untrusted_or_failed_pending_is_not_retryable(cutover, batch, failure):
    env, event = source_fixture(cutover, batch)
    pending_fast(batch)
    if failure == "workflow": batch["data"]["actions/runs/107"]["path"] = ".github/workflows/other.yml"
    elif failure == "head": batch["data"]["actions/jobs/907"]["head_sha"] = batch["heads"][1]
    elif failure == "run-attempt": batch["data"]["actions/runs/107"]["run_attempt"] = 2
    elif failure == "check-missing":
        batch["data"][f"commits/{batch['heads'][0]}/check-runs?check_name=openrepotools-pr-fast&filter=latest&per_page=100"] = {"total_count": 0, "check_runs": []}
    elif failure == "failed": batch["data"]["actions/jobs/907"].update(status="completed", conclusion="failure")
    history = (lambda _number: {"pageInfo": {"hasNextPage": True}, "nodes": []}) if failure == "history" else base_changes
    assert cutover.route(env, event, batch["root"], request_for(batch),
                          threads=lambda number: threads(number, batch), base_changes=history) == cutover.FULL


@pytest.mark.parametrize("status", ["in_progress", "completed"])
def test_ci_cutover_repair_admission_wait_requires_authentic_live_caller(cutover, batch, artifact, tmp_path, monkeypatch, status):
    env, event, _data = duplicate_fixture(cutover, batch, artifact)
    artifact["run"].update(status=status, conclusion="success" if status == "completed" else None)
    batch["data"]["actions/runs/601/artifacts?per_page=100&page=1"] = {"total_count": 0, "artifacts": []}
    sleeps, attempts, output = run_main(cutover, batch, env, event, tmp_path, monkeypatch)
    assert sleeps == ([10] * 30 if status == "in_progress" else [])
    assert len(attempts) == (31 if status == "in_progress" else 1)
    assert "omit_full=false" in output


@pytest.mark.parametrize("state", ["in_progress", "completed"])
@pytest.mark.parametrize("caller", ["valid", "wrong-actor", "wrong-attempt"])
def test_ci_cutover_repair_pending_admission_transition_during_reads_needs_fresh_poll(cutover, batch, artifact, state, caller):
    env, event, data = duplicate_fixture(cutover, batch, artifact)
    endpoint = "actions/runs/601/artifacts?per_page=100&page=1"
    published = batch["data"][endpoint]
    batch["data"][endpoint] = {"total_count": 0, "artifacts": []}
    artifact["run"].update(status="queued", conclusion=None)
    if caller == "wrong-actor":
        artifact["run"]["actor"]["login"] = "writer"
    elif caller == "wrong-attempt":
        artifact["run"]["run_attempt"] = 2
    reader = request_for(batch)
    def request(repo, path):
        answer = reader(repo, path)
        if path == endpoint:
            artifact["run"].update(status=state, conclusion="success" if state == "completed" else None)
            batch["data"][endpoint] = published
        return answer
    first = cutover.route(env, event, batch["root"], request, lambda _id: data,
                          lambda number: threads(number, batch), base_changes)
    if caller != "valid":
        assert first == cutover.FULL
        return
    assert first == {**cutover.FULL, "retryable": True}
    second = cutover.route(env, event, batch["root"], reader, lambda _id: data,
                           lambda number: threads(number, batch), base_changes)
    assert second["mode"] == "candidate" and second["omit_full"] is True


def test_ci_cutover_repair_default_artifact_reader_never_waits_for_absent_admission(cutover, batch, artifact):
    _env, _event, data = duplicate_fixture(cutover, batch, artifact)
    artifact["run"].update(status="queued", conclusion=None)
    batch["data"]["actions/runs/601/artifacts?per_page=100&page=1"] = {"total_count": 0, "artifacts": []}
    with pytest.raises(cutover.verifier.Refused) as refused:
        cutover.evidence.artifact_record(artifact["run"], "admission", request_for(batch), lambda _id: data)
    assert not isinstance(refused.value, cutover.verifier.PendingEvidence)
