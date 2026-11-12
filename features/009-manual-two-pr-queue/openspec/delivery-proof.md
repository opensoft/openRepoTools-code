# Feature009 amendment: additive fast and candidate preparation

ID:009-DELIVERY-PROOF-20261111. Governing spec change: manual-two-pr-queue,
approved baseline ed85f6dc99f95243185138fd4d8ebfc485fe67a1; reconciliation #26.
Requirements FR018–FR021; sole Speckit task set DELIVERY-PROOF-07, T015–T018.

Brett set the full rollout goal while retaining no live canary, ruleset changes/
bypass, app access or release changes. Working spec/plan/tasks were updated first.

Add exact-source fast feedback and a workflow_call-only trusted candidate entry.
Derive immutable bounded membership rooted at live main; require scoped regular
content, correct fast Actions provenance, managed exact-head Codex and resolved
threads, deterministic prefix merges and live identity rechecks. Reuse all full
CI jobs, fail closed on unsuccessful calls, and reverify after heavy integration.
No existing queue/rule consumes these checks; full acceptance remains unchanged.
Candidate prefix calculations write private immutable Git objects only, never
refs/index/worktrees. Read APIs create no status/review/queue or credential.

Verify offline Git/mocked-API vectors, forged/stale/truncated evidence, changed
heads/main, failed aggregates, workflow trust boundaries, original full-job
baseline and the prior shadow/pilot/queue contracts. No live proof is claimed
from local fixtures or additive fast source runs.

Disposition: accepted preparation. Activation/ruleset migration/canary and later
dependent/wider scope require separate approval and qualification. No lane/tool/
session takeover, release change or bypass is authorized.
