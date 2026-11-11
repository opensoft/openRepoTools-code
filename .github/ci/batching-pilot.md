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

The only eligible files are `.github/ci/task-set-delivery.md` and this reference.
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
