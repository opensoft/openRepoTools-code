# SPDX-License-Identifier: Apache-2.0
"""Offline local-review authentication; no live receipts or queue operations."""

from __future__ import annotations

import copy
import json
import subprocess

import pytest

from conftest import REPO
from test_ci_delivery import batch, delivery, request_for, threads, verify as verify_hosted

MARKER = "<!-- openrepotools-local-review:v1 -->"
REPO_NAME = "opensoft/openRepoTools-code"
PERMISSION = "collaborators/reviewer/permission"


def body(record):
    return MARKER + "\n```json\n" + json.dumps(record) + "\n```"


def install_local(batch, number=7, *, hosted=False):
    record = {"schema_version": 1, "repository": REPO_NAME, "pull_request": number,
              "head_sha": batch["prs"][number]["head"]["sha"], "base_sha": batch["base"],
              "reviewer": "codex-local", "skill": "pre-pr-review", "status": "accepted",
              "unresolved_findings": 0, "findings": "No actionable findings remain.",
              "resolution": "All reproduced issues fixed and re-reviewed.",
              "validation": "Canonical focused regression suite passed."}
    comment = {"id": 1000 + number, "user": {"login": "reviewer", "id": 42, "type": "User"},
               "created_at": "2026-11-11T00:01:00Z", "updated_at": "2026-11-11T00:01:00Z",
               "issue_url": f"https://api.github.com/repos/{REPO_NAME}/issues/{number}",
               "html_url": f"https://github.com/{REPO_NAME}/pull/{number}#issuecomment-{1000+number}",
               "body": body(record)}
    endpoint = f"issues/{number}/comments?per_page=100"
    if hosted:
        for index, previous in enumerate(batch["data"][endpoint]):
            previous["id"] = 2000 + number + index
    batch["data"][endpoint] = (batch["data"][endpoint] if hosted else []) + [comment]
    batch["data"][PERMISSION] = {"permission": "write", "role_name": "maintain",
                                 "user": copy.deepcopy(comment["user"])}
    return record, comment


def local_threads(batch, number):
    return dict(threads(number), comments={"pageInfo": {"hasNextPage": False}, "nodes": [
        {"databaseId": row.get("id", 2000 + number), "lastEditedAt": None, "body": row["body"]}
        for row in batch["data"][f"issues/{number}/comments?per_page=100"]]})


def verify(delivery, batch, request=None, read_threads=None):
    return verify_hosted(delivery, batch, request,
                         read_threads or (lambda number: local_threads(batch, number)))


def read_review(delivery, batch, request=None, read_threads=None):
    return delivery.clean_review(7, batch["heads"][0], request or request_for(batch),
                                 read_threads or (lambda number: local_threads(batch, number)),
                                 base=batch["base"])


@pytest.mark.parametrize("both_local", [False, True])
def test_ci_local_review_qualifies_mixed_or_local_only_real_candidate(delivery, batch, both_local):
    install_local(batch)
    if both_local:
        install_local(batch, 8)
    proof = verify(delivery, batch)
    assert proof["verified"] is True and proof["full_ci_required"] is True
    assert [row["head"] for row in proof["members"]] == batch["heads"]


@pytest.mark.parametrize("skill", ["pre-pr-review", "pr-review", "branch-or-pr-review"])
@pytest.mark.parametrize("permission", ["write", "admin"])
def test_ci_local_review_accepts_current_writer_and_supported_skills(delivery, batch, skill, permission):
    record, comment = install_local(batch)
    record["skill"] = skill
    comment["body"] = body(record)
    batch["data"][PERMISSION]["permission"] = permission
    receipt, response = read_review(delivery, batch)
    assert receipt["kind"] == "local-codex-review"
    assert receipt["comment_id"] == comment["id"]
    assert receipt["author_id"] == 42
    assert "body" not in receipt and "findings" not in receipt
    assert response == threads(7)


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", True), ("repository", "fork/project"),
    ("pull_request", 8), ("pull_request", True), ("head_sha", "a" * 40),
    ("base_sha", "b" * 40), ("reviewer", "chatgpt-codex-connector[bot]"),
    ("skill", "unknown"), ("status", "revoked"), ("status", "pending"),
    ("unresolved_findings", 1), ("unresolved_findings", False),
    ("findings", ""), ("findings", " " * 10), ("resolution", None),
    ("validation", []), ("findings", "x" * 4001), ("validation", "x" + " " * 4000),
    ("unexpected", "extra"),
])
def test_ci_local_review_wrong_or_incomplete_record_refuses(delivery, batch, field, value):
    record, comment = install_local(batch, hosted=True)
    record[field] = value
    comment["body"] = body(record)
    with pytest.raises(ValueError):
        read_review(delivery, batch)


