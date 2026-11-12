# SPDX-License-Identifier: Apache-2.0
"""Additive delivery proof; no queue, status, ruleset or release writes.

Candidate mode runs only from trusted main. Git merge-tree may create private
immutable objects in that disposable checkout; it changes no ref/index/worktree.
Successful verification still requires the entire heavy suite and a final recheck.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess

import shadow_scope as policy

REPOSITORY = policy.REPOSITORY
FAST = "openrepotools-pr-fast"
FAST_WORKFLOW = ".github/workflows/task-set-fast.yml"


def delivery_intended(text):
    if not policy.intended(text):
        return False
    lines = re.findall(r"(?m)^CI-Delivery:[^\n]*", text)
    return [line.rstrip(" \t\r") for line in lines] == ["CI-Delivery: claude-current"]


class Refused(ValueError):
    """A fixed-vocabulary refusal safe to expose in the CI log."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def read_threads(number):
    require(type(number) is int and number > 0, "Invalid PR identity")
    query = ('query { repository(owner:"opensoft",name:"openRepoTools-code") { '
             f'pullRequest(number:{number}) {{ reviewThreads(first:100) {{ '
             'pageInfo { hasNextPage } nodes { isResolved } } } } }')
    data = subprocess.run(["gh", "api", "--hostname", "github.com", "graphql",
                           "-f", "query=" + query], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15).stdout
    return json.loads(data)["data"]["repository"]["pullRequest"]["reviewThreads"]


def read_base_changes(number):
    require(type(number) is int and number > 0, "Invalid PR identity")
    query = ('query { repository(owner:"opensoft",name:"openRepoTools-code") { '
             f'pullRequest(number:{number}) {{ timelineItems(first:100, '
             'itemTypes:[BASE_REF_CHANGED_EVENT]) { pageInfo { hasNextPage } '
             'nodes { ... on BaseRefChangedEvent { createdAt } } } } } }')
    data = subprocess.run(["gh", "api", "--hostname", "github.com", "graphql",
                           "-f", "query=" + query], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15).stdout
    return json.loads(data)["data"]["repository"]["pullRequest"]["timelineItems"]


def clean_review(number, head, request, threads):
    comments = request(REPOSITORY, f"issues/{number}/comments?per_page=100")
    require(isinstance(comments, list) and len(comments) < 100,
            "Incomplete review comments")
    receipts = []
    for comment in comments:
        user = comment["user"]
        if user["login"] != "chatgpt-codex-connector[bot]" or user["type"] != "Bot":
            continue
        if "<!-- codex-pull-request-review-summary -->" not in comment["body"]:
            continue
        matches = re.findall(r"<!-- codex-review-state:v1 (.+?) -->", comment["body"])
        if matches:
            require(len(matches) == 1, "Ambiguous Codex summary")
            receipts.append((comment["updated_at"], json.loads(matches[0])["code_review"]))
    require(bool(receipts), "No completed Codex summary")
    review = max(receipts, key=lambda entry: entry[0])[1]
    require(review["commit_sha"] == head and review["status"] == "completed"
            and review["has_any_findings"] is False
            and review["has_unresolved_findings"] is False, "Codex head is not clean")
    response = threads(number)
    require(response["pageInfo"]["hasNextPage"] is False
            and isinstance(response["nodes"], list) and len(response["nodes"]) <= 100
            and all(row["isResolved"] is True for row in response["nodes"]),
            "Unresolved or incomplete review threads")
    return max(receipts, key=lambda entry: entry[0]), response


