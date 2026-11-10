# SPDX-License-Identifier: Apache-2.0
"""Amendment 23, act 2's slice 2b: `lane-handoff` writes the PAUSED handoff
only through the lane's own register checkout.

Until this slice `lane-handoff` resolved the row's handoff cell against
`LANES_REPO` and then W (`workspace-root`), published the new top block there
under W's lock, and then added, committed, pulled and pushed it in W with no
lock at all, its output and git's words sent to `/dev/null` (lane
openRepoTools-3's finding 282, its second writer). Under the default
resolution every other write of the lane already went through
`<W>-lanes/<lane>/` (slice 1a), so the handoff was the one write left in W.

Now:
  * the file is the one `lanes-edit.sh handoff-path <lane> --create` names,
    in the checkout the lane's writes go through;
  * the top block is ONE `write-handoff --prepend` call, under that
    checkout's lock and S3/S4: written, committed by pathspec with the
    `Lane:` trailer and pushed, and where S3 refuses, written and NOT
    committed, with git's and S3's words printed rather than discarded;
  * the register's file-level PAUSED line is appended with `LANES_LANE`.

Each case drives a real `lane-handoff` in `test_lane_start_row_stamp`'s
sandbox with the default resolution (no `LANES_REPO`, no `LANES_FILE`) and the
opt-in `LANES_ROUTE_WRITES=1`, after a real `lane-start` made the lane's row
and checkout. W is brought up to origin first, so the old code finds the
handoff there and its unlocked commit in W is what each case sees at the base.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO
from test_a23_lane_start import (HANDOFF, SIBLING_WORDS, _assert_nothing_unpublished, _other_repository,
                                 _racing_git, _sibling_handoff, _with_cell,
                                 _cell, _edit, _origin, _peer, _peer_push, _published, _started, _tip)
from test_a23_lane_start_read import W_reflog, assert_W_moved_only_by_fast_forward
from test_lane_start_row_stamp import LANE, Sandbox, pytestmark, short_root  # noqa: F401

WHY = "a test handoff"
SUBJECT = f"handoff({LANE}@Eagle): PAUSED, {WHY}"


def _handoff(box: Sandbox, *args: str, env: dict | None = None, why: str = WHY) -> subprocess.CompletedProcess:
    """`lane-handoff --lane repoZ-1 … <why>`, from a shell with no tmux."""
    if not (box.bin / "lane-handoff").exists():
        shutil.copy2(REPO / "lane-handoff", box.bin / "lane-handoff")
        (box.bin / "lane-handoff").chmod(0o755)
    # A LANE WINDOW'S OWN SEAMS STAY OUT: `WORKBENCHES_CLAUDE_*` names the
    # caller's window and checkout, which `lane-handoff` reads where tmux is off.
    full = {k: v for k, v in box.env.items() if not k.startswith("WORKBENCHES_")}
    full.update(LANE_HANDOFF_NO_TMUX="1", CLAUDE_PROFILE_NAME="test-profile")
    full.update(env or {})
    return subprocess.run([str(box.bin / "lane-handoff"), "--lane", LANE, *args, why],
                          env=full, capture_output=True, text=True, timeout=180, check=False)


def _ready(tmp_path: Path, short_root: Path) -> tuple[Sandbox, Path, str, list[str]]:
    """A started lane whose handoff a peer wrote, with W brought up to origin
    (so W has it too, as `lane-start`'s refreshes leave it)."""
    box, checkout, _lane_dir, before = _started(tmp_path, short_root)
    cell = _cell(box)
    _peer_push(box, {cell: HANDOFF}, "the lane's handoff, written elsewhere")
    assert _edit(box, "refresh-workspace").returncode == 0
    assert (box.wip / cell).read_text(encoding="utf-8") == HANDOFF
    return box, checkout, cell, before


# -------------------------------------------------------------------- cases

def test_handoff_written_and_pushed_from_checkout(tmp_path, short_root):
    box, checkout, cell, before = _ready(tmp_path, short_root)

    result = _handoff(box)
    assert result.returncode == 0, result.stderr

    published = _published(box, cell)
    block, sep, rest = published.partition("\n---\n\n")
    assert sep, published
    assert rest == HANDOFF, published
    assert block.startswith(f"Lane: {LANE} (test-profile, session "), block
    assert "## RESUME PROMPT — PAUSED " in block, block
    assert f"({WHY})" in block, block
    assert _origin(box, "log", "-1", "--format=%s", "main", "--", cell).strip() == SUBJECT
    assert f"Lane: {LANE}" in _origin(box, "log", "-1", "--format=%b", "main", "--", cell)
    assert f"handoff refreshed: {checkout}/{cell} " in result.stderr, result.stderr
    assert f"committed: {SUBJECT}" in result.stderr, "write-handoff's own words are printed"
    assert "which exited 0: its words above say what it committed and pushed" in result.stderr, result.stderr

    # THE ONE WRITE IN W IS GONE: W moved only by fast-forward, and its copy of
    # the handoff took no byte from this act.
    assert_W_moved_only_by_fast_forward(box, before)
    assert (box.wip / cell).read_text(encoding="utf-8") in (HANDOFF, published)
    assert (checkout / cell).read_text(encoding="utf-8") == published
    _assert_nothing_unpublished(box, checkout)


def test_S3_refusal_writes_file_no_commit_prints_git_words(tmp_path, short_root):
    box, checkout, cell, before = _ready(tmp_path, short_root)
    # THE CHECKOUT IS CURRENT FIRST: S3 refuses a foreign staged entry before it
    # fast-forwards, so a checkout still behind the peer's handoff commit has no
    # file to write into (`write-handoff`'s 8), which is another case.
    box.git("-C", str(checkout), "fetch", "-q", "origin", "main")
    box.git("-C", str(checkout), "merge", "-q", "--ff-only", "origin/main")
    assert (checkout / cell).read_text(encoding="utf-8") == HANDOFF
    foreign = checkout / "handoffs" / "repoQ" / "foreign.md"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("a person's file, staged and never committed\n", encoding="utf-8")
    box.git("-C", str(checkout), "add", "--", "handoffs/repoQ/foreign.md")
    tip = _tip(box)

    result = _handoff(box)
    assert result.returncode == 0, result.stderr

    # WRITTEN (R-A11-11: a swap is never left unwritten) and NOT committed.
    written = (checkout / cell).read_text(encoding="utf-8")
    assert written.startswith(f"Lane: {LANE} (test-profile, session "), written
    assert written.endswith("\n---\n\n" + HANDOFF), written
    assert box.git("-C", str(checkout), "status", "--porcelain", "--", cell).startswith(" M "), \
        "the handoff is modified in the checkout and not committed"
    assert "handoffs/repoQ/foreign.md" in box.git("-C", str(checkout), "diff", "--cached", "--name-only")
    assert _tip(box) == tip, "nothing was published, from the lane's checkout or from W"
    # THE WORDS ARE PRINTED, NOT SENT TO /dev/null: S3's refusal naming the
    # entry, the helper's note, and lane-handoff's own.
    assert "the index holds staged entries this write did not make" in result.stderr, result.stderr
    assert "handoffs/repoQ/foreign.md" in result.stderr
    assert "the handoff is WRITTEN and NOT committed" in result.stderr
    assert f"commit -m \"{SUBJECT}\"" in result.stderr, result.stderr
    assert "NOT committed" in result.stderr, result.stderr
    assert "write-handoff` exited 2" in result.stderr, result.stderr
    assert "Never re-run this handoff" in result.stderr, result.stderr

    assert_W_moved_only_by_fast_forward(box, before)
    assert (box.wip / cell).read_text(encoding="utf-8") == HANDOFF, "W's copy took no byte"


def test_append_line_carries_LANES_LANE(tmp_path, short_root):
    box, checkout, cell, _before = _ready(tmp_path, short_root)
    calls = box.root / "lanes-edit-calls.log"
    wrapper = box.root / "recording-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
printf '%s LANES_LANE=%s\\n' "${{1-}}" "${{LANES_LANE-<unset>}}" >> '{calls}'
exec '{box.bin / "lanes-edit.sh"}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)

    result = _handoff(box, env={"LANES_EDIT": str(wrapper)})
    assert result.returncode == 0, result.stderr

    recorded = calls.read_text(encoding="utf-8").splitlines()
    for verb in ("append-line", "write-handoff"):
        made = [line for line in recorded if line.startswith(verb + " ")]
        assert made == [f"{verb} LANES_LANE={LANE}"], (verb, recorded)
    register = _published(box, "lanes/LANES.md")
    assert f"PAUSED — lane {LANE}, session " in register, register
    assert f", {WHY} kind unknown; handoff refreshed" in register, register
    assert _published(box, cell).endswith("\n---\n\n" + HANDOFF)
    _assert_nothing_unpublished(box, checkout)


def test_no_git_handoff_says_written_and_nothing_committed(tmp_path, short_root):
    """728, and question 4 of the review of #316: under `LANES_NO_GIT=1` the
    block is written in the lane's checkout and nothing is committed, and the
    exit-0 words say so rather than point at a commit and a push."""
    box, checkout, cell, _before = _ready(tmp_path, short_root)
    # NOTHING IS FETCHED UNDER LANES_NO_GIT, so the checkout is current first.
    box.git("-C", str(checkout), "fetch", "-q", "origin", "main")
    box.git("-C", str(checkout), "merge", "-q", "--ff-only", "origin/main")
    head = box.git("-C", str(checkout), "rev-parse", "HEAD")
    tip = _tip(box)

    result = _handoff(box, env={"LANES_NO_GIT": "1"})
    assert result.returncode == 0, result.stderr
    written = (checkout / cell).read_text(encoding="utf-8")
    assert written.startswith(f"Lane: {LANE} (test-profile, session "), written
    assert written.endswith("\n---\n\n" + HANDOFF), written
    assert box.git("-C", str(checkout), "rev-parse", "HEAD") == head, "nothing is committed"
    assert _tip(box) == tip, "or pushed"
    assert "what it committed and pushed" not in result.stderr, result.stderr
    said = [line for line in result.stderr.splitlines()
            if "LANES_NO_GIT=1" in line and "nothing is committed" in line]
    assert len(said) == 1, result.stderr
    # 990 of the review of #311, as slice 3's F24 answers it for both writers
    # of the act: a 0 records `handoff refreshed`, which claims no commit, and
    # the step line above is what says that nothing was committed.
    register = (checkout / "lanes" / "LANES.md").read_text(encoding="utf-8")
    paused = [line for line in register.splitlines() if f"PAUSED — lane {LANE}, session " in line]
    assert len(paused) == 1, register
    assert paused[0].endswith("; handoff refreshed"), paused


def _forcing(box: Sandbox, rc: int, write: bool) -> Path:
    """A `LANES_EDIT` whose `write-handoff` exits `rc`: after the real verb has
    written, committed and pushed (`write`), or at once, having written
    nothing. Every other verb is the real helper's."""
    real = box.bin / "lanes-edit.sh"
    wrapper = box.root / f"forcing-lanes-edit-{rc}.sh"
    first = f"'{real}' \"$@\"; " if write else ""
    wrapper.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = write-handoff ]; then {first}exit {rc}; fi
