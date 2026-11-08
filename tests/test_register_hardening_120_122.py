# SPDX-License-Identifier: Apache-2.0
"""The register's two rewrites prove what they copied and what landed, the
sweep's preflight asks `ensure_log`'s own question, a lane whose log already
closes it is told so, and add-row's archive scan refuses a line it cannot take
apart: opensoft/openRepoTools#120 (Copilot round 5 on #93) and #122 (round 6).

Each case builds the throwaway register `test_register_scan_hardening_138.py`
builds — a bare repository and a clone of it in a temporary directory, with a
temporary `$HOME` — and runs the real `lanes-edit.sh` against it. A write that
has to come out short is cut by a `cat` first on `PATH` that cuts ONE exact
copy and hands every other call to the real one; a scan that has to fail, by
an `awk` that refuses ONE exact program. Nothing here reaches a network or the
operator's own register.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import REPO
from test_register_scan_hardening_138 import (  # noqa: F401  (pytestmark is this module's too)
    HEADER, OLD_ID, UNPRIVILEGED_ONLY, Register as SweepRegister, lane_line, log_text, pytestmark, row)

NEW_ID = "cccc0122-0003-4000-8000-000000000003"
#: The archive exactly as `archive_rows` creates it: a title, a paragraph, then
#: the header (line 7) and its rule (line 8). Rows follow from line 9.
ARCHIVE_HEAD = ("# LANES-retired.md — rows RETIRED out of `lanes/LANES.md`\n\n"
                "lane-collision-protocol Amendment 19(d). These lanes are finished. Their\n"
                "positions are NEVER REISSUED: every reader of the next free position and\n"
                "`lanes --closed` read this file beside the register.\n\n" + HEADER)
#: The copy seam reads where a `cat`'s output is going, which only Linux says.
PROC_FD = pytest.mark.skipif(not Path("/proc/self/fd/1").exists(),
                             reason="the copy seam reads /proc/<pid>/fd/1")


class Register(SweepRegister):
    """`test_register_scan_hardening_138`'s register, with thirty rows of another
    repository below repoX's — so a copy cut at half its lines still holds every
    row a case edits — and the seams these cases need."""

    def __init__(self, tmp: Path):
        super().__init__(tmp)
        self.write("lanes/LANES.md", self.read("lanes/LANES.md") + "".join(
            row(f"repoZ-{n}", OLD_ID, f"another repository's row {n}") for n in range(1, 31)))
        self.publish("another repository's rows")

    def published(self, rel: str) -> str:
        return self.raw_git("-C", str(self.origin), "show", f"main:{rel}")

    def shim(self, name: str, body: str) -> None:
        """A `<name>` first on PATH: `body`, then the real one."""
        real = shutil.which(name, path=os.environ.get("PATH"))
        path = self.fakebin / name
        path.write_text(f'#!/usr/bin/env bash\n{body}\nexec "{real}" "$@"\n')
        path.chmod(0o755)

    def cut_cat(self, cut: str) -> None:
        """A `cat` that cuts a copy at half its lines. `copy…`: the
        register's copy into a file named `pre`, the copy every proof of a
        rewrite is made against. `write…`: the rewrite itself, `cat -- <tmp>/out`
        into the register — and with `…and restore fail`, the copy's bytes put
        back into the register as well. `…fail(s)` exits 1 after the half, as a
        full disk does; `…says done` exits 0, a short write nothing reported."""
        rc = 0 if cut.endswith("says done") else 1
        goes_to = 'case "$(readlink "/proc/$$/fd/1" 2>/dev/null)" in {} ) true ;; *) false ;; esac'
        if cut.startswith("copy"):
            when = ('[ "${1-}" = -- ] && case "${2-}" in */lanes/LANES.md) true ;; *) false ;; esac && '
                    + goes_to.format("*/pre"))
        elif cut == "write and restore fail":
            when = ('[ "${1-}" = -- ] && case "${2-}" in */out) true ;; '
                    '*/pre) ' + goes_to.format("*/lanes/LANES.md") + ' ;; *) false ;; esac')
        else:
            when = '[ "${1-}" = -- ] && case "${2-}" in */out) true ;; *) false ;; esac'
        self.shim("cat", f'if {when}; then\n'
                         f'  n=$(wc -l < "$2"); head -n $((n / 2)) -- "$2"; exit {rc}\nfi')


@pytest.fixture
def reg(tmp_path: Path) -> Register:
    return Register(tmp_path)


# ------------------------------------------- #120 item 1: the two rewrites

def retire_repo_x_3(reg: Register) -> None:
    reg.write("lanes/LANES.md", reg.read("lanes/LANES.md").replace(
        "| more old words |", "| RETIRED · 2026-09-01T00:00:00Z · swept |"))
    reg.publish("repoX-3 retired")


#: The one act per rewrite: `set-row-state` ends in `replace_line`, and
#: `archive-rows --yes` in `delete_lines`.
ACTS = {
    "replace_line": ("set-row-state", "repoX-2", "PAUSED · cut short"),
    "delete_lines": ("archive-rows", "repoX", "--yes"),
}
CUTS = ["copy fails", "copy says done", "write fails", "write says done",
        "write and restore fail"]


@PROC_FD
@pytest.mark.parametrize("cut", CUTS)
@pytest.mark.parametrize("act", sorted(ACTS))
def test_120_item_1_a_rewrite_cut_short_leaves_the_register_whole(reg, act, cut):
    """#120 item 1: `cat -- <out> > LANES.md` had its status read, but not
    its result, and `>` truncates before `cat` writes. A write that failed
    part-way left a HALF register behind a refusal that called it UNCHANGED;
    one that was short and said nothing was a half register committed (exit
    0). And the COPY every proof is made against was read with no status at
    all, so a short copy made a short register look like a one-line edit of
    itself: rewritten, committed and pushed. Each refuses (5) now, and the
    register on disk and on origin is byte for byte what it was — or, where
    the bytes could not be put back either, the refusal says the register MAY
    NOW BE TRUNCATED, keeps the exact copy it was made from and names where,
    and nothing is committed (the review of #263, NIT 6). The copy is kept in
    the checkout's own git directory, mode 0600, under a name of its own, where
    a restart that empties the temporary directory leaves it (the delta
    review's NIT). The copy refusal says THIS ACT has committed nothing and
    names what the act had already written here, never "Nothing was written"
    (S2)."""
    if act == "delete_lines":
        retire_repo_x_3(reg)
    register = reg.read("lanes/LANES.md")
    before = reg.head()
    reg.cut_cat(cut)
    result = reg.run(*ACTS[act], LANES_LANE="repoX-1")
    assert result.returncode == 5, (result.stdout, result.stderr)
    assert reg.head() == before
    assert reg.published("lanes/LANES.md") == register
    if cut == "write and restore fail":
        assert "IT MAY NOW BE TRUNCATED" in result.stderr
        assert "UNCHANGED" not in result.stderr
        found = re.search(r"are kept in (\S+) \(", result.stderr)
        assert found, result.stderr
        kept = Path(found.group(1))
        assert kept.read_text(encoding="utf-8") == register
        assert kept.parent.resolve() == Path(reg.git("rev-parse", "--absolute-git-dir").strip()).resolve()
        assert re.fullmatch(r"lanes-edit-register-before-edit\.\d{8}T\d{6}Z\.\d+", kept.name), kept.name
        assert stat.S_IMODE(kept.stat().st_mode) == 0o600
        return
    assert reg.read("lanes/LANES.md") == register
    if cut.startswith("copy"):
        assert "could not be copied whole" in result.stderr
        assert "this act has committed nothing" in result.stderr
        assert "Nothing was written" not in result.stderr
        if act == "delete_lines":
            assert "NOT committed: lanes/archive/LANES-retired.md (created)" in result.stderr
    else:
        assert "have been put back and proved" in result.stderr
        assert "UNCHANGED" not in result.stderr


def test_120_item_1_a_peer_edit_is_refused_before_the_copy_and_never_captured(reg):
    """The delta review of #263 pinned the words of a refusal made after a
    peer's uncommitted register edit was captured as a commit of its own
    (`handle_preexisting`). Amendment 23 S3 step 4 withdraws the capture
    (ratified choice 9, #198 slice 1b): the write refuses (2) over the peer's
    edit before its copy is made, commits nothing, and leaves the edit as it
    was, for `commit` to commit as its own act. The copy's cut never runs."""
    before = reg.head()
    reg.write("lanes/LANES.md", reg.read("lanes/LANES.md").replace(
        "another repository's row 30 |", "another repository's row 30, edited by a peer |"))
    edited = reg.read("lanes/LANES.md")
    reg.cut_cat("copy fails")
    result = reg.run(*ACTS["replace_line"], LANES_LANE="repoX-1")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "holds an uncommitted edit, which may be a peer's" in result.stderr
    assert "captured pre-existing edit" not in result.stderr
    assert "nothing has been committed" not in result.stderr
    assert "MAY NOW BE TRUNCATED" not in result.stderr
    assert reg.head() == before
    assert reg.read("lanes/LANES.md") == edited


@UNPRIVILEGED_ONLY
@pytest.mark.parametrize("act", sorted(ACTS))
def test_120_item_1_a_write_that_never_reached_the_register_says_it_is_as_it_was(reg, act):
    """The review of #263, NIT 3 (its X4): a register the write could not even
    open is byte for byte what it was, and the refusal says so in words of its
    own, apart from the put-back's and the truncation's. archive-rows has
    appended the archive by then, and the refusal names it (S2)."""
    if act == "delete_lines":
        retire_repo_x_3(reg)
    register = reg.read("lanes/LANES.md")
    before = reg.head()
    path = reg.wip / "lanes/LANES.md"
    path.chmod(0o444)
    try:
        result = reg.run(*ACTS[act], LANES_LANE="repoX-1")
    finally:
        path.chmod(0o644)
    assert result.returncode == 5, (result.stdout, result.stderr)
    assert "the write did not reach it, and it is byte for byte as it was before this edit" in result.stderr
    assert "put back" not in result.stderr
    assert "MAY NOW BE TRUNCATED" not in result.stderr
    assert reg.read("lanes/LANES.md") == register
    assert reg.head() == before
    assert reg.published("lanes/LANES.md") == register
    if act == "delete_lines":
        assert "NOT committed: lanes/archive/LANES-retired.md (created)" in result.stderr


@PROC_FD
def test_120_item_1_a_sweep_refused_part_way_names_what_it_wrote_and_is_not_called_closed(reg):
    """The review of #263, S2: retire-rows appends a lane's RETIRED line before
    it rewrites the row, so a copy refusal that said "Nothing was written" left
    `?? lanes/log/repoX-2.md` behind it. And a re-run then read that
    uncommitted line and called the lane "already CLOSED … nothing more is
    owed", about a row never retired and a line never published. The refusal
    names the log, and the re-run refuses the line as this checkout's alone."""
    reg.cut_cat("copy fails")
    result = reg.sweep("repoX-2")
    assert result.returncode == 5, (result.stdout, result.stderr)
    assert "this act has committed nothing" in result.stderr
    assert "NOT committed: lanes/log/repoX-2.md (its RETIRED line)" in result.stderr
    assert "Nothing was written" not in result.stderr
    (reg.fakebin / "cat").unlink()
    rerun = reg.sweep("repoX-2")
    assert rerun.returncode == 2, (rerun.stdout, rerun.stderr)
    assert "in THIS CHECKOUT ends on a RETIRED line, and origin/main's copy does not" in rerun.stderr
    assert "already CLOSED" not in rerun.stderr
    assert "`repoX-2`" in reg.published("lanes/LANES.md")
    assert "RETIRED" not in reg.published("lanes/LANES.md").split("`repoX-2`")[1].splitlines()[0]


# ------------------------------- #120 item 2: the sweep's published-path scan

#: Amendment 23 S3's refusal of an unpushed commit, in its own words
#: (`cs_refuse`). Under #198 slice 1b it comes before any scan of a sweep: a
#: commit made here and not pushed is refused (2) as soon as the write starts.
S3_LACKS = "this checkout holds 1 commit(s) origin/main lacks by content:"
S3_WORDS = ("would push them under its own name or strand itself behind them "
            "(Amendment 23 S3). Nothing was written.")


def case_sensitive(path: Path) -> bool:
    probe = path / "case-probe"
    probe.write_text("")
    try:
        return not (path / "CASE-PROBE").exists()
    finally:
        probe.unlink()


def test_120_item_2_a_rename_whose_commit_never_landed_refuses_in_the_scan(reg):
    """#120 item 2: the sweep's preflight asked whether origin publishes the
    log under another case only where this checkout had NO log, and compared a
    basename with a path besides. So the state a case-only rename leaves when
    its commit is not pushed — the row's spelling here, committed; the old
    spelling still on origin; a checkout merely AHEAD — passed the scan, and
    `ensure_log` refused it inside the write loop, after the lane before it had
    had its log created and appended. #263's scan refused it with `ensure_log`'s
    own words. Under Amendment 23 S3 (#198 slice 1b) the rename's commit is an
    unpushed commit, and S3 refuses it (2) before the scan, naming it: the
    scan's words are reached only where origin moves after this write's
    fast-forward under its lock. Nothing is written either way."""
    if not case_sensitive(reg.tmp):
        pytest.skip("two log names that differ only by case need a case-sensitive filesystem")
    reg.write("lanes/log/repox-3.md", log_text("repox-3", lane_line(
        "NOTED", "repoX-3", OLD_ID, "2026-09-13T00:00:00Z") + " — migrated; history kept here"))
    reg.publish("repoX-3's log, under the spelling it had before Amendment 15")
    reg.git("mv", "lanes/log/repox-3.md", "lanes/log/repoX-3.md")
    reg.git("commit", "-q", "-m", "repoX-3's log takes the row's spelling (not pushed)")
    before = reg.head()
    result = reg.sweep("repoX-2", "repoX-3")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert S3_LACKS in result.stderr
    assert "repoX-3's log takes the row's spelling (not pushed)" in result.stderr
    assert S3_WORDS in result.stderr
    assert "published as lanes/log/repox-3.md" not in result.stderr
    assert reg.head() == before
    assert not (reg.wip / "lanes/log/repoX-2.md").exists()
    assert reg.dirty() == ""


#: `ensure_log`'s own recovery sentence, which the sweep's scan repeats word for
#: word (the comment above the scan promises "in its words"): both dies carry it.
ENSURE_LOG_RECOVERY = ("Re-run the write: it fast-forwards this checkout to origin's tip under its lock "
                       "first (Amendment 23 S3), and the rename then happens once, inside its own commit.")


def test_120_item_2_a_log_respelled_on_origin_after_the_fast_forward_refuses_in_the_scan(reg, tmp_path):
    """S4 of lane openRepoTools-3's review of the re-homed slice 1b: the scan's
    refusal at `retire_rows`' published-log check (B73's hand-resolved die) had
    no case, because Amendment 23 S3 refuses the state it was written for, a
    case-only rename whose commit is not pushed, before the scan. It is reached
    only where origin moves AFTER S3's fast-forward and after the sweep's
    behind-check: here a peer respells repoX-3's log on origin and a reader
    fetches it into this shared checkout, which still holds the row's spelling,
    clean and in step with the tip S3 fast-forwarded to. The scan refuses (2) in
    `ensure_log`'s words and recovery, before the lane ahead of it in this one
    commit has a log made or a line appended: nothing is written."""
    if not case_sensitive(reg.tmp):
        pytest.skip("two log names that differ only by case need a case-sensitive filesystem")
    original = log_text("repoX-3", lane_line("NOTED", "repoX-3", OLD_ID, "2026-09-13T00:00:00Z")
                        + " — migrated; history kept here")
    reg.write("lanes/log/repoX-3.md", original)
    reg.publish("repoX-3's log, under the row's spelling")
    peer = tmp_path / "peer"
    reg.raw_git("clone", "-q", str(reg.origin), str(peer))
    reg.raw_git("-C", str(peer), "mv", "lanes/log/repoX-3.md", "lanes/log/repox-3.md")
    reg.raw_git("-C", str(peer), "commit", "-q", "-m", "a peer respells repoX-3's log")
    register = reg.read("lanes/LANES.md")
    before = reg.head()
    real = shutil.which("git", path=os.environ.get("PATH"))
    mark = tmp_path / "fetched"
    # The sweep's behind-check is the last read of `origin/main` before its scan:
    # the peer's push and a reader's fetch of it follow that call, in the shared
    # checkout, and the call's own answer (0 behind) is handed back unchanged.
    shim = reg.fakebin / "git"
    shim.write_text(f"""#!/usr/bin/env bash
case " $* " in
  *" rev-list --count HEAD..refs/remotes/origin/main "*)
    if [ ! -e '{mark}' ]; then
      : > '{mark}'
      out=$('{real}' "$@") || exit $?
      '{real}' -C '{peer}' push -q origin main || exit 1
      '{real}' -C '{reg.wip}' fetch -q origin '+refs/heads/main:refs/remotes/origin/main' || exit 1
      printf '%s\\n' "$out"
      exit 0
    fi ;;
esac
exec '{real}' "$@"
""")
    shim.chmod(0o755)
    result = reg.sweep("repoX-2", "repoX-3")
    shim.unlink()
    assert mark.exists(), "the peer never landed: the sweep's behind-check was never reached"
    assert reg.published("lanes/log/repox-3.md") == original, "the peer's respelling is on origin"
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert S3_LACKS not in result.stderr, "S3 had nothing to refuse: the checkout was in step with origin"
    assert ("lane repoX-3's object log is published as lanes/log/repox-3.md while this checkout has "
            "lanes/log/repoX-3.md instead") in result.stderr
    assert ("the row spells the lane repoX-3, so the log is lanes/log/repoX-3.md (Amendment 15), "
            "and writing one here now would leave TWO files for one lane.") in result.stderr
    assert ENSURE_LOG_RECOVERY in result.stderr
    assert "Origin moved after" not in result.stderr
    assert result.stderr.rstrip().endswith("Nothing was written.")
    assert (REPO / "lanes-edit.sh").read_text(encoding="utf-8").count(ENSURE_LOG_RECOVERY) == 2, \
        "the scan's refusal and ensure_log's say the same sentence"
    assert reg.head() == before
    assert reg.dirty() == ""
    assert reg.read("lanes/LANES.md") == register
    assert reg.read("lanes/log/repoX-3.md") == original
    assert not (reg.wip / "lanes/log/repoX-2.md").exists()
    assert "RETIRED" not in reg.published("lanes/LANES.md")


# ------------------------------- #120 item 3: a log that already closes the lane

@pytest.mark.parametrize("last", ["ENDED", "RETIRED"])
def test_120_item_3_a_lane_whose_log_closes_it_is_told_it_is_closed(reg, last):
    """#120 item 3: the refusal for a lane whose log's LAST lane-kind line is
    ENDED or RETIRED read the same as the one for a running lane, and named no
    way out. It says the lane is already CLOSED and hidden (19(b)) — never
    `lane-end`, which is not the exit for a lane that has ended. For RETIRED it
    names `archive-rows <repo>` (19(d)) exactly; for ENDED it says archive-rows
    is not the row's exit, and never that the lane "is not retired a second
    time" (the review of #263, NITs 3 and 5)."""
    reg.write("lanes/log/repoX-2.md", log_text(
        "repoX-2", lane_line("STARTED", "repoX-2", OLD_ID, "2026-09-11T00:00:00Z"),
        lane_line(last, "repoX-2", OLD_ID, "2026-09-11T02:00:00Z")))
    reg.publish(f"repoX-2 started and {last.lower()}")
    before = reg.head()
    result = reg.sweep("repoX-2")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert f"{last} line" in result.stderr
    assert "already CLOSED" in result.stderr
    assert "lane-end" not in result.stderr
    if last == "RETIRED":
        assert "`lanes-edit.sh archive-rows repoX`" in result.stderr
    else:
        assert "`archive-rows` is not its exit" in result.stderr
        assert "lanes-edit.sh archive-rows" not in result.stderr
        assert "retired a second time" not in result.stderr
    assert reg.head() == before


@pytest.mark.parametrize("last", ["ENDED", "RETIRED"])
def test_120_item_3_a_closing_line_only_this_checkout_has_is_not_called_closed(reg, last):
    """The review of #263, S2, from a commit rather than a cut sweep: a closing
    line committed here and never pushed is refused, and never called CLOSED.
    #263's scan refused it as this checkout's alone, with its article right:
    "an ENDED line" (the delta review's NIT). Under Amendment 23 S3 (#198
    slice 1b) the commit is an unpushed commit, and S3 refuses it (2) before
    the scan, naming it: the scan's words are reached only where origin moves
    after this write's fast-forward under its lock. Nothing is written."""
    started = lane_line("STARTED", "repoX-2", OLD_ID, "2026-09-11T00:00:00Z")
    reg.write("lanes/log/repoX-2.md", log_text("repoX-2", started))
    reg.publish("repoX-2 started")
    reg.write("lanes/log/repoX-2.md", log_text(
        "repoX-2", started, lane_line(last, "repoX-2", OLD_ID, "2026-09-12T00:00:00Z")))
    reg.commit(f"repoX-2 {last.lower()}, not pushed")
    before = reg.head()
    result = reg.sweep("repoX-2")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert S3_LACKS in result.stderr
    assert f"repoX-2 {last.lower()}, not pushed" in result.stderr
    assert S3_WORDS in result.stderr
    assert "in THIS CHECKOUT ends on" not in result.stderr
    assert "already CLOSED" not in result.stderr
    assert reg.head() == before
    assert reg.dirty() == ""
    assert "RETIRED" not in reg.published("lanes/LANES.md").split("`repoX-2`")[1].splitlines()[0]


def test_120_item_3_a_lane_whose_log_says_it_is_parked_is_sent_to_lane_end(reg):
    """…and the other branch: a log whose last lane-kind line is STARTED,
    PAUSED or RESUMED is a lane a person can still pick up, so the refusal
    sends it to `lane-end <lane>` and not to the archive."""
    reg.write("lanes/log/repoX-2.md", log_text(
        "repoX-2", lane_line("STARTED", "repoX-2", OLD_ID, "2026-09-11T00:00:00Z"),
        lane_line("PAUSED", "repoX-2", OLD_ID, "2026-09-11T01:00:00Z")))
    reg.publish("repoX-2 is parked")
    result = reg.sweep("repoX-2")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "carries a PAUSED line" in result.stderr
    assert "lane-end repoX-2" in result.stderr
    assert "archive-rows" not in result.stderr


# --------------------------------------------- #122: add-row's archive scan

RETIRED_CELL = "RETIRED · 2026-08-02T00:00:00Z · moved"
#: Three ways a hand edit or a bad merge leaves a row of repoX-4 that the scan
#: cannot take apart, each with what it does to the first cell.
MANGLED = {
    "the lane lost its backticks": f"| repoX-4 | harness `{OLD_ID}` | Eagle / test / brett | 2026-08-01 | none | none | {RETIRED_CELL} |",
    "no backtick at all": f"| repoX-4 | harness {OLD_ID} | Eagle / test / brett | 2026-08-01 | none | none | {RETIRED_CELL} |",
    "one backtick lost": f"| `repoX-4 | harness {OLD_ID} | Eagle / test / brett | 2026-08-01 | none | none | {RETIRED_CELL} |",
}


#: The row `add_repo_x_4` adds, with its newline: a peer that publishes it
#: first publishes the very line add-row appends.
NEW_ROW = row("repoX-4", NEW_ID, "new here", "2026-10-19")
ARCHIVE = "lanes/archive/LANES-retired.md"


def add_repo_x_4(reg: Register) -> subprocess.CompletedProcess:
    return reg.run("add-row", NEW_ROW.rstrip("\n"), LANES_LANE="repoX-4")


def peer_pushes_before_its_push(reg: Register, tmp_path: Path, changes: dict[str, str], *,
                                diff_log: Path | None = None, diff_context: int | None = None,
                                extra_shell: str = "") -> Path:
    """The shell suite's `repo19race` shape. A peer clone commits `changes`
    (a path and its whole new text each, one commit each, in order) now, and a
    `git` first on PATH pushes them the moment the writer's own checkout runs
    its first `push`: after add-row has committed its row, so its push is
    refused. (#263 raced the `pull --rebase`; Amendment 23 S4 removed the pull,
    #198 slice 1b, and replays a refused push on origin's new tip.) Returns the
    mark the shim leaves; the caller removes the shim.

    The same shim would see add-row's take-back diff (the register's `-U0`
    diff against origin's), which went with the pull: `diff_log` records each
    such call, so a case can assert there is none; `diff_context` would run it
    with context. `extra_shell` runs in the shim before it hands each call to
    the real `git`, with `@MARK@` standing for the mark's path."""
    peer = tmp_path / "peer"
    reg.raw_git("clone", "-q", str(reg.origin), str(peer))
    for rel, text in changes.items():
        (peer / rel).parent.mkdir(parents=True, exist_ok=True)
        (peer / rel).write_text(text, encoding="utf-8")
        reg.raw_git("-C", str(peer), "add", "--", rel)
        reg.raw_git("-C", str(peer), "commit", "-q", "-m", f"peer: {rel}")
    real = shutil.which("git", path=os.environ.get("PATH"))
    mark = tmp_path / "raced"
    shim = reg.fakebin / "git"
    take_back = ""
    if diff_log is not None:
        take_back += f"""  printf '%s\\t%s\\n' "${{GIT_DIFF_OPTS-<unset>}}" "$*" >> '{diff_log}'\n"""
    if diff_context is not None:
        take_back += (f'  a=(); for x in "$@"; do if [ "$x" = -U0 ]; then a+=(-U{diff_context}); '
                      'else a+=("$x"); fi; done; set -- "${a[@]}"\n')
    if take_back:
        take_back = ('case " $* " in *" -U0 refs/remotes/origin/main -- "*)\n'
                     + take_back + "  ;;\nesac\n")
    if extra_shell:
        take_back += extra_shell.replace("@MARK@", str(mark)) + "\n"
    shim.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = -C ] && [ "${{3-}}" = push ] && [ ! -e '{mark}' ]; then
  case "${{2-}}" in */wip)
    : > '{mark}'
    '{real}' -C '{peer}' push -q origin main || exit 1 ;;
  esac
fi
{take_back}exec '{real}' "$@"
""")
    shim.chmod(0o755)
    return mark


def a_good_archive(reg: Register) -> str:
    reg.write(ARCHIVE, ARCHIVE_HEAD + row("repoX-9", OLD_ID, RETIRED_CELL, "2026-08-01"))
    reg.publish("a good archive")
    return reg.read(ARCHIVE)


@pytest.mark.parametrize("where", ["published", "committed here, not pushed"])
@pytest.mark.parametrize("mangle", sorted(MANGLED))
def test_122_an_archive_row_the_scan_cannot_take_apart_reissues_no_position(reg, mangle, where):
    """#122: the scan skipped any archive table line with no backticked lane
    token — and read a first backtick in ANOTHER cell as the lane — so a
    retired row whose lane cell a hand edit had mangled disappeared from the
    answer, and add-row reissued its position (exit 0). Such a line is refused
    by its line number and its copy now (1), in add-row's own words. The
    archive's own header and its rule are `|` lines with no backtick on every
    archive `archive_rows` writes, and they are not named."""
    mangled = MANGLED[mangle]
    reg.write("lanes/archive/LANES-retired.md", ARCHIVE_HEAD
              + row("repoX-9", OLD_ID, RETIRED_CELL, "2026-08-01") + mangled + "\n")
    if where == "published":
        reg.publish("the archive, with a hand-mangled row 10")
    else:
        reg.commit("the archive, with a hand-mangled row 10 (not pushed)")
    before = reg.head()
    result = add_repo_x_4(reg)
    assert result.returncode == 1, (result.stdout, result.stderr)
    copies = "origin/main and this checkout" if where == "published" else "this checkout"
    assert f"line 10 ({copies}): {mangled}" in result.stderr
    assert "carries a line this scan cannot take apart (above)" in result.stderr
    assert "line 7 (" not in result.stderr
    assert "line 8 (" not in result.stderr
    assert reg.head() == before
    assert "`repoX-4`" not in reg.published("lanes/LANES.md")


def test_122_an_archive_scan_that_failed_is_not_an_archive_with_no_match(reg):
    """#122, the `|| :` half: the scan's status was the `sort -u` behind it,
    so an awk that FAILED read as "no archived row matched" and the archived
    repoX-4 was added again (exit 0). It is a refusal (1) now."""
    reg.write("lanes/archive/LANES-retired.md", ARCHIVE_HEAD
              + row("repoX-4", OLD_ID, RETIRED_CELL, "2026-08-01"))
    reg.publish("the archive holds repoX-4")
    reg.shim("awk", 'case "$*" in *"function key("*) echo "test shim: awk refused" >&2; exit 2 ;; esac')
    before = reg.head()
    result = add_repo_x_4(reg)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert reg.head() == before
    assert "`repoX-4`" not in reg.published("lanes/LANES.md")


def test_122_a_line_number_says_which_copy_it_is_in(reg):
    """The review of #263, NIT 4: with the published archive and this
    checkout's apart, one bad line was listed as "line 10" and "line 12" with
    no word on which file either number belongs to."""
    mangled = MANGLED["the lane lost its backticks"]
    reg.write("lanes/archive/LANES-retired.md", ARCHIVE_HEAD
              + row("repoX-9", OLD_ID, RETIRED_CELL, "2026-08-01") + mangled + "\n")
    reg.publish("the archive, with a hand-mangled row 10")
    reg.write("lanes/archive/LANES-retired.md", ARCHIVE_HEAD
              + row("repoX-7", OLD_ID, RETIRED_CELL, "2026-08-01")
              + row("repoX-8", OLD_ID, RETIRED_CELL, "2026-08-01")
              + row("repoX-9", OLD_ID, RETIRED_CELL, "2026-08-01") + mangled + "\n")
    reg.commit("two more rows above it, not pushed")
    result = add_repo_x_4(reg)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert f"line 10 (origin/main): {mangled}" in result.stderr
    assert f"line 12 (this checkout): {mangled}" in result.stderr


def test_122_a_refusal_on_the_replay_leaves_no_row_to_publish(reg, tmp_path):
    """The review of #263, M1, the shell suite's `repo19race` shape: a peer
    publishes an archive line this scan cannot take apart while add-row is
    publishing. Under #263 the after-rebase rescan refused (1) and only its
    retired-match branch took the committed row back, so the next unrelated
    write published the row add-row had refused. Under Amendment 23 S4 (#198
    slice 1b) the push is refused, the replay drops add-row's commit and runs
    its checks again on origin's new tip, and they refuse (1) with nothing
    left at HEAD: no compensating commit is needed, and none is made."""
    archive = a_good_archive(reg)
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        ARCHIVE: archive + MANGLED["the lane lost its backticks"] + "\n"})
    result = add_repo_x_4(reg)
    (reg.fakebin / "git").unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "carries a line this scan cannot take apart (above)" in result.stderr
    assert "compensating LOCAL commit" not in result.stderr
    assert reg.git("log", "--oneline", "origin/main..HEAD") == "", "nothing of add-row's is left to publish"
    assert "`repoX-4`" not in reg.read("lanes/LANES.md")
    assert "`repoX-4`" not in reg.git("diff", "origin/main", "HEAD", "--", "lanes/LANES.md")
    assert "`repoX-4`" not in reg.published("lanes/LANES.md")
    after = reg.run("set-row-state", "repoX-2", "PAUSED · the next unrelated write", LANES_LANE="repoX-1")
    assert after.returncode == 0, (after.stdout, after.stderr)
    assert "PAUSED · " in reg.published("lanes/LANES.md").split("`repoX-2`")[1].splitlines()[0]
    assert "`repoX-4`" not in reg.published("lanes/LANES.md")


#: What the rescan after the rebase refuses, each with add-row's exit: a peer's
#: archive line it cannot take apart (another lane's), or a peer's retirement
#: of repoX-4 itself.
RESCAN_REFUSALS = {
    "a line the scan cannot take apart": (
        MANGLED["the lane lost its backticks"].replace("repoX-4", "repoQ-7") + "\n", 1),
    "a retirement": (row("repoX-4", OLD_ID, RETIRED_CELL, "2026-08-01"), 2),
}


@pytest.mark.parametrize("why", sorted(RESCAN_REFUSALS))
def test_122_a_refusal_on_the_replay_leaves_a_peers_identical_row_alone(reg, tmp_path, why):
    """The delta review of #263, D1: a peer publishes the byte-identical
    repoX-4 row while add-row is publishing. Under #263 the rebase dropped
    add-row's commit as already upstream, and the take-back deleted the
    PEER's copy in a local commit that the next write published. Under
    Amendment 23 S4 (#198 slice 1b) the push is refused and the replay drops
    add-row's own commit, by what it is, and its checks refuse on origin's new
    tip, for either refusal: nothing is taken back, nothing of add-row's is
    left, and the next write leaves the peer's row as it is."""
    archive = a_good_archive(reg)
    refusal, code = RESCAN_REFUSALS[why]
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        "lanes/LANES.md": reg.read("lanes/LANES.md") + NEW_ROW, ARCHIVE: archive + refusal})
    result = add_repo_x_4(reg)
    (reg.fakebin / "git").unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == code, (result.stdout, result.stderr)
    assert "origin/main already carries this exact row" not in result.stderr, \
        "#263's rebase dropped add-row's commit as upstream and said so; the replay does neither"
    ahead = reg.git("log", "--oneline", "origin/main..HEAD")
    after = reg.run("set-row-state", "repoX-2", "PAUSED · the next unrelated write", LANES_LANE="repoX-1")
    assert after.returncode == 0, (after.stdout, after.stderr)
    assert reg.published("lanes/LANES.md").count("`repoX-4`") == 1, (ahead, result.stderr)
    assert ahead == ""
    assert "compensating LOCAL commit" not in result.stderr


