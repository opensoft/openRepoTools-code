# SPDX-License-Identifier: Apache-2.0
"""Fresh observations may wait; changing snapshots never supply accepted proof."""

import json

import pytest

from test_ci_candidate_metadata import candidate, route
from test_ci_cutover import artifact, batch, cutover, delivery, request_for


def test_ci_candidate_stability_body_race_waits_without_proof_then_revalidates(cutover, batch, candidate):
    expected = route(cutover, batch, candidate)
    assert expected['mode'] == 'candidate' and expected['omit_full'] is True
    _env, _event, _data, live = candidate
    reader, reads = request_for(batch), []

    def request(repo, endpoint):
        if endpoint == 'pulls/9':
            reads.append(True)
            if len(reads) == 2:
                live['body'] += '\nSummary arrived during verification.'
                live['updated_at'] = '2026-11-14T02:51:19Z'
        return reader(repo, endpoint)

    observed = route(cutover, batch, candidate, request)
    assert observed == {**cutover.FULL, 'retryable': True}
    assert 'proof' not in observed and len(reads) == 2
    # A separate observation revalidates the real artifact/sources and strict
    # current rereads. The original event is not rewritten or manufactured.
    assert route(cutover, batch, candidate) == expected


def candidate_gate_fixture(cutover, monkeypatch, results):
    proof = {'mode': 'candidate', 'omit_full': True, 'proof': 'a' * 64}
    calls, sleeps = [], []

    def observe(*_args, **_kwargs):
        calls.append(True)
        return results.pop(0) if len(results) > 1 else dict(results[0])

    monkeypatch.setattr(cutover, 'route', observe)
    monkeypatch.setattr(cutover.time, 'sleep', sleeps.append)
    env = {'OMIT_FULL': 'true', 'ROUTE_MODE': proof['mode'], 'ROUTE_PROOF': proof['proof']}
    return proof, env, calls, sleeps


def test_ci_candidate_stability_gate_reobserves_original_proof(cutover, monkeypatch, tmp_path):
    proof = {'mode': 'candidate', 'omit_full': True, 'proof': 'a' * 64}
    _proof, env, calls, sleeps = candidate_gate_fixture(
        cutover, monkeypatch, [{**cutover.FULL, 'retryable': True}, proof])
    cutover.gate(env, {}, tmp_path)
    assert len(calls) == 2 and sleeps == [10]


def test_ci_candidate_stability_gate_cannot_substitute_changed_proof(cutover, monkeypatch, tmp_path):
    changed = {'mode': 'candidate', 'omit_full': True, 'proof': 'b' * 64}
    _proof, env, calls, sleeps = candidate_gate_fixture(
        cutover, monkeypatch, [{**cutover.FULL, 'retryable': True}, changed])
    with pytest.raises(cutover.verifier.Refused, match='Omitted-work proof no longer verifies'):
        cutover.gate(env, {}, tmp_path)
    assert len(calls) == 2 and sleeps == [10]


def test_ci_candidate_stability_gate_exhaustion_refuses_with_same_bound(cutover, monkeypatch, tmp_path):
    monkeypatch.setattr(cutover, 'PENDING_ATTEMPTS', 2)
    _proof, env, calls, sleeps = candidate_gate_fixture(
        cutover, monkeypatch, [{**cutover.FULL, 'retryable': True}])
    with pytest.raises(cutover.verifier.Refused, match='Omitted-work proof no longer verifies'):
        cutover.gate(env, {}, tmp_path)
    assert len(calls) == 3 and sleeps == [10, 10]


@pytest.mark.parametrize('change', ['metadata', 'queued-to-running', 'running-to-completed'])
def test_ci_candidate_stability_valid_caller_movement_needs_fresh_observation(cutover, batch, candidate, change):
    caller = batch['data']['actions/runs/601']
    caller.update(status='queued' if change == 'queued-to-running' else 'in_progress', conclusion=None)
    expected = route(cutover, batch, candidate)
    assert expected['mode'] == 'candidate'
    reader, reads = request_for(batch), []

    def request(repo, endpoint):
        if endpoint == 'actions/runs/601':
            reads.append(True)
            if len(reads) == 3:
                caller['updated_at'] = '2026-11-14T02:51:19Z'
                if change == 'queued-to-running':
                    caller['status'] = 'in_progress'
                elif change == 'running-to-completed':
                    caller.update(status='completed', conclusion='success')
        return reader(repo, endpoint)

    assert route(cutover, batch, candidate, request) == {**cutover.FULL, 'retryable': True}
    assert len(reads) == 3  # The strict artifact reread already passed on read two.
    assert route(cutover, batch, candidate) == expected


@pytest.mark.parametrize('field', ['number', 'state', 'draft', 'merged', 'head', 'base',
                                  'author', 'body-type', 'merge-hint'])
