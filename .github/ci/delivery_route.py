# SPDX-License-Identifier: Apache-2.0
"""Trusted-main, default-full CI routing. Reads only; never grants merge authority."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time
import zipfile

import delivery_evidence as evidence
import delivery_verify as verifier
import shadow_scope as policy

REPOSITORY = policy.REPOSITORY
FULL = {"mode": "full", "omit_full": False}
LEGACY = {"guard-launch-mode", "tests", "tests-no-submodule", "package"}
GATE = "openrepotools-delivery"
DIRECT = ".github/workflows/tests.yml"
PARENTS = "--format=%P"
ERRORS = policy.ERRORS + (zipfile.BadZipFile, RuntimeError)
require = verifier.require


def enabled(root):
    try:
        value = evidence.read_json((root / ".github/ci/delivery-policy.json").read_bytes())
        return (set(value) == {"schema_version", "enabled"}
                and type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["enabled"] is True)
    except policy.ERRORS:
        return False


def effective_gate(request=policy.github):
    try:
        rows = evidence.pages(request, "rules/branches/main", None)
        contexts = []
        for rule in rows:
            require(isinstance(rule, dict) and isinstance(rule["type"], str), "Malformed rule")
            if rule["type"] == "required_status_checks":
                values = rule["parameters"]["required_status_checks"]
                require(isinstance(values, list), "Malformed status rule")
                for value in values:
                    require(isinstance(value["context"], str) and "integration_id" in value,
                            "Incomplete app-bound rule")
                    contexts.append((value["context"], value["integration_id"]))
        return (any(name == GATE and type(app) is int and app == 15368 for name, app in contexts)
                and not any(name in LEGACY for name, _app in contexts))
    except policy.ERRORS:
        return False


def current_run(env, request):
    require(env["GITHUB_REPOSITORY"] == REPOSITORY, "Foreign repository")
    run_id = evidence.positive(int(env["GITHUB_RUN_ID"]))
    run = request(REPOSITORY, f"actions/runs/{run_id}")
    require(run["id"] == run_id and run["repository"]["id"] == evidence.REPOSITORY_ID
            and run["repository"]["full_name"] == REPOSITORY
            and run["head_repository"]["full_name"] == REPOSITORY
            and run["head_repository"]["id"] == evidence.REPOSITORY_ID
            and run["run_attempt"] == int(env["GITHUB_RUN_ATTEMPT"])
            and run["event"] == env["GITHUB_EVENT_NAME"] and run["path"] == DIRECT,
            "Reusable/foreign workflow must remain full")
    return run


def source(env, event, root, main, request, base_changes):
    require(event["action"] in {"opened", "synchronize", "reopened"}, "Unsupported PR event")
    number = evidence.positive(event["number"])
    pr = request(REPOSITORY, f"pulls/{number}")
    require(policy.snapshot(pr) == policy.snapshot(event["pull_request"])
            and pr["state"] == "open" and pr["draft"] is False
            and pr["number"] == number and verifier.delivery_intended(pr["body"])
            and not re.search(r"(?m)^Depends-On:", pr["body"]), "Source is not opted-in/current")
    head, branch = policy.side(pr, "head")
    base, base_ref = policy.side(pr, "base")
    require(base == main and base_ref == "main" and policy.source_branch(branch)
            and policy.regular_scope(root, main, head), "Source is outside fixed scope")
    policy.git(root, "merge-base", "--is-ancestor", main, head)
    tested = policy.sha(env["GITHUB_SHA"])
    require(policy.git(root, "show", "-s", PARENTS, tested).decode().split() == [main, head],
            "Source test-merge identity differs")
    fast = verifier.fast_receipt(pr, head, request, base_changes)
    require(pr == request(REPOSITORY, f"pulls/{number}")
            and request(REPOSITORY, "git/ref/heads/" + branch)["object"]["sha"] == head,
            "Source moved during verification")
    return {"base": main, "head": head, "tested": tested, "fast": evidence.digest(fast)}


def duplicate(env, event, root, main, request, fetch, threads, base_changes):
    require(event["action"] in {"opened", "synchronize", "reopened"}, "Unsupported candidate event")
    number = evidence.positive(event["number"])
    pr = request(REPOSITORY, f"pulls/{number}")
    head, branch = policy.side(pr, "head")
    require(policy.snapshot(pr) == policy.snapshot(event["pull_request"])
            and pr["number"] == number and pr["state"] == "open" and pr["draft"] is True
            and pr["user"]["login"] == "mergify[bot]"
            and policy.side(pr, "base") == (main, "main")
            and policy.QUEUE.fullmatch(branch) is not None, "Not a current draft candidate")
    require(policy.git(root, "show", "-s", PARENTS, policy.sha(env["GITHUB_SHA"])).decode().split()
            == [main, head], "Candidate test-merge identity differs")
    run = evidence.candidate_runs(head, request)
    evidence.run_identity(run, head, branch)
    record = evidence.artifact_record(run, "admission", request, fetch)
    proof = evidence.candidate_chain(record, root)
    require(proof["base"] == main, "Admission belongs to another main")
    # Independently re-read live sources; do not manufacture a push payload to
    # trick the admission verifier into accepting a pull_request event.
    for member in proof["members"]:
        source_pr, _receipt = verifier.source_pr(member["head"], main, root, request, threads, base_changes)
        require(source_pr["number"] == member["number"]
                and verifier.delivery_intended(source_pr["body"]), "Admission source differs")
    require(pr == request(REPOSITORY, f"pulls/{number}")
            and request(REPOSITORY, "git/ref/heads/" + branch)["object"]["sha"] == head
            and run == request(REPOSITORY, f"actions/runs/{run['id']}"), "Candidate evidence moved")
    return {"candidate": head, "record": evidence.digest(record)}


def landed(env, event, root, request, fetch):
    after = policy.sha(env["GITHUB_SHA"])
    pair = policy.git(root, "show", "-s", PARENTS, after).decode().split()
    require(len(pair) == 2, "Main event is not a merge")
    response = request(REPOSITORY,
                       "actions/workflows/task-set-candidate-shadow.yml/runs?per_page=20&page=1")
    rows = response["workflow_runs"]
    require(isinstance(rows, list) and len(rows) <= 20, "Malformed recent candidate history")
    proofs = []
    for row in rows:
        if row["status"] != "completed" or row["conclusion"] != "success":
            continue
        try:
            run = evidence.run_identity(request(REPOSITORY, f"actions/runs/{evidence.positive(row['id'])}"),
                                        completed=True)
            # A per-head all-state lookup also refuses multiple historical runs
            # or a later rerun outside this recent discovery window.
            require(evidence.candidate_runs(run["head_sha"], request) == run,
                    "Candidate history is ambiguous")
            record = evidence.artifact_record(run, "qualified", request, fetch)
            if pair[1] not in [member["head"] for member in record["proof"]["members"]]:
                continue
            proofs.append(evidence.landing(record, run, env, event, root, request))
        except ERRORS:
            # An unrelated/expired candidate is not evidence for this landing.
            continue
    require(len(proofs) == 1, "No unique completed landing proof")
    return proofs[0]


def route(env, event, root, request=policy.github, fetch=evidence.download,
          threads=verifier.read_threads, base_changes=verifier.read_base_changes):
    if not enabled(root):
        return dict(FULL)
    try:
        require(effective_gate(request), "Effective protection is not migrated")
        run = current_run(env, request)
        main = policy.sha(policy.git(root, "rev-parse", "HEAD").decode().strip())
        require(request(REPOSITORY, "git/ref/heads/main")["object"]["sha"] == main,
                "Trusted main changed")
        kind = env["GITHUB_EVENT_NAME"]
        if kind == "pull_request":
            head, branch = policy.side(event["pull_request"], "head")
            require(run["head_sha"] == head and run["head_branch"] == branch, "Run source differs")
            if policy.QUEUE.fullmatch(branch):
                proof = duplicate(env, event, root, main, request, fetch, threads, base_changes)
                mode = "candidate"
            else:
                proof = source(env, event, root, main, request, base_changes)
                mode = "source"
        elif kind == "push" and env["GITHUB_REF"] == "refs/heads/main":
            require(run["head_sha"] == policy.sha(env["GITHUB_SHA"])
                    and run["head_branch"] == "main", "Run landing differs")
            proof = landed(env, event, root, request, fetch)
            mode = "landing"
        else:
            return dict(FULL)
        require(effective_gate(request)
                and request(REPOSITORY, "git/ref/heads/main")["object"]["sha"] == main
                and run == request(REPOSITORY, f"actions/runs/{run['id']}"), "Routing evidence changed")
        return {"mode": mode, "omit_full": True, "proof": evidence.digest(proof)}
    except ERRORS:
        return dict(FULL)


def gate(env, event, root, request=policy.github):
    if env.get("OMIT_FULL") == "true":
        result = route(env, event, root, request)
        require(result["omit_full"] is True and result["mode"] == env["ROUTE_MODE"]
                and result["proof"] == env["ROUTE_PROOF"], "Omitted-work proof no longer verifies")
    else:
        require(all(env.get(key) == "success" for key in
                    ("GUARD_RESULT", "TESTS_RESULT", "NO_SUBMODULE_RESULT", "PACKAGE_RESULT")),
                "Full suite did not succeed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("route", "gate"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        event = evidence.read_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        if args.mode == "gate":
            gate(os.environ, event, root)
            return
        # One bounded startup wait, only under explicitly enabled policy. The
        # same strict proof is re-read; waiting never changes what is accepted.
        result = route(os.environ, event, root)
        if enabled(root) and not result["omit_full"] and os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            for _ in range(6):
                time.sleep(10)
                result = route(os.environ, event, root)
                if result["omit_full"]:
                    break
    except ERRORS:
        if args.mode == "gate":
            parser.exit(1, "Delivery gate refused incomplete, changed or unsuccessful evidence.\n")
        result = dict(FULL)
    print(json.dumps(result, sort_keys=True))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"mode={result['mode']}\nomit_full={str(result['omit_full']).lower()}\n"
                     f"proof={result.get('proof', '')}\n")


if __name__ == "__main__":
    main()