def test_122_a_refusal_on_the_replay_drops_its_own_row_beside_a_peers_copy_in_another_place(reg, tmp_path):
    """…and the other direction. Where the peer put the identical row in
    another place, #263's rebase KEPT add-row's commit and the register held
    two copies, and the take-back removed this checkout's. Under Amendment 23
    S4 (#198 slice 1b) the replay drops add-row's commit whole before its
    checks refuse, so the register holds the peer's copy alone once the next
    write brings it to origin's tip, and that write publishes no second one."""
    archive = a_good_archive(reg)
    seeded = row("repoX-3", OLD_ID, "more old words")
    peer_register = reg.read("lanes/LANES.md").replace(seeded, seeded + NEW_ROW)
    assert peer_register != reg.read("lanes/LANES.md")
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        "lanes/LANES.md": peer_register,
        ARCHIVE: archive + RESCAN_REFUSALS["a line the scan cannot take apart"][0]})
    result = add_repo_x_4(reg)
    (reg.fakebin / "git").unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == 1, (result.stdout, result.stderr)
    ahead = reg.git("log", "--oneline", "origin/main..HEAD")
    after = reg.run("set-row-state", "repoX-2", "PAUSED · the next unrelated write", LANES_LANE="repoX-1")
    assert after.returncode == 0, (after.stdout, after.stderr)
    assert reg.published("lanes/LANES.md").count("`repoX-4`") == 1, result.stderr
    assert reg.read("lanes/LANES.md").count("`repoX-4`") == 1
    assert ahead == ""
    assert "compensating LOCAL commit" not in result.stderr


