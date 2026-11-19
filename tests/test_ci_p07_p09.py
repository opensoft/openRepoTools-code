# SPDX-License-Identifier: Apache-2.0
"""The exact-pair gate, not an alternative way to publish queue status."""

from copy import deepcopy
import hashlib
import importlib
import json
import re

import pytest

from conftest import REPO, NEEDS_UPSTREAM
from test_ci_delivery import commit, delivery, git
from test_ci_v13_delivery import write
from test_ci_pilot_queue import matches, reader


@pytest.fixture
def pair(delivery):
    return delivery.exact_pair


@pytest.fixture
def pair_evidence(delivery):
    return importlib.import_module("delivery_evidence")


@pytest.fixture
def exact(tmp_path, pair, monkeypatch):
    root = tmp_path / "exact"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "CI fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    for path in pair.projection.P01_FILES:
        write(root, path, "# reviewed original\n")
    anchor = commit(root, "foundation")
    profiles, heads, bodies = {}, [], {}
    for name, number, count in (("P07", 97, 40), ("P09", 103, 165)):
        git(root, "checkout", "-q", "--detach", anchor)
        file = f"tests/test_{name.lower()}.py"
        task = "T" + str(number)
        write(root, file, "# scoped\n")
        write(root, pair.projection.MARKERS + task, "")
        files = {file: "A"}
        if number == 103:
            for path in pair.TRANSITION:
                write(root, path, "# reviewed transition\n")
                files[path] = "M"
        commit(root, name)
        for index in range(1, count):
            git(root, "commit", "--allow-empty", "-qm", f"{name} checkpoint {index}")
        head = git(root, "rev-parse", "HEAD")
        rows = git(root, "rev-list", "--reverse", "--parents", f"{anchor}..{head}") + "\n"
        profiles[name] = {"anchor": anchor, "chain_sha256": hashlib.sha256(rows.encode()).hexdigest(),
                          "commit_count": count, "tasks": [task], "files": files, "branch": name.lower()}
        heads.append((number, head))
        bodies[str(number)] = hashlib.sha256(name.encode()).hexdigest()
    monkeypatch.setattr(pair, "PREREQUISITE", anchor)
    monkeypatch.setattr(pair, "PAIR", tuple(heads))
    monkeypatch.setattr(pair, "HEADS", tuple(head for _, head in heads))
    monkeypatch.setattr(pair, "BODIES", bodies)
    monkeypatch.setattr(pair.v13, "configuration", lambda *_: {})
    monkeypatch.setattr(pair, "TRANSITION", {
        path: (git(root, "rev-parse", f"{anchor}:{path}"), git(root, "rev-parse", f"HEAD:{path}"))
        for path in pair.TRANSITION})
    git(root, "checkout", "-q", "--detach", anchor)
    config = {"schema_version": 1, "scope": pair.SCOPE, "enabled": True,
              "body_sha256": bodies, "profiles": profiles}
    write(root, pair.CONFIG, json.dumps(config))
    main = commit(root, "activated fixture")
    previous, members, prs = main, [], {}
    for number, head in heads:
        tree = git(root, "merge-tree", "--write-tree", previous, head)
        prefix = git(root, "commit-tree", tree, "-p", previous, "-p", head, "-m", "candidate prefix")
        members.append({"number": number, "head": head, "prefix": prefix, "tree": tree, "delivery": True})
        name = "P07" if number == 97 else "P09"
        repo = {"full_name": pair.git.REPOSITORY}
        prs[number] = {"number": number, "body": name, "state": "open", "draft": False, "merged": False,
                       "base": {"sha": main, "ref": "main", "repo": repo},
                       "head": {"sha": head, "ref": name.lower(), "repo": repo}}
        previous = prefix
    return root, anchor, main, members, prs


