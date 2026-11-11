# Manual two-PR queue: configuration, not live qualification

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
tests.yml already runs on arbitrary PR bases, including draft batch candidates;
it is unchanged. This stage runs **full CI per PR plus full batch CI**, not
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
