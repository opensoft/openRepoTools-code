# Feature 009 amendment: full-CI coverage-parity prerequisite

ID: 009-COVERAGE-PARITY-20261111. Governing change: spec leg
`openspec/changes/manual-two-pr-queue/`; approved baseline
`66ba22f429caea8da4c664f04f5567bb924064ac`. Reconciliation: spec issue #26.
Affected requirements: FR-011–FR-013; task set COVERAGE-PARITY-05, T009–T011.

Authority: Brett requested implementing the coverage-parity PR first, retaining
ordinary full CI, all test coverage and lanes 1–5. No live canary, ruleset bypass,
app access or release changes. Working spec/plan/tasks were updated before code.

Make tests.yml locally reusable with an empty workflow_call event, changing none
of its existing events, environment or jobs. A PR-only qualification caller uses
that exact same workflow; no copied integration implementation or reduced input.
The baseline inventories the complete parsed jobs from merged code d3c55e5,
including commands, matrices, step order, checkout modes and aggregators. Its
hashes are generated from sorted compact JSON, not arbitrary replacement values.
New test files remain automatically discovered by the existing shard planner.

Verify red-first parity, mutation refusals, fail-closed call aggregation, existing
workflow/shard/queue tests, hosted ordinary full CI and separate reusable-call
qualification. Local tests and a configured caller are not hosted acceptance.

Disposition: accepted for preparation. Open code/spec PRs and request exact-head
Codex review. No merge, queue request, fast-only mode, ruleset/app/release changes,
assembly pin update, canary, lane takeover or installed-session update is implied.