@NEEDS_UPSTREAM
def test_ci_p07_p09_exact_queue_and_inventory(pair, reader):
    live = json.loads((REPO / pair.CONFIG).read_text())
    prepared = json.loads((REPO / ".github/ci/v13-prepared-cohort.json").read_text())
    assert live["enabled"] is True and prepared["enabled"] is False
    assert live["body_sha256"] == pair.BODIES
    queue = reader(REPO / ".mergify.yml")["queue_rules"][-1]
    assert queue["name"] == "openrepotools-sql-register-p07-p09"
    assert queue["batch_size"] == 2 and queue["batch_max_failure_resolution_attempts"] == 0
    assert queue["max_checks_retries"] == 0 and queue["merge_method"] == "merge"
    conditions = queue["queue_conditions"]
    assert queue["merge_conditions"] == [
        "check-success=@github-actions/openrepotools-batch-heavy",
        "check-success=@sonarqubecloud/SonarCloud Code Analysis",
    ]
    assert {"base=main", "-draft", "-closed", "-from-fork",
            "check-success=@github-actions/openrepotools-pr-fast",
            "check-success=@github-actions/openrepotools-delivery"} <= {
                item for item in conditions if isinstance(item, str)}
    alternatives = next(item["or"] for item in conditions if isinstance(item, dict))
    assert len(alternatives) == 2
    for (name, profile), item in zip(live["profiles"].items(), alternatives):
        cut = prepared["profiles"][name]
        assert profile["files"] == cut["files"] and profile["tasks"] == cut["tasks"]
        assert profile["branch"] == cut["source"]["branch"]
        paths = set(profile["files"]) | {pair.projection.MARKERS + task for task in profile["tasks"]}
        number, branch, count, negative = item["and"]
        assert number == f"number={cut['source']['number']}"
        assert branch == f"head={profile['branch']}" and count == f"#files={len(paths)}"
        match = re.compile(negative.removeprefix("-files~="))
        assert all(not match.search(path) for path in paths)
        assert all(match.search(path) for path in (".github/workflows/release.yml", "tests/extra.py",
                                                  "tests/sql_register_landed/T999"))


@NEEDS_UPSTREAM
@pytest.mark.parametrize(("checks", "accepted"), [
    ({"check-success": ["@github-actions/openrepotools-batch-heavy"]}, False),
    ({"check-success": ["@github-actions/openrepotools-batch-heavy"],
      "check-neutral": ["@sonarqubecloud/SonarCloud Code Analysis"]}, False),
    ({"check-success": ["@github-actions/openrepotools-batch-heavy",
                        "@other-app/SonarCloud Code Analysis"]}, False),
    ({"check-success": ["@sonarqubecloud/SonarCloud Code Analysis"]}, False),
    ({"check-success": ["@github-actions/openrepotools-batch-heavy",
                        "@sonarqubecloud/SonarCloud Code Analysis"]}, True),
])
def test_ci_p07_p09_candidate_merge_requires_existing_sonar_gate(reader, checks, accepted):
    queue = reader(REPO / ".mergify.yml")["queue_rules"][-1]
    assert all(matches(condition, checks) for condition in queue["merge_conditions"]) is accepted


def test_ci_p07_p09_exact_source_rejects_drift(exact, pair):
    root, anchor, main, members, prs = exact
    assert pair.configuration(root, anchor) is None
    for row in members:
        number, head = row["number"], row["head"]
        pr = prs[number]
        def request(repo, path):
            assert repo == pair.git.REPOSITORY
            if path == f"pulls/{number}":
                return pr
            return {"object": {"sha": main if path.endswith("/main") else head}}
        assert pair.source(root, main, pr, request) == number
        with pytest.raises(ValueError, match="metadata differs"):
            pair.source(root, main, dict(pr, body="edited"), request)
        with pytest.raises(ValueError, match="source moved"):
            pair.source(root, main, pr, lambda _r, _p: dict(pr, state="closed"))


@pytest.mark.parametrize("fault", [None, "one", "reverse", "extra", "wrong-tree", "wrong-tip"])
def test_ci_p07_p09_only_exact_ordered_trees(exact, pair, fault):
    root, _anchor, main, members, _prs = exact
    candidate = members[-1]["prefix"]
    if fault == "one":
        members = members[:1]
    elif fault == "reverse":
        members.reverse()
    elif fault == "extra":
        members += members[:1]
    elif fault == "wrong-tree":
        members[-1]["tree"] = members[0]["tree"]
    elif fault == "wrong-tip":
        candidate = members[0]["prefix"]
    if fault:
        with pytest.raises(ValueError):
            pair.ordered_trees(root, main, candidate, members)
    else:
        assert pair.ordered_trees(root, main, candidate, members) == tuple(m["tree"] for m in members)