exec '{real}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


@pytest.mark.parametrize(("rc", "write", "record"), [
    (2, True, "handoff written, NOT published (write-handoff exited 2)"),
    (3, True, "handoff written, its publication NOT confirmed (write-handoff exited 3)"),
    (6, True, "handoff written, NOT published (write-handoff exited 6)"),
    (5, True, "handoff written, its publication NOT confirmed (write-handoff exited 5)"),
    (1, False, "handoff NOT refreshed (write-handoff exited 1 and wrote nothing)"),
])
def test_register_paused_line_says_what_the_write_did(tmp_path, short_root, rc, write, record):
    """#303's fit (c) in lane openRepoTools-3's review of #316, and its
    question 6 on #311: the register's file-level PAUSED line says
    `handoff refreshed` only where `write-handoff` wrote the block and exited
    0. Otherwise it uses the skill's phrases (slice 3's F23): written and NOT
    published (2, 6), its publication NOT confirmed (3, and any other exit
    after a write, which claims nothing either way), or NOT refreshed and
    why. And
    982: exit 6's words no longer say the commit is kept on HEAD of the lane's
    checkout, since a 6 may have made no commit, or (2a's 604) made it in an
    8(d) handoff's own repository."""
    box, _checkout, _cell_, _before = _ready(tmp_path, short_root)

    result = _handoff(box, env={"LANES_EDIT": str(_forcing(box, rc, write))})
    register = _published(box, "lanes/LANES.md")
    paused = [line for line in register.splitlines() if f"PAUSED — lane {LANE}, session " in line]
    assert len(paused) == 1, (register, result.stderr)
    assert paused[0].endswith(f"; {record}"), (paused, result.stderr)
    if not write:
        assert "## RESUME PROMPT — PAUSED " in result.stderr, result.stderr
    if rc == 6:
        assert "KEPT on HEAD" not in result.stderr, result.stderr
        assert "its words above say whether a commit was made, where it is kept" in result.stderr, result.stderr


