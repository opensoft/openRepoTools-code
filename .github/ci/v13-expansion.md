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

Renewed owner consent (issue165 comments6938017311 and6938099557) requires
P07 before P09. The disabled inspector therefore accepts only that order and
previews P07 first with the original foundation, followed by P09's declared
helper transition. Reversed order refuses; this does not change any live queue
or grant consent to a moved product head.

The resolved cut includes P09's T237zzi (one trailing empty line removed;
unchanged AST), per lane2 comment6930368576 and lane3 ruling6930389021.
Lane1 published P07 `4e9821ab` and P09 `f4f0ebce`; their declared histories
start at P01 `7f1141be` and landed P03 `6aa8b5c0`, respectively. Each anchor
must contain the common prerequisite and already be in frozen main. This does
not permit rebasing, skipped commits or widening an inventory. Consent6928862535
is conditional; review links remain pending until actual exact-head reviews.

Those old cuts are superseded. Current observed heads5a120647/b8f9e35a are
NOT READY under exact-head reviews6941178190/6940693024. Both source bindings,
histories, review and consent references are therefore empty/null pending the
next completed owner cuts. Observed hashes are diagnostic context only; they
cannot generate a preview. The helper `tests/sql_register_cleanup.py` is an
exact added regular-file inventory entry, per P07 handoff6940832411 and lane3
agreement6940947493. Its final T270 ownership record still must land in spec80;
declaring this path does not accept the helper's code or broaden live scopes.

The preparation ceilings are P07 16 commits and P09 24 commits,
counted from their respective declared anchors. P07's four-plus-nine-plus-three
chain is owner-confirmed in issue165 comment6935365475; P09 retains its prior
eight-plus-sixteen ceiling pending its final owner handoff. These are not automatic
bindings of unpublished heads. Exact bundles, complete ordered SHAs, current
review/consent and validation are still required. Larger or different chains
need explicit reviewed changes; never truncate history or restack a lane to
fit. Live policy limits and all fallback behavior remain unchanged.

These held limits do not fit the later26/58-commit observations and are not
being published as their qualification. Final counts need fresh explicit
boundary/prefix validation and independent review after the owners finish.

P07's final exported CX-31 tip18529e5a has a complete16-commit chain whose
prefixes and exact inventory were checked independently. The ceiling update
does not bind that head or satisfy its conditional consent: the genuine
exact-head review, new33-node hosted verification, fresh full CI and landed
spec80 notes remain separate gates. The observed P09 CX-31 chain has29 commits;
structural acquisition alone does not raise its ceiling or accept that cut.

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

The original preparation left both PRs open. Subsequent owner authority permits
checked preparation merges only after spec#80, fresh exact-head product reviews
and CI pass. Neither preparation merge activates delivery or authorizes a queue
command. The separately approved narrow live rollout still requires reviewed
live support and the complete canary gates above. P08 stays held; no ruleset
change/bypass, app grant, paid upgrade, release edit/tag, tool installation,
assembly-pin advance, shared-checkout refresh or lane/session change follows.