def test_ci_p07_p09_fast_log_proves_actual_base(exact, pair_evidence, monkeypatch):
    root, anchor, main, members, _prs = exact
    first = members[0]
    receipt = ({}, {"run_attempt": 1}, {"id": 12}, {})
    payload = {"base": main, "full_ci_required": True, "head": first["head"], "tested": first["prefix"]}
    def output(_):
        return "2026-11-18T20:14:28.6506894Z " + json.dumps(payload, sort_keys=True) + "\n"
    monkeypatch.setattr(pair_evidence, "job_log", output)
    assert pair_evidence.exact_fast_tree(root, main, first["head"], receipt) == first["tree"]
    payload["base"] = anchor
    with pytest.raises(ValueError, match="did not test current base"):
        pair_evidence.exact_fast_tree(root, main, first["head"], receipt)


def test_ci_p07_p09_current_fast_only_source_run(pair_evidence, monkeypatch):
    e = pair_evidence
    repo = {"id": e.REPOSITORY_ID}
    base, head, tree, digest = "1" * 40, "2" * 40, "3" * 40, "a" * 64
    association = [{"number": 97}]
    pr = {"number": 97, "head": {"sha": head, "ref": "p07"}}
    event = {"id": 88, "event": "reopened", "created_at": "2026-11-18T20:00:00Z"}
    fast = ({}, {"id": 69, "created_at": "2026-11-18T20:00:10Z", "pull_requests": association}, {}, {})
    run = {"id": 70, "path": ".github/workflows/tests.yml", "event": "pull_request",
           "repository": repo, "head_repository": repo, "head_sha": head, "head_branch": "p07",
           "pull_requests": association, "run_attempt": 1, "status": "completed",
           "conclusion": "success", "created_at": "2026-11-18T20:00:15Z"}
    jobs = [{"name": name, "id": i, "run_id": 70, "run_attempt": 1, "head_sha": head,
             "status": "completed", "conclusion": "success" if name in e.SOURCE_ROUTED else "skipped"}
            for i, name in enumerate(sorted(e.SOURCE_OMITTED | e.SOURCE_ROUTED), start=1)]
    route = {"mode": "source", "omit_full": True, "proof": digest}
    monkeypatch.setattr(e, "exact_fast_tree", lambda *_: tree)
    monkeypatch.setattr(e, "job_log", lambda _id: "2026-11-18T20:01:00Z " + json.dumps(route))

    def request(_repo, endpoint):
        if endpoint.startswith("issues/97/events?"):
            return [event]
        if endpoint.startswith("actions/workflows/tests.yml/runs?"):
            return {"workflow_runs": [run], "total_count": 1}
        if endpoint.startswith("actions/runs/70/attempts/1/jobs?"):
            return {"jobs": jobs, "total_count": len(jobs)}
        assert endpoint == "actions/runs/70"
        return deepcopy(run)

    assert e.exact_source_ci(None, base, pr, fast, request) == {
        "reopen_event_id": 88, "fast_run_id": 69, "delivery_run_id": 70,
        "tree": tree, "route_proof": digest}
    job = next(row for row in jobs if row["name"] == "tests")
    job["conclusion"] = "success"
    with pytest.raises(ValueError, match="not fast-only"):
        e.exact_source_ci(None, base, pr, fast, request)
    job["conclusion"] = "skipped"
    route["omit_full"] = False
    with pytest.raises(ValueError, match="No stable fast-only"):
        e.exact_source_ci(None, base, pr, fast, request)
    event["event"] = "closed"
    with pytest.raises(ValueError, match="not this source's newest reopen"):
        e.exact_source_ci(None, base, pr, fast, request)


