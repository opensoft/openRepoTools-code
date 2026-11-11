# Manual full-CI queues: operator procedure and qualification

This is a code-local CI operator reference for both Claude and Codex. The
assembly's rules and the spec leg's feature 009 remain authoritative. Existing
lane claims, review and landing coordination still apply. No canary is authorized
by adding or merging this configuration.

## What is prepared

`.mergify.yml` defines `openrepotools-docs-pilot`: serial, one candidate at a time,
maximum two PRs, 60-second fill window, no automatic enqueue, retry or failure
splitting. A batch may contain fewer than two PRs; never count a singleton as a
successful two-PR test. No checkbox is enabled; entry requires a queue command
from a repository writer. Eligibility and labels alone do not enqueue anything.

The documentation queue's only eligible files are
`.github/ci/task-set-delivery.md` and this reference.
Every original PR must be open, non-draft and same-repository, have a head under
`ci/batch-pilot/` and the manual `batch-pilot-reviewed` label, and target main or
an immediate predecessor under that prefix with `Depends-On: #N` in its body.
Mergify must recognize that actual branch/body chain. Do not register GitHub
native stack objects, cross forks/repositories or queue more than two members.

Both original PRs and the combined candidate must pass GitHub Actions'
`guard-launch-mode`, `tests`, `tests-no-submodule` and `package` gates. Existing
tests.yml runs on PR opening, code updates and reopening on arbitrary bases,
including draft batch candidates. Label-only events (including Mergify adding
`queued`) do not start another full run or publish skipped replacement checks;
a code update still runs all gates even when that PR is labeled `queued`.
Main/release-branch pushes, nightly and manual runs are unchanged. This stage
runs **full CI per PR plus full batch CI**, not
fast-only PR CI. `verify` feedback and `ci-pilot` observations replace no gate.
The advisory classifier is not read by Mergify and grants no admission.

## Before a future authorized canary

1. Obtain separate permission to run and land the two canary PRs. Verify the
   actual app installation, plan capability, rulesets and queue access. Stop
   if they block: no app grants, purchase, bypass or ruleset change is implied.
2. Preserve lanes 1–5 and use isolated worktrees; do not message, restart,
   rebind, rename, rebase or edit the active lanes, profiles or register.
3. Verify every exact current head/base, full check result, Codex receipt and
   unresolved thread. The label is a maintainer attestation, **not an automated
   Codex review proof**. Set it only after those checks and user authority.
4. Prepare only the approved two members. For dependent PRs, use ordinary PR
   bases and Depends-On markers, with gh-stack only for approved local authoring.
   When authorized, the writer requests the named queue using the documented
   Mergify queue command on the highest member. No queue command is issued now.
5. Record heads, bases, member order, the actual batch/candidate SHA and full
   candidate run/attempt, and compare the landed tree to the tested candidate.
   Failures, partial/singleton batches or retries are not a clean two-PR result.

If a head/base changes, remove the attestation label and recheck fresh evidence
before another request. Do not restack while queued. Dequeue rather than edit
a queue branch. An external main merge resets candidate validation; no repo-wide
freeze setting or lane takeover is authorized. Retain ordinary main/nightly and
release-branch checks. Releases, tags, assembly pins and OpenSpec archive remain
separate. Installing this queue does not update a pinned checkout or running
session's instructions.

Configuration/schema tests prove only preparation. Live batching, access,
coverage, failure recovery and CI-saving acceptance require separate evidence.

## Evidence for a two-PR result

Keep the original member heads and bases, Mergify's actual member order, the
combined candidate commit and tree, and its full CI run URL and attempt. Compare
the final landed commit's tree with that tested candidate tree, not just its
commit message or a clean working directory. Record each member's merge result.
A singleton, partial landing, changed base, failed candidate or retry must be
reported explicitly rather than described as a clean two-PR batch.

## Authorized real-code batch: PRs #35 and #36

The separate manual queue `openrepotools-real-code-35-36` accepts only these
same-repository, open, non-draft PRs targeting `main`:

- #35, `fix/exit-refusals-keep-their-words`, changing only `lane-handoff` and
  `tests/test_a23_lane_handoff.py`.
