# Exact-head local review receipts

Governing change: openRepoTools-spec
`openspec/changes/accept-exact-head-local-reviews/`, reconciled under spec issue
26. Implementation: feature 009 LOCAL-REVIEW-10, T033–T035. Approved baseline:
code `5173ad25910ca4d7acfd6052090246ccc084f1a1`, spec
`1b1c93fa0afa3d92bc908419534a1fc627bc26ec`.

Authority: Brett requested implementing the narrow code/spec local-review
receipt change, adding regression tests and opening PRs while disabled. This is
an explicit new review contract, not a retrospective hosted-review waiver.

Add authenticated new PR comments naming the exact repository/PR/head/base,
local Codex review skill, findings/resolution/validation and accepted status with
zero unresolved findings. Live writer identity/permission, complete unedited
metadata, newest-local supersession/revocation and final receipt/thread rereads
fail closed. Preserve hosted-only review and every full-CI/coverage contract.

Disposition: implementation in progress; local/hosted checks and publication are
separate evidence. No merge, activation, settings, canary, queue operation, app
access, release/tag, assembly pin, installed tool or running-lane change.