def test_ci_candidate_stability_invalid_final_pr_never_waits(cutover, batch, candidate, field):
    _env, _event, _data, live = candidate
    reader, reads = request_for(batch), []

    def request(repo, endpoint):
        if endpoint == 'pulls/9':
            reads.append(True)
            if len(reads) == 2:
                live['body'] += '\nDescriptive movement does not hide identity failure.'
                if field in {'head', 'base'}:
                    live[field]['sha'] = 'f' * 40
                elif field == 'author':
                    live['user']['login'] = 'not-mergify'
                elif field == 'body-type':
                    live['body'] = []
                elif field == 'merge-hint':
                    live['merge_commit_sha'] = 'f' * 40
                else:
                    live[field] = {'number': 99, 'state': 'closed', 'draft': False, 'merged': True}[field]
        return reader(repo, endpoint)

    assert route(cutover, batch, candidate, request) == cutover.FULL
    assert len(reads) == 2


def test_ci_candidate_stability_changed_branch_never_waits(cutover, batch, candidate):
    _env, _event, _data, live = candidate
    branch = 'git/ref/heads/' + live['head']['ref']
    reader, reads = request_for(batch), []

    def request(repo, endpoint):
        if endpoint == 'pulls/9':
            reads.append(True)
            if len(reads) == 2:
                live['body'] += '\nSummary movement.'
        if endpoint == branch:
            batch['data'][branch]['object']['sha'] = 'f' * 40
        return reader(repo, endpoint)

    assert route(cutover, batch, candidate, request) == cutover.FULL
    assert len(reads) == 2


@pytest.mark.parametrize('change', ['failed', 'cancelled', 'rerun', 'actor', 'head',
                                   'id', 'path', 'repository', 'unknown-status'])
def test_ci_candidate_stability_invalid_final_caller_never_waits(cutover, batch, candidate, change):
    _env, _event, _data, live = candidate
    caller, reader, reads = batch['data']['actions/runs/601'], request_for(batch), []
    candidate_reads = []

    def request(repo, endpoint):
        if endpoint == 'pulls/9':
            candidate_reads.append(True)
            if len(candidate_reads) == 2:
                live['body'] += '\nMetadata movement cannot hide a bad caller.'
        if endpoint == 'actions/runs/601':
            reads.append(True)
            if len(reads) == 3:
                if change in {'failed', 'cancelled'}:
                    caller.update(status='completed', conclusion='failure' if change == 'failed' else 'cancelled')
                elif change == 'rerun':
                    caller['run_attempt'] = 2
                elif change == 'actor':
                    caller['actor']['login'] = 'not-mergify'
                elif change == 'head':
                    caller['head_sha'] = 'f' * 40
                elif change == 'id':
                    caller['id'] = 902
                elif change == 'path':
                    caller['path'] = '.github/workflows/untrusted.yml'
                elif change == 'repository':
                    caller['repository']['id'] = 1
                else:
                    caller['status'] = 'unknown'
        return reader(repo, endpoint)

    assert route(cutover, batch, candidate, request) == cutover.FULL
    assert len(reads) == 3 and len(candidate_reads) == 2


@pytest.mark.parametrize('failure', ['admission', 'review'])
def test_ci_candidate_stability_next_observation_rechecks_real_proof(cutover, batch, candidate, failure):
    _env, _event, _data, live = candidate
    reader, reads = request_for(batch), []

    def request(repo, endpoint):
        if endpoint == 'pulls/9':
            reads.append(True)
            if len(reads) == 2:
                live['body'] += '\nSummary movement.'
        return reader(repo, endpoint)

    assert route(cutover, batch, candidate, request) == {**cutover.FULL, 'retryable': True}
    if failure == 'admission':
        batch['data']['actions/artifacts/701']['digest'] = 'sha256:' + '0' * 64
    else:
        batch['data']['issues/7/comments?per_page=100'] = []
    assert route(cutover, batch, candidate) == cutover.FULL


@pytest.mark.parametrize('field', ['pull_request', 'caller'])
def test_ci_candidate_stability_pending_diagnostics_never_include_values(cutover, batch, candidate, capsys, field):
    _env, _event, _data, live = candidate
    secret = 'Private descriptive movement must never be logged.'
    caller, reader, reads = batch['data']['actions/runs/601'], request_for(batch), []

    def request(repo, endpoint):
        target = 'pulls/9' if field == 'pull_request' else 'actions/runs/601'
        if endpoint == target:
            reads.append(True)
            if len(reads) == (2 if field == 'pull_request' else 3):
                if field == 'pull_request':
                    live['body'] += '\n' + secret
                else:
                    caller['display_title'] = secret
        return reader(repo, endpoint)

    assert route(cutover, batch, candidate, request) == {**cutover.FULL, 'retryable': True}
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert [json.loads(line) for line in captured.err.splitlines()] == [{
        'delivery_diagnostic': 'candidate-reread-pending', 'stage': 'candidate', 'fields': [field]}]


def test_ci_candidate_stability_source_gate_does_not_gain_retry(cutover, monkeypatch, tmp_path):
    source = {'mode': 'source', 'omit_full': True, 'proof': 'a' * 64}
    _proof, env, calls, sleeps = candidate_gate_fixture(
        cutover, monkeypatch, [{**cutover.FULL, 'retryable': True}, source])
    env['ROUTE_MODE'] = 'source'
    with pytest.raises(cutover.verifier.Refused, match='Omitted-work proof no longer verifies'):
        cutover.gate(env, {}, tmp_path)
    assert len(calls) == 1 and sleeps == []