#: The ways the take-back cannot remove its row once it has found it: its copy
#: of the register cut short, its write cut short (put back), the pass that
#: removes the line refused, a pass that dropped a line too many, and a
#: `numstat` proof that reads the copies as binary (an attribute on every
#: path, which no `core.bigFileThreshold` changes).
TAKE_BACK_CUTS = [pytest.param("copy", marks=PROC_FD), pytest.param("write", marks=PROC_FD),
                  "awk pass", "line count", "numstat"]


@pytest.mark.parametrize("cut", TAKE_BACK_CUTS)
def test_122_a_refusal_on_the_replay_says_nothing_of_a_committed_row_whatever_is_cut(reg, tmp_path, cut):
    """The delta review of #263, on the wording, and delta review 4's N1 and
    S4's N2: where #263's take-back could not rewrite the register (its copy
    or its write cut short, its pass, its line count or its `numstat` proof
    refused), add-row HAD committed its row, and the refusal had to say so in
    add-row's own words. Under Amendment 23 S4 (#198 slice 1b) there is no
    take-back: the replay drops add-row's commit and its checks refuse (1)
    with nothing of add-row's left, so the same cuts change nothing. The
    refusal says nothing of a committed row, because there is none."""
    archive = a_good_archive(reg)
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        ARCHIVE: archive + RESCAN_REFUSALS["a line the scan cannot take apart"][0]})
    real_awk = shutil.which("awk", path=os.environ.get("PATH"))
    if cut == "awk pass":
        reg.shim("awk", 'case "$*" in *LANES_DROP_LINES*) echo "test shim: the removal pass refused" >&2; exit 2 ;; esac')
    elif cut == "line count":
        reg.shim("awk", f'case "$*" in *LANES_DROP_LINES*) "{real_awk}" "$@" | sed 1d; exit 0 ;; esac')
    elif cut == "numstat":
        (reg.home / "attributes").write_text("* -diff\n", encoding="utf-8")
        (reg.home / ".gitconfig").write_text(f"[core]\n\tattributesFile = {reg.home / 'attributes'}\n",
                                             encoding="utf-8")
    elif cut == "copy":
        copies = tmp_path / "copies"
        # The register's SECOND copy into a `pre` is cut: add-row's own append
        # makes the first, the take-back's `delete_lines` the second.
        reg.shim("cat", 'if [ "${1-}" = -- ] && case "${2-}" in */lanes/LANES.md) true ;; *) false ;; esac && '
                        'case "$(readlink "/proc/$$/fd/1" 2>/dev/null)" in */pre) true ;; *) false ;; esac; then\n'
                        f"  echo copy >> '{copies}'\n"
                        f"  if [ \"$(grep -c . '{copies}')\" -ge 2 ]; then n=$(wc -l < \"$2\"); head -n $((n / 2)) -- \"$2\"; exit 1; fi\n"
                        "fi")
    else:
        # The take-back's rewrite is the one write from an `out` add-row makes.
        reg.cut_cat("write fails")
    result = add_repo_x_4(reg)
    for shim in ("git", "cat", "awk"):
        if (reg.fakebin / shim).exists():
            (reg.fakebin / shim).unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "carries a line this scan cannot take apart (above)" in result.stderr
    assert "HAS committed" not in result.stderr
    for archive_rows_words in ("the rows are in", "The archive may have been appended", "resolve that partial move"):
        assert archive_rows_words not in result.stderr
    assert "compensating LOCAL commit" not in result.stderr
    assert reg.git("log", "--format=%s", "origin/main..HEAD") == "", "nothing of add-row's is left to publish"
    assert "`repoX-4`" not in reg.published("lanes/LANES.md")


