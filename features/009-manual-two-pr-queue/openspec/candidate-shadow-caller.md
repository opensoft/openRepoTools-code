# Feature009 amendment: non-gating candidate caller

ID: 009-CANDIDATE-SHADOW-20261112. Governing change: manual-two-pr-queue;
spec baseline bc24929427a1551a3ed17f625fefb0234aa56ac5; reconciliation #26.
Sole executable task set CANDIDATE-SHADOW-08, T019–T021 in the spec leg.
Requirements: FR-022–FR-024.

Brett approved preparing/opening the next config-only PR, retaining full CI.
The canonical proposal/design and task list were amended first. Reuse our clean
isolated feature pair without modifying the active shared checkout or lanes.

Add a push-only non-gating caller for the existing complete candidate proof.
Only a successful main-owned read-only probe schedules the unchanged reusable
entry; absent/refused/failed/uncertain evidence stays on ordinary full CI. The
entry independently verifies, executes all thirteen full jobs and rechecks.
Probe scheduling is not admission, review or a heavy receipt. All existing full
CI, queues, coverage inventory, release flows and required checks stay unchanged.

Verify actual probe shell and graph/permission/output contracts plus the existing
Git/API fault, parity, shard and queue regressions offline and unprivileged.
No source success aliases, queue command, live canary, merge, bypass, app/ruleset
change, release act, installed-session change or assembly pin move is authorized.
Source preparation is not live qualification or one-heavy-run efficiency; a
positive later observation deliberately duplicates full CI before any cutover.