def fast_receipt(pr, head, request, base_changes):
    endpoint = f"commits/{head}/check-runs?check_name={FAST}&filter=latest&per_page=100"
    response = request(REPOSITORY, endpoint)
    checks = response["check_runs"]
    require(type(response["total_count"]) is int and response["total_count"] == len(checks) == 1,
            "Missing or ambiguous fast check")
    check = checks[0]
    require(check["name"] == FAST and check["head_sha"] == head
            and check["app"]["slug"] == "github-actions"
            and check["status"] == "completed" and check["conclusion"] == "success",
            "Fast check is not successful exact-head Actions evidence")
    link = re.fullmatch(
        r"https://github[.]com/opensoft/openRepoTools-code/actions/runs/([1-9]\d*)/job/([1-9]\d*)",
        check["details_url"], flags=re.ASCII)
    require(link is not None, "Unrecognized fast workflow identity")
    run_id, job_id = (int(value) for value in link.groups())
    require(type(check["id"]) is int and check["id"] == job_id, "Fast job identity differs")
    run = request(REPOSITORY, f"actions/runs/{run_id}")
    require(type(run["id"]) is int and run["id"] == run_id and run["event"] == "pull_request"
            and run["path"] == FAST_WORKFLOW and run["head_sha"] == head
            and run["head_branch"] == pr["head"]["ref"]
            and run["head_repository"]["full_name"] == REPOSITORY
            and run["check_suite_id"] == check["check_suite"]["id"]
            and type(run["run_attempt"]) is int and run["run_attempt"] >= 1
            and run["status"] == "completed" and run["conclusion"] == "success",
            "Fast run belongs to another workflow/head or is incomplete")
    associated = run["pull_requests"]
    require(isinstance(associated, list) and len(associated) == 1,
            "Fast run has no unique source PR")
    source = associated[0]
    api = "https://api.github.com/repos/" + REPOSITORY
    require(type(source["number"]) is int and source["number"] == pr["number"]
            and source["url"] == f"{api}/pulls/{pr['number']}"
            and source["head"]["sha"] == head
            and source["head"]["ref"] == pr["head"]["ref"]
            and source["head"]["repo"]["url"] == api
            and source["base"]["ref"] == "main"
            and source["base"]["sha"] == pr["base"]["sha"]
            and source["base"]["repo"]["url"] == api,
            "Fast run source association differs")
    history = base_changes(pr["number"])
    require(history["pageInfo"]["hasNextPage"] is False
            and isinstance(history["nodes"], list) and len(history["nodes"]) <= 100,
            "Incomplete base-change history")
    # Run PR associations are mutable. Its immutable creation time plus complete
    # retarget history proves the current base was already selected for this run.
    created = datetime.strptime(run["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    require(all(datetime.strptime(row["createdAt"], "%Y-%m-%dT%H:%M:%SZ") < created
                for row in history["nodes"]), "Fast run predates a base change")
    job = request(REPOSITORY, f"actions/jobs/{job_id}")
    require(type(job["id"]) is int and job["id"] == job_id
            and type(job["run_id"]) is int and job["run_id"] == run_id and job["head_sha"] == head
            and job["run_attempt"] == run["run_attempt"] and job["name"] == FAST
            and job["status"] == "completed" and job["conclusion"] == "success",
            "Fast job does not match the current successful run")
    require(run == request(REPOSITORY, f"actions/runs/{run_id}")
            and response == request(REPOSITORY, endpoint),
            "Fast run/check changed during verification")
    return response, run, job, history


def source_pr(head, main, root, request, threads, base_changes):
    associated = request(REPOSITORY, f"commits/{head}/pulls?per_page=100")
    require(isinstance(associated, list) and len(associated) < 100,
            "Incomplete source PR discovery")
    candidates = [pr for pr in associated if pr["state"] == "open"
                  and pr["head"]["sha"] == head
                  and pr["head"]["repo"]["full_name"] == REPOSITORY]
    require(len(candidates) == 1, "Source head has no unique open PR")
    number = candidates[0]["number"]
    require(type(number) is int and number > 0, "Invalid member number")
    pr = request(REPOSITORY, f"pulls/{number}")
    require(pr["number"] == number and pr["state"] == "open" and pr["draft"] is False,
            "Member is not open and ready")
    actual_head, branch = policy.side(pr, "head")
    base, base_ref = policy.side(pr, "base")
    require(actual_head == head and policy.source_branch(branch) and base_ref == "main"
            and base == main and policy.intended(pr["body"])
            and not re.search(r"(?m)^Depends-On:", pr["body"]),
            "Member scope/identity/topology is not the independent pilot")
    policy.git(root, "merge-base", "--is-ancestor", main, head)
    require(policy.regular_scope(root, main, head), "Member changes unsupported paths or modes")
    evidence = (fast_receipt(pr, head, request, base_changes),
                clean_review(number, head, request, threads))
    return pr, evidence


def verify_fast(env, event, root):
    require(env["GITHUB_REPOSITORY"] == REPOSITORY
            and env["GITHUB_EVENT_NAME"] == "pull_request"
            and event["action"] in {"opened", "synchronize", "reopened"},
            "Unsupported fast source event")
    tested = policy.sha(env["GITHUB_SHA"])
    require(policy.git(root, "rev-parse", "HEAD").decode().strip() == tested,
            "Fast checkout differs from the event")
    pr = event["pull_request"]
    base, head = policy.sha(pr["base"]["sha"]), policy.sha(pr["head"]["sha"])
    pair = policy.git(root, "show", "-s", "--format=%P", tested).decode().split()
    require(pair == [base, head], "Fast test-merge parents differ from event identities")
    policy.git(root, "diff", "--check", base, tested, "--")
    return {"tested": tested, "base": base, "head": head, "full_ci_required": True}


