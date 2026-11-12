# Shared Claude/Codex task-set instructions: manual full-CI delivery

The separate [trusted shadow observer](shadow-classifier.md) reports only
conservative event observations. It never enables fast-only CI, grants queue
admission or replaces current-head review. The original pilot and all full-CI
gates remain unchanged; candidate/landing qualification is a later stage.

Read the assembly's AGENTS.md and AGENTS-shape.md first. This is a code-local
supplement for both agents, not replacement governance or a second specification
store. Canonical feature 008 and its OpenSpec change live in openRepoTools-spec.

## Current authority

Feature 008's classifier is **advisory only**. Full tests.yml checks remain required; the
assembly's exact-pin composed run is separate acceptance. A `claude-current`
shadow result does not authorize fast-only CI, a queue or a merge. No Mergify
queue was activated by feature 008. Feature 009's separate
[manual queues](batching-pilot.md) supply separately approved full-CI batching;
they do not use this classifier or enable fast-only CI. Do
not copy OpenBenches efficiency labels, admission receipts or allowlists here.

Code [PR #34](https://github.com/opensoft/openRepoTools-code/pull/34) owns the
`verify` workflow, its `verify/**` branches, selectors and optional PostgreSQL.
Check its actual merge state and latest instructions before using it. Targeted
verification is feedback, never full integration or release acceptance. Do not
copy or cherry-pick its file just to make this pilot work.

The 2026-11-11 rollout adds the main-only `openrepotools-code` queue for normal
code PRs without renaming lane branches. A repository writer checks current
authority, exact-head review, threads, paths, base and all full gates before
the explicit named command. See the runbook; eligibility alone enqueues nothing.
An independent PR targets main; do not flatten a genuine dependency to qualify.
Workflow/queue/pin/package-control and unknown/mixed paths need separate normal
reviewed landing, not this queue. Existing lanes and installed tools stay put.

## Small task sets without disrupting lanes

- Preserve lanes 1–5, their bindings, claims, worktrees, feature/task IDs and
  current work. Do not message, restart, rename, rebind or rebase another lane
  as part of adoption. Existing sessions explicitly read this reference at a
  safe checkpoint; adding a file does not refresh a running session's context.
- In the canonical spec-leg tasks.md, assign each task to one set and one PR.
  Record set ID, outcome, task IDs, immediate predecessor, fast verification
  command and safe intermediate state. Aim for one review decision and about
  2–5 related tasks. Keep tests with the behavior they verify.
- Stack only genuine dependencies. Independent lanes remain independent; do
  not chain all five lanes together. A lower PR must remain safe on its own.
  Keep the existing claim and landing coordination; stacking grants no slot.

## Authoring and review, not queue activation

Use the shared task-set-delivery workflow supplied by OpenBenches. Where installed,
verify gh-stack 0.3.0; do not install/replace tools or credentials implicitly.
Its local init/add/view/push operations may order authorized branches. Create
ordinary dependent PRs, each upper PR based on its predecessor's head branch
and carrying `Depends-On: #N`. Do not use stack submit/link/merge or register
GitHub stack objects; that mode has different Mergify governance requirements.

Request exact-head Codex review with a top-level `@codex review` comment unless
explicitly waived for that PR. A quota response, Copilot, or old-head review is
not approval. Recheck head/base/checks and unresolved findings after changes.
Preserve existing review policy; do not invent a bypass or post a green status.

No unrelated live stack/canary, queue command, app access, ruleset bypass, paid
upgrade, release change or tag is authorized by configuration preparation. A future
manual full-CI canary must satisfy the runbook's access, review and authorization
checks. Fast-only activation additionally requires trusted default-branch
classification, coverage parity and separately qualified candidate/landed-tree
evidence. Never promote the head-owned shadow classifier directly to a gate.

Leg PRs do not advance the assembled project. After separately authorized leg
merges, use the existing pin tooling and exact-pin composed checks. Never treat
code/spec/assembly PRs as a single atomic cross-repository stack.

## Full-CI documentation stack checkpoints

For an authorized manual documentation canary, record each member's head SHA,
base branch and base SHA before applying its review attestation. The upper
member names its immediate predecessor in both the PR base and `Depends-On`.
Every member retains the four full CI gates; a green advisory classifier is
not a substitute. Keep the branches unchanged while the queue is testing them.
