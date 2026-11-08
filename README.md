# openRepoTools-code

The **code leg** of the `openrepotools` project: the implementation and its
tests. The requirements it implements live in
[`opensoft/openRepoTools-spec`](https://github.com/opensoft/openRepoTools-spec).

**Clone the assembly root, not this repository.** This leg is mounted as a
submodule at `code/` inside
[`opensoft/openRepoTools`](https://github.com/opensoft/openRepoTools), which
is what pins the commit of this repository that the project currently is:

```sh
git clone --recurse-submodules https://github.com/opensoft/openRepoTools.git
cd openRepoTools
make bootstrap
```

Working here directly is fine — it is an ordinary repository with an ordinary
branch. What advancing this leg does NOT do is advance the project: that is a
commit in the assembly root moving the gitlink, `contracts/code-pin.yaml` and
any workflow `@<sha>` reference together.

Being the code leg confers no authority over the implementation. The split is
navigation; authority travels in grants, and a project that keeps spec and
code in one repository is reviewed identically.

Topic: `xf-project-openrepotools`.

## What is in it

Every command `openRepoTools --install` places is a file at this leg's root —
`openRepoTools` itself, `park`, `resume`, `status` and the lane tooling — with
the alias table `repos.tsv`, the `skills/` and `commands/` it installs, the
suite under `tests/` (`tests/run.sh` runs it), the CI under
`.github/workflows/`, and the pinned standard at `upstream/openRepoShape`
(`contracts/openreposhape-pin.yaml`). Installing is unchanged: the one-liner in
the assembly root's `README.md` fetches the root's `openRepoTools`, which hands
over to the installer here at the commit the root pins.

The manuals — `docs/README-lanes.md` for the lane tooling and
`docs/README-claude-current.md` for `claude-current` and
`claude-restart-check` — and every specification are in
[`opensoft/openRepoTools-spec`](https://github.com/opensoft/openRepoTools-spec).

Licence: Apache-2.0. See [LICENSE](LICENSE).
