# SPDX-License-Identifier: Apache-2.0
"""Amendment 23, act 2's slice 2b: `lane-start` writes only through the lane's
own register checkout, and W moves only by fast-forward.

Until this slice `lane-start` wrote the handoff's Rule 3 stamp itself: it
published it under W's lock and then added, committed, pulled and pushed it in
W with no lock at all (lane openRepoTools-3's finding 282, its first writer).
Under the default resolution the lane's other writes already went through
`<W>-lanes/<lane>/` (slice 1a), so the stamp was the one write left in W, and
it read W's copy of the handoff, which nothing brought up to date.

Now:
  * `refresh-workspace` fast-forwards W before the first read and again once
    the writes are done, and the row is read from W after the first;
  * the lane's checkout is made at "5. the row", and its writable handoff path
    is printed beside the row's spelling;
  * the stamp is ONE `write-handoff --stamp` call, under the checkout's lock
    and S3/S4, and its exit is a note: the launch is refused only by a
    restart's own fences;
  * the first prompt is read from the file that call writes.

Each case drives a real `lane-start` in `test_lane_start_row_stamp`'s sandbox
with the default resolution (no `LANES_REPO`, no `LANES_FILE`) and the opt-in
`LANES_ROUTE_WRITES=1`. A "peer" is another clone of the sandbox's origin that
commits and pushes, as another workstation's lane does.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_a23_lane_start_read import (W_reflog, _no_clone_git, assert_W_moved_only_by_fast_forward,
                                      default_resolution, no_auto_gc, rows)
from test_lane_start_row_stamp import LANE, Sandbox, _checkout_of_length, pytestmark, short_root  # noqa: F401

HANDOFF = "Lane: repoZ-1 — single-use resume prompt\n\n# state\n\nthe lane's own words\n"
PEER_SID = "bbbb0001-2222-4000-8000-bbbb00012222"


# ------------------------------------------------------------------ helpers

def _origin(box: Sandbox, *args: str) -> str:
    return box.git("--git-dir", str(box.root / "origin.git"), *args)


def _published(box: Sandbox, rel: str) -> str:
    return _origin(box, "show", f"main:{rel}")


def _tip(box: Sandbox) -> str:
    return _origin(box, "rev-parse", "main").strip()


def _cell(box: Sandbox) -> str:
    """The handoff cell of the lane's published row."""
    found = [r for r in _published(box, "lanes/LANES.md").splitlines()
             if r.startswith(f"| `{LANE}`")]
    assert len(found) == 1, found
    return found[0].split("|")[6].strip()


def _peer(box: Sandbox) -> Path:
    p = box.root / "peer"
    if not p.exists():
        box.git("clone", "-q", str(box.root / "origin.git"), str(p))
        no_auto_gc(box, "-C", str(p))
    box.git("-C", str(p), "fetch", "-q", "origin", "main")
    box.git("-C", str(p), "merge", "-q", "--ff-only", "origin/main")
    return p


def _peer_push(box: Sandbox, files: dict[str, str], msg: str) -> None:
    p = _peer(box)
    for rel, text in files.items():
        (p / rel).parent.mkdir(parents=True, exist_ok=True)
        (p / rel).write_text(text, encoding="utf-8")
    box.git("-C", str(p), "add", "--", *files)
    box.git("-C", str(p), "commit", "-q", "-m", msg)
    box.git("-C", str(p), "push", "-q", "origin", "HEAD:main")


def _edit(box: Sandbox, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(box.bin / "lanes-edit.sh"), *args], env=env or box.env,
                          capture_output=True, text=True, timeout=180, check=False)


def _boxed(tmp_path: Path, short_root: Path) -> tuple[Sandbox, Path, Path]:
    """The sandbox with the default resolution and the opt-in, W kept from gc."""
    box = Sandbox(tmp_path)
    checkout = default_resolution(box)
    no_auto_gc(box, "-C", str(box.wip))
    no_auto_gc(box, "--git-dir", str(box.root / "origin.git"))
    lane_dir = _checkout_of_length(short_root, None)
    box.checkout(lane_dir)
    return box, checkout, lane_dir


def _started(tmp_path: Path, short_root: Path) -> tuple[Sandbox, Path, Path, list[str]]:
    """A new lane's first start, with W's reflog as it stood before it."""
    box, checkout, lane_dir = _boxed(tmp_path, short_root)
    before = W_reflog(box)
    first = box.start("--dir", str(lane_dir), window_name="claude")
    assert first.returncode == 0, first.stderr
    assert (checkout / ".git").is_dir(), "the first start made the lane's checkout"
    assert "own register checkout could not be made" not in first.stderr, first.stderr
    return box, checkout, lane_dir, before


def _assert_nothing_unpublished(box: Sandbox, checkout: Path) -> None:
    cherry = box.git("-C", str(checkout), "cherry", "origin/main", "HEAD")
    assert not [c for c in cherry.splitlines() if c.startswith("+")], cherry


