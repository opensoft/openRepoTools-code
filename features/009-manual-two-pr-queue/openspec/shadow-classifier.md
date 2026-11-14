# Feature 009 amendment: trusted shadow event observations

ID: 009-SHADOW-CLASSIFIER-20261111. Governing change: spec leg
`openspec/changes/manual-two-pr-queue/`; approved spec baseline
`476dadc5172be2f88a2a0cd21c744c35b9521d58`. Reconciliation: spec issue #26.
Affected requirements FR-014–FR-017; task set SHADOW-CLASSIFIER-06, T012–T014.

Authority: Brett requested implementing the shadow-classifier PR next, ordinary
full CI and lanes 1–5 preserved, no live canary, ruleset changes/bypass, app access
or release changes. Working spec/plan/tasks were updated before implementation.

Add an independent trusted-main observer and head-owned offline contract tests,
retaining the old pilot and every full/reusable/verify/release workflow, baseline
and queue. Port OpenBenches' live-identity, regular scoped-diff, read-failure and
already-merged metadata proof patterns, not its skip or admission authority.
All observations remain full/no-skip/no-admission. Main/PR/branch drift fails
conservatively; missing trusted policy never falls back to PR-owned execution.
Candidate/run/landing proof is explicitly deferred; actor/prefix alone proves none.

Verify red-first source tests, mocked APIs and local Git vectors, trusted workflow
and bootstrap contracts, workflow lint, strict OpenSpec, and existing full-CI,
parity/shard/pilot/queue regressions. Hosted bootstrap is not live positive-scope
acceptance; cloud full CI and exact-head review are separate publication gates.

Disposition: accepted for preparation. No merge/archive, queue/canary, ruleset/
app/release change, assembly pin bump or lane/session/tool replacement is implied.