def test_a_handoff_path_that_failed_is_said_and_the_block_printed(tmp_path, short_root):
    """Battery survivor LH03 (decision 11): where `handoff-path` fails,
    lane-handoff says it could not read where the handoff is written, prints
    the block for the hand, and the register's PAUSED line says the handoff
    was NOT refreshed and why (fit (c))."""
    box, _checkout, cell, _before = _ready(tmp_path, short_root)
    real = box.bin / "lanes-edit.sh"
    wrapper = box.root / "no-path-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = handoff-path ]; then echo "handoff-path: the register could not be read" >&2; exit 1; fi
exec '{real}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)
    handoff = _published(box, cell)

    result = _handoff(box, env={"LANES_EDIT": str(wrapper)})
    assert f"where lane {LANE}'s handoff is written could not be read" in result.stderr, result.stderr
    assert "## RESUME PROMPT — PAUSED " in result.stderr, result.stderr
    assert _published(box, cell) == handoff, "the handoff took no block"
    paused = [line for line in _published(box, "lanes/LANES.md").splitlines()
              if f"PAUSED — lane {LANE}, session " in line]
    assert len(paused) == 1, (paused, result.stderr)
    assert paused[0].endswith("; handoff NOT refreshed (handoff-path exited 1)"), paused


def test_a_cell_in_a_sibling_lanes_checkout_takes_no_block_and_the_block_is_printed(tmp_path, short_root):
    """723 of lane openRepoTools-3's review of #316, at lane-handoff's call
    site: the lane's row cell names lane repoZ-2's handoff in repoZ-2's own
    clone of the register beside W. `handoff-path` refuses it (slice 2a's
    601), so nothing is written there, the block is printed for the hand, and
    the register's PAUSED line says the handoff was NOT refreshed."""
    box, _checkout, _cell_, _before = _ready(tmp_path, short_root)
    f = _sibling_handoff(box)
    sib = f.parents[2]
    _peer_push(box, {"lanes/LANES.md": _with_cell(box, str(f))}, "the lane's cell names repoZ-2's handoff")
    text, head = f.read_text(encoding="utf-8"), box.git("-C", str(sib), "rev-parse", "HEAD")

    result = _handoff(box)
    assert f.read_text(encoding="utf-8") == text, "nothing was written in the sibling's handoff"
    assert SIBLING_WORDS in text
    assert box.git("-C", str(sib), "status", "--porcelain") == "", "the sibling's checkout is clean"
    assert box.git("-C", str(sib), "rev-parse", "HEAD") == head, "and took no commit"
    assert "in another checkout of the register beside W" in result.stderr, result.stderr
    assert "## RESUME PROMPT — PAUSED " in result.stderr, result.stderr
    paused = [line for line in _published(box, "lanes/LANES.md").splitlines()
              if f"PAUSED — lane {LANE}, session " in line]
    assert len(paused) == 1, (paused, result.stderr)
    assert paused[0].endswith("; handoff NOT refreshed (handoff-path exited 2)"), paused