def test_ci_p07_p09_landing_rejects_wrong_tree_and_inventory_drift(exact, pair_evidence, monkeypatch):
    e = pair_evidence
    root, _anchor, main, members, prs = exact
    first, last = (row["prefix"] for row in members)
    run = {"id": 17}
    proof = {"base": main, "candidate": last, "members": members}
    record = {"proof": proof}
    for row in members:
        prs[row["number"]].update(state="closed", merged=True, merge_commit_sha=row["prefix"],
                                  merged_by={"login": e.MERGIFY}, merged_at="2026-11-18T20:02:00Z")
    monkeypatch.setattr(e, "completed_jobs", lambda *_: "2026-11-18T20:01:00Z")
    monkeypatch.setattr(e, "exact_pair_catalogue", lambda *_: ("inventory", [run]))
    live = [last]
    catalogue = [run]

    def request(_repo, endpoint):
        if endpoint.startswith("pulls/"):
            return deepcopy(prs[int(endpoint.split("/")[1])])
        if endpoint == "actions/runs/17":
            return deepcopy(run)
        if endpoint == "git/ref/heads/main":
            return {"object": {"sha": live[0]}}
        assert endpoint.startswith("inventory?")
        return {"workflow_runs": catalogue}

    assert e.exact_pair_landing(proof, record, run, {"GITHUB_SHA": last}, {"before": main},
                                root, last, request)["after"] == last
    assert e.exact_pair_landing(proof, record, run, {"GITHUB_SHA": last}, {"before": first},
                                root, last, request)["after"] == last
    assert e.exact_pair_landing(proof, record, run, {"GITHUB_SHA": first}, {"before": main},
                                root, last, request)["after"] == first
    live[0] = first
    assert e.exact_pair_landing(proof, record, run, {"GITHUB_SHA": first}, {"before": main},
                                root, first, request)["after"] == first
    live[0] = last
    original = members[1]["tree"]
    members[1]["tree"] = members[0]["tree"]
    with pytest.raises(ValueError, match="Landed exact-pair member"):
        e.exact_pair_landing(proof, record, run, {"GITHUB_SHA": last}, {"before": main},
                             root, last, request)
    members[1]["tree"] = original
    catalogue.append({"id": 18})
    with pytest.raises(ValueError, match="landing evidence moved"):
        e.exact_pair_landing(proof, record, run, {"GITHUB_SHA": last}, {"before": main},
                             root, last, request)


def test_ci_p07_p09_catalogue_distinguishes_one_heavy_from_two(pair_evidence, monkeypatch):
    e = pair_evidence
    started = "2026-11-18T20:01:00Z"
    base, other_head = "1" * 40, "3" * 40
    repo = {"id": e.REPOSITORY_ID}
    run = {"id": 70, "run_number": 77, "run_attempt": 1, "path": e.CALLER, "event": "push",
           "head_branch": "mergify/merge-queue/a1b2c3d4e5", "head_sha": "2" * 40,
           "created_at": started, "status": "completed", "conclusion": "success",
           "repository": repo, "head_repository": repo}
    probe = dict(run, id=71, run_number=78, head_sha=other_head, conclusion="failure",
                 head_branch="mergify/merge-queue/b1c2d3e4f5",
                 referenced_workflows=[{"path": path, "sha": other_head} for path in sorted(e.CALLEES)],
                 actor={"login": e.MERGIFY}, triggering_actor={"login": e.MERGIFY})
    jobs = [{"name": name, "id": i, "run_id": 71, "head_sha": other_head, "run_attempt": 1,
             "status": "completed", "conclusion": conclusion, "steps": []}
            for i, (name, conclusion) in enumerate(
                (("probe", "success"), ("candidate", "skipped"), (e.HEAVY, "failure")), start=1)]
    jobs[0]["steps"] = [{"name": "Preserve verified admission", "conclusion": "skipped"}]
    jobs[-1]["steps"] = [{"name": "Require admitted complete integration", "conclusion": "failure"},
                         {"name": "Final live candidate verification", "conclusion": "skipped"}]
    blob, bad_blob = "a" * 40, "b" * 40
    current_blob = [blob]
    monkeypatch.setattr(e.policy, "git", lambda *_: blob.encode())

    def request(_repo, endpoint):
        if endpoint == f"commits/{base}":
            return {"sha": base, "commit": {"committer": {"date": "2026-11-18T20:00:00Z"}}}
        if endpoint.startswith("actions/workflows/"):
            return {"workflow_runs": [run, probe], "total_count": 2}
        if endpoint.startswith("actions/runs/71/attempts/1/jobs?"):
            return {"jobs": jobs, "total_count": len(jobs)}
        assert endpoint.startswith("contents/") and endpoint.endswith(f"?ref={other_head}")
        return {"sha": current_blob[0]}

    assert e.exact_pair_catalogue(None, base, run, request)[1] == [run, probe]
    current_blob[0] = bad_blob
    with pytest.raises(ValueError, match="not the reviewed variant"):
        e.exact_pair_catalogue(None, base, run, request)
    current_blob[0] = blob
    jobs.append(dict(jobs[-1], id=4, name="candidate / full-ci / tests", conclusion="success"))
    with pytest.raises(ValueError, match="may have executed heavy CI"):
        e.exact_pair_catalogue(None, base, run, request)
    jobs.pop()
    jobs[-1]["steps"][1]["conclusion"] = "failure"
    with pytest.raises(ValueError, match="Incomplete probe-only job-step"):
        e.exact_pair_catalogue(None, base, run, request)
    jobs[-1]["steps"][1]["conclusion"] = "skipped"
    probe["run_attempt"] = 2
    with pytest.raises(ValueError, match="Ambiguous exact-pair heavy attempt"):
        e.exact_pair_catalogue(None, base, run, request)


