# Additive fast and candidate proof: prepared, not activated

Feature009 task set DELIVERY-PROOF-07 prepares the next delivery primitives.
Ordinary full CI, required-check rules, manual queues, release validation and
the trusted shadow observer remain unchanged. No existing queue calls this
candidate entry or consumes its new check. No live candidate/canary is created.

## Source fast feedback

`task-set-fast.yml` runs only on opened/synchronize/reopened PRs. It verifies
the actual checkout and exact test-merge parents, checks whitespace/syntax and
runs the complete claude-current regression plus guard/hygiene/delivery tests.
The source job receives no API token in its environment. This additive check
is not admission or full integration; mixed/unsupported work still has full CI.
It is deliberately not triggered by labels or late edited/closed metadata.

## Reusable candidate entry

`task-set-candidate.yml` has only a parameterless workflow_call, no dispatch or
queue/push trigger. The proposed non-gating caller below requires a separately
approved merge before it can observe queue events. The entry:

1. Executes main-owned verifier code with read-only GitHub metadata permissions.
2. Requires genuine same-repository Mergify push context, exact queue ref/SHA and
   current trusted main before deriving one or two ordered independent members.
3. Requires unique open non-draft same-repository main-based PRs with the fixed
   observational intent marker and modified regular claude-current/test content.
   Dependencies, mixed/control/release paths and duplicate/ambiguous members fail.
4. Requires exact-head successful `openrepotools-pr-fast` evidence from GitHub
   Actions at the expected workflow, run, job and current attempt. Another app,
   workflow or head cannot supply that receipt.
5. Requires the official managed Codex summary at the exact head, completed with
   no findings/unresolved findings, plus complete resolved-thread evidence.
   Quota responses, unmanaged text, old receipts and incomplete API pages fail.
6. Requires every candidate prefix to equal its deterministic clean merge.
   Git merge-tree creates only private immutable objects in the disposable CI
   checkout; it updates no ref, index, source file or user worktree. This helper
   uses Git2.38+ available on the Ubuntu24.04 CI runner; no installed CLI/package
   runtime requirement is changed.
7. Rechecks live sources/ref/main, then calls the SAME thirteen-job tests.yml at
   the candidate commit. This is code-leg integration, not Triad/release acceptance.
8. Its always-running aggregate requires successful verifier and full call, then
   repeats trusted live verification. A head/ref/base change during integration,
   a failed/cancelled/skipped job or missing evidence cannot qualify.

Verification emits immutable proof, not a source success status, queue command
or review/admission grant. No skip flag is consumed. A singleton can be valid
but is never reported as a two-member canary. No retry or historical scan hides
a failed attempt. Live membership and landed prefix/final trees still need
separate observed acceptance before widening.

Independent means the members share no Git history beyond current main, not
merely that their bodies omit Depends-On. Fast provenance also requires one
current source PR/main association and complete bounded base-change history.
The run's immutable creation time must be strictly later than every retarget;
current associations alone can change and do not prove a historical base. A
fresh reopened run can qualify after retargeting; a historical rerun cannot
erase the retarget. Equal-second ordering is ambiguous and refuses. Successful
run/check state is reread after job lookup, and fast/base-history/Codex/thread
snapshots are revalidated before final source/ref consistency acceptance.

## Activation remains a separate decision

The current main rules require four full source checks. They remain intact.
Replacing that arrangement, wiring Mergify admission/merge conditions, disabling
duplicate PR CI, qualifying a live two-PR batch and widening to dependent stacks
or additional components require separate approved configuration and evidence.
Never post green statuses named after full tests that did not run.

The full rollout goal does not override the current prohibitions on live canaries,
ruleset changes/bypass, app access or releases. Preserve lanes1–5, their claims,
bindings, worktrees, running benches and installed sessions. Assembly pins and
composed acceptance remain coherent separate delivery stages.

## Proposed non-gating caller (CANDIDATE-SHADOW-08)

`task-set-candidate-shadow.yml` prepares push-only observation on
`mergify/merge-queue/*`. No dispatch, auto-enqueue, secret inheritance or write
permission is added. A probe checks out only main and executes the existing
main-owned candidate verifier. Only an explicit successful proof writes the
literal scheduling output qualify=true. Missing policy, stale/mixed/unknown
content, unsupported context or any verifier failure writes qualify=false;
timeout, cancellation or job failure cannot schedule additional qualification.
No event data or verifier stdout is copied into shell/output instructions.

That boolean schedules only an ADDITIONAL call to the existing candidate entry,
which verifies independently, runs the same full suite and rechecks live evidence.
It is not admission, a CI exemption or a heavy receipt. The caller is non-gating:
no existing queue or ruleset consumes its observation or its nested check names.
The existing verifier still requires the exact claude-current/test regular-file
scope, one or two independent main-based members, current fast provenance and
clean official exact-head Codex evidence. Local review or a quota message cannot
substitute for those future candidate receipts.

This proposal does not save heavy runs. After a separately approved merge,
eligible observations intentionally add a full run while existing source and
candidate full CI continue. Mixed or uncertain work stays on that original full
path. The original tests.yml, thirteen-job inventory, reusable entry, all queues
and release workflows are unchanged. Opening the PR does not execute a live
candidate, merge it, advance assembly pins or refresh running sessions.

Next gates are separate: checked source merge with user authority; approved
live scoped qualification with exact member/run/candidate/landed-tree evidence;
then an explicit proposal for admission and required-check migration. Until that
cutover is approved, retain the current four required full gates. Never post
success aliases for tests not run. Broader scopes/dependencies, apps, rulesets,
releases and lanes remain outside this preparation.
