# Trusted shadow classifier: observations, never permission

This is the shadow-only prerequisite after coverage parity, under feature 009
in the spec leg. It ports conservative proof patterns from OpenBenches'
`scripts/stack-ci.py` and `scripts/project-stack-ci.py`, including the
already-merged metadata refinement. It does not copy their skip authority,
component allowlists, admission labels or candidate receipts.

## Trust boundary

`ci-shadow.yml` checks out **main**, with full Git history and no persisted
credentials, for its observer. Only that checkout's `shadow_scope.py` runs with
the existing GitHub token's read-only contents/PR permissions. No new credential,
app grant or service is needed. Git operations read objects only; API requests
are bounded GETs against this repository on github.com. No status, ref, source,
lane or profile is written. Metadata never becomes a shell command.

The observer reports fixed-vocabulary JSON and a safe summary. All results have
`mode=shadow`, `required_ci=full`, `skip_ci=false` and
`queue_admission=false`. No GITHUB_OUTPUT flag or workflow consumer is added.
Green observer/contract jobs are not review, integration, admission or release
receipts. Existing `pilot_scope.py` / `ci-pilot.yml` remain unchanged.

During the preparation PR, main does not yet carry this policy. The observer
reports `policy-unavailable` with full fallback; it never executes PR-owned code
as a bootstrap fallback. The separate source-contract job runs local mocked-API
tests at the PR commit without passing the observer's API token. A green bootstrap
fallback is not evidence that the head's observer has run on live positive scope.

## Initial scope and observations

The only potentially scoped files are modified regular `claude-current` (100755)
and `tests/test_claude_current.py` (100644), without mode changes. Intent is exactly
one `CI-Shadow: claude-current` line in the PR body, or source-push head commit.
Intent and any actor/label/prefix declare no authority.

- Open PRs: same-repository, open/non-draft, independent base main, exact live
  head/base/ref/body agreement, current main ancestry and the allowlisted diff.
  Third-party metadata is recomputed from live evidence, not exempted by actor.
- Source pushes: exact event/context and live branch identity, current main
  ancestry, commit intent and scoped content. Verify/release/queue branches are
  not normal source observations. The observer excludes release branches/tags.
- Edited already-merged metadata: same source head, live merged PR, main base,
  two-parent merge naming that head, merge ancestry on current main and scoped
  landed diff. Only this proved observation may tolerate stale event base or
  test-merge metadata. It is NOT a successful tested-landing receipt.
- Candidate-shaped PR/push events: `candidate-proof-required`, full scope.
  A Mergify-looking branch or bot is not membership, review or heavy-run proof.
- Main pushes: `landing-proof-required`, full scope. Existing full main/release
  acceptance remains independent.

Main is checked against the policy checkout and rechecked after observation.
Source PR/branch identities are reread. Missing objects, read errors, stale
identity, moving main, mixed/empty/unsafe diffs, malformed events, closed/dequeued
actions outside narrow edited-merge proof and dependent topology stay full.
No historical candidate scan, retries or reduced test selector is implemented.

## Qualification and limits

The source tests use disposable local Git histories and mocked APIs, covering
source/metadata changes, stale retarget snapshots, moving main/branches/PRs,
read failures, unsupported topology and modes, explicit unproved candidates,
safe bootstrap and non-execution of injected text. Full ordinary CI still runs.

This stage opens code/spec PRs only. It adds no fast-only CI, queue command,
canary, ruleset change/bypass, app access, release change/tag, assembly pins or
installed-session update. Preserve lanes 1–5 and their worktrees/bindings.
Candidate/run/landed-tree identity proofs, required-check migration and live
qualification are later separately approved stages.