def test_ci_p07_p09_receipt_records_both_sources_and_requires_current_base_review(pair, pair_evidence, delivery):
    e = pair_evidence
    repo = e.REPOSITORY
    candidate, base = "4" * 40, "5" * 40
    run = {"id": 12, "head_sha": candidate, "head_branch": "mergify/merge-queue/main/batch-1"}
    members = []
    for index, (number, head) in enumerate(pair.PAIR, start=1):
        members.append({"number": number, "head": head, "prefix": candidate, "tree": "6" * 40,
                        "delivery": True, "source_ci": {
                            "reopen_event_id": index, "fast_run_id": index + 2,
                            "delivery_run_id": index + 4, "review_comment_id": index + 6,
                            "tree": "7" * 40, "route_proof": "a" * 64}})
    proof = {"base": base, "candidate": candidate, "tree": "6" * 40, "members": members,
             "scope": pair.SCOPE, "verified": True, "full_ci_required": True}
    record = {"schema_version": 1, "phase": "admission", "repository": repo,
              "repository_id": e.REPOSITORY_ID, "run_id": 12, "run_attempt": 1,
              "branch": run["head_branch"], "proof": proof}
    assert e.record_valid(record, run, "admission") == record
    members[1]["source_ci"]["reopen_event_id"] = members[0]["source_ci"]["reopen_event_id"]
    with pytest.raises(ValueError, match="Reused exact-pair source receipt"):
        e.record_valid(record, run, "admission")
    del members[1]["source_ci"]
    with pytest.raises(ValueError, match="Invalid member schema"):
        e.record_valid(record, run, "admission")
    comments = {"pageInfo": {"hasNextPage": False}, "nodes": []}
    with pytest.raises(ValueError, match="review must bind the current base"):
        delivery.clean_review(97, pair.HEADS[0], lambda *_: [], lambda _n: {"comments": comments},
                              base=base, exact_base=True)


def test_ci_p07_p09_complete_paginated_review_history(delivery):
    first, second = ({"id": n, "body": str(n)} for n in range(1, 102)), [{"id": 102, "body": "last"}]
    rows = list(first)
    pages = {"/comments?per_page=100": rows[:100], "/comments?per_page=100&page=2": rows[100:] + second}
    request = lambda _repo, endpoint: pages[endpoint.removeprefix("issues/103")]
    comments = delivery.read_rest_comments(103, request)
    assert len(comments) == 102
    graph = {"comments": {"pageInfo": {"hasNextPage": False},
                          "nodes": [{"databaseId": row["id"], "body": row["body"]} for row in comments]}}
    delivery.consistent_comments(comments, graph)
    graph["comments"]["nodes"][-1]["body"] = "replacement"
    with pytest.raises(ValueError, match="inconsistent review comment"):
        delivery.consistent_comments(comments, graph)
    pages["/comments?per_page=100&page=2"].append(rows[0])
    with pytest.raises(ValueError, match="inconsistent review comment"):
        delivery.read_rest_comments(103, request)
