# SPDX-License-Identifier: Apache-2.0
"""Trusted-main observations only: never a skip, admission or review receipt.

Ported proof patterns: OpenBenches stack-ci.py and project-stack-ci.py.
Candidate/run receipts are deliberately NOT implemented by this shadow stage.
Only read APIs and local Git objects are inspected; no ref, status or lane writes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY = "opensoft/openRepoTools-code"
SCOPE = {"claude-current": "100755", "tests/test_claude_current.py": "100644"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
QUEUE = re.compile(r"mergify/merge-queue/[0-9a-f]{10}\Z")
OPEN_ACTIONS = {"opened", "reopened", "synchronize", "edited", "labeled",
                "unlabeled", "ready_for_review"}
ERRORS = (KeyError, TypeError, ValueError, AttributeError, OSError,
          UnicodeError, subprocess.SubprocessError)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=20).stdout


def github(repo, endpoint):
    data = subprocess.run(["gh", "api", "--hostname", "github.com",
                           f"repos/{repo}/{endpoint}"], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=15).stdout
    return json.loads(data)


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid commit identity")
    return value


def valid_branch(value):
    return (isinstance(value, str) and bool(BRANCH.fullmatch(value))
            and ".." not in value and all(
                part and not part.startswith(".") and not part.endswith((".", ".lock"))
                for part in value.split("/")))


def side(pr, name):
    value = pr[name]
    if (value["repo"]["full_name"].lower() != REPOSITORY.lower()
            or not valid_branch(value["ref"])):
        raise ValueError("Foreign or invalid branch")
    return sha(value["sha"]), value["ref"]


def snapshot(pr):
    return (pr["number"], pr["state"], pr["draft"], pr.get("merged"),
            pr.get("body"), pr.get("merge_commit_sha"), side(pr, "head"), side(pr, "base"),
            pr["user"]["login"])


def intended(text):
    if not isinstance(text, str):
        return False
    lines = re.findall(r"(?m)^CI-Shadow:[^\n]*", text)
    return [line.rstrip(" \t\r") for line in lines] == ["CI-Shadow: claude-current"]


def regular_scope(root, base, head):
    """Modified allowlisted regular files only; no renames, additions or modes."""
    raw = git(root, "diff", "--raw", "--no-abbrev", "--no-renames", "-z", base, head, "--")
    fields = raw.split(b"\0")
    if fields[-1] != b"" or len(fields) < 3 or len(fields) % 2 != 1:
        return False
    for header, path in zip(fields[:-1:2], fields[1:-1:2]):
        if not header.startswith(b":"):
            return False
        old, new, _old_blob, _new_blob, status = header[1:].decode("ascii").split()
        name = path.decode("utf-8")
        if name not in SCOPE or status != "M" or old != new or new != SCOPE[name]:
            return False
    return True


def source_branch(ref):
    return not ref.startswith(("release/", "verify/", "mergify/")) and ref != "main"


def pr_observation(event, root, main, request):
    number = event["number"]
    if type(number) is not int or number < 1:
        raise ValueError("Invalid PR number")
    expected = event["pull_request"]
    pr = request(REPOSITORY, f"pulls/{number}")
    if (type(pr["number"]) is not int or type(expected["number"]) is not int
            or pr["number"] != number or expected["number"] != number):
        raise ValueError("PR identity changed")
    head, branch = side(pr, "head")
    base, base_ref = side(pr, "base")
    if side(expected, "head") != (head, branch):
        raise ValueError("Source head changed")
    side(expected, "base")  # Validate origin/format even for a stale merged base.
    scope, observation, reason = "full", "full-fallback", "pr-not-qualified"
    if QUEUE.fullmatch(branch):
        # A bot/prefix is NOT membership, review or heavy-integration evidence.
        reason, observation = "candidate-proof-required", "candidate-shaped-pr"
    elif (event["action"] == "edited" and pr["state"] == "closed"
          and pr["merged"] is True and pr["draft"] is False):
        if base_ref == "main" and source_branch(branch) and intended(pr["body"]):
            merge = sha(pr["merge_commit_sha"])
            pair = git(root, "show", "-s", "--format=%P", merge).decode().split()
            git(root, "merge-base", "--is-ancestor", merge, main)
            if len(pair) == 2 and pair[1] == head and regular_scope(root, sha(pair[0]), merge):
                scope, observation, reason = (
                    "claude-current", "merged-scoped-metadata", "same-head-merged-content")
    elif (event["action"] in OPEN_ACTIONS and pr["state"] == "open"
          and pr["draft"] is False and expected["state"] == "open"
          and expected["draft"] is False and side(expected, "base") == (base, base_ref)
          and expected.get("body") == pr.get("body")
          and source_branch(branch) and base_ref == "main" and base == main
          and intended(pr["body"])):
        git(root, "merge-base", "--is-ancestor", main, head)
        if regular_scope(root, base, head):
            scope, observation, reason = "claude-current", "scoped-pr", "live-scoped-content"
    if snapshot(pr) != snapshot(request(REPOSITORY, f"pulls/{number}")):
        raise ValueError("PR changed during observation")
    return scope, observation, reason, head, base


def push_observation(env, event, root, main, request):
    ref, head = event["ref"], sha(event["after"])
    if (event["repository"]["full_name"].lower() != REPOSITORY.lower()
            or event["deleted"] is not False or event["forced"] is not False
            or ref != env["GITHUB_REF"] or head != sha(env["GITHUB_SHA"])
            or not isinstance(ref, str) or not ref.startswith("refs/heads/")):
        raise ValueError("Unverified push identity")
    branch = ref[len("refs/heads/"):]
    if not valid_branch(branch):
        raise ValueError("Invalid branch")
    if branch == "main":
        return "full", "main-push", "landing-proof-required", head, sha(event["before"])
    if QUEUE.fullmatch(branch):
        return "full", "candidate-shaped-push", "candidate-proof-required", head, main
    if not source_branch(branch):
        return "full", "full-fallback", "unsupported-source-branch", head, main
    endpoint = "git/ref/heads/" + branch
    if sha(request(REPOSITORY, endpoint)["object"]["sha"]) != head:
        raise ValueError("Branch changed")
    git(root, "merge-base", "--is-ancestor", main, head)
    message = git(root, "show", "-s", "--format=%B", head).decode("utf-8")
    scoped = intended(message) and regular_scope(root, main, head)
    if sha(request(REPOSITORY, endpoint)["object"]["sha"]) != head:
        raise ValueError("Branch changed during observation")
    return ("claude-current", "scoped-source-push", "live-scoped-content", head, main) if scoped else (
        "full", "full-fallback", "source-not-qualified", head, main)


def classify(env, event, root, request=github):
    result = {"mode": "shadow", "required_ci": "full", "skip_ci": False,
              "queue_admission": False, "candidate_scope": "full",
              "observation": "full-fallback", "reason": "unsupported-event",
              "policy_sha": None, "main": None, "head": None, "base": None}
    try:
        if env.get("GITHUB_REPOSITORY") != REPOSITORY or not isinstance(event, dict):
            return result
        policy = sha(git(root, "rev-parse", "HEAD").decode().strip())
        result["policy_sha"] = policy
        main = sha(request(REPOSITORY, "git/ref/heads/main")["object"]["sha"])
        result["main"] = main
        if main != policy:
            result["reason"] = "policy-main-moved"
            return result
        if env.get("GITHUB_EVENT_NAME") == "pull_request":
            observation = pr_observation(event, root, main, request)
        elif env.get("GITHUB_EVENT_NAME") == "push":
            observation = push_observation(env, event, root, main, request)
        else:
            return result
        if sha(request(REPOSITORY, "git/ref/heads/main")["object"]["sha"]) != main:
            result["reason"] = "main-moved-during-observation"
            return result
        (result["candidate_scope"], result["observation"], result["reason"],
         result["head"], result["base"]) = observation
    except ERRORS:
        result["reason"] = "unreadable-or-stale-context"
    return result


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        event = {}
    result = classify(os.environ, event, Path.cwd())
    print(json.dumps(result, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("### Trusted shadow classifier\n\n"
                         f"Observation: `{result['observation']}`; "
                         f"scope: `{result['candidate_scope']}`; reason: `{result['reason']}`.\n\n"
                         "Full CI remains required. Skips: **no**. Queue admission: **no**.\n")


if __name__ == "__main__":
    main()
