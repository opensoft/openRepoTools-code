# SPDX-License-Identifier: Apache-2.0
"""Read-only candidate receipts and separate historical landing verification.

No archive extraction, arbitrary URLs, settings/status writes or closed-as-open
admission. Missing/expired/ambiguous evidence is a refusal, never a skip grant.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
import re
import subprocess
import tempfile
from urllib.parse import urlencode
import zipfile

import shadow_scope as policy
import delivery_v13 as v13
import delivery_p07_p09 as exact_pair
from delivery_verify import PendingEvidence, require

REPOSITORY = policy.REPOSITORY
REPOSITORY_ID = 1434660228
CALLER = ".github/workflows/task-set-candidate-shadow.yml"
CALLEES = {".github/workflows/task-set-candidate.yml", ".github/workflows/tests.yml"}
HEAVY = "openrepotools-batch-heavy"
MERGIFY = "mergify[bot]"
TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
FULL_JOBS = {"guard-launch-mode", "tests", "tests-no-submodule", "package",
             "delivery-route", "openrepotools-delivery"} | {
    f"{name} ({shard})" for name, shards in {
        "tests-shard": ["pytest-1", "pytest-2", "pytest-3", "pytest-4", "shell"],
        "tests-no-submodule-shard": ["pytest-1", "pytest-2", "pytest-3", "shell"]}.items()
    for shard in shards}
CANDIDATE_JOBS = {"probe", "candidate / Verify queue candidate",
                  "candidate / Candidate full-suite qualification", HEAVY} | {
    "candidate / full-ci / " + name for name in FULL_JOBS}
ARCHIVE_LIMIT = 262144
JSON_LIMIT = 32768
SOURCE_OMITTED = {"guard-launch-mode", "package", "tests", "tests-no-submodule",
                  "tests-shard", "tests-no-submodule-shard"}
SOURCE_ROUTED = {"delivery-route", "openrepotools-delivery"}


class FastProofLogPending(PendingEvidence):
    """An authenticated, successful fast job's log is not yet available."""


def positive(value):
    require(type(value) is int and value > 0, "Invalid numeric identity")
    return value


def unique_object(pairs):
    require(len(pairs) == len(dict(pairs)), "Duplicate JSON key")
    return dict(pairs)