@pytest.mark.parametrize("failure", [
    "edited", "wrong-issue", "wrong-permalink", "boolean-id", "bad-author-id",
    "author-id-mismatch", "author-login-mismatch", "bad-login", "bad-created",
    "duplicate-key", "missing-key", "non-object", "quoted", "two-records", "v2", "oversized",
    "comment-cap", "local-cap", "duplicate-id",
])
def test_ci_local_review_forged_edited_malformed_or_saturated_evidence_refuses(delivery, batch, failure):
    record, comment = install_local(batch, hosted=True)
    data = batch["data"]
    if failure == "edited":
        comment["updated_at"] = "2026-11-11T00:02:00Z"
    elif failure == "wrong-issue":
        comment["issue_url"] = comment["issue_url"].replace("issues/7", "issues/8")
    elif failure == "wrong-permalink":
        comment["html_url"] += "wrong"
    elif failure == "boolean-id":
        comment["id"] = True
    elif failure == "bad-author-id":
        comment["user"]["id"] = True
    elif failure == "author-id-mismatch":
        data[PERMISSION]["user"]["id"] = 43
    elif failure == "author-login-mismatch":
        data[PERMISSION]["user"]["login"] = "someone-else"
    elif failure == "bad-login":
        comment["user"]["login"] = "../other"
    elif failure == "bad-created":
        comment["created_at"] = comment["updated_at"] = "tomorrow"
    elif failure == "duplicate-key":
        comment["body"] = comment["body"].replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    elif failure == "missing-key":
        del record["validation"]
        comment["body"] = body(record)
    elif failure == "non-object":
        comment["body"] = body([])
    elif failure == "quoted":
        comment["body"] = "Example only:\n" + comment["body"]
    elif failure == "two-records":
        comment["body"] += "\n" + body(record)
    elif failure == "v2":
        comment["body"] = comment["body"].replace(":v1", ":v2")
    elif failure == "oversized":
        comment["body"] += "x" * 16385
    elif failure == "comment-cap":
        data["issues/7/comments?per_page=100"] = [copy.deepcopy(comment) for _ in range(100)]
    elif failure == "local-cap":
        data["issues/7/comments?per_page=100"] = [copy.deepcopy(comment) for _ in range(11)]
    elif failure == "duplicate-id":
        data["issues/7/comments?per_page=100"].append(copy.deepcopy(comment))
    with pytest.raises((ValueError, KeyError)):
        read_review(delivery, batch)


@pytest.mark.parametrize("kind", ["Bot", "Organization", "read", "none"])
def test_ci_local_review_untrusted_lookalike_cannot_authorize_or_replace_hosted(delivery, batch, kind):
    _record, comment = install_local(batch)
    if kind in {"read", "none"}:
        batch["data"][PERMISSION]["permission"] = kind
    else:
        comment["user"]["type"] = kind
    with pytest.raises(ValueError):
        read_review(delivery, batch)
    # A non-writer/bot lookalike is not a local veto over genuine hosted review.
    hosted = copy.deepcopy(install_hosted_comment(batch))
    batch["data"]["issues/7/comments?per_page=100"].insert(0, hosted)
    assert read_review(delivery, batch)