@pytest.mark.parametrize("how", ["moved", "unmoved"])
def test_exit_6_names_the_publish_act_only_where_the_helper_offers_it(tmp_path, short_root, how):
    """NIT 2 of lane openRepoTools-3's review of opensoft/openRepoTools-code#20
    at 4031100, at lane-handoff's exit-6 note (`lane-start`'s twin is in
    test_a23_lane_start). The note ended "once those words are answered,
    LANES_LANE=... commit ..., the publish act" for every 6. Where the push
    was refused because origin MOVED (A37's keep-if-gone here; the six-attempt
    bound is the same), the helper's own words (`cp_recovery_steps`) say the
    publish act refuses (2) and give S6.3's archive, and after the archive and
    the drop there is nothing left to publish. Where origin did not move, they
    offer the act. The note defers to those words and names the act only where
    they offer it."""
    box, _checkout, cell, _before = _ready(tmp_path, short_root)
    shim, mark = _racing_git(box, how, _peer(box), cell)

    result = _handoff(box, env={"LANES_GIT": str(shim)})
    assert mark.exists(), "the push of the handoff's commit was refused"
    err = result.stderr
    said = [line for line in err.splitlines() if "`write-handoff` exited 6" in line and "NOT published" in line]
    assert len(said) == 1, err
    helper = err.split("`write-handoff` exited 6")[0]
    if how == "moved":
        assert "so the publish act refuses (2)" in helper, ("the helper's words give the archive", err)
        assert "# the archive, on origin" in helper, err
        assert 'commit "<what it is>"' not in helper, ("and do not offer the act", err)
    else:
        assert "refused with origin/main unmoved" in helper, err
        assert 'commit "<what it is>", the publish act' in helper, ("the helper offers the act", err)
    note = said[0]
    assert "once those words are answered, LANES_LANE=" not in note, ("the unconditional offer", note)
    assert "Where they offer the publish act, it is " in note, note
    assert f'LANES_LANE={LANE} ' in note and 'commit "<what it is>", the publish act' in note, note
    assert "where origin moved they say it refuses (2) and give S6.3's archive instead" in note, note


