# CI-CUTOVER-09 implementation pointer

Authority: Brett approved preparing/opening the actual claude-current cutover PR
only. Full proposal/design/requirements live in the spec leg at
`openspec/changes/prepare-claude-current-ci-cutover/`. The sole implementation
checklist is feature009's tasks.md, T022–T026, reconciled under issue26.

This is a pointer, not a duplicate full proposal or acceptance record. The code
runbook is `.github/ci/delivery-cutover.md`; shared Claude/Codex instructions link
it. The flag remains false, existing full checks stay enforced, and no settings,
canary, merge, assembly, release, installed tool or lane change is authorized.

Local verification: 741 focused tests passed, zero skips, through tests/run.sh
as UID1000 in an offline disposable 2CPU/2GiB existing bench image. Workflow lint,
strict OpenSpec and whitespace checks passed. Hosted CI/reuse qualification,
exact-head review and every live acceptance gate remain separate.

Sonar follow-up: remove the arbitrary proof-output CLI argument. The writer now
exclusively creates only proof.json in the canonical Actions runner temporary
directory, refusing files/symlinks/redirection. Seven new rejection/exclusive
creation regressions bring the focused result to748 passed, zero skips; lint and
whitespace remain clean. Latest-head hosted reanalysis/review remain separate.