def install_hosted_comment(batch):
    review = {"code_review": {"commit_sha": batch["heads"][0], "status": "completed",
                             "has_any_findings": False, "has_unresolved_findings": False}}
    return {"id": 2007, "user": {"login": "chatgpt-codex-connector[bot]", "type": "Bot"},
            "updated_at": "2026-11-11T00:00:00Z",
            "body": "<!-- codex-pull-request-review-summary -->\n"
                    "<!-- codex-review-state:v1 " + json.dumps(review) + " -->"}


def test_ci_local_review_newest_server_order_controls_not_list_order(delivery, batch):
    record, old = install_local(batch, hosted=True)
    newer = copy.deepcopy(old)
    newer["id"] += 1
    newer["html_url"] = newer["html_url"].replace("1007", "1008")
    record["status"] = "revoked"
    newer["body"] = body(record)
    batch["data"]["issues/7/comments?per_page=100"].insert(0, newer)
    with pytest.raises(ValueError):
        read_review(delivery, batch)
    # A new acceptance, not an edit, can supersede that revocation.
    accepted = copy.deepcopy(old)
    accepted["created_at"] = accepted["updated_at"] = "2026-11-11T00:02:00Z"
    accepted["id"] += 2
    accepted["html_url"] = accepted["html_url"].replace("1007", "1009")
    batch["data"]["issues/7/comments?per_page=100"].insert(0, accepted)
    assert read_review(delivery, batch)[0]["comment_id"] == 1009


@pytest.mark.parametrize("failure", ["edited", "deleted", "replaced", "permission", "api", "thread"])
def test_ci_local_review_live_candidate_rechecks_receipt_access_and_threads(delivery, batch, failure):
    record, comment = install_local(batch)
    original = request_for(batch)
    reads = 0
    def request(repo, endpoint):
        nonlocal reads
        if endpoint == "pulls/8":
            reads += 1
            if failure == "edited":
                comment["updated_at"] = "2026-11-11T00:03:00Z"
            elif failure == "deleted":
                batch["data"]["issues/7/comments?per_page=100"] = []
            elif failure == "replaced":
                record["validation"] = "New results"
                comment["body"] = body(record)
            elif failure == "permission":
                batch["data"][PERMISSION]["permission"] = "read"
        if endpoint == PERMISSION and failure == "api":
            raise subprocess.TimeoutExpired("gh", 15)
        return original(repo, endpoint)
    def live_threads(number):
        result = local_threads(batch, number)
        if reads and number == 7 and failure == "thread":
            result["nodes"] = [{"isResolved": False}]
        return result
    with pytest.raises((ValueError, subprocess.SubprocessError)):
        verify(delivery, batch, request, live_threads)


@pytest.mark.parametrize("failure", ["same-second-edit", "truncated", "missing", "duplicate", "wrong-id"])
def test_ci_local_review_graphql_edit_evidence_must_be_complete_and_unedited(delivery, batch, failure):
    install_local(batch)
    def edited(number):
        response = local_threads(batch, number)
        node = response["comments"]["nodes"][0]
        if failure == "same-second-edit":
            node["lastEditedAt"] = "2026-11-11T00:01:00Z"
        elif failure == "truncated":
            response["comments"]["pageInfo"]["hasNextPage"] = True
        elif failure == "missing":
            del response["comments"]
        elif failure == "duplicate":
            response["comments"]["nodes"].append(copy.deepcopy(node))
        else:
            node["databaseId"] += 1
        return response
    with pytest.raises((ValueError, KeyError)):
        read_review(delivery, batch, read_threads=edited)


def test_ci_local_review_permission_is_cached_only_within_one_live_read(delivery, batch):
    record, comment = install_local(batch)
    other = copy.deepcopy(comment)
    other["id"] += 1
    other["html_url"] = other["html_url"].replace("1007", "1008")
    batch["data"]["issues/7/comments?per_page=100"].append(other)
    original, reads = request_for(batch), []
    def request(repo, endpoint):
        reads.append(endpoint)
        return original(repo, endpoint)
    assert read_review(delivery, batch, request)[0]["comment_id"] == 1008
    assert reads.count(PERMISSION) == 1
    batch["data"][PERMISSION]["permission"] = "read"
    with pytest.raises(ValueError):
        read_review(delivery, batch, request)
    assert reads.count(PERMISSION) == 2