#: What is set up before add-row runs (the delta review of #263, S3): each is a
#: way context reaches the take-back's diff, or a hunk where the row is not the
#: first line of it.
CONTEXT_CASES = [
    "GIT_DIFF_OPTS=-u3 in add-row's environment",
    "diff.interHunkContext=3 beside an unpushed edit one row above the end",
    "context the diff carries anyway, beside that edit",
    "another lane's unpushed row just above",
]


@pytest.mark.parametrize("case", CONTEXT_CASES)
def test_122_a_take_back_finds_its_row_whatever_context_the_diff_carries(reg, tmp_path, case):
    """The delta review of #263, S3: `-U0` alone did not keep context out of
    #263's take-back diff (a `GIT_DIFF_OPTS=-u3`, a user's
    `diff.interHunkContext`, a second row in the same hunk), the row was put
    at the wrong line, and the next ordinary write published the row add-row
    had refused. Under Amendment 23 S4 (#198 slice 1b) no such diff is asked
    for: the replay drops add-row's commit by what it is and its checks refuse
    (1), whatever context a diff would carry. The nearby edit and the other
    lane's row are published first, since S3 refuses a write over an unpushed
    commit."""
    archive = a_good_archive(reg)
    extra = {"LANES_LANE": "repoX-4"}
    diff_log = tmp_path / "take-back-diff"
    context = None
    if case.startswith("GIT_DIFF_OPTS"):
        extra["GIT_DIFF_OPTS"] = "-u3"
    elif case.startswith("another lane"):
        reg.write("lanes/LANES.md", reg.read("lanes/LANES.md")
                  + row("repoX-5", OLD_ID, "another lane's row, published", "2026-10-19"))
        reg.publish("another lane's row, just above")
    else:
        if case.startswith("diff.interHunkContext"):
            (reg.home / ".gitconfig").write_text("[diff]\n\tinterHunkContext = 3\n", encoding="utf-8")
        else:
            context = 3
        reg.write("lanes/LANES.md", reg.read("lanes/LANES.md").replace(
            "another repository's row 29 |", "another repository's row 29, edited here |"))
        reg.publish("an edit one row above the end")
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        ARCHIVE: archive + RESCAN_REFUSALS["a line the scan cannot take apart"][0]},
        diff_log=diff_log, diff_context=context)
    result = reg.run("add-row", NEW_ROW.rstrip("\n"), **extra)
    (reg.fakebin / "git").unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == 1, (result.stdout, result.stderr)
    after = reg.run("set-row-state", "repoX-2", "PAUSED · the next unrelated write", LANES_LANE="repoX-1")
    assert after.returncode == 0, (after.stdout, after.stderr)
    assert reg.published("lanes/LANES.md").count("`repoX-4`") == 0, result.stderr
    assert "compensating LOCAL commit" not in result.stderr
    assert not diff_log.exists(), "no take-back diff is asked for"