# -------------------------------------------------------------------- cases

def test_launch_creates_checkout_and_writes_only_there(tmp_path, short_root):
    box, checkout, _lane_dir, before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")

    second = box.start("--fresh", window_name=LANE)
    assert second.returncode == 0, second.stderr
    assert "W was not fast-forwarded" not in second.stderr, second.stderr
    assert "as W last fetched it" not in second.stderr, second.stderr

    register = _published(box, "lanes/LANES.md")
    assert sum(1 for r in register.splitlines() if r.startswith(f"| `{LANE}`")) == 1
    row = [r for r in register.splitlines() if r.startswith(f"| `{LANE}`")][0]
    assert "LIVE · " in row, row
    assert "RESUMED by " in row, row
    assert f"RESUMED — lane {LANE}, session " in _published(box, f"lanes/log/{LANE}.md")
    stamped = _published(box, cell)
    assert f"(lane {LANE}) at " in stamped, stamped
    assert stamped.splitlines()[2].startswith("RESUMED by "), stamped
    assert _origin(box, "log", "-1", "--format=%s%n%b", "main").startswith(f"handoff({LANE}@Eagle): RESUMED by ")
    assert f"Lane: {LANE}" in _origin(box, "log", "-1", "--format=%b", "main")

    assert_W_moved_only_by_fast_forward(box, before)
    assert box.git("-C", str(box.wip), "rev-parse", "HEAD").strip() == _tip(box), "W ends on origin's tip"
    _assert_nothing_unpublished(box, checkout)