def test_ci_local_review_final_read_refuses_same_count_replaced_comment_history(delivery, batch):
    install_local(batch, hosted=True)
    reads = 0
    def read(number):
        nonlocal reads
        result = local_threads(batch, number)
        if number == 7:
            reads += 1
            if reads > 1:
                # An unrelated comment disappears while a newer revocation is
                # posted between REST and GraphQL. Counts and selected receipt
                # still match, but the complete histories no longer do.
                result["comments"]["nodes"][0]["databaseId"] = 9007
        return result
    with pytest.raises(ValueError, match="comment history"):
        verify(delivery, batch, read_threads=read)


def test_ci_local_review_final_read_refuses_same_id_ordinary_comment_edited_to_receipt(delivery, batch):
    record, accepted = install_local(batch)
    ordinary = copy.deepcopy(accepted)
    ordinary.update(id=1008, body="An ordinary comment, not review acceptance.",
                    created_at="2026-11-11T00:02:00Z", updated_at="2026-11-11T00:02:00Z")
    batch["data"]["issues/7/comments?per_page=100"].append(ordinary)
    record["status"] = "revoked"
    reads = 0
    def read(number):
        nonlocal reads
        result = local_threads(batch, number)
        if number == 7:
            reads += 1
            if reads > 1:
                result["comments"]["nodes"][1].update(
                    body=body(record), lastEditedAt="2026-11-11T00:02:00Z")
        return result
    with pytest.raises(ValueError, match="comment history"):
        verify(delivery, batch, read_threads=read)


def test_ci_local_review_hosted_fallback_cannot_hide_new_local_decision(delivery, batch):
    reads = 0
    def read(number):
        nonlocal reads
        result = local_threads(batch, number)
        if number == 7:
            reads += 1
            if reads > 1:
                result["comments"]["nodes"].append({
                    "databaseId": 9007, "lastEditedAt": None,
                    "body": MARKER + " new revocation arrived after REST"})
        return result
    with pytest.raises(ValueError, match="comment history"):
        verify(delivery, batch, read_threads=read)


def test_ci_local_review_read_threads_requests_complete_edit_metadata(delivery, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert "comments(first:100)" in args[-1] and "databaseId lastEditedAt" in args[-1]
        payload = {"data": {"repository": {"pullRequest": {
            "reviewThreads": threads(7), "comments": {"pageInfo": {"hasNextPage": False},
                                                       "nodes": []}}}}}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload).encode())
    monkeypatch.setattr(delivery.subprocess, "run", run)
    assert delivery.read_threads(7) == dict(threads(7), comments={
        "pageInfo": {"hasNextPage": False}, "nodes": []})
    assert calls[0][1]["timeout"] == 15 and calls[0][1]["check"] is True


@pytest.mark.parametrize("response", [
    {"pageInfo": {"hasNextPage": True}, "nodes": []},
    {"pageInfo": {"hasNextPage": False}, "nodes": [{"isResolved": False}]},
])
def test_ci_local_review_cannot_replace_unresolved_or_incomplete_threads(delivery, batch, response):
    install_local(batch)
    def read(number):
        return dict(local_threads(batch, number), **response)
    with pytest.raises(ValueError):
        read_review(delivery, batch, read_threads=read)


def test_ci_local_review_preparation_keeps_flag_jobs_and_queue_unchanged():
    assert json.loads((REPO / ".github/ci/delivery-policy.json").read_text())["enabled"] is False
    # No new write-capable workflow or custom success check accompanies the reader.
    text = (REPO / ".github/ci/delivery_verify.py").read_text()
    assert '"-X", "POST"' not in text and '"-X", "PATCH"' not in text