def _printed_call(stderr: str) -> list[str]:
    """The `write-handoff --prepend` call a kept block's note prints, as the
    words a shell reads from it: `LANES_LANE=<lane>`, the helper, the verb, the
    lane, `--prepend`, the block's file, `--subject`, the subject."""
    found = [line for line in stderr.splitlines() if line.startswith("lane-handoff:   LANES_LANE=")]
    assert len(found) == 1, stderr
    return shlex.split(found[0][len("lane-handoff:   "):])


def _run_printed_call(box: Sandbox, words: list[str], helper: Path | None = None) -> subprocess.CompletedProcess:
    """Run the printed call as a shell would, from the caller's environment;
    `helper` stands in for the helper a test wrapped."""
    name, _eq, lane = words[0].partition("=")
    env = {k: v for k, v in box.env.items() if not k.startswith("WORKBENCHES_")}
    env[name] = lane
    return subprocess.run([str(helper or words[1]), *words[2:]], env=env, capture_output=True, text=True,
                          timeout=180, check=False)


def _no_temp_file(box: Sandbox) -> dict:
    """A `mktemp` first on PATH whose `-d` makes the directory with a
    directory in the place of the block's file, so the block cannot be put in
    it, as a full or broken temporary directory would."""
    real = subprocess.run(["bash", "-c", "command -v mktemp"], env=box.env, capture_output=True,
                          text=True, check=True).stdout.strip()
    shim = box.root / "mktempshim"
    shim.mkdir()
    (shim / "mktemp").write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = -d ]; then d="$('{real}' "$@")" && mkdir "$d/block" && printf '%s\\n' "$d"; exit; fi