#: The ways git classes the register as binary (delta review 4 of #263, S4),
#: each set up before add-row runs.
BINARY_CASES = [
    "`lanes/LANES.md -diff` in .git/info/attributes",
    "a published .gitattributes marking it binary",
    "core.bigFileThreshold below the register's size",
]


@pytest.mark.parametrize("case", BINARY_CASES)
def test_122_a_take_back_reads_its_diff_as_text_whatever_classes_the_register_binary(reg, tmp_path, case):
    """Delta review 4 of #263, S4: where git classed the register as binary,
    #263's take-back diff had no hunk to read, add-row kept its commit, and
    the next write published the row add-row had refused (M1 again). Under
    Amendment 23 S4 (#198 slice 1b) the replay drops add-row's commit by what
    it is, with no diff of the register to read, and its checks refuse (1)
    whatever classes the register binary. The next write is an `append-line`:
    a `set-row-state` refuses under such a threshold on its own `numstat`
    proof, as it does on main."""
    archive = a_good_archive(reg)
    if case.startswith("`lanes/LANES.md -diff`"):
        (reg.wip / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (reg.wip / ".git" / "info" / "attributes").write_text("lanes/LANES.md -diff\n", encoding="utf-8")
    elif case.startswith("a published .gitattributes"):
        reg.write(".gitattributes", "lanes/LANES.md binary\n")
        reg.publish("every clone reads the register as binary")
    else:
        (reg.home / ".gitconfig").write_text("[core]\n\tbigFileThreshold = 200\n", encoding="utf-8")
        assert (reg.wip / "lanes/LANES.md").stat().st_size > 200
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        ARCHIVE: archive + RESCAN_REFUSALS["a line the scan cannot take apart"][0]})
    result = add_repo_x_4(reg)
    (reg.fakebin / "git").unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert reg.git("log", "--oneline", "origin/main..HEAD") == "", "nothing of add-row's is left to publish"
    after = reg.run("append-line", "a plain line, the next unrelated write", LANES_LANE="repoX-1")
    assert after.returncode == 0, (after.stdout, after.stderr)
    assert reg.published("lanes/LANES.md").count("`repoX-4`") == 0, result.stderr
    assert "compensating LOCAL commit" not in result.stderr