def test_launch_fast_forwards_W_before_and_after(tmp_path, short_root):
    box, checkout, lane_dir = _boxed(tmp_path, short_root)
    made = _edit(box, "lane-checkout", LANE, "--create")
    assert made.returncode == 0, made.stderr
    before = W_reflog(box)
    # Another workstation's start of this lane: its row, and its handoff.
    register = _published(box, "lanes/LANES.md")
    row = (f"| `{LANE}` | harness `{PEER_SID}` (minted by lane-start, 2026-10-22T00:00:00Z) | "
           f"Eagle / default / peer | 2026-10-22T00:00Z | none | handoffs/repoZ/peer.md | "
           f"LIVE · 2026-10-22T00:00:00Z · STARTED by {PEER_SID} (lane {LANE}) — lane-start on Eagle: row created |")
    _peer_push(box, {"lanes/LANES.md": register + row + "\n", "handoffs/repoZ/peer.md": HANDOFF},
               "a peer's start of the lane")

    start = box.start("--dir", str(lane_dir), "--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert "ALREADY has a row" not in start.stderr, start.stderr
    assert len(rows(box.wip / "lanes" / "LANES.md")) == 1, "W was brought up to the peer's row first"
    assert box.git("-C", str(box.wip), "rev-parse", "HEAD").strip() == _tip(box), "and to the stamp after"
    assert _origin(box, "log", "-1", "--format=%s", "main").startswith(f"handoff({LANE}@Eagle): RESUMED by ")
    assert_W_moved_only_by_fast_forward(box, before)
    _assert_nothing_unpublished(box, checkout)


def test_launch_not_refused_when_S3_refuses(tmp_path, short_root):
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    assert _edit(box, "refresh-workspace").returncode == 0
    foreign = checkout / "handoffs" / "repoQ" / "foreign.md"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("a person's file, staged and never committed\n", encoding="utf-8")
    box.git("-C", str(checkout), "add", "--", "handoffs/repoQ/foreign.md")
    tip = _tip(box)

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert _tip(box) == tip, "nothing was published, from the lane's checkout or from W"
    assert "RESUMED by " not in _published(box, cell)
    assert "the stamp line it would have written under the handoff's header block: RESUMED by " in start.stderr, start.stderr
    assert "handoffs/repoQ/foreign.md" in box.git("-C", str(checkout), "diff", "--cached", "--name-only")
    assert box.git("-C", str(box.wip), "status", "--porcelain") == "", "W took no write"


def test_the_1312Z_shape_all_three_writes_pushed(tmp_path, short_root):
    """The shape of 2026-10-17T13:12Z: the lane's checkout clean, nothing
    ahead and ten commits behind, one of them a change to the row beside the
    lane's, one the lane's handoff. The row state, the log line and the stamp
    all land on origin."""
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    register = _published(box, "lanes/LANES.md")
    other = (f"| `repoZ-2` | harness `{PEER_SID}` | Eagle / default / peer | 2026-10-22T00:00Z | none | "
             "handoffs/repoZ/two.md | LIVE · 2026-10-22T00:00:00Z · STARTED by peer |")
    _peer_push(box, {"lanes/LANES.md": register + other + "\n"}, "repoZ-2's row")
    changed = other.replace("STARTED by peer", "PAUSED by peer")
    _peer_push(box, {"lanes/LANES.md": register + changed + "\n"}, "repoZ-2's state")
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff")
    for n in range(7):
        _peer_push(box, {f"handoffs/repoQ/note-{n}.md": f"note {n}\n"}, f"another lane's note {n}")
    box.git("-C", str(checkout), "fetch", "-q", "origin", "main")
    assert box.git("-C", str(checkout), "rev-list", "--left-right", "--count",
                   "HEAD...origin/main").split() == ["0", "10"]
    assert box.git("-C", str(checkout), "status", "--porcelain") == ""

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    published = _published(box, "lanes/LANES.md")
    row = [r for r in published.splitlines() if r.startswith(f"| `{LANE}`")]
    assert len(row) == 1, row
    assert "RESUMED by " in row[0], row
    assert changed in published, "the peer's change to the row beside it is kept"
    assert f"RESUMED — lane {LANE}, session " in _published(box, f"lanes/log/{LANE}.md")
    assert _published(box, cell).splitlines()[2].startswith("RESUMED by "), _published(box, cell)
    _assert_nothing_unpublished(box, checkout)


def test_first_prompt_reads_the_checkout_copy(tmp_path, short_root):
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    assert _edit(box, "refresh-workspace").returncode == 0
    stray = box.wip / cell
    stray.write_text(HANDOFF.replace("# state", "# state STRAY-W-EDIT"), encoding="utf-8")

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert "RESUMED by " in start.stdout, start.stdout
    assert f"(lane {LANE}) at " in start.stdout, start.stdout
    assert "STRAY-W-EDIT" not in start.stdout, start.stdout
    assert "STRAY-W-EDIT" not in _published(box, cell), "W's stray never reaches origin"
    assert "STRAY-W-EDIT" in stray.read_text(encoding="utf-8"), "and W's stray is a person's to settle"


def test_writable_handoff_path_printed(tmp_path, short_root):
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    second = box.start(window_name=LANE)
    assert second.returncode == 0, second.stderr
    assert f"{checkout}/{cell}" in second.stderr, second.stderr
    assert cell in second.stderr


def test_dry_run_creates_nothing_and_leaves_W(tmp_path, short_root):
    box, checkout, lane_dir = _boxed(tmp_path, short_root)
    box.env.pop("LANES_ROUTE_WRITES")
    first = box.start("--dir", str(lane_dir), window_name="claude")
    assert first.returncode == 0, first.stderr
    assert not checkout.parent.exists(), "without the opt-in the row is W's"
    box.env["LANES_ROUTE_WRITES"] = "1"
    _peer_push(box, {_cell(box): HANDOFF}, "the lane's handoff, written elsewhere")
    head = box.git("-C", str(box.wip), "rev-parse", "HEAD")
    before = W_reflog(box)

    plan = box.start("--fresh", "--dry-run", window_name=LANE)
    assert plan.returncode == 0, plan.stderr
    assert not checkout.exists(), "a dry run makes no lane checkout"
    assert not checkout.parent.exists(), "and no folder for one"
    assert box.git("-C", str(box.wip), "rev-parse", "HEAD") == head, "W did not move"
    assert W_reflog(box) == before
    for planned in ("refresh-workspace", f"lane-checkout {LANE} --create", f"write-handoff {LANE} --stamp"):
        assert any("PLAN" in line and planned in line for line in plan.stderr.splitlines()), (planned, plan.stderr)


def test_publish_failure_no_longer_refuses_a_plain_resume(tmp_path, short_root):
    """`lane-start:4455` died 2 after the row and the log were written, when
    `publish-handoff` failed, a lock wait over 60 s included. The stamp is the
    record of the resume, never its licence."""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    assert _edit(box, "refresh-workspace").returncode == 0
    wrapper = box.root / "refusing-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
case "${{1-}}" in publish-handoff|write-handoff) echo "test: $1 refused" >&2; exit 1 ;; esac
exec '{box.bin / "lanes-edit.sh"}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)

    start = subprocess.run([str(box.bin / "lane-start"), "repoZ", "1", "--no-launch", "--fresh"],
                           env=dict(box.env, LANES_EDIT=str(wrapper), FAKE_TMUX_WINDOW_NAME=LANE),
                           capture_output=True, text=True, timeout=180, check=False)
    assert start.returncode == 0, start.stderr
    assert "test: write-handoff refused" in start.stderr, start.stderr
    assert "RESUMED by " in start.stderr
    assert "write-handoff" in start.stderr
    assert "Nothing was launched" not in start.stderr
    assert "RESUMED by " not in _published(box, cell)
    assert os.path.exists(box.wip / cell)


# ------------------------------------------- fix round 1 (#316's review)

def _first_prompt_note(stderr: str) -> str:
    """5d's one line where the launch goes on with no first prompt."""
    found = [line for line in stderr.splitlines() if "launched with no first prompt" in line]
    assert len(found) == 1, stderr
    return found[0]


