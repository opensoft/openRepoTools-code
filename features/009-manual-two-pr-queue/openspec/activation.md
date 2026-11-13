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
