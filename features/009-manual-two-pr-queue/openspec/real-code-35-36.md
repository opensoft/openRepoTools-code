# Bounded amendment: one real-code batch

On 2026-11-11 Brett approved adding a narrow manual real-code queue and batching
openRepoTools-code PRs #35 and #36 once full CI and exact-head Codex review pass,
then verifying the landed tree. This is an explicit, bounded exception to the
documentation-only pilot, not a replacement specification or a general rollout.

The new queue is restricted to the two PR numbers, their existing head branch
names, their exact allowed file vectors and base `main`. Reviewed head hashes
are checked by the operator immediately before queue commands; they are not
claimed to be supported Mergify SHA conditions. Changes require fresh evidence
and must not be forced into active lane branches.

Keep the documentation queue, all four original/candidate full CI gates, manual
entry, serial checks, maximum two members, and zero automatic retry/splitting.
No artificial dependency, rebase, retarget or lane takeover is needed: the two
existing PRs are independent. Acceptance requires actual two-member membership,
green combined CI and a final landed tree equal to the tested candidate tree.

Preserve lanes 1–5 and PR #32. No ruleset bypass, app-access, paid upgrade,
release, tag, image, installed-session or assembly-pin change is included.