def test_no_lane_copy_launches_with_no_first_prompt_never_W_copy(tmp_path, short_root):
    """727, and question 2 of lane openRepoTools-3's review of #316: where the
    lane's own copy of its handoff is not there (here its checkout cannot be
    made), the launch goes on with NO first prompt. It names the missing file
    and the command that makes the checkout, and it never reads W's copy,
    which does not carry this resume's stamp (Amendment 23 S2: reads follow
    the writes, never through W)."""
    box = Sandbox(tmp_path)
    checkout = default_resolution(box, route=False)
    no_auto_gc(box, "-C", str(box.wip))
    lane_dir = _checkout_of_length(short_root, None)
    box.checkout(lane_dir)
    first = box.start("--dir", str(lane_dir), window_name="claude")
    assert first.returncode == 0, first.stderr
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    box.env["LANES_ROUTE_WRITES"] = "1"
    assert _edit(box, "refresh-workspace").returncode == 0
    assert "the lane's own words" in (box.wip / cell).read_text(encoding="utf-8"), "W holds the handoff"
    box.env["LANES_GIT"] = str(_no_clone_git(box))

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert "own register checkout could not be made" in start.stderr, start.stderr
    assert not checkout.exists()
    assert "own words" not in start.stdout, "W's copy is never the first prompt"
    assert "first prompt: the top block of" not in start.stderr, start.stderr
    note = _first_prompt_note(start.stderr)
    assert f"{checkout}/{cell}" in note, note
    assert f"lane-checkout {LANE} --create" in note, note


def test_no_git_stamp_says_written_and_not_committed(tmp_path, short_root):
    """721, and question 4 of the review of #316 (rv2b's SHOULD 1): under
    `LANES_NO_GIT=1` `write-handoff` writes the stamp, commits nothing and
    exits 0. The exit-0 words say that, never "committed and pushed"."""
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    # NOTHING IS FETCHED UNDER LANES_NO_GIT (S3 returns at once), so the
    # checkout is brought up to the handoff first.
    box.git("-C", str(checkout), "fetch", "-q", "origin", "main")
    box.git("-C", str(checkout), "merge", "-q", "--ff-only", "origin/main")
    head = box.git("-C", str(checkout), "rev-parse", "HEAD")
    tip = _tip(box)
    box.env["LANES_NO_GIT"] = "1"

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert (checkout / cell).read_text(encoding="utf-8").splitlines()[2].startswith("RESUMED by "), \
        "the stamp is written in the lane's checkout"
    assert box.git("-C", str(checkout), "rev-parse", "HEAD") == head, "and nothing is committed"
    assert _tip(box) == tip, "or pushed"
    assert "committed and pushed" not in start.stderr, start.stderr
    said = [line for line in start.stderr.splitlines() if "LANES_NO_GIT=1" in line and "NOT committed" in line]
    assert len(said) == 1, start.stderr
    assert f"{checkout}/{cell}" in said[0], said


NEWER = "Lane: repoZ-1 — single-use resume prompt\n\n# state\n\nNEWER BLOCK FROM ANOTHER WORKSTATION\n"


def test_refused_stamp_names_a_checkout_copy_behind_origin(tmp_path, short_root):
    """725 of the review of #316: the lane's checkout refuses a plain launch's
    stamp (a stray is staged there) while origin holds a newer PAUSED block
    from another workstation. The launch goes on with the checkout's copy,
    and says that origin's differs: it names both copies and the command that
    brings the checkout up to date."""
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff")
    box.git("-C", str(checkout), "fetch", "-q", "origin", "main")
    box.git("-C", str(checkout), "merge", "-q", "--ff-only", "origin/main")
    _peer_push(box, {cell: NEWER}, "a newer PAUSED block, from another workstation")
    foreign = checkout / "handoffs" / "repoQ" / "foreign.md"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("a person's file, staged and never committed\n", encoding="utf-8")
    box.git("-C", str(checkout), "add", "--", "handoffs/repoQ/foreign.md")

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert "Rule 3's stamp was NOT written" in start.stderr, start.stderr
    said = [line for line in start.stderr.splitlines() if "is not origin's" in line]
    assert len(said) == 1, start.stderr
    assert f"{checkout}/{cell}" in said[0], said
    assert f"origin/main:{cell}" in said[0], said
    assert f"git -C {checkout} merge --ff-only origin/main" in said[0], said
    assert "own words" in start.stdout, "the first prompt is the checkout's copy, as said"
    assert "NEWER BLOCK" not in start.stdout


def _duplicate_row(register: str) -> str:
    """The register with the lane's row written twice, one line each."""
    lines = register.splitlines(keepends=True)
    found = [i for i, r in enumerate(lines) if r.startswith(f"| `{LANE}`")]
    assert len(found) == 1, found
    return "".join(lines[:found[0] + 1] + [lines[found[0]]] + lines[found[0] + 1:])


def _duplicate_refusal(stderr: str) -> str:
    said = [line for line in stderr.splitlines() if f"rows for lane {LANE}" in line]
    assert len(said) == 1, stderr
    return said[0]