- #36, `fix/a14-three-nudge-race`, changing only `tests/test_lane_helpers.sh`.

Brett authorized this two-member real-code test on 2026-11-11. The documentation
queue is unchanged. This exception does not admit #32, arbitrary `fix/` branches,
other files, release changes or automatic merges. Both PRs and their combined
candidate retain all four full CI gates. Batches are at most two, with a
60-second fill window, one candidate at a time and no automatic retries/splits.

Before requesting this queue, verify Codex review and full CI at exact heads
`447b51b93d762d2b89ae1bd175811d1907010ca2` (#35) and
`63a47bdcc98ebb63bb253ea2e2d449d94eb4bdba` (#36), plus current bases, diff paths
and review threads. The queue's PR-number/branch/path filters are service gates;
these head hashes are operator checks, not supported SHA conditions. Stop if
either head changes: do not rewrite an active lane's branch to force admission.

The writer's manual queue commands attest that preflight was completed; no new
review label is needed for this exact pair. Mergify cancels a waiting command
or dequeues a queued member when its head changes. Request the named queue on
both independent PRs in quick succession so they can form one batch. Do not
retarget them, invent a dependency or register a native stack merely to batch.
Check actual two-member membership before accepting the result; a singleton
is not this test. Record candidate/landed trees and CI evidence as above.

Preserve lanes 1–5, existing sessions and #32. No ruleset bypass, app-access,
paid upgrade, release or assembly-pin change is authorized. A later general
code queue or fast-only CI rollout needs its own scoped change and evidence.

## General manual code queue — approved rollout

The 2026-11-11 rollout adds `openrepotools-code`. This is a **main-only** queue
for independent same-repository open non-draft code PRs, not an automatic merge
rule or fast-only CI. Keep actual dependencies as dependencies; gh-stack can
author them where installed, but do not register native stack objects, flatten
them or rewrite an active lane merely to qualify here.

Eligible paths are the known root commands, `repos.tsv`, `README.md`, and safe
file paths under `tests/`, `src/`, `commands/`, `skills/` and `features/`.
The release stamp, workflows, queue configuration, pins/gitlinks, package
metadata and unknown/mixed paths refuse. Such control changes still use ordinary
reviewed PRs and full CI; do not widen this allowlist ad hoc to clear a refusal.

### Before each command

1. Confirm user merge authority and existing lane claims/landing coordination.
   Do not take over lanes 1–5 or apply a repository freeze/bypass.
2. Read back the exact current head, base main, changed paths, all four full
   GitHub Actions gates, exact-head Codex review and unresolved threads. Request
   `@codex review` when no fresh exact-head bot receipt exists; quota is no pass.
3. Record those identities and review/CI links. This preflight and the named
   command are an **operator attestation**, not service-enforced Codex/SHA proof.
   No review label is required or sufficient. Only repository writers can queue.
4. For the authorized eligible PR, use:

   ```bash
   gh pr comment PR_NUMBER --repo opensoft/openRepoTools-code \
     --body '@mergifyio queue openrepotools-code'
   ```

   Request two independent ready PRs close together when a two-member batch is
   desired. Batch size is a maximum; a singleton is not a two-PR qualification.
5. Verify Mergify's actual members/order, checking base, candidate SHA/tree,
   successful full candidate run and the landed tree. Report partial/failed/
   singleton/retried results honestly. There is one active candidate, a 60-second
   fill window, 90-minute checks and no automatic retry or failure splitting.

A head push invalidates the pending/queued manual request: verify fresh review
and CI and explicitly request again. On a base change, dequeue and repeat
preflight; never edit a live queue branch. An external main merge resets testing.
If service/plan/rules block, stop for approval; no paid upgrade or access change
is implied. This rollout itself enqueues no existing PR or new live canary.

Code #44 removes obsolete label-triggered full runs: Mergify adding `queued`
does not replace full checks with skipped checks, and code updates still run
the complete suite. Full original and combined CI, ordinary main/release-branch
pushes and nightly/manual runs remain. Do not claim one heavy run total.

Fresh assembly-root sessions read the pinned code references through AGENTS.md
and CLAUDE.md. A profile launch neither queues a PR nor creates a lane. Existing
sessions read the new reference at a safe checkpoint; do not restart them.