exec '{real}' "$@"
""", encoding="utf-8")
    (shim / "mktemp").chmod(0o755)
    return {"PATH": f"{shim}{os.pathsep}{box.env['PATH']}"}


@pytest.mark.parametrize("kind", ["path-failed", "row-names-none", "wrote-nothing", "no-temp-file"])
def test_a_kept_block_goes_in_by_the_one_printed_call_never_by_hand(tmp_path, short_root, kind):
    """NIT 3 of lane openRepoTools-3's review of opensoft/openRepoTools-code#20
    at 4031100 (its finding 983 on #311, for the skill): the notes where this
    command could not write the top block (the handoff not found, the block
    not put in a temporary file, `write-handoff` writing nothing) told the
    reader to put it at the head of the handoff "by hand". They print the one
    `write-handoff --prepend` call instead, filled in, as slice 3's block 2
    does, and keep the block in a file the call names. Run as printed, once the
    cause is answered, the call puts the block at the head of the handoff and
    publishes it; where no file could be made, the call says `<block file>`."""
    box, _checkout, cell, _before = _ready(tmp_path, short_root)
    real = box.bin / "lanes-edit.sh"
    env: dict = {}
    helper = None
    if kind == "path-failed":
        wrapper = box.root / "no-path-lanes-edit.sh"
        wrapper.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = handoff-path ]; then echo "handoff-path: the register could not be read" >&2; exit 1; fi
exec '{real}' "$@"
""", encoding="utf-8")
        wrapper.chmod(0o755)
        env = {"LANES_EDIT": str(wrapper)}
    elif kind == "row-names-none":
        _peer_push(box, {"lanes/LANES.md": _with_cell(box, "")}, "the lane's row names no handoff")
    elif kind == "wrote-nothing":
        env = {"LANES_EDIT": str(_forcing(box, 1, False))}
        helper = real
    else:
        env = _no_temp_file(box)
    handoff = _published(box, cell)

    result = _handoff(box, env=env)
    err = result.stderr
    assert "## RESUME PROMPT — PAUSED " in err, "the block is printed"
    assert "by hand:" not in err, err
    assert "never by a hand edit of the handoff:" in err, err
    words = _printed_call(err)
    assert words[2:5] == ["write-handoff", LANE, "--prepend"], words
    assert words[6:] == ["--subject", SUBJECT], words
    if kind == "wrote-nothing":
        assert _published(box, cell) == handoff, "the handoff took no block"
    if kind == "no-temp-file":
        assert words[5] == "<block file>", words
        assert "no file could be made to keep it in" in err, err
        return

    kept = Path(words[5])
    assert kept.read_text(encoding="utf-8").startswith(f"Lane: {LANE} (test-profile, session "), "the block is kept"
    assert kept.read_text(encoding="utf-8") in err, "and is the one printed"
    if kind == "row-names-none":
        assert _published(box, cell) == handoff
        _peer_push(box, {"lanes/LANES.md": _with_cell(box, cell)}, "the row names the handoff again")
    answered = _run_printed_call(box, words, helper)
    assert answered.returncode == 0, answered.stderr
    published = _published(box, cell)
    assert published == kept.read_text(encoding="utf-8") + "---\n\n" + handoff, published
    assert _origin(box, "log", "-1", "--format=%s", "main", "--", cell).strip() == SUBJECT