def test_duplicate_row_only_in_W_is_named_a_stray_there(tmp_path, short_root):
    """730 of lane openRepoTools-3's review of #316: under the opt-in, a
    duplicate row that only W's working tree shows is a stray in W, the
    readers' copy, where no tool writes (Amendment 23 S5). The refusal says
    so, and never sends a merge, or a commit, to W."""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    register = box.wip / "lanes" / "LANES.md"
    register.write_text(_duplicate_row(register.read_text(encoding="utf-8")), encoding="utf-8")
    tip = _tip(box)

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 2, start.stderr
    said = _duplicate_refusal(start.stderr)
    assert "is a stray in W" in said, said
    assert "origin/main, as W last fetched it, has 1" in said, said
    assert "Merge them into one row" not in said, said
    assert "lanes-edit.sh commit" not in said, said
    assert _tip(box) == tip, "nothing was written"


def test_published_duplicate_row_is_refused_before_W_is_named(tmp_path, short_root):
    """730: under the opt-in, a duplicate row that origin carries never reaches
    the words that send a merge to W. `canon-lane` reads the published
    register after W is fast-forwarded and refuses the two rows first
    (Amendment 15(d)), naming the merge and the push; nothing is written. (A
    pin, green at the parent too: it is why the duplicate-row refusal under
    the opt-in only ever meets a stray in W.)"""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    _peer_push(box, {"lanes/LANES.md": _duplicate_row(_published(box, "lanes/LANES.md"))},
               "a duplicate row for the lane, from another workstation")
    tip = _tip(box)

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 2, start.stderr
    assert f"the PUBLISHED register spells lane {LANE} two ways" in start.stderr, start.stderr
    assert "Merge them into one row by hand in" not in start.stderr, start.stderr
    assert not [line for line in start.stderr.splitlines() if f"rows for lane {LANE}" in line], start.stderr
    assert _tip(box) == tip, "nothing was written"


def test_stamp_exit_6_says_what_the_helper_said_not_kept_on_HEAD(tmp_path, short_root):
    """982 of lane openRepoTools-3's review of #311, which 2b's words share:
    `write-handoff`'s 6 is not one state. `git add` or `commit` failed and
    nothing is committed, or the commit is kept on HEAD and named; and with
    2a's 604, an 8(d) handoff's commit or push in its own repository failed.
    So lane-start's note points at the helper's words, and names the publish
    act only for a commit kept in this lane's register checkout. (It also
    pins the battery's survivor LS45: the 6 arm falling to the generic note.)"""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    real = box.bin / "lanes-edit.sh"
    wrapper = box.root / "six-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = write-handoff ]; then '{real}' "$@"; exit 6; fi
exec '{real}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)

    start = subprocess.run([str(box.bin / "lane-start"), "repoZ", "1", "--no-launch", "--fresh"],
                           env=dict(box.env, LANES_EDIT=str(wrapper), FAKE_TMUX_WINDOW_NAME=LANE),
                           capture_output=True, text=True, timeout=180, check=False)
    assert start.returncode == 0, start.stderr
    said = [line for line in start.stderr.splitlines() if "`write-handoff` exited 6" in line]
    assert len(said) == 1, start.stderr
    assert "KEPT on HEAD" not in said[0], said
    assert "and NOT published" in said[0], said
    assert "its words above say whether a commit was made, where it is kept" in said[0], said
    assert f"LANES_LANE={LANE} " in said[0], said
    assert "the publish act" in said[0], said


def test_first_prompt_follows_a_handoff_a_peer_moved_during_the_stamp(tmp_path, short_root):
    """rv2b's NIT 1 on #316: a peer moves the lane's handoff, and the row's
    cell with it, while this launch stamps it. The write's replay follows the
    cell and stamps the moved file, and 5d reads THAT file, not the path
    `handoff-path` named before the write, which is gone from the checkout."""
    box, checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    moved = cell[:-len(".md")] + "-moved.md"
    peer = _peer(box)
    real = box.bin / "lanes-edit.sh"
    mark = box.root / "moved.mark"
    wrapper = box.root / "moving-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = write-handoff ] && [ ! -e '{mark}' ]; then
  : > '{mark}'
  git -C '{peer}' fetch -q origin main && git -C '{peer}' merge -q --ff-only origin/main &&
    git -C '{peer}' mv -- '{cell}' '{moved}' &&
    sed -i 's#{cell}#{moved}#' '{peer}/lanes/LANES.md' &&
    git -C '{peer}' commit -q -am 'a peer moves the handoff' &&
    git -C '{peer}' push -q origin HEAD:main || exit 99