def verify_candidate(env, event, root, request=policy.github, threads=read_threads,
                     base_changes=read_base_changes):
    require(env["GITHUB_REPOSITORY"] == REPOSITORY and env["GITHUB_EVENT_NAME"] == "push"
            and env["GITHUB_ACTOR"] == "mergify[bot]"
            and event["sender"]["login"] == "mergify[bot]"
            and event["repository"]["full_name"] == REPOSITORY
            and event["deleted"] is False and event["forced"] is False,
            "Not a genuine supported queue push")
    ref, candidate = env["GITHUB_REF"], policy.sha(env["GITHUB_SHA"])
    require(isinstance(ref, str) and ref.startswith("refs/heads/"),
            "Unrecognized candidate ref")
    branch = ref[len("refs/heads/"):]
    require(policy.QUEUE.fullmatch(branch) is not None and event["ref"] == ref
            and policy.sha(event["after"]) == candidate, "Candidate event/ref mismatch")
    main = policy.sha(policy.git(root, "rev-parse", "HEAD").decode().strip())
    require(policy.sha(request(REPOSITORY, "git/ref/heads/main")["object"]["sha"]) == main,
            "Trusted main moved")
    endpoint = "git/ref/heads/" + branch
    require(policy.sha(request(REPOSITORY, endpoint)["object"]["sha"]) == candidate,
            "Queue ref changed")
    chain, current = [], candidate
    for _ in range(2):
        if current == main:
            break
        pair = policy.git(root, "show", "-s", "--format=%P", current).decode().split()
        require(len(pair) == 2, "Candidate is not a bounded merge chain")
        previous, head = (policy.sha(value) for value in pair)
        chain.append((previous, head, current))
        current = previous
    require(current == main and 1 <= len(chain) <= 2, "Candidate is not rooted at current main")
    require(policy.regular_scope(root, main, candidate), "Combined candidate is outside scope")
    members, snapshots, seen_heads = [], [], set()
    for previous, head, prefix in reversed(chain):
        require(head not in seen_heads, "Duplicate source head")
        for other in seen_heads:
            require(policy.git(root, "merge-base", "--all", other, head).decode().split() == [main],
                    "Source members share non-main history")
        seen_heads.add(head)
        pr, evidence = source_pr(head, main, root, request, threads, base_changes)
        require(pr["number"] not in [row["number"] for row in members], "Duplicate source member")
        expected = policy.sha(policy.git(
            root, "merge-tree", "--write-tree", previous, head).decode().strip())
        tree = policy.sha(policy.git(root, "rev-parse", prefix + "^{tree}").decode().strip())
        require(expected == tree and policy.regular_scope(root, previous, prefix),
                "Candidate prefix is not the expected clean scoped merge")
        members.append({"number": pr["number"], "head": head, "prefix": prefix, "tree": tree,
                        "delivery": delivery_intended(pr["body"])})
        snapshots.append((pr, evidence))
    for pr, evidence in snapshots:
        require(policy.snapshot(pr) == policy.snapshot(
            request(REPOSITORY, f"pulls/{pr['number']}")), "Source changed during verification")
        require(evidence == (fast_receipt(pr, pr["head"]["sha"], request, base_changes),
                             clean_review(pr["number"], pr["head"]["sha"], request, threads)),
                "Source evidence changed during verification")
        require(policy.snapshot(pr) == policy.snapshot(
            request(REPOSITORY, f"pulls/{pr['number']}")), "Source changed during evidence recheck")
    require(policy.sha(request(REPOSITORY, endpoint)["object"]["sha"]) == candidate
            and policy.sha(request(REPOSITORY, "git/ref/heads/main")["object"]["sha"]) == main,
            "Candidate/main changed during verification")
    return {"verified": True, "full_ci_required": True, "base": main, "candidate": candidate,
            "tree": members[-1]["tree"], "members": members}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fast", "candidate"))
    parser.add_argument("--proof-kind", choices=("admission", "qualified"))
    parser.add_argument("--proof-output", type=Path)
    parser.add_argument("--require-delivery", action="store_true")
    args = parser.parse_args()
    mode = args.mode
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        result = (verify_fast(os.environ, event, Path.cwd()) if mode == "fast"
                  else verify_candidate(os.environ, event, Path(__file__).resolve().parents[2]))
        if args.require_delivery:
            require(mode == "candidate" and all(row["delivery"] is True for row in result["members"]),
                    "Member delivery intent is missing")
        if args.proof_kind or args.proof_output:
            require(mode == "candidate" and args.proof_kind and args.proof_output,
                    "Proof output requires a candidate phase and path")
            # Imported lazily to keep the existing standalone fast CLI unchanged.
            from delivery_evidence import make_record
            record = make_record(result, args.proof_kind, os.environ)
            args.proof_output.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    except Refused as error:
        parser.exit(1, f"Delivery verification refused: {error}.\n")
    except policy.ERRORS:
        parser.exit(1, "Delivery verification refused: incomplete, stale or unsupported evidence.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