def read_json(data):
    return json.loads(data, object_pairs_hook=unique_object,
                      parse_constant=lambda _value: require(False, "Non-finite JSON"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def run_identity(run, candidate=None, branch=None, completed=False):
    positive(run["id"])
    require(run["repository"]["full_name"] == REPOSITORY
            and run["repository"]["id"] == REPOSITORY_ID
            and run["head_repository"]["full_name"] == REPOSITORY
            and run["head_repository"]["id"] == REPOSITORY_ID
            and run["event"] == "push" and run["path"] == CALLER
            and run["actor"]["login"] == MERGIFY
            and run["triggering_actor"]["login"] == MERGIFY
            and type(run["run_attempt"]) is int and run["run_attempt"] == 1
            and policy.QUEUE.fullmatch(run["head_branch"]) is not None,
            "Run is not an authentic first-attempt candidate caller")
    policy.sha(run["head_sha"])
    require(candidate is None or run["head_sha"] == candidate, "Run candidate differs")
    require(branch is None or run["head_branch"] == branch, "Run branch differs")
    if completed:
        require(run["status"] == "completed" and run["conclusion"] == "success",
                "Candidate run is not successful")
        expected = {f"{REPOSITORY}/{path}@{run['head_sha']}" for path in CALLEES}
        workflows = run["referenced_workflows"]
        require(len(workflows) == 2 and {row["path"] for row in workflows} == expected
                and all(row["sha"] == run["head_sha"]
                        and row["ref"] == "refs/heads/" + run["head_branch"]
                        for row in workflows), "Unexpected immutable workflow reuse")
    else:
        require(run["status"] in {"queued", "in_progress", "completed"}
                and (run["status"] != "completed" or run["conclusion"] == "success"),
                "Candidate run failed or stopped")
    return run


def record_valid(record, run, phase):
    require(set(record) == {"schema_version", "phase", "repository", "repository_id",
                            "run_id", "run_attempt", "branch", "proof"}
            and type(record["schema_version"]) is int and record["schema_version"] == 1
            and record["phase"] == phase and phase in {"admission", "qualified"}
            and record["repository"] == REPOSITORY
            and record["repository_id"] == REPOSITORY_ID
            and positive(record["run_id"]) == run["id"]
            and type(record["run_attempt"]) is int and record["run_attempt"] == 1
            and record["branch"] == run["head_branch"], "Receipt provenance differs")
    proof = record["proof"]
    fields = {"verified", "full_ci_required", "base", "candidate", "tree", "members"}
    scoped = "scope" in proof
    require(set(proof) == fields | ({"scope"} if scoped else set())
            and (not scoped or proof["scope"] in {v13.SCOPE, exact_pair.SCOPE})
            and proof["verified"] is True and proof["full_ci_required"] is True
            and proof["candidate"] == run["head_sha"], "Receipt proof differs")
    for key in ("base", "candidate", "tree"):
        policy.sha(proof[key])
    members = proof["members"]
    require(isinstance(members, list) and 1 <= len(members) <= 2, "Invalid member inventory")
    exact = proof.get("scope") == exact_pair.SCOPE
    for row in members:
        require(set(row) == {"number", "head", "prefix", "tree", "delivery"} | ({"source_ci"} if exact else set())
                and type(row["delivery"]) is bool, "Invalid member schema")
        positive(row["number"])
        for key in ("head", "prefix", "tree"):
            policy.sha(row[key])
        if exact:
            source = row["source_ci"]
            identifiers = {"reopen_event_id", "fast_run_id", "delivery_run_id", "review_comment_id"}
            require(set(source) == identifiers | {"tree", "route_proof"}, "Invalid source receipt schema")
            for key in identifiers:
                positive(source[key])
            policy.sha(source["tree"])
            require(re.fullmatch(r"[0-9a-f]{64}", source["route_proof"]) is not None,
                    "Invalid source route proof")
    require(len({row["number"] for row in members}) == len(members)
            and len({row["head"] for row in members}) == len(members)
            and members[-1]["prefix"] == proof["candidate"]
            and members[-1]["tree"] == proof["tree"], "Ambiguous final member")
    if exact:
        require(tuple((row["number"], row["head"]) for row in members) == exact_pair.PAIR
                and all(row["delivery"] is True for row in members), "Exact-pair receipt differs")
        for key in ("reopen_event_id", "fast_run_id", "delivery_run_id", "review_comment_id"):
            require(len({row["source_ci"][key] for row in members}) == 2, "Reused exact-pair source receipt")
    return record


def make_record(proof, phase, env, request=policy.github):
    require(env["GITHUB_REPOSITORY"] == REPOSITORY
            and env["GITHUB_EVENT_NAME"] == "push", "Unsupported proof writer context")
    run_id = positive(int(env["GITHUB_RUN_ID"]))
    require(env["GITHUB_RUN_ATTEMPT"] == "1", "Rerun cannot publish admission")
    run = run_identity(request(REPOSITORY, f"actions/runs/{run_id}"),
                       policy.sha(env["GITHUB_SHA"]), env["GITHUB_REF"].removeprefix("refs/heads/"))
    record = {"schema_version": 1, "phase": phase, "repository": REPOSITORY,
              "repository_id": REPOSITORY_ID, "run_id": run_id, "run_attempt": 1,
              "branch": run["head_branch"], "proof": proof}
    return record_valid(record, run, phase)


def pages(request, endpoint, field, limit=3):
    """Exhaust all bounded pages; saturation at the cap refuses, not truncates."""
    rows = []
    separator = "&" if "?" in endpoint else "?"
    for page in range(1, limit + 1):
        response = request(REPOSITORY, f"{endpoint}{separator}per_page=100&page={page}")
        values = response[field] if field else response
        require(isinstance(values, list) and len(values) <= 100, "Malformed API page")
        rows.extend(values)
        if len(values) < 100:
            if field and "total_count" in response:
                require(type(response["total_count"]) is int
                        and response["total_count"] == len(rows), "Incomplete API inventory")
            return rows
    require(False, "API inventory exceeds safe bound")


def download(artifact_id):
    # Known GitHub endpoint only; never a URL or command taken from a receipt.
    positive(artifact_id)
    with tempfile.TemporaryFile() as output:
        subprocess.run(["gh", "api", "--hostname", "github.com",
                        f"repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"],
                       check=True, stdout=output, stderr=subprocess.PIPE, timeout=15)
        require(output.tell() <= ARCHIVE_LIMIT, "Oversized artifact archive")
        output.seek(0)
        return output.read(ARCHIVE_LIMIT + 1)


def job_log(job_id):
    positive(job_id)
    command = ["gh", "api", "--hostname", "github.com"]
    endpoint = f"repos/{REPOSITORY}/actions/jobs/{job_id}/logs"
    with tempfile.TemporaryFile() as output:
        options = dict(check=True, stdout=output, stderr=subprocess.PIPE, timeout=15)
        try:
            subprocess.run([*command, endpoint], **options)
        except subprocess.CalledProcessError as exc:
            if (exc.stderr or b"").strip() != (
                b"the response contains terminal escape sequences; "
                b"pass --allow-escape-sequences to output it anyway"
            ):
                raise
            # Job logs are proof input in this private file, never terminal output.
            output.seek(0)
            output.truncate()
            subprocess.run([*command, "--allow-escape-sequences", endpoint], **options)
        require(output.tell() <= 2 * 1024 * 1024, "Oversized source evidence log")
        output.seek(0)
        return output.read().decode()


def exact_fast_tree(root, base, head, receipt, *, allow_pending_log=False):
    """Prove what the successful identity step checked, not its mutable association."""
    _check, run, job, _history = receipt
    require(run["run_attempt"] == 1, "Exact-pair source fast was retried")
    try:
        log = job_log(job["id"])
    except subprocess.CalledProcessError as exc:
        # Only the exact-pair source router may wait after authenticating the
        # completed fast job. A downloaded log still has to prove the checkout.
        if allow_pending_log and re.fullmatch(
                rb"gh: (?:HTTP 404|[^\r\n]+ \(HTTP 404\))", (exc.stderr or b"").strip()):
            raise FastProofLogPending() from exc
        raise
    lines = re.findall(r'^\S+ (\{"base": "[0-9a-f]{40}", "full_ci_required": true, '
                       r'"head": "[0-9a-f]{40}", "tested": "[0-9a-f]{40}"\})\s*$',
                       log, re.MULTILINE)
    require(len(lines) == 1, "Expected one exact source fast checkout proof")
    proof = read_json(lines[0])
    require(proof["base"] == base and proof["head"] == head, "Fast proof did not test current base")
    tested = ensure_commit(root, proof["tested"])
    require(policy.git(root, "show", "-s", "--format=%P", tested).decode().split() == [base, head],
            "Exact-pair fast checkout parents differ")
    tree = policy.sha(policy.git(root, "rev-parse", tested + "^{tree}").decode().strip())
    require(tree == policy.git(root, "merge-tree", "--write-tree", base, head).decode().strip(),
            "Exact-pair fast checkout tree differs")
    return tree


def exact_source_ci(root, base, pr, fast_receipt, request):
    """Candidate admission requires that the current source actually ran fast-only."""
    head = pr["head"]["sha"]
    tree = exact_fast_tree(root, base, head, fast_receipt)
    fast = fast_receipt[1]
    events = pages(request, f"issues/{pr['number']}/events", None)
    states = [item for item in events if item["event"] in {"closed", "reopened"}]
    require(bool(states) and len({positive(item["id"]) for item in states}) == len(states),
            "Missing or ambiguous exact-pair event history")
    newest = max(states, key=lambda row: (datetime.strptime(row["created_at"], TIMESTAMP), row["id"]))
    reopened = datetime.strptime(newest["created_at"], TIMESTAMP)
    require(newest["event"] == "reopened" and
            0 <= (datetime.strptime(fast["created_at"], TIMESTAMP) - reopened).total_seconds() <= 120,
            "Fast proof is not this source's newest reopen")
    query = urlencode({"head_sha": head, "event": "pull_request", "created": ">=" + newest["created_at"]})
    rows = pages(request, "actions/workflows/tests.yml/runs?" + query,
                 "workflow_runs")
    require(len(rows) == 1, "Expected one fresh source delivery run")
    run = rows[0]
    rid = positive(run["id"])
    require(run["path"] == ".github/workflows/tests.yml" and run["event"] == "pull_request"
            and run["repository"]["id"] == REPOSITORY_ID and run["head_repository"]["id"] == REPOSITORY_ID
            and run["head_sha"] == head and run["head_branch"] == pr["head"]["ref"]
            and run["pull_requests"] == fast["pull_requests"]
            and type(run["run_attempt"]) is int and run["run_attempt"] == 1
            and run["status"] == "completed" and run["conclusion"] == "success"
            and 0 <= (datetime.strptime(run["created_at"], TIMESTAMP) - reopened).total_seconds() <= 120,
            "Not fresh successful source delivery")
    jobs = pages(request, f"actions/runs/{rid}/attempts/1/jobs", "jobs")
    require(len(jobs) == len(SOURCE_OMITTED | SOURCE_ROUTED)
            and {row["name"] for row in jobs} == SOURCE_OMITTED | SOURCE_ROUTED
            and len({positive(row["id"]) for row in jobs}) == len(jobs),
            "Source delivery job inventory differs")
    for job in jobs:
        require(job["run_id"] == rid and job["run_attempt"] == 1 and job["head_sha"] == head
                and job["status"] == "completed" and
                job["conclusion"] == ("success" if job["name"] in SOURCE_ROUTED else "skipped"),
                "Exact-pair source delivery was not fast-only")
    route = next(job for job in jobs if job["name"] == "delivery-route")
    lines = re.findall(r'^\S+ (\{"mode": "source", "omit_full": true, "proof": "[0-9a-f]{64}"\})\s*$',
                       job_log(route["id"]), re.MULTILINE)
    require(len(lines) == 1 and request(REPOSITORY, f"actions/runs/{rid}") == run,
            "No stable fast-only source route proof")
    return {"reopen_event_id": newest["id"], "fast_run_id": positive(fast["id"]),
            "delivery_run_id": rid, "tree": tree, "route_proof": read_json(lines[0])["proof"]}


def artifact_record(run, phase, request=policy.github, fetch=download, *, allow_pending=False):
    run_identity(run)
    name = f"candidate-{phase}-{run['head_sha']}-a1"
    rows = pages(request, f"actions/runs/{run['id']}/artifacts", "artifacts")
    selected = [row for row in rows if row["name"] == name]
    if (allow_pending and phase == "admission" and not selected
            and run["status"] in {"queued", "in_progress"}):
        # This observation grants no artifact proof. Reacquire the authenticated
        # caller and real receipt afresh after the existing bounded wait.
        raise PendingEvidence("Authenticated candidate has not published admission yet")
    require(len(selected) == 1, "Missing or duplicate receipt artifact")
    item = selected[0]
    artifact_id = positive(item["id"])
    require(item["expired"] is False and type(item["size_in_bytes"]) is int
            and 0 < item["size_in_bytes"] <= ARCHIVE_LIMIT
            and item["workflow_run"]["id"] == run["id"]
            and item["workflow_run"]["repository_id"] == REPOSITORY_ID
            and item["workflow_run"]["head_repository_id"] == REPOSITORY_ID
            and item["workflow_run"]["head_sha"] == run["head_sha"],
            "Artifact belongs to another run/repository/head")
    data = fetch(artifact_id)
    require(0 < len(data) <= ARCHIVE_LIMIT
            and item["digest"] == "sha256:" + hashlib.sha256(data).hexdigest(),
            "Artifact archive digest differs")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        require(len(infos) == 1 and infos[0].filename == "proof.json"
                and not infos[0].is_dir() and 0 < infos[0].file_size <= JSON_LIMIT
                and not infos[0].flag_bits & 1, "Unsupported artifact contents")
        record = record_valid(read_json(archive.read(infos[0])), run, phase)
    require(item == request(REPOSITORY, f"actions/artifacts/{artifact_id}"),
            "Artifact changed while reading")
    current = request(REPOSITORY, f"actions/runs/{run['id']}")
    if allow_pending and phase == "admission" and run != current:
        run_identity(current, run["head_sha"], run["head_branch"])
        require(current["id"] == run["id"]
                and (current["status"] == "completed" or current["conclusion"] is None),
                "Admission caller identity/state changed")
        # A moving caller supplies no record. The existing bounded observer
        # must reacquire the real archive and every independent source proof.
        raise PendingEvidence("Authenticated admission caller changed while reading")
    require(run == current, "Artifact/run changed while reading")
    return record


def completed_jobs(run, request=policy.github):
    run_identity(run, completed=True)
    rows = pages(request, f"actions/runs/{run['id']}/attempts/1/jobs", "jobs")
    require(len(rows) == len(CANDIDATE_JOBS)
            and {row["name"] for row in rows} == CANDIDATE_JOBS
            and len({positive(row["id"]) for row in rows}) == len(rows),
            "Candidate job inventory differs")
    for row in rows:
        require(row["run_id"] == run["id"] and row["run_attempt"] == 1
                and row["head_sha"] == run["head_sha"]
                and row["status"] == "completed" and row["conclusion"] == "success",
                "Candidate job did not complete successfully")
        datetime.strptime(row["completed_at"], TIMESTAMP)
    return max(row["completed_at"] for row in rows)


def ensure_commit(root, value):
    """Acquire a validated immutable public object, never its checkout or refs."""
    commit = policy.sha(value)
    try:
        policy.git(root, "cat-file", "-e", commit + "^{commit}")
    except subprocess.CalledProcessError:
        policy.git(root, "-c", "credential.helper=", "-c", "credential.interactive=false",
                   "-c", "fetch.recurseSubmodules=false", "fetch", "--no-tags",
                   "--no-write-fetch-head", "https://github.com/" + REPOSITORY + ".git", commit)
    policy.git(root, "cat-file", "-e", commit + "^{commit}")
    return commit


def candidate_chain(record, root):
    proof = record["proof"]
    is_v13 = proof.get("scope") == v13.SCOPE
    # Queue branches may already be deleted at main-push time.
    ensure_commit(root, proof["candidate"])
    if proof.get("scope") == exact_pair.SCOPE:
        for member in proof["members"]:
            exact_pair.cut(root, proof["base"], member["head"])
            tree = policy.git(root, "merge-tree", "--write-tree",
                              proof["base"], member["head"]).decode().strip()
            require(tree == member["source_ci"]["tree"], "Exact-pair source receipt tree differs")
        exact_pair.ordered_trees(root, proof["base"], proof["candidate"], proof["members"])
        return proof
    previous, heads = proof["base"], []
    for row in proof["members"]:
        head, prefix = row["head"], row["prefix"]
        require(row["delivery"] is True, "Member did not opt into delivery")
        if is_v13:
            projection, _cut, _profile = v13.cut(root, proof["base"], head)
            anchor = projection["prerequisite"]["head"]
        else:
            anchor = proof["base"]
            policy.git(root, "merge-base", "--is-ancestor", anchor, head)
        for other in heads:
            require(policy.git(root, "merge-base", "--all", other, head).decode().split()
                    == [anchor], "Member histories are not independent")
        heads.append(head)
        scoped = (v13.prefix(root, proof["base"], head, previous, prefix) if is_v13 else
                  policy.regular_scope(root, proof["base"], head)
                  and policy.regular_scope(root, previous, prefix))
        require(policy.git(root, "show", "-s", "--format=%P", prefix).decode().split()
                == [previous, head] and scoped, "Candidate chain differs")
        tree = policy.git(root, "rev-parse", prefix + "^{tree}").decode().strip()
        require(tree == row["tree"] == policy.git(
            root, "merge-tree", "--write-tree", previous, head).decode().strip(),
            "Candidate prefix tree differs")
        previous = prefix
    return proof


def candidate_runs(candidate, request):
    policy.sha(candidate)
    rows = pages(request, f"actions/workflows/task-set-candidate-shadow.yml/runs?head_sha={candidate}",
                 "workflow_runs", limit=1)
    matching = [row for row in rows if row["head_sha"] == candidate and row["event"] == "push"]
    require(len(matching) == 1, "No unique candidate caller")
    run = request(REPOSITORY, f"actions/runs/{positive(matching[0]['id'])}")
    return run_identity(run, candidate)


def exact_pair_catalogue(root, base, run, request):
    """Do not count a trusted probe-only refusal as a second heavy run."""
    epoch = request(REPOSITORY, f"commits/{base}")
    require(epoch["sha"] == base, "Exact-pair window base differs")
    cutoff = datetime.strptime(epoch["commit"]["committer"]["date"], TIMESTAMP)
    endpoint = "actions/workflows/task-set-candidate-shadow.yml/runs?" + urlencode({
        "event": "push", "created": ">=" + cutoff.strftime(TIMESTAMP)})
    rows = pages(request, endpoint, "workflow_runs")
    by_id = {positive(item["id"]): item for item in rows}
    fields = ("id", "path", "event", "head_branch", "head_sha", "run_attempt", "created_at",
              "run_number", "status", "conclusion")
    recent = by_id.get(run["id"])
    require(len(rows) == len(by_id) and recent is not None
            and all(recent[key] == run[key] for key in fields),
            "Exact-pair heavy catalogue differs")
    for item in rows:
        head = policy.sha(item["head_sha"])
        require(item["path"] == CALLER and item["event"] == "push"
                and item["repository"]["id"] == REPOSITORY_ID
                and item["head_repository"]["id"] == REPOSITORY_ID
                and datetime.strptime(item["created_at"], TIMESTAMP) >= cutoff,
                "Unknown run in exact-pair catalogue")
        if item["id"] == run["id"]:
            continue
        require(item["status"] == "completed" and type(item["run_attempt"]) is int
                and item["run_attempt"] == 1, "Ambiguous exact-pair heavy attempt")
        require(item["actor"]["login"] == MERGIFY and item["triggering_actor"]["login"] == MERGIFY
                and policy.QUEUE.fullmatch(item["head_branch"]) is not None
                and item["conclusion"] == "failure",
                "Not an authentic probe-only refusal")
        jobs = pages(request, f"actions/runs/{item['id']}/attempts/1/jobs", "jobs")
        outcomes = {job["name"]: job["conclusion"] for job in jobs}
        require(len({positive(job["id"]) for job in jobs}) == len(jobs)
                and len(outcomes) == len(jobs)
                and outcomes == {"probe": "success", "candidate": "skipped", HEAVY: "failure"}
                and all(job["run_id"] == item["id"] and job["head_sha"] == head
                        and job["run_attempt"] == 1 and job["status"] == "completed" for job in jobs),
                "Another run executed or may have executed heavy CI")
        by_name = {job["name"]: job for job in jobs}
        for name, step, conclusion in (
            ("probe", "Preserve verified admission", "skipped"),
            (HEAVY, "Require admitted complete integration", "failure"),
            (HEAVY, "Final live candidate verification", "skipped"),
        ):
            require([row["conclusion"] for row in by_name[name]["steps"] if row["name"] == step]
                    == [conclusion], "Incomplete probe-only job-step evidence")
        for path in sorted(CALLEES | {CALLER}):
            expected = policy.git(root, "rev-parse", f"{base}:{path}").decode().strip()
            observed = request(REPOSITORY, f"contents/{path}?ref={head}")
            require(observed["sha"] == expected, "Probe-only workflow was not the reviewed variant")
    return endpoint, rows


def exact_pair_landing(proof, record, run, env, event, root, main, request):
    base, members = proof["base"], proof["members"]
    after, before = policy.sha(env["GITHUB_SHA"]), policy.sha(event["before"])
    finished = datetime.strptime(completed_jobs(run, request), TIMESTAMP)
    endpoint, rows = exact_pair_catalogue(root, base, run, request)
    chain, cursor = [], main
    for _ in members:
        if cursor == base:
            break
        parents = policy.git(root, "show", "-s", "--format=%P", cursor).decode().split()
        require(len(parents) == 2, "Landing is not an exact-pair prefix")
        chain.append((cursor, parents))
        cursor = parents[0]
    chain.reverse()
    require(cursor == base and bool(chain), "Live main is outside the qualified pair")
    matches = [(index, pair) for index, (commit, pair) in enumerate(chain) if commit == after]
    require(len(matches) == 1, "Main event is not a verified pair prefix")
    index, parents = matches[0]
    require(before == parents[0] or (index == 1 and before == base), "Pair landing predecessor differs")
    snapshots = []
    previous = finished
    for (commit, parents), member in zip(chain, members):
        n = member["number"]
        pr = request(REPOSITORY, f"pulls/{n}")
        require(parents[1] == member["head"]
                and policy.git(root, "rev-parse", commit + "^{tree}").decode().strip() == member["tree"]
                and pr["number"] == n and pr["state"] == "closed" and pr["merged"] is True
                and pr["merge_commit_sha"] == commit and policy.side(pr, "head")[0] == member["head"]
                and policy.side(pr, "base")[1] == "main" and pr["merged_by"]["login"] == MERGIFY,
                "Landed exact-pair member identity differs")
        merged = datetime.strptime(pr["merged_at"], TIMESTAMP)
        require(merged >= previous, "Exact-pair landing predates qualification or predecessor")
        previous = merged
        snapshots.append((n, pr))
    require(pages(request, endpoint, "workflow_runs") == rows
            and all(pr == request(REPOSITORY, f"pulls/{n}") for n, pr in snapshots)
            and run == request(REPOSITORY, f"actions/runs/{run['id']}")
            and request(REPOSITORY, "git/ref/heads/main")["object"]["sha"] == main,
            "Exact-pair landing evidence moved")
    return {"candidate": proof["candidate"], "after": after, "record": digest(record)}


def landing(record, run, env, event, root, request=policy.github):
    """Closed records are historical proof, never open candidate admission."""
    require(env["GITHUB_EVENT_NAME"] == "push" and env["GITHUB_REF"] == "refs/heads/main"
            and env["GITHUB_ACTOR"] == MERGIFY
            and event["sender"]["login"] == MERGIFY
            and event["repository"]["full_name"] == REPOSITORY
            and event["ref"] == env["GITHUB_REF"] and event["forced"] is False
            and event["deleted"] is False, "Not an authentic main landing event")
    after = policy.sha(event["after"])
    require(after == policy.sha(env["GITHUB_SHA"]), "Main event identity differs")
    main = policy.sha(policy.git(root, "rev-parse", "HEAD").decode().strip())
    require(request(REPOSITORY, "git/ref/heads/main")["object"]["sha"] == main,
            "Trusted main moved")
    policy.git(root, "merge-base", "--is-ancestor", after, main)
    proof = candidate_chain(record_valid(record, run, "qualified"), root)
    if proof.get("scope") == exact_pair.SCOPE:
        return exact_pair_landing(proof, record, run, env, event, root, main, request)
    if proof.get("scope") == v13.SCOPE:
        stable = v13.unchanged_policy(root, proof["base"], main)
    else:
        changed = policy.git(root, "diff", "--name-only", proof["base"], main, "--").decode().splitlines()
        stable = all(path in policy.SCOPE for path in changed)
    require(stable, "Policy/commands changed since qualification")
    finished = completed_jobs(run, request)
    # Reconstruct the prefix ending at this event, not any lookalike final tree.
    chain, current = [], after
    for _ in range(2):
        if current == proof["base"]:
            break
        pair = policy.git(root, "show", "-s", "--format=%P", current).decode().split()
        require(len(pair) == 2, "Landing is not a bounded merge prefix")
        chain.append((current, pair))
        current = pair[0]
    require(current == proof["base"] and 1 <= len(chain) <= len(proof["members"]),
            "Landing has another root/member count")
    require(policy.sha(event["before"]) == chain[0][1][0], "Main event did not land one prefix")
    snapshots = []
    for (commit, pair), member in zip(reversed(chain), proof["members"]):
        pr = request(REPOSITORY, f"pulls/{member['number']}")
        require(pair[1] == member["head"]
                and policy.git(root, "rev-parse", commit + "^{tree}").decode().strip() == member["tree"]
                and pr["number"] == member["number"] and pr["state"] == "closed"
                and pr["merged"] is True and pr["merge_commit_sha"] == commit
                and policy.side(pr, "head")[0] == member["head"]
                and policy.side(pr, "base")[1] == "main"
                and datetime.strptime(pr["merged_at"], TIMESTAMP)
                >= datetime.strptime(finished, TIMESTAMP),
                "Landed source/merge record differs from completed qualification")
        snapshots.append(pr)
    require(all(pr == request(REPOSITORY, f"pulls/{pr['number']}") for pr in snapshots)
            and run == request(REPOSITORY, f"actions/runs/{run['id']}")
            and request(REPOSITORY, "git/ref/heads/main")["object"]["sha"] == main,
            "Historical provenance changed")
    return {"candidate": proof["candidate"], "after": after, "record": digest(record)}
