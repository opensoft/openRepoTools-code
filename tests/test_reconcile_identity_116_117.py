# SPDX-License-Identifier: Apache-2.0
"""opensoft/openRepoTools#116 (its second half) and #117 (its second part):
what `lane-reconcile` says about a recorded tree that is not the tree its
record is about, and about one whose directory is gone while git still
registers it. Each case runs the real `lane-start` and `lanes-edit.sh` in the
sandbox `test_lifecycle_fail_open_113_114_115.py` builds (a bare origin, a
register clone, a fake tmux and gh, and a `git` that fails only the one call a
case names); nothing reaches the network.

  * #116. A sidecar recorded a tree's branch, head, upstream, dirty and
    unpushed counts, and `checkout`, which nothing compared. So an INDEPENDENT
    CLONE put on the recorded path, on the same branch at the same commit with
    no upstream, read exactly as the tree recorded, and was `ok`. A record now
    carries `repo:`, the path's git common directory, and a different one now
    is `wrong-repository`, counted toward recovery. A record with no `repo:`
    (every one a released helper wrote) is not compared, and an identity git
    cannot give now is `unreadable`, never a match.
  * #117. The sweep skipped every path a sidecar named, so a recorded tree
    whose directory was removed while its registration was kept read `missing`
    (or `possible-loss`) with no `git worktree prune` named; and where the
    record spelled the path through a symlink, git's physical spelling was not
    skipped and the one tree was named twice, `missing` and
    `stale-registration`. Now it is one row, which names the prune.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from test_lifecycle_fail_open_113_114_115 import (  # noqa: F401
    LANE, US, control_root, first_commit, make_box, ok, pytestmark, reconcile, rows, swapped)


@pytest.fixture
def box(tmp_path: Path):
    return make_box(tmp_path, tmp_path / "state")


def record(box, tree: Path) -> Path:
    """Record `tree` for the lane as `set-lane-tree` reads it now, and return
    its sidecar."""
    tid = ok(box, "set-lane-tree", LANE, str(tree), "--checkout", str(box.lane_dir)).strip()
    sidecar = control_root(box) / "trees" / f"{tid}.yaml"
    assert sidecar.is_file(), tid
    return sidecar


def classes(out: str) -> list:
    return [(r[2], r[3]) for r in rows(out, "TREE")]


def trees_line(out: str) -> list:
    found = rows(out, "TREES")
    assert len(found) == 1, out
    return found[0][1:]


# ------------------------------------------------------------------ #116

def test_116_a_tree_swapped_for_another_repository_reads_wrong_repository(box):
    first_commit(box)
    tree = box.lane_dir / ".claude" / "worktrees" / "w"
    box.git("-C", str(box.lane_dir), "worktree", "add", "-q", "-b", "feat/w", str(tree))
    sidecar = record(box, tree)
    recorded = sidecar.read_text(encoding="utf-8")
    ours = os.path.realpath(box.lane_dir / ".git")
    # `lane-trees`' row keeps its thirteen fields: its readers and the T018
    # goldens hold that shape, so the identity is read from the sidecar.
    listed = ok(box, "lane-trees", LANE).rstrip("\n").split("\n")
    assert len(listed) == 1 and len(listed[0].split(US)) == 13, listed
    swapped(box)
    assert classes(reconcile(box)) == [("ok", str(tree))]

    # THE SAME PATH, BRANCH AND COMMIT, AND NO UPSTREAM, IN AN INDEPENDENT CLONE.
    head = box.git("-C", str(tree), "rev-parse", "HEAD").strip()
    box.git("-C", str(box.lane_dir), "worktree", "remove", str(tree))
    box.git("clone", "-q", str(box.lane_dir), str(tree))
    box.git("-C", str(tree), "checkout", "-q", "--no-track", "-b", "feat/w", head)
    now = ok(box, "lane-tree-now", str(tree)).rstrip("\n").split(US)
    assert now == ["feat/w", head, "none", "0", "0"], now
    theirs = os.path.realpath(tree / ".git")
    assert theirs != ours

    out = reconcile(box)
    assert classes(out) == [("wrong-repository", str(tree))], out
    # The identity it was compared with is the one the record was filed with.
    assert f"\nrepo: {ours}\n" in recorded, recorded
    why = rows(out, "TREE")[0][4]
    assert f"recorded as a checkout of the repository at {ours}" in why, why
    assert f"git answers for the repository at {theirs} there now" in why, why
    assert "it is left exactly as it is" in why, why
    assert trees_line(out) == ["1 inventoried", "0 dirty or unpushed", "1 require recovery",
                               "0 unmanaged or stale"], out
    # Nothing was touched: the clone is still where and what it was.
    assert box.git("-C", str(tree), "rev-parse", "HEAD").strip() == head
    assert sidecar.read_text(encoding="utf-8") == recorded

    # AN OLD RECORD, WITH NO `repo:`, IS NOT COMPARED: it reads as it always did.
    sidecar.write_text("".join(line for line in recorded.splitlines(keepends=True)
                               if not line.startswith("repo: ")), encoding="utf-8")
    assert "repo:" not in sidecar.read_text(encoding="utf-8")
    out = reconcile(box)
    assert classes(out) == [("ok", str(tree))], out
    assert trees_line(out)[2] == "0 require recovery", out


def test_116_a_repository_git_cannot_name_now_is_unreadable_and_never_a_match(box):
    first_commit(box)
    tree = box.lane_dir / ".claude" / "worktrees" / "w"
    box.git("-C", str(box.lane_dir), "worktree", "add", "-q", "-b", "feat/w", str(tree))
    record(box, tree)
    swapped(box)
    out = reconcile(box, FAKE_GIT_FAIL=f"-C {tree} rev-parse --git-common-dir")
    assert classes(out) == [("unreadable", str(tree))], out
    why = rows(out, "TREE")[0][4]
    assert "which repository it is could not be read" in why, why
    assert f"repository at {os.path.realpath(box.lane_dir / '.git')}" in why, why
    assert trees_line(out)[2] == "1 require recovery", out


# ------------------------------------------------------------------ #117

@pytest.mark.parametrize("held", ["clean", "dirty"])
@pytest.mark.parametrize("spelling", ["direct", "symlinked"])
def test_117_a_recorded_tree_gone_with_its_registration_kept_is_one_row_naming_the_prune(
        box, tmp_path, spelling, held):
    """And the prune is named only where git holds a registration: a recorded
    tree removed with `git worktree remove` beside it is `missing` as before."""
    first_commit(box)
    base = box.lane_dir
    if spelling == "symlinked":
        # As the estate's `projects` link spells every checkout under it.
        link = tmp_path / "projects-link"
        link.symlink_to(box.lane_dir.parent, target_is_directory=True)
        base = link / box.lane_dir.name
    tree = base / ".claude" / "worktrees" / "gone"
    box.git("-C", str(box.lane_dir), "worktree", "add", "-q", "-b", "feat/gone", str(tree))
    if held == "dirty":
        (tree / "work.txt").write_text("uncommitted\n", encoding="utf-8")
    record(box, tree)
    tidy = box.lane_dir / ".claude" / "worktrees" / "tidy"
    box.git("-C", str(box.lane_dir), "worktree", "add", "-q", "-b", "feat/tidy", str(tidy))
    record(box, tidy)
    # The directory goes and git's registration of it stays; the tidy tree
    # goes with its registration.
    shutil.rmtree(tree)
    box.git("-C", str(box.lane_dir), "worktree", "remove", str(tidy))
    registered = box.git("-C", str(box.lane_dir), "worktree", "list", "--porcelain")
    assert f"worktree {os.path.realpath(tree.parent)}/gone\n" in registered, registered
    assert f"worktree {os.path.realpath(tidy)}\n" not in registered, registered
    swapped(box)

    out = reconcile(box)
    found = {r[3]: (r[2], r[4]) for r in rows(out, "TREE")}
    word = "missing" if held == "clean" else "possible-loss"
    assert len(rows(out, "TREE")) == 2 and sorted(found) == sorted([str(tree), str(tidy)]), out
    assert found[str(tree)][0] == word, out
    assert (f"git still registers it in {box.lane_dir}: "
            f"`git -C {box.lane_dir} worktree prune` is a person's act") in found[str(tree)][1], out
    assert found[str(tidy)][0] == "missing" and "worktree prune" not in found[str(tidy)][1], out
    assert "stale-registration" not in out
    assert trees_line(out) == ["2 inventoried", "0 dirty or unpushed", "2 require recovery",
                               "0 unmanaged or stale"], out
