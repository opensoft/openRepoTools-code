# Prepared claude-current CI cutover

Status: **disabled; preparation PR only**. No migration, canary, queue command,
assembly refresh or release acceptance is performed by this change.

## What is prepared

`delivery-policy.json` commits `enabled: false`. `tests.yml` retains its ordinary
events and parameterless reusable entry. Its original thirteen expanded jobs
retain their commands, environment, matrices, checkout modes and accounting.
Two read-only controls add an honest `openrepotools-delivery` check. The old
reviewed baseline is not regenerated: tests remove only the exact reviewed
needs/if projection before comparing every original job hash. The new controls
are separately frozen and mutation-tested.

The router executes only a main checkout with persisted Git credentials disabled.
Missing policy bootstraps full CI. Disabled/unreadable policy and any incomplete
or uncertain proof select full. A router failure cannot silently skip full jobs.
The final gate requires all four actual full results, or independently rechecks
the same omitted-work proof. It never posts success under an unrun test's name.

Even a future true flag cannot omit work until complete effective branch rules
require `openrepotools-delivery` from GitHub Actions (integration15368) and none
of `guard-launch-mode`, `tests`, `tests-no-submodule`, `package` remains required.
The public effective-rules GET endpoint needs metadata read, not admin writes.
No ruleset, branch protection, app, permission grant or bypass is applied here.

## Initial supported scope

Only modified regular files `claude-current` (100755) and
`tests/test_claude_current.py` (100644), with unchanged modes. One or two
independent main-based same-repository members; no dependent-stack flattening.
Both exact body lines are required for future efficiency:

```text
CI-Shadow: claude-current
CI-Delivery: claude-current
```

Intent is not review or merge authority. Source routing requires live identity,
test-merge parents and exact-head successful fast-workflow/run/job/base-history
evidence. The complete candidate admission still requires genuine clean managed
Codex receipts and complete resolved threads. Quota replies and local preparation
review substitutions cannot manufacture those future receipts.

Authenticated current run.path distinguishes ordinary tests.yml from reuse.
Reusable calls force full even though GitHub retains the caller's original event.
Release branches, nightly and manual runs force full. No release workflow changes.

## Candidate, held queue and historical landing

The queue-push caller writes immutable admission and qualified JSON artifacts
from trusted verification into runner.temp, using the existing pinned upload
action. Records contain validated IDs, hashes and opt-in flags, not raw PR/review
bodies or secrets.
The CLI accepts no output path: it exclusively creates the fixed proof.json in
the canonical Actions runner.temp, refusing existing files and symlinks.
Readers bind numeric artifact ID/name/archive SHA256/run/head/repository/current
first attempt and reread provenance. Archives are size-limited,
one exact JSON member only, never extracted. All Git/API operations are bounded.
If a queue branch was deleted, the validated immutable public candidate commit
may be fetched by SHA from the fixed public repository, without credentials,
ref/tag/FETCH_HEAD updates or checkout. Unavailable objects retain full work.

A candidate-PR duplicate is omitted only for a genuine current caller plus its
admission record and independently revalidated live sources/Git chain. Actor,
branch prefix or draft status alone never exempts work. Missing admission costs
a full run. An enabled PR route waits at most six ten-second intervals for startup
evidence; each read is independently bounded and all uncertainty stays full.

The parameterless candidate entry performs complete full CI and final live
verification before publishing qualified evidence. A unique **top-level**
`openrepotools-batch-heavy` waits for the whole call and rechecks live delivery
intent/reviews/identity. The new writer-requested manual queue
`openrepotools-claude-current` requires app-qualified fast + delivery on sources
and heavy on the combined candidate. It keeps protection injection at `queue`,
serial execution, max2 members, 60-second fill, 90-minute budget and zero retries/
splits. Older queues remain unchanged. No rule automatically enqueues anything.

Main-push reuse has a **separate historical reader**, not open admission with
invented push flags or now-closed PRs relabeled as open. It requires one unique
first-attempt successful authentic caller, the exact nineteen expanded jobs
(the original thirteen plus controls and verification/qualification), matching
immutable caller/callee SHAs, qualified record and unchanged policy/commands.
Every tested source head, ordered actual merge parent/prefix tree and GitHub
closed/merged record after completion must match. It searches only twenty recent
caller runs, with complete bounded per-head uniqueness checks; older/unknown
evidence falls back to full. Lookalike/manual merges, reruns, failures, skipped
jobs, changed policy or stale refs also fall back. New nested names are a
conservative contract to confirm in a later authorized canary, not live evidence.

## Future owner-approved migration (NOT executed)

1. Merge this code/spec only after exact-head full/reuse CI and review, reconciling
   Sonar PR51's wheel-only baseline amendment and coverage collectors first.
2. Approve the changed source merge floor described below. Confirm the effective
   checks, queue config/service readiness and genuine managed review capacity.
3. Separately approve/install app-bound `openrepotools-delivery` as the required
   verification context and remove the four legacy required contexts. Preserve
   every unrelated rule. No bypass. Keep the flag false during migration.
4. Enable only via a separately reviewed config PR. Require failure/recovery and
   a user-authorized two-member live efficiency canary: fast-only source/candidate
   PR CI, one complete heavy caller, no duplicate full main run, exact prefix and
   final landed trees. Reject or roll back on uncertainty; do not claim success
   from source tests, labels or queue membership alone.
5. Reconcile governance and later assembly pins/composed CI/session adoption
   under their own approvals. Preserve running lanes and active plans.

**Changed source floor:** after activation, delivery success can mean fast
verification, not heavy integration. The named Mergify queue holds heavy; GitHub's
new required check by itself would not prevent a collaborator from directly
merging a fast-only source. Both Claude and Codex MUST use the named manual queue
for an authorized opted-in source, never direct merge. Queue-only usage is an
operator policy unless separately approved service controls enforce it. This PR
does not pretend otherwise or silently request a bypass/new ruleset control.

Rollback: an ordinary reviewed `enabled: false` change resumes every original
full job. Restoring legacy required contexts is a separate owner-approved setting
change. Neither rollback nor this preparation changes release eligibility, apps,
installed tools, live sessions or lane ownership.

## Primary references

- [Effective branch rules and permissions](https://docs.github.com/en/rest/repos/rules)
- [Caller context in reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows#calling-a-reusable-workflow)
- [Attempt-specific job inventory](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run-attempt)
- [Artifact API](https://docs.github.com/en/rest/actions/artifacts)
- [Mergify queue rules](https://docs.mergify.com/merge-queue/rules/)
- [Two-step qualification](https://docs.mergify.com/merge-queue/two-step/)

Reference proof patterns: OpenBenches5df4fa0, project-stack-ci.py. Its scopes,
review trust and effective GitHub rules are not copied as authority here.