def test_the_printed_call_round_trips_a_quote_in_the_why(tmp_path, short_root):
    r"""The printed call runs as printed under bash and zsh alike: each word is
    single-quoted, a quote in it spelled '\'' (the skill's `hf_quote`), so a
    why with a quote and a space reads back as the subject the write would
    have used."""
    box, _checkout, _cell_, _before = _ready(tmp_path, short_root)
    wrapper = box.root / "no-path-lanes-edit.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
if [ "${{1-}}" = handoff-path ]; then exit 1; fi
exec '{box.bin / "lanes-edit.sh"}' "$@"
""", encoding="utf-8")
    wrapper.chmod(0o755)

    result = _handoff(box, env={"LANES_EDIT": str(wrapper)}, why="it's a 'quoted' test")
    words = _printed_call(result.stderr)
    assert words[7] == f"handoff({LANE}@Eagle): PAUSED, it's a 'quoted' test", words


def test_an_8d_cell_takes_the_block_committed_and_pushed_in_its_own_repository(tmp_path, short_root):
    """722 of lane openRepoTools-3's review of #316, at lane-handoff's write:
    slice 2a's 604 (A57) commits and pushes an Amendment 8(d) handoff in its
    own repository. The block is on top, committed by pathspec under the
    PAUSED subject and pushed to that repository's origin, its tree clean;
    the register's PAUSED line records `handoff refreshed`; and the exit-0
    words point at the helper's (a 0 may also commit nothing, F24)."""
    box, _checkout, _cell_, _before = _ready(tmp_path, short_root)
    other = _other_repository(box)
    _peer_push(box, {"lanes/LANES.md": _with_cell(box, str(other / "handoff.md"))},
               "the lane's cell names another repository's handoff")
    before = box.git("-C", str(other), "rev-parse", "HEAD").strip()

    result = _handoff(box)
    assert result.returncode == 0, result.stderr
    written = (other / "handoff.md").read_text(encoding="utf-8")
    assert written.startswith(f"Lane: {LANE} (test-profile, session "), written
    assert written.endswith("\n---\n\n" + HANDOFF), written
    o = ["-C", str(other)]
    assert box.git(*o, "status", "--porcelain") == "", "its tree is clean"
    assert box.git(*o, "rev-parse", "HEAD~1").strip() == before
    assert box.git(*o, "log", "-1", "--format=%s").strip() == SUBJECT
    assert (box.git("--git-dir", str(box.root / "other.git"), "rev-parse", "main").strip()
            == box.git(*o, "rev-parse", "HEAD").strip()), "and its origin holds the commit"
    assert "committed there and pushed to origin/main" in result.stderr, result.stderr
    assert "what it committed and pushed, or that nothing was committed" in result.stderr, result.stderr
    paused = [line for line in _published(box, "lanes/LANES.md").splitlines()
              if f"PAUSED — lane {LANE}, session " in line]
    assert len(paused) == 1, (paused, result.stderr)
    assert paused[0].endswith("; handoff refreshed"), paused



def test_a_why_with_a_tab_is_a_space_in_the_subject(tmp_path, short_root):
    """733 (M4, the battery's LH04) of lane openRepoTools-3's review of #316:
    `write-handoff` refuses a subject that carries a control character, so
    `subject_text` spells each one as a space, and a why with a tab still
    refreshes the handoff, as the old `git commit -m` did (decision 19)."""
    box, _checkout, cell, _before = _ready(tmp_path, short_root)

    result = _handoff(box, why="a test\thandoff")
    assert result.returncode == 0, result.stderr
    published = _published(box, cell)
    assert published.endswith("\n---\n\n" + HANDOFF), published
    assert _origin(box, "log", "-1", "--format=%s", "main", "--", cell).strip() == SUBJECT


# ------------------------------------- a closed lane (opensoft/openRepoTools#118)

