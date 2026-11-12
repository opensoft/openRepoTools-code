# Feature 009 amendment: general manual code queue

ID: 009-GENERAL-CODE-20261111. Governing change: spec leg
`openspec/changes/manual-two-pr-queue/`; approved spec baseline
`dbfed9ebfe57484c868b8be1a2a79e1f012f4def`. Reconciliation: spec issue #26.

Authority: Brett explicitly requested finishing the rollout: merge #44 after
CI, add the general manual code queue, and update assembly pins and Claude
instructions, preserving lanes 1–5 with no bypass, app access or release change.
Working spec/plan/tasks were updated before implementation (T004–T008).

Append `openrepotools-code` for independent main-based normal code PRs. Retain
all full gates, writer-only manual admission, serial/two-member operation and
zero auto retries/splitting. Refuse control/release/unknown paths and unsupported
topology. The command attests operator-verified exact-head review and authority;
it is not automatic Codex enforcement. No review label, autoqueue or live canary.

Validation: parsed policy positive/negative vectors, unchanged full workflow
contracts, exact-head Codex review, Mergify schema validation and full CI. Final
project delivery additionally needs reconciled specs and coherent merged pins
with composed validation. Do not advance pins to a feature-branch commit or
claim new instructions refreshed an existing session. No releases or tools change.

Disposition: accepted; implementation and landing evidence are tracked in the
spec feature's sole executable tasks and final as-built reconciliation record.
