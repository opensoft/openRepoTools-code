This is the **code leg** of openRepoTools (`openrepotools`): the implementation
and its tests.

**The project's rules are not here.** They are in the assembly root
`opensoft/openRepoTools`, in `AGENTS-shape.md` — read that before touching anything
that spans the legs. This leg is mounted there at `code/`, and the other leg,
`opensoft/openRepoTools-spec`, beside it at `../spec/`, once the root is cloned with
`--recurse-submodules`.

Working here is ordinary — an ordinary repository on an ordinary branch. What
advancing this leg does NOT do is advance the project: that is ONE commit in
`opensoft/openRepoTools` moving the gitlink, `contracts/code-pin.yaml` and every
workflow `@<sha>` for this leg together.

Being the code leg confers no authority over the implementation. The split is
navigation.

## What is particular to openRepoTools' code leg

The project's own instructions — driving `park`, `resume` and `status`, the
lane tooling's protocol, the pinned standard's three rules, how to test and the
CI policy — are the assembly root's `AGENTS.md`, and they govern here. This
section adds only what standing in this leg changes.

- **The suite runs here**: `git submodule update --init upstream/openRepoShape`,
  then `tests/run.sh`, which serializes every lane on a workstation behind
  `${TMPDIR:-/tmp}/openrepotools-pytest.lock` and passes any pytest argument on.
- **The pinned standard is here**: `upstream/openRepoShape`, recorded in
  `contracts/openreposhape-pin.yaml`. Never edit it in place, never pin a commit
  that is not on openRepoShape's `main`, and recompute the digest rather than
  adjust it — the root `AGENTS.md` gives the three rules in full.
- **The manuals and the specifications are not here.** They are the spec
  leg's `docs/` (`README-lanes.md`, `README-claude-current.md`), `openspec/` and
  `specs/`: `../spec/` when this leg is mounted in the assembly root, and
  `opensoft/openRepoTools-spec` when it is cloned on its own.
- **A feature's code is written in its code worktree**,
  `worktrees/<NNN-feature>/code/` under the assembly root, on the feature's
  branch. A genuine bounded amendment to an approved spec baseline is recorded
  in that worktree's `features/<NNN-feature>/openspec/`; a full proposal never
  is, and goes to the spec leg.
