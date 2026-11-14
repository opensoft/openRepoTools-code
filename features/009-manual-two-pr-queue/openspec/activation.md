# CI-ACTIVATION-11: scoped activation phase

Disposition at this record's creation: owner-approved; required-check migration
complete; reviewed enablement and live qualification not yet performed. Later
qualification is tracked under [reconciliation issue 26](https://github.com/opensoft/openRepoTools-spec/issues/26).
Governing change: `opensoft/openRepoTools-spec`,
`openspec/changes/activate-claude-current-ci-cutover/`.
Working requirements FR-035–FR-038; sole implementation checklist T036–T041 in
`specs/009-manual-two-pr-queue/tasks.md`; reconciliation issue 26.

## Authority and baseline

Brett Heap, 2026-11-13: "Approve scoped activation and canary. Proceed with the
required-check migration, reviewed enablement PR, and two-PR test. Preserve lanes
1–5; no bypass, app access, paid upgrades, release or assembly-pin changes."

This separately approves the already disclosed changed source merge floor:
delivery can mean fast verification; only the named manual queue holds heavy
integration. Queue-only usage is operator policy, not GitHub-enforced exclusivity.
No direct fast-source merge is authorized.

Source baseline: code `22aac02ba5cfcb2777e4bf05a574e26c555bd38b`, spec
`9311051d340a64b81b94f70dff4ea66809112de6`. Preserve inherited Sonar fixes,
dependency pins, all full jobs/commands, artifact and review schemas, releases,
active plans and all running lanes. The initial scope stays unchanged.

## Evidence boundaries

Settings, reviewed source qualification, local failure/recovery fixtures, live
candidate/landing qualification and assembly adoption are separate gates.
Record actual readbacks and run/tree identities below as they complete. Neither
this approval record nor a passing local test is a live admission/merge receipt.
Source PRs and this phase are not archive or assembly-pin authority.

## Required-check migration — 2026-11-13 06:27 America/La_Paz

Guarded source main 22aac02 and successful full run 43397357900. The existing
GitHub Actions delivery check was successful and bound to app 15368. The live
flag remained false before and after the write.

Updated only the required-context list in repository ruleset 25966308, from
guard-launch-mode/tests/tests-no-submodule/package to openrepotools-delivery
with integration_id 15368. Preserved name, active enforcement, main-only branch
condition, empty bypass actors, strictness and do-not-enforce-on-create flags.
Target/effective readbacks matched; every unrelated effective rule was unchanged.
Classic protection remains disabled with off/empty contexts/checks. No new
permission, bypass, app, release, assembly or lane act was performed.

This is a service-migration receipt, not flag enablement or live efficiency.

## Enablement test boundaries

The committed-state assertion now expects the owner-approved true policy. The
existing disabled/no-network case uses an explicit false fixture and verifies
that state before calling the router. Three new default-on cases require full
fallback for absent, unbound or legacy-retaining protection.

The old local-review and queue preparation checks also asserted a false global
default. Their phase expectations now match true; their read-only-reader and
full-entry/queue assertions are preserved. The local-review case is renamed to
describe the current approved phase. These two intentional test-identity renames
and three added protection cases are not dropped runtime/full-suite coverage.

Red-first default-on checks failed four assertions against the old false policy,
while the explicit disabled case passed. The first broad run found the remaining
historical local-review phase assertion (483 passed/1 failed); a complete policy
reference search identified the queue assertion too. Final validation follows
the corrected phase expectations; no failure is recast as passing qualification.

## Later qualification and R4 refusal — 2026-11-13

The enablement and directly related metadata repairs were checked normally.
Generated-hint repair PR66 landed at660459f with its reviewed/tested tree; paired
spec PR44 landed at375666d. Ordinary source CI passed15/15, reusable17/17 and
actual-main43506231972 passed15/15, first attempts. All complete5342-case
inventories preserved existing identities/skips and passed the81new regressions.

Fresh source PR67 then passed initial metadata/Git checks but logged fast-reread
at21:39:54.806Z, in the fast workflow's completion window. Its own full fallback
was cancelled, not qualified. No receipt, queue or heavy acceptance occurred.
The pending-observation ordering follow-up grants no proof while waiting; strict
completed/admission checks and all retry limits remain required.
The same no-proof boundary covers an authenticated candidate caller still
missing its admission artifact. The queued-caller transition was reproduced
locally, not by a live queue. A fresh poll must validate the actual artifact;
default readers, invalid callers and strict artifact-present proofs are unchanged.

This code-local amendment remains a dated record, not a second live acceptance
ledger. Complete run/artifact/member/prefix/final-tree evidence and remaining
adoption boundaries are reconciled in the spec leg's
`specs/009-manual-two-pr-queue/activation-evidence.md` and issue26 above. Follow
that canonical dated record for later outcomes; do not reinterpret these failed
attempts or infer assembly, release, tool or running-lane adoption authority.

## R5 candidate-description follow-up — 2026-11-14

After pending-observation qualification, fresh source PR71/72 passed fast-only
and formed a genuine two-member batch. Draft PR73 selected full at00:27:07.974Z;
edit history records a description edit at00:27:05Z. That chronology exposes an
initial exact-body incompatibility, not a proven sole historical cause. Both
sources were dequeued and the duplicate/heavy runs cancelled before landing.
This remains failed efficiency acceptance, never a completed heavy qualification.

CI-METADATA-15 permits only initial string/null candidate-description differences
in a temporary comparison copy and adds field-name/fixed-code diagnostics. No
description supplies admission or review proof. Genuine draft/ref/main/head,
tested parents, scope, actual admission, independent source reviews and strict
final raw rereads remain mandatory. Invalid description types retain full.
The spec leg's canonical ledger/tasks govern qualification and genuinely fresh
R6 acceptance; this amendment claims neither live success nor assembly adoption.

## R6 final consistency reread — CI-METADATA-16

Fresh sources75/76 qualified fast-only and real ordered two-member admission,
but draft77 logged candidate-reread at02:51:19.803Z after its initial proof checks.
Mergify edited the description in the same second. The individual original raw
field was not captured; do not assert a sole historical cause. The owned duplicate
and heavy runs were cancelled, sources dequeued and draft closed before landing;
main stayeda15a6b5. This is failed efficiency acceptance, not a test assertion.

The bounded fresh-observation repair never accepts a raced view. Only a still-
valid authenticated final PR/caller movement can request the existing no-proof
wait; accepted proof still requires exact raw rereads. Hard identity/ref/body/
hint/caller/source/artifact failures remain full. Candidate gate uses the same
per-invocation bound and original mode/digest; exhaustion or changed proof refuses.
Source gate semantics and all budgets/schemas/workflows remain unchanged. The
canonical spec ledger records qualification and genuinely fresh R7 acceptance;
this code-local dated pointer grants no live success or assembly authority.
