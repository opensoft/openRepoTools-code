# Bounded amendment: remove redundant label-triggered full CI

On 2026-11-11 Brett authorized the narrow CI-efficiency fix after real-code
batch #43: Mergify's automatic `queued` labels had triggered duplicate full
original-PR runs despite unchanged code. The old `labeled` trigger only served
the removed macOS job; no current full-CI job reads labels.

Remove `labeled` from tests.yml's PR event types. Label-only events must start
no full run, rather than produce skipped replacement checks. Keep `opened`,
`synchronize` and `reopened`, without path/base/draft/label filters, so real code
updates and Mergify draft candidates retain every full check even while queued.
This explicitly replaces only the old label-event clause of the workflow
contract; it is not permission for fast-only member CI or wider queue admission.

Keep all four required gate names, shard coverage and fail-closed aggregation.
Main/release-branch pushes, nightly/manual runs, the Mergify configuration and
release workflows remain unchanged. Regression tests must reject the old label
trigger and preserve all code-update triggers and unconditional full jobs.

Preserve lanes 1–5, running benches and unrelated PRs. No live canary, ruleset
bypass, app-access, paid upgrade, release/tag, installed-session or assembly-pin
change is included.