#: Where the take-back's removal is written but cannot be committed (delta
#: review 4 of #263, N3), each with what `git status` then shows.
COMPENSATION_FAILS = {
    "staging": ('if [ -e \'@MARK@\' ]; then case " $* " in *" add -- lanes/LANES.md "*)\n'
                '  echo "test shim: add refused" >&2; exit 1 ;; esac; fi', " M lanes/LANES.md",
                "but staging that removal failed, so it is only in the working tree, and add-row's "
                "commit still holds the row."),
    "commit": ('case " $* " in *" commit "*"cancel add-row"*)\n'
               '  echo "test shim: commit refused" >&2; exit 1 ;; esac', "M  lanes/LANES.md",
               "and that removal is staged, but its compensating commit failed, so add-row's commit "
               "still holds the row."),
}


@pytest.mark.parametrize("step", sorted(COMPENSATION_FAILS))
def test_122_the_replay_makes_no_removal_for_a_refused_add_or_commit_to_strand(reg, tmp_path, step):
    """Delta review 4 of #263, N3: where #263's take-back could not stage or
    commit its removal, the removal was left in the working tree or staged
    under add-row's commit, and the next write's commit carried it under that
    write's caption. Under Amendment 23 S4 (#198 slice 1b) there is no
    removal to commit: the replay drops add-row's commit and its checks refuse
    (1), so the same `add` and `commit` failures leave the checkout clean,
    nothing of add-row's to publish, and no cancelling commit anywhere."""
    archive = a_good_archive(reg)
    shell, status, said = COMPENSATION_FAILS[step]
    mark = peer_pushes_before_its_push(reg, tmp_path, {
        ARCHIVE: archive + RESCAN_REFUSALS["a line the scan cannot take apart"][0]}, extra_shell=shell)
    result = add_repo_x_4(reg)
    (reg.fakebin / "git").unlink()
    assert mark.exists(), "the peer never raced the push"
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert reg.dirty() == "", (status, reg.dirty())
    assert reg.git("log", "--format=%s", "origin/main..HEAD") == "", "nothing of add-row's is left to publish"
    assert said not in result.stderr
    caption = "LANES(repoX-4@Eagle): cancel add-row"
    assert "Commit the removal" not in result.stderr
    after = reg.run("set-row-state", "repoX-2", "PAUSED · the next unrelated write", LANES_LANE="repoX-1")
    assert after.returncode == 0, (after.stdout, after.stderr)
    assert reg.published("lanes/LANES.md").count("`repoX-4`") == 0
    assert caption not in reg.raw_git("-C", str(reg.origin), "log", "--format=%s", "main")
