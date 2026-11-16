# P07/P09: disabled CI expansion preparation

This is preparation, not activation. `v13-prepared-cohort.json` is deliberately
separate from the active P05/P06 projection and delivery policy. No workflow,
live verifier or Mergify queue consumes this file. Merging this preparation
alone cannot grant skipping, a green review receipt or queue admission.

The source PRs are P07/code#97 and P09/code#103. Lane2 must finalize their
fixes and exact histories; lane3 must publish fresh exact-head READY reviews.
Coordination starts at opensoft/openRepoTools#165 comment6927765450. Old public
heads are observations only. A null source binding is pending, not a wildcard.
P08/code#106 stays held, including `.github/workflows/release.yml`.

The resolved cut includes P09's T237zzi (one trailing empty line removed;
unchanged AST), per lane2 comment6930368576 and lane3 ruling6930389021.
Lane1 published P07 `4e9821ab` and P09 `f4f0ebce`; their declared histories
start at P01 `7f1141be` and landed P03 `6aa8b5c0`, respectively. Each anchor
must contain the common prerequisite and already be in frozen main. This does
not permit rebasing, skipped commits or widening an inventory. Consent6928862535
is conditional; review links remain pending until actual exact-head reviews.

With acquired immutable objects in an isolated checkout, inspect a bound cohort:

```sh
python3 .github/ci/v13_expansion.py --main OBSERVED_MAIN_SHA
```

The inspector makes no network calls, changes no ref/index/worktree, and can
write only private immutable merge-preview objects. It rejects stale main,
unsupported histories, mixed paths, unsafe modes, nonempty markers, dependent
members and conflicts. A valid preview still requires **full CI** and grants
**no admission**. Review/consent links are context, not authenticated authority.

P09 changes a frozen foundation helper. Its before/after blobs must receive a
separate explicit foundation/landing review before any future activation; do
not broaden the live verifier or copy a new digest merely to clear a refusal.
Activation also needs current-main/source/review proofs, reviewed queue and
admission support, complete coverage parity and separate live-batch authority.
No single flag in this manifest can perform those steps.

These paired code/spec PRs stay open for review. No merge, live batch, ruleset
change/bypass, app grant, paid upgrade, release edit/tag, tool installation,
assembly-pin advance, shared-checkout refresh or lane/session change follows.