fi
exec '{real}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)

    start = subprocess.run([str(box.bin / "lane-start"), "repoZ", "1", "--no-launch", "--fresh"],
                           env=dict(box.env, LANES_EDIT=str(wrapper), FAKE_TMUX_WINDOW_NAME=LANE),
                           capture_output=True, text=True, timeout=180, check=False)
    assert start.returncode == 0, start.stderr
    assert mark.exists(), "the peer moved the handoff during the stamp"
    assert _cell(box) == moved
    assert "RESUMED by " in _published(box, moved)
    assert f"{checkout}/{moved}" in start.stderr, start.stderr
    assert "launched with no first prompt" not in start.stderr, start.stderr
    assert "RESUMED by " in start.stdout, (start.stdout, start.stderr)
    assert "own words" in start.stdout, start.stdout


# ------------------------------------------- the mutant battery's survivors (item 10)

def _peer_start_row() -> str:
    """Another workstation's start of this lane: its row, naming its handoff."""
    return (f"| `{LANE}` | harness `{PEER_SID}` (minted by lane-start, 2026-10-22T00:00:00Z) | "
            f"Eagle / default / peer | 2026-10-22T00:00Z | none | handoffs/repoZ/peer.md | "
            f"LIVE · 2026-10-22T00:00:00Z · STARTED by {PEER_SID} (lane {LANE}) — lane-start on Eagle: row created |")


def _recording(box: Sandbox) -> tuple[Path, Path]:
    """A `LANES_EDIT` that records each call's verb and `LANES_LANE`, then runs
    the real helper."""
    calls = box.root / "lanes-edit-calls.log"
    wrapper = box.root / "recording-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
printf '%s LANES_LANE=%s\\n' "${{1-}}" "${{LANES_LANE-<unset>}}" >> '{calls}'
exec '{box.bin / "lanes-edit.sh"}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper, calls


def _verbs(calls: Path, verb: str) -> list[str]:
    return [line for line in calls.read_text(encoding="utf-8").splitlines() if line.startswith(verb + " ")]


def test_no_refresh_of_W_without_the_opt_in(tmp_path, short_root):
    """Battery survivor LS03 (slice 2b's decision 2): without the opt-in W is
    the write checkout, which every write's S3 fast-forwards under its own
    lock, so the start asks for no `refresh-workspace`."""
    box = Sandbox(tmp_path)
    default_resolution(box, route=False)
    lane_dir = _checkout_of_length(short_root, None)
    box.checkout(lane_dir)
    wrapper, calls = _recording(box)
    box.env["LANES_EDIT"] = str(wrapper)

    first = box.start("--dir", str(lane_dir), window_name="claude")
    assert first.returncode == 0, first.stderr
    assert _verbs(calls, "canon-lane"), "the recorder saw the start's calls"
    assert _verbs(calls, "refresh-workspace") == [], calls.read_text(encoding="utf-8")


def test_no_refresh_of_W_for_a_callers_LANES_REPO(tmp_path, short_root):
    """Battery survivor LS02 (decision 2): a caller's explicit `LANES_REPO` and
    `LANES_FILE` are the caller's register, not W, so even under the opt-in
    the start asks for no `refresh-workspace`."""
    box = Sandbox(tmp_path)                 # LANES_REPO and LANES_FILE name box.wip
    box.env["LANES_ROUTE_WRITES"] = "1"
    lane_dir = _checkout_of_length(short_root, None)
    box.checkout(lane_dir)
    wrapper, calls = _recording(box)
    box.env["LANES_EDIT"] = str(wrapper)

    first = box.start("--dir", str(lane_dir), window_name="claude")
    assert first.returncode == 0, first.stderr
    assert _verbs(calls, "canon-lane"), "the recorder saw the start's calls"
    assert _verbs(calls, "refresh-workspace") == [], calls.read_text(encoding="utf-8")