def _closed(tmp_path: Path, short_root: Path) -> tuple[Sandbox, Path, str]:
    """A started lane that `lane-end`'s own line has closed: its log's last
    lane-kind line is an ENDED and its lifecycle reads CLOSED, with the handoff
    a peer wrote still in the lane's checkout."""
    box, checkout, cell, _before = _ready(tmp_path, short_root)
    row = next(r for r in _published(box, "lanes/LANES.md").splitlines()
               if r.startswith(f"| `{LANE}`"))
    minted = re.search(r"harness `([0-9a-f-]{36})`", row)
    assert minted, row
    ended = _edit(box, "log", "ENDED", f"lane:{LANE}", "finished",
                  env=dict(box.env, LANES_LANE=LANE, LANES_SESSION=minted.group(1)))
    assert ended.returncode == 0, ended.stderr
    _assert_nothing_unpublished(box, checkout)
    return box, checkout, cell


def _held(box: Sandbox, checkout: Path, cell: str) -> dict:
    """Every place a handoff writes, as one comparable value: the published
    register, the lane's object log and the commits behind them, W's reflog,
    the lane's checkout (its head, its changed files and the handoff file), the
    lifecycle snapshot, and the restart intent."""
    read = dict(box.env, LANES_NO_FETCH="1")
    return {
        "origin": _tip(box),
        "register": _published(box, "lanes/LANES.md"),
        "log": _published(box, f"lanes/log/{LANE}.md"),
        "W": W_reflog(box),
        "checkout head": box.git("-C", str(checkout), "rev-parse", "HEAD"),
        "checkout status": box.git("-C", str(checkout), "status", "--porcelain"),
        "handoff": (checkout / cell).read_text(encoding="utf-8"),
        "lifecycle": _edit(box, "lane-state", LANE, env=read).stdout,
        "restart intent": _edit(box, "restart-intent", LANE, env=read).returncode,
    }


@pytest.mark.parametrize("mode", [(), ("--restart",)], ids=["plain", "restart"])
def test_118_a_closed_lane_is_refused_before_any_write(tmp_path, short_root, mode):
    """opensoft/openRepoTools#118, Brett Heap's "Refuse, as --late does
    (Recommended)": `lane-handoff` on a lane whose last lane-kind line is an
    ENDED took its lifecycle from CLOSED to SWAPPING, wrote a PAUSED after the
    ENDED and finished at SWAPPED. It now exits 2 with `--late`'s own words, and
    writes nothing: no commit, no changed file, no log line, no lifecycle
    transition and, under `--restart`, no restart intent."""
    box, checkout, cell = _closed(tmp_path, short_root)
    before = _held(box, checkout, cell)
    assert "state\tCLOSED" in before["lifecycle"], before["lifecycle"]
    assert before["log"].splitlines()[-1].startswith("ENDED"), before["log"]

    result = _handoff(box, *mode)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert f"lane {LANE}'s last lane-kind line is ENDED (at " in result.stderr, result.stderr
    assert ("the lane is closed, and a handoff after it would reopen a lane nobody is in"
            in result.stderr), result.stderr
    assert "Nothing was renamed and nothing was written" in result.stderr, result.stderr
    assert "handoff refreshed" not in result.stderr and "lifecycle:" not in result.stderr
    assert _held(box, checkout, cell) == before


def test_118_a_lane_started_again_after_its_close_is_handed_off_as_before(tmp_path, short_root):
    """The refusal reads the log's last lane-kind line, which is the lane's
    state: a lane that `lane-start` reopened after its ENDED has a STARTED or
    RESUMED last, and is handed off whatever its snapshot said in between."""
    box, _checkout, _cell = _closed(tmp_path, short_root)
    again = box.start("--fresh", window_name=LANE)
    assert again.returncode == 0, again.stderr

    result = _handoff(box)
    assert result.returncode == 0, result.stderr
    assert "the lane is closed" not in result.stderr, result.stderr
