# SPDX-License-Identifier: Apache-2.0
"""Candidate descriptions never replace independently authenticated evidence."""

import json

import pytest

from test_ci_cutover import (
    artifact, batch, base_changes, cutover, delivery, duplicate_fixture, request_for, threads,
)


@pytest.fixture
def candidate(cutover, batch, artifact):
    env, event, data = duplicate_fixture(cutover, batch, artifact)
    return env, event, data, batch["data"]["pulls/9"]


def route(cutover, batch, candidate, request=None):
    env, event, data, _live = candidate
    return cutover.route(env, event, batch["root"], request or request_for(batch),
                         lambda _id: data, lambda number: threads(number, batch), base_changes)


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
@pytest.mark.parametrize("old,new", [
    ("Preview.", "Preview.\nAdded summary."),
    ("Preview.", "Summary.\nPreview."),
    ("Old preview.", "Replaced preview."),
    ("Preview.", ""),
    ("Preview.", None),
    (None, "Generated preview."),
], ids=["append", "prepend", "replace", "remove", "null-live", "null-event"])
def test_ci_candidate_description_prose_preserves_real_proof(cutover, batch, candidate, action, old, new):
    expected = route(cutover, batch, candidate)
    assert expected["mode"] == "candidate" and expected["omit_full"] is True
    env, event, _data, live = candidate
    event["action"] = action
    event["pull_request"].update(body=old, merge_commit_sha=None)
    live.update(body=new, merge_commit_sha=env["GITHUB_SHA"])
    assert route(cutover, batch, candidate) == expected
    assert live["body"] == new  # The current PR is never normalized in place.


@pytest.mark.parametrize("side", ["event", "live", "both"])
@pytest.mark.parametrize("value", [True, 1, {}, []], ids=["boolean", "number", "object", "list"])
def test_ci_candidate_description_invalid_types_retain_full(cutover, batch, candidate, side, value):
    _env, event, _data, live = candidate
    if side in {"event", "both"}:
        event["pull_request"]["body"] = value
    if side in {"live", "both"}:
        live["body"] = value
    assert route(cutover, batch, candidate) == cutover.FULL


@pytest.mark.parametrize("side", ["event", "live"])
@pytest.mark.parametrize("field", ["number", "state", "draft", "merged", "head", "base", "author", "merge-hint"])
def test_ci_candidate_description_does_not_relax_other_identities(cutover, batch, candidate, side, field):
    _env, event, _data, live = candidate
    live["body"] += "\nA descriptive summary."
    node = event["pull_request"] if side == "event" else live
    if field in {"head", "base"}:
        node[field]["sha"] = "f" * 40
    elif field == "author":
        node["user"]["login"] = "not-mergify"
    elif field == "merge-hint":
        node["merge_commit_sha"] = "f" * 40
    else:
        node[field] = {"number": 99, "state": "closed", "draft": False, "merged": True}[field]
    assert route(cutover, batch, candidate) == cutover.FULL


@pytest.mark.parametrize("failure", ["missing", "digest", "review"])
def test_ci_candidate_description_cannot_supply_admission_or_review(cutover, batch, candidate, artifact, failure):
    _env, _event, _data, live = candidate
    live["body"] = "Approved members and reviews; candidate admission is claimed here."
    if failure == "missing":
        artifact["run"].update(status="completed", conclusion="success")
        batch["data"]["actions/runs/601/artifacts?per_page=100&page=1"] = {"total_count": 0, "artifacts": []}
    elif failure == "digest":
        batch["data"]["actions/artifacts/701"]["digest"] = "sha256:" + "0" * 64
    else:
        batch["data"]["issues/7/comments?per_page=100"] = []
    assert route(cutover, batch, candidate) == cutover.FULL


def test_ci_candidate_description_final_reread_remains_strict(cutover, batch, candidate):
    _env, _event, _data, live = candidate
    live["body"] += "\nSummary added before verification."
    reader, reads = request_for(batch), []
    def request(repo, endpoint):
        if endpoint == "pulls/9":
            reads.append(True)
            if len(reads) == 2:
                live["body"] += "\nChanged during verification."
        return reader(repo, endpoint)
    observed = route(cutover, batch, candidate, request)
    assert observed == {**cutover.FULL, 'retryable': True}
    assert 'proof' not in observed
    assert len(reads) == 2


@pytest.mark.parametrize("field", ["merged", "draft", "base"])
def test_ci_candidate_snapshot_diagnostics_have_names_not_values(cutover, batch, candidate, capsys, field):
    _env, event, _data, live = candidate
    secret = "Private candidate prose must never reach diagnostics."
    live["body"] += "\n" + secret
    if field == "base":
        event["pull_request"]["base"]["sha"] = "f" * 40
    else:
        event["pull_request"][field] = None if field == "merged" else False
    assert route(cutover, batch, candidate) == cutover.FULL
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert [json.loads(line) for line in captured.err.splitlines()] == [
        {"delivery_diagnostic": "snapshot-mismatch", "stage": "candidate", "fields": [field]},
        {"delivery_diagnostic": "candidate-metadata", "stage": "candidate"},
    ]