def test_a_refresh_that_could_not_fast_forward_reads_the_row_from_origin(tmp_path, short_root):
    """Battery survivors LS07, LS10 and LS12 (decisions 2 and 3): where
    `refresh-workspace` cannot fast-forward W, here because W holds a commit
    of its own, the launch says so and goes on, and it reads the lane's row
    from origin/main as W last fetched it, never from W's working tree, which
    is behind: the row a peer pushed is found, and no second row is offered."""
    box, _checkout, lane_dir = _boxed(tmp_path, short_root)
    made = _edit(box, "lane-checkout", LANE, "--create")
    assert made.returncode == 0, made.stderr
    (box.wip / "local-note.md").write_text("a commit only W has\n", encoding="utf-8")
    box.git("-C", str(box.wip), "add", "--", "local-note.md")
    box.git("-C", str(box.wip), "commit", "-q", "-m", "a commit only W has")
    _peer_push(box, {"lanes/LANES.md": _published(box, "lanes/LANES.md") + _peer_start_row() + "\n",
                     "handoffs/repoZ/peer.md": HANDOFF}, "a peer's start of the lane")

    start = box.start("--dir", str(lane_dir), "--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert "W was not fast-forwarded before this launch reads it" in start.stderr, start.stderr
    assert "row is read from origin/main as W last fetched it" in start.stderr, start.stderr
    assert "ALREADY has a row" not in start.stderr, start.stderr
    assert rows(box.wip / "lanes" / "LANES.md") == [], "W's working tree is still behind"
    published = [r for r in _published(box, "lanes/LANES.md").splitlines() if r.startswith(f"| `{LANE}`")]
    assert len(published) == 1, published


def test_the_stamp_is_written_with_LANES_LANE(tmp_path, short_root):
    """Battery survivor LS41 (decision 5): the stamp's `write-handoff` carries
    `LANES_LANE`, as every write of a lane does (Amendment 23 S1). The helper
    also routes this verb by its lane argument today, so only the call shows
    it."""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    wrapper, calls = _recording(box)
    box.env["LANES_EDIT"] = str(wrapper)

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert _verbs(calls, "write-handoff") == [f"write-handoff LANES_LANE={LANE}"], calls.read_text(encoding="utf-8")


def test_unrouted_start_behind_a_peers_row_names_refresh_workspace(tmp_path, short_root):
    """Battery survivor LS17 (decision 9): without the opt-in, with the default
    resolution, W is the register read and nothing refreshes it first. Where
    a peer has published the lane's row and W is behind, the start refuses a
    second row, and its recovery is `refresh-workspace`, the one act that
    moves W (only ever a fast-forward), never a fetch and merge typed in W."""
    box = Sandbox(tmp_path)
    default_resolution(box, route=False)
    lane_dir = _checkout_of_length(short_root, None)
    box.checkout(lane_dir)
    _peer_push(box, {"lanes/LANES.md": _published(box, "lanes/LANES.md") + _peer_start_row() + "\n",
                     "handoffs/repoZ/peer.md": HANDOFF}, "a peer's start of the lane")
    tip = _tip(box)

    start = box.start("--dir", str(lane_dir), window_name="claude")
    assert start.returncode == 2, start.stderr
    assert "ALREADY has a row" in start.stderr, start.stderr
    assert "refresh-workspace   # W is only ever fast-forwarded" in start.stderr, start.stderr
    assert "merge --ff-only origin/" not in start.stderr, start.stderr
    assert _tip(box) == tip, "nothing was written"


def test_a_row_only_in_W_is_named_a_stray_there(tmp_path, short_root):
    """Battery survivor LS19 (decision 9): under the opt-in, a row that W's
    working tree carries and origin does not is a stray in W, the readers'
    copy, where no tool writes (Amendment 23 S5). The recovery says so and
    makes it a write of the lane's own checkout, never a publish from W."""
    box, _checkout, lane_dir = _boxed(tmp_path, short_root)
    register = box.wip / "lanes" / "LANES.md"
    register.write_text(register.read_text(encoding="utf-8") + _peer_start_row() + "\n", encoding="utf-8")

    start = box.start("--dir", str(lane_dir), window_name="claude")
    assert f"this checkout has a row for {LANE} and the register on origin/main has none" in start.stderr, \
        start.stderr
    assert "RECOVERY — that row is a stray in W" in start.stderr, start.stderr
    assert "publish the register from here" not in start.stderr, start.stderr


# ------------------------------------------------- part 2: on slice 2a's round (723)

SIBLING_WORDS = "not this lane's words"


def _sibling_handoff(box: Sandbox) -> Path:
    """Lane repoZ-2's own clone of the register beside W, its handoff
    committed there (lane openRepoTools-3's 723 scenario)."""
    sib = Path(os.path.realpath(box.wip) + "-lanes") / "repoZ-2"
    box.git("clone", "-q", str(box.root / "origin.git"), str(sib))
    no_auto_gc(box, "-C", str(sib))
    f = sib / "handoffs" / "repoZ" / "two.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"Lane: repoZ-2 — single-use resume prompt\n\n# state\n\n{SIBLING_WORDS}\n", encoding="utf-8")
    box.git("-C", str(sib), "add", "--", "handoffs/repoZ/two.md")
    box.git("-C", str(sib), "commit", "-q", "-m", "repoZ-2's handoff")
    return f


def _with_cell(box: Sandbox, cell: str) -> str:
    """The published register with the lane's row naming `cell` as its handoff."""
    out = []
    for line in _published(box, "lanes/LANES.md").splitlines(keepends=True):
        if line.startswith(f"| `{LANE}`"):
            cells = line.split("|")
            cells[6] = f" {cell} "
            line = "|".join(cells)
        out.append(line)
    return "".join(out)


def test_a_cell_in_a_sibling_lanes_checkout_is_neither_stamped_nor_delivered(tmp_path, short_root):
    """723 of lane openRepoTools-3's review of #316, at lane-start's two call
    sites: the lane's row cell names lane repoZ-2's handoff, in repoZ-2's own
    clone of the register beside W. Since slice 2a's 601 (A54) `handoff-path`
    and `write-handoff` refuse a handoff in another checkout of the register,
    so the stamp writes nothing there, and 5d, which reads only the file
    `handoff-path` names (727), delivers none of repoZ-2's block: the launch
    goes on with no first prompt, and says why."""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    f = _sibling_handoff(box)
    sib = f.parents[2]
    _peer_push(box, {"lanes/LANES.md": _with_cell(box, str(f))}, "the lane's cell names repoZ-2's handoff")
    text, head = f.read_text(encoding="utf-8"), box.git("-C", str(sib), "rev-parse", "HEAD")

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert f.read_text(encoding="utf-8") == text, "nothing was written in the sibling's handoff"
    assert box.git("-C", str(sib), "status", "--porcelain") == "", "the sibling's checkout is clean"
    assert box.git("-C", str(sib), "rev-parse", "HEAD") == head, "and took no commit"
    assert SIBLING_WORDS not in start.stdout, start.stdout
    assert "in another checkout of the register beside W" in start.stderr, start.stderr
    assert "launched with no first prompt" in start.stderr, start.stderr



def _other_repository(box: Sandbox, *, origin: bool = True) -> Path:
    """Another repository, not the register (Amendment 8(d)): its handoff
    committed on `main`, and (with `origin`) a bare origin `main` tracks."""
    other = box.root / "other"
    box.git("init", "-q", "-b", "main", str(other))
    no_auto_gc(box, "-C", str(other))
    (other / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    box.git("-C", str(other), "add", "--", "handoff.md")
    box.git("-C", str(other), "commit", "-q", "-m", "another repository's handoff")
    if origin:
        bare = box.root / "other.git"
        box.git("init", "-q", "--bare", "-b", "main", str(bare))
        box.git("-C", str(other), "remote", "add", "origin", str(bare))
        box.git("-C", str(other), "push", "-q", "-u", "origin", "main")
    return other


def test_an_8d_cell_is_stamped_committed_and_pushed_in_its_own_repository(tmp_path, short_root):
    """722 of lane openRepoTools-3's review of #316, at lane-start's stamp:
    slice 2a's 604 (A57) commits and pushes an Amendment 8(d) handoff in its
    own repository, as e2037b9 did. The stamp is there, committed and pushed
    to that repository's origin and its tree clean; the register's origin
    takes no stamp commit; the first prompt is that file's top block; and the
    exit-0 words point at the helper's, which say where it was committed (a
    0 may also commit nothing, slice 3's F24)."""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    other = _other_repository(box)
    _peer_push(box, {"lanes/LANES.md": _with_cell(box, str(other / "handoff.md"))},
               "the lane's cell names another repository's handoff")
    before = box.git("-C", str(other), "rev-parse", "HEAD").strip()

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    stamped = (other / "handoff.md").read_text(encoding="utf-8")
    assert stamped.splitlines()[2].startswith("RESUMED by "), stamped
    o = ["-C", str(other)]
    assert box.git(*o, "status", "--porcelain") == "", "its tree is clean"
    assert box.git(*o, "rev-parse", "HEAD~1").strip() == before
    assert box.git(*o, "log", "-1", "--format=%s").startswith(f"handoff({LANE}@Eagle): RESUMED by ")
    assert (box.git("--git-dir", str(box.root / "other.git"), "rev-parse", "main").strip()
            == box.git(*o, "rev-parse", "HEAD").strip()), "and its origin holds the commit"
    assert not [s for s in _origin(box, "log", "--format=%s", "main").splitlines()
                if s.startswith(f"handoff({LANE}@Eagle): RESUMED by ")], "the register took no stamp commit"
    assert "committed there and pushed to origin/main" in start.stderr, start.stderr
    assert "handoff stamped through `write-handoff`, which exited 0: " in start.stderr, start.stderr
    assert "or that nothing was committed" in start.stderr, start.stderr
    assert "own words" in start.stdout, start.stdout


def test_an_8d_stamp_whose_push_fails_there_says_what_the_helper_said(tmp_path, short_root):
    """982 of lane openRepoTools-3's review of #311 (2b's words share it), its
    8(d) case: another repository with no origin, so slice 2a's 604 commits
    the stamp there and cannot push it, and `write-handoff` exits 6. The
    launch goes on, and lane-start's note points at the helper's words, which
    say where the commit is kept, never at HEAD of the lane's checkout."""
    box, _checkout, _lane_dir, _before = _started(tmp_path, short_root)
    other = _other_repository(box, origin=False)
    _peer_push(box, {"lanes/LANES.md": _with_cell(box, str(other / "handoff.md"))},
               "the lane's cell names another repository's handoff")
    before = box.git("-C", str(other), "rev-parse", "HEAD").strip()

    start = box.start("--fresh", window_name=LANE)
    assert start.returncode == 0, start.stderr
    assert box.git("-C", str(other), "rev-parse", "HEAD~1").strip() == before, "committed there"
    assert "and committed there, on main" in start.stderr, start.stderr
    said = [line for line in start.stderr.splitlines() if "`write-handoff` exited 6" in line]
    assert len(said) == 1, start.stderr
    assert "its words above say whether a commit was made, where it is kept" in said[0], said
    assert "KEPT on HEAD" not in start.stderr, start.stderr
