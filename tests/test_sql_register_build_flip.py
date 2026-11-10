# SPDX-License-Identifier: Apache-2.0
"""TEST 14: THE BUILD BEFORE THE RENDERER'S GIT HALF (feature 007; the test
plan's AT-14; FR-001, FR-002, FR-003, FR-059).

One constant is the flip: `RENDER_GIT_HALF`, beside `SCHEMA_VERSION` in the
checkout's `lanes-index` (lane 1's T105, L1-A3). While it is False, Q6(c)'s
refusal of `mode=primary` is built in, and lane 3's T328 is the only change
that sets it True. So the module builds both states from the one checkout,
with T203's `flipped_copy` (PC-5): the REFUSING copy has the constant False,
the FLIPPED copy has it True, whichever way the checkout's own says.

WHAT IT HOLDS, by task:

  * T212 (L2-N2), the refusing state:
    - `test_mode_primary_is_refused_until_the_git_half_and_goes_to_sql_once_
      flipped[refusing]`: `lanes-index mode` exits 78 with the fixed text and
      nothing on stdout, and so does it over `store=sqlite` or no
      `register_url=`, since Q6(c)'s check runs first (Y:4849; lane 1, #165
      6747929926 point 1); every other command this build has that reads the
      configuration exits 2 with the same text: `status`, `sync` and
      `reconcile` with `LANES_INDEX` unset, and `export`, which writes it to
      `<out>/why`; `cutover`, `rollback` and `set-mode primary` exit 2 with
      it too, once a build has them (TP:2598-2600). No `psql` runs, no store
      is made, and the files, the HEAD and origin are unchanged;
    - `[mode-under-index-off]`: with `LANES_INDEX=off` kept set over the same
      file, `lanes-index mode` still exits 78 with the text, never `index`
      (lane 3, #165 6747957479; lane 1, 6748099727). Its `[J3]` word is
      `sql_register_build_flip and mode-under-index-off`;
    - `test_lanes_edit_asks_lanes_index_mode_only_where_a_configuration_
      exists` (D3): with no configuration file and `LANES_INDEX_CONFIG`
      unset, a logging stand-in at `lanes-index`'s path records no call, and
      the verb writes in files mode;
    - `test_mode_primary_with_sqlite_is_refused` (P162-163; R-F9-5): on T203's
      FLIPPED copy, where Q6(c)'s refusal is lifted, `mode=primary` with
      `store=sqlite`, or with no `register_url=`, is T104's refusal, 2 (lane
      1's L1v4.10:117), and not Q6(c)'s text. On the refusing copy Q6(c)'s 78
      comes first, which `[refusing]` holds. This is lane 2's reading of the
      two lines together (NOTES question 29);
    - `test_register_read_exits_78_under_the_refusal[readers|for-guard]`:
      `register read` exits 78 with the text, never 2, in the readers' forms
      (contract section 3.6's forms 1 and 3) and in `--for guard`'s (forms 2
      and 4), as contract section 2.7's 78 row names them;
    - `test_readers_under_the_refusal_answer_the_78_as_a_failed_read[<read>|
      listing|session-start|guard|projection]`: run from the same estate under
      the refusal, with the fake `psql`'s log empty, a read that decides
      exits 69 with nothing on stdout; the listings and the `SessionStart`
      block answer from the mirror, exit 0, and carry the `read: mirror`
      line; the prompt guard exits 2; and `managed-projection` answers 1,
      UNKNOWN, never 8.

THE CODES ARE READ FROM THE CONSTANTS (contracts/exit-codes.md section 1:
"the tests read the constant, never a literal"): `EXIT_CONFIG` and
`EXIT_REFUSED`, which T105 names in `lanes-index`. A code `lanes-edit.sh`
exits with (69, 1 and 2 from the readers) has no constant, and is a literal.

THE REFUSING STATE'S CONFIGURATION (T212's bullet; lane 1's CLI4.5 section
2.5; R09): `mode=primary`, with `register_url=` and `reader_url=` on
`db.invalid`, each carrying `sslmode=verify-full` and an `sslrootcert=` that
names a test root file, and 0600 password files. That meets the block's
configuration rule, and Q6(c)'s 78 does not rest on it: Q6(c) runs before
T104's R8, R9, R10 and R15, so test 14's own state, a register URL on
`db.invalid` with no TLS, gives the same 78 (R-F9-5).

THE FAKE-`psql` HOST RULE (L1v4.5:525; lane 1, #165 6741670709 item 9): the
refusing state's `register_url=`, on `db.invalid`, meets it by `verify-full`
and a root file, and every other configuration here either names no URL or
carries the same `verify-full` and root file, since T104 refuses any other at
load (CLI4.5 section 2.5). The fake is T203's `REGISTER_FAKE_PSQL`, first on
`PATH`; its log stays empty in every case here, since nothing connects.

`LANES_INDEX` (R-F9-5): `tests/conftest.py` sets `LANES_INDEX=off` for the
whole run, and `Estate` builds its environment without it. Under it `sync`
and `reconcile` keep #160's no-op exit 0, even over a `mode=primary` file, so
`[refusing]` runs them with it unset; `lanes-index mode` reads the
configuration whatever it says, which `[mode-under-index-off]` holds.

THE STAND-IN AT `lanes-index`'S PATH. The checkout's `lanes-edit.sh` finds
`lanes-index` beside itself (`$SCRIPT_DIR/lanes-index`, then `PATH`), so each
`lanes-edit.sh` case runs a copy of it, with what it reads beside it, and puts
`LOGGING_WRAPPER` at `lanes-index`'s path there: it logs each call, then runs
the `lanes-index` it stands in front of. A reader case first asserts that the
reader asked `lanes-index`, so a case that never reaches the refusal fails on
that, never vacuously (`session-start` excepted, as T217's mirror test does).

NO NETWORK AND NO ENGINE. Every remote is a bare repository under `tmp_path`,
`$HOME` is temporary, and `db.invalid` is never resolved: nothing connects.

WHAT EACH WAITS FOR (the block's Order): T212's tests fail until L1-A3, L1-A4,
L1-A11 and L5-A5 land: lane 1's T105 (the constant and `mode`), T113
(`register read`) and lane 5's T504 (the read door). D3's test passes at once
on a build that never asks the mode.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from urllib.parse import quote

import pytest

import sql_register_helpers as helpers
from conftest import REPO, WINDOWS_SKIP
from test_lanes_index import UUID_A2, Estate, estate

__all__ = ["estate"]  # the fixture, imported so that pytest finds it here

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

LANES_EDIT = REPO / "lanes-edit.sh"

#: Q6(c)'S FIXED TEXT (agreement test 14; the test plan's AT-14, TP:2540-2542;
#: design Y:4872). The design may reword it, not weaken it (P1413), and the
#: test pins what the design prints.
REFUSED_TEXT = ("mode=primary is not available in this build: the renderer's git half is not "
                "installed, so a write could not be mirrored; nothing was written")

#: `lanes-index`'s own stderr lines are prefixed so (contract section 2.6).
PREFIX = "lanes-index: "

#: A subcommand a build does not have yet answers 64 with these words (lane
#: 1's T105; #165 6747929926: "so does every subcommand not yet built").
NOT_BUILT = "this build does not have it"

#: What a case copies beside the stand-in, as T217's `Primary` does (CLI4.5:885).
COPIED_BESIDE = ("lanes-edit.sh", "lanes", "repos.tsv", "lane-start", "lane-worktrees")

#: The stand-in's log, beside it.
CALL_LOG = "lanes-index.calls"

#: THE LOGGING STAND-IN (AT-14's fixture): `lanes-index` at the path
#: `lanes-edit.sh` finds. It logs each call, one JSON object per line, then
#: runs `TARGET`, the `lanes-index` it stands in front of, with the same argv,
#: stdin and descriptors.
LOGGING_WRAPPER = r'''#!/usr/bin/env python3
# TEST 14's LOGGING STAND-IN at lanes-index's path (feature 007, AT-14): one
# JSON object per call in lanes-index.calls beside it, then the lanes-index it
# stands in front of, with the same argv, stdin and descriptors.
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
record = {"argv": sys.argv[1:], "pid": os.getpid(), "ppid": os.getppid()}
with open(os.path.join(HERE, "lanes-index.calls"), "a", encoding="utf-8") as log:
    log.write(json.dumps(record) + "\n")
os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
'''

#: The `read: mirror` line (design S3, "The mirror reads"), on stderr.
MIRROR_LINE = re.compile(r"^read: mirror at [0-9a-f]{12}, .*$", re.M)

#: The guard's hook JSON, as T217 feeds it (UserPromptSubmit).
GUARD_INPUT = json.dumps({"session_id": UUID_A2, "prompt": "hello", "hook_event_name":
                          "UserPromptSubmit", "transcript_path": "/dev/null", "cwd": "/"})

#: THE READS THAT DECIDE (TP:2587-2589), each with an argv `Estate` answers in
#: files mode, as T217's readers' table gives them: under the refusal each
#: exits 69 with nothing on stdout.
DECIDE_READS = {
    "who": ("who", "opensoft/repoA#7"),
    "binding": ("binding", "repoA-1"),
    "live-holder": ("live-holder", "repoA-1"),
    "next-free": ("next-free", "repoA"),
    "lane-last": ("lane-last", "repoA-1"),
    "register-row": ("register-row", "repoC-9"),
    "session-lane": ("session-lane", UUID_A2),
    "canon-lane": ("canon-lane", "repoA-1"),
    "resolve-home": ("resolve-home", "repoA-1"),
}

#: The listings (TP:2590): each answers from the mirror, exit 0.
LISTINGS = (("lanes",), ("history", "--all"))

#: `[<read>|listing|session-start|guard|projection]` (TP:2644).
READER_CASES = sorted(DECIDE_READS) + ["listing", "session-start", "guard", "projection"]

#: What a decide read and `managed-projection` exit, `lanes-edit.sh`'s own
#: codes (contracts/exit-codes.md, `lanes-edit.sh`'s table; design S3).
READ_FAILED, PROJECTION_UNKNOWN, PROJECTION_NEVER, GUARD_REFUSED = 69, 1, 8, 2


# ------------------------------------------------------------------ helpers
def shown(proc: subprocess.CompletedProcess) -> str:
    return (f"exit {proc.returncode}\n--- stdout ---\n{proc.stdout[-3000:]}"
            f"\n--- stderr ---\n{proc.stderr[-3000:]}")


def load_index(path: Path = helpers.LANES_INDEX):
    """`lanes-index` as a module, fresh, as `test_lanes_index.py` loads it."""
    loader = SourceFileLoader("lanes_index_build_flip_module", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def exit_code(name: str) -> int:
    """The checkout's `lanes-index`'s named exit code (contracts/exit-codes.md
    section 1), asserted to be there: T105 names `EXIT_CONFIG`, `EXIT_REFUSED`
    and `EXIT_USAGE`."""
    module = load_index()
    assert isinstance(getattr(module, name, None), int), (
        f"the checkout's lanes-index names no `{name}`: Q6(c)'s exit codes are named "
        f"with lane 1's T105 (L1-A4; contracts/exit-codes.md section 1)")
    return getattr(module, name)


def constant_lines(path: Path = helpers.LANES_INDEX) -> list:
    return helpers.RENDER_GIT_HALF_LINE.findall(Path(path).read_bytes())


def state_copy(directory: Path, value: bool) -> Path:
    """T203's `flipped_copy` of the checkout's `lanes-index` (PC-5): `False`
    is the refusing state, `True` the flipped one. The checkout must hold the
    constant's one line, which lane 1's T105 adds (L1-A3)."""
    found = constant_lines()
    assert len(found) == 1, (
        f"the checkout's lanes-index holds {len(found)} `RENDER_GIT_HALF = ` lines, not one: "
        f"Q6(c)'s constant lands with lane 1's T105 (L1-A3)")
    return helpers.flipped_copy(helpers.LANES_INDEX, directory, value)


def write_private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def calls(bin_dir: Path) -> list:
    """The stand-in's log: one dict per call, in call order."""
    path = bin_dir / CALL_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def forget_calls(bin_dir: Path) -> None:
    path = bin_dir / CALL_LOG
    if path.exists():
        path.write_text("", encoding="utf-8")


def beside(bin_dir: Path, target: Path) -> Path:
    """`bin_dir` holding a copy of the checkout's `lanes-edit.sh` and what it
    reads beside it, with `LOGGING_WRAPPER` at `lanes-index`'s path there in
    front of `target`. Returns the copied `lanes-edit.sh`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in COPIED_BESIDE:
        shutil.copy2(REPO / name, bin_dir / name)
    wrapper = bin_dir / "lanes-index"
    wrapper.write_text(LOGGING_WRAPPER.replace("TARGET", repr(str(target))), encoding="utf-8")
    wrapper.chmod(0o755)
    return bin_dir / "lanes-edit.sh"


class Refusing:
    """Test 14's refusing state over an `Estate`: the configuration that says
    `mode=primary` at the workstation's default path (and named by
    `LANES_INDEX_CONFIG`), the refusing copy of `lanes-index`, and T203's fake
    `psql` first on `PATH`, logging every call."""

    def __init__(self, estate: Estate):
        self.e = estate
        self.root = estate.root / "test14"
        self.root.mkdir(parents=True, exist_ok=True)
        # A stand-in root file for `sslrootcert=`: it must exist as a regular
        # file (contract section 2.5), and nothing ever reads it as a root.
        self.root_file = self.root / "tls" / "register-root.pem"
        self.root_file.parent.mkdir(parents=True, exist_ok=True)
        self.root_file.write_text("test 14's stand-in root file; nothing connects to db.invalid\n",
                                  encoding="utf-8")
        self.passfile = write_private(self.root / "secrets" / "register.pgpass",
                                      "db.invalid:5432:lanes:lanes_w_test14:not-a-secret\n")
        self.reader_passfile = write_private(self.root / "secrets" / "reader.pgpass",
                                             "db.invalid:5432:lanes:lanes_r_test14:not-a-secret\n")
        self.config = estate.write_config(self.config_text())
        self.copy = state_copy(self.root / "refusing", False)
        self.psql_dir = self.root / "psqlbin"
        self.psql_dir.mkdir(parents=True, exist_ok=True)
        fake = self.psql_dir / "psql"
        fake.write_text(helpers.REGISTER_FAKE_PSQL, encoding="utf-8")
        fake.chmod(0o755)
        self.psql_log = self.root / "psql.log"

    def url(self, user: str) -> str:
        """A URL on `db.invalid` that meets the block's configuration rule."""
        root = quote(str(self.root_file), safe="/")
        return f"postgresql://{user}@db.invalid:5432/lanes?sslmode=verify-full&sslrootcert={root}"

    def config_text(self, *, mode: str = "primary", store: str | None = None,
                    register: bool = True) -> str:
        lines = [f"mode={mode}"]
        if store:
            lines.append(f"store={store}")
        if register:
            lines += [f"register_url={self.url('lanes_w_test14')}",
                      f"register_passfile={self.passfile}",
                      f"reader_url={self.url('lanes_r_test14')}",
                      f"reader_passfile={self.reader_passfile}"]
        return "\n".join(lines) + "\n"

    def other_config(self, name: str, text: str) -> Path:
        """A second 0600 configuration, outside every work tree, for a case
        that names it by `LANES_INDEX_CONFIG`."""
        return write_private(self.root / "configs" / name, text)

    def env(self, **extra) -> dict:
        env = {"LANES_INDEX_CONFIG": str(self.config), "FAKE_PSQL_LOG": str(self.psql_log),
               "PATH": self.e.path_with(self.psql_dir), "LANES_INDEX": None,
               "LANES_EDIT": str(LANES_EDIT)}
        env.update(extra)
        return env

    def index(self, copy: Path, *args, **extra) -> subprocess.CompletedProcess:
        """`copy` run as `Estate.index` runs the checkout's `lanes-index`."""
        return self.e.run(sys.executable, copy, *args, env=self.env(**extra))

    def edit(self, edit_path: Path, *args, input_text: str | None = None,
             **extra) -> subprocess.CompletedProcess:
        """The copied `lanes-edit.sh` at `edit_path`, on this workstation."""
        env = self.env(LANES_EDIT=str(edit_path), **extra)
        return self.e.run("bash", edit_path, *args, env=env, input_text=input_text)

    def psql_calls(self) -> list:
        if not self.psql_log.exists():
            return []
        return [line for line in self.psql_log.read_text(encoding="utf-8").splitlines() if line]

    def origin_and_head(self) -> tuple:
        return self.e.tip(), self.e._git("rev-parse", "HEAD").strip()


def the_78(proc: subprocess.CompletedProcess, config_code: int, what: str) -> None:
    """Q6(c)'s answer from `mode`: 78, nothing on stdout, and stderr exactly
    one line, the fixed text."""
    assert proc.returncode == config_code, (what, shown(proc))
    assert proc.stdout == "", (what, "stdout must be empty, never `index` or `primary`",
                               shown(proc))
    assert proc.stderr.splitlines() == [PREFIX + REFUSED_TEXT], (what, shown(proc))


# ---------------------------------------------- T212: test 14, refusing
def refusing_case(state: Refusing) -> None:
    """`[refusing]`: 78 from `mode`, 2 from every other command, the same
    text, nothing connected and nothing written."""
    config_code, refused, usage = (exit_code("EXIT_CONFIG"), exit_code("EXIT_REFUSED"),
                                   exit_code("EXIT_USAGE"))
    before = state.origin_and_head()
    the_78(state.index(state.copy, "mode"), config_code, "mode")
    # Q6(c) FIRST (Y:4849; R-F9-5): `store=sqlite`, or no `register_url=`,
    # is the same 78 while the constant is False, never T104's 2.
    for name, text in (("store-sqlite", state.config_text(store="sqlite")),
                       ("no-register-url", state.config_text(register=False))):
        conf = state.other_config(f"{name}.conf", text)
        the_78(state.index(state.copy, "mode", LANES_INDEX_CONFIG=str(conf)), config_code,
               f"mode over {name}")
    # EVERY OTHER COMMAND THIS BUILD HAS THAT READS THE CONFIGURATION: 2 with
    # the text. `sync` and `reconcile` with `LANES_INDEX` unset (R-F9-5).
    for argv in (("status",), ("sync",), ("reconcile",)):
        proc = state.index(state.copy, *argv, LANES_INDEX=None)
        assert proc.returncode == refused, (argv, shown(proc))
        assert REFUSED_TEXT in proc.stderr, (argv, shown(proc))
    out = state.root / "export-out"
    out.mkdir()
    proc = state.index(state.copy, "export", "--out", str(out), LANES_INDEX=None)
    assert proc.returncode == refused, ("export", shown(proc))
    why = (out / "why").read_text(encoding="utf-8") if (out / "why").exists() else ""
    assert REFUSED_TEXT in proc.stderr + why, ("export: the text, on stderr or in <out>/why",
                                               why, shown(proc))
    assert not (out / "meta").exists(), "export wrote an image under the refusal"
    # THE OPERATOR'S ACTS on a schema that is not a scratch schema (TP:2598-
    # 2600): 2 with the text, in a build that has them; before that, 64.
    for argv in (("cutover",), ("rollback",), ("set-mode", "primary")):
        proc = state.index(state.copy, *argv, LANES_INDEX=None)
        if proc.returncode == usage and NOT_BUILT in proc.stderr:
            continue
        assert proc.returncode == refused, (argv, shown(proc))
        assert REFUSED_TEXT in proc.stderr, (argv, shown(proc))
    assert state.psql_calls() == [], ("a refused configuration connected", state.psql_calls())
    assert not state.e.sqlite.exists(), "a store was made under the refusal"
    assert state.origin_and_head() == before, "the files, the HEAD or origin moved"
    assert state.config.read_text(encoding="utf-8") == state.config_text(), \
        "the configuration was rewritten"


def mode_under_index_off_case(state: Refusing) -> None:
    """`[mode-under-index-off]`: `LANES_INDEX=off` kept set over the same
    `mode=primary` file, and `mode` still answers 78 with the text, never
    `index` (lane 3, #165 6747957479; lane 1, 6748099727)."""
    config_code = exit_code("EXIT_CONFIG")
    the_78(state.index(state.copy, "mode", LANES_INDEX="off"), config_code,
           "mode under LANES_INDEX=off")
    assert state.psql_calls() == [], state.psql_calls()


STATE_CASES = {
    "refusing": refusing_case,
    "mode-under-index-off": mode_under_index_off_case,
}


@pytest.mark.parametrize("case", list(STATE_CASES))
def test_mode_primary_is_refused_until_the_git_half_and_goes_to_sql_once_flipped(estate, case):
    """Test 14's one test of both states (AT-14): with the refusal in place,
    `mode=primary` is refused where the configuration is read, 78 from
    `mode`, 2 from every other command, with the fixed text."""
    STATE_CASES[case](Refusing(estate))


def test_lanes_edit_asks_lanes_index_mode_only_where_a_configuration_exists(estate):
    """D3 (FR-002; contract section 3.1, "Asked only where a configuration
    exists"): with no configuration file and `LANES_INDEX_CONFIG` unset, a
    logging stand-in at `lanes-index`'s path records no call, and the verb
    writes in files mode. `LANES_INDEX=off`, which `tests/conftest.py` sets
    for the run and which skips the index's nudge, never skips the mode query
    (Y:5717), so under it the only call a write could make is the one D3
    bars. Then `--index`, with the variable unset, reaches the stand-in, so
    the stand-in is where `lanes-edit.sh` finds `lanes-index`."""
    bin_dir = estate.root / "d3-bin"
    edit = beside(bin_dir, helpers.LANES_INDEX)
    assert not (estate.config / "openRepoTools" / "lanes-index.conf").exists()
    env = {"LANES_EDIT": str(edit), "LANES_INDEX_CONFIG": None, "LANES_INDEX": "off",
           "LANES_LANE": "repoA-2"}
    tip = estate.tip()
    text = "test 14 - D3, a write with no configuration"
    proc = estate.run("bash", edit, "log", "NOTED", "lane:repoA-2", text, env=env)
    assert proc.returncode == 0, shown(proc)
    assert calls(bin_dir) == [], ("the stand-in at lanes-index's path was called", calls(bin_dir))
    assert estate.tip() != tip, "the write did not push"
    assert text in estate._git("show", "origin/main:lanes/log/repoA-2.md"), \
        "the note is not in the files"
    proc = estate.run("bash", edit, "lanes", "--index",
                      env={"LANES_EDIT": str(edit), "LANES_INDEX_CONFIG": None,
                           "LANES_INDEX": None})
    assert [c["argv"][:1] for c in calls(bin_dir)] == [["export"]], (
        "`lanes --index` did not reach the stand-in, so it is not where lanes-edit.sh "
        "finds lanes-index", calls(bin_dir), shown(proc))


def test_mode_primary_with_sqlite_is_refused(estate):
    """`mode=primary` with `store=sqlite`, or with no `register_url=` (whose
    store is SQLite by default), on T203's flipped copy, where Q6(c)'s
    refusal is lifted: T104's refusal answers 2 (L1v4.10:117), with nothing
    on stdout and a `REFUSED:` line that is not Q6(c)'s text (lane 2's
    reading, NOTES question 29). `lanes-index mode` reads the configuration
    whatever `LANES_INDEX` says (lane 3, #165 6747957479)."""
    refused = exit_code("EXIT_REFUSED")
    state = Refusing(estate)
    copy = state_copy(state.root / "flipped", True)
    for name, text in (("store-sqlite", state.config_text(store="sqlite")),
                       ("no-register-url", state.config_text(register=False))):
        conf = state.other_config(f"{name}.conf", text)
        proc = state.index(copy, "mode", LANES_INDEX_CONFIG=str(conf))
        assert proc.returncode == refused, (name, shown(proc))
        assert proc.stdout == "", (name, shown(proc))
        lines = proc.stderr.splitlines()
        assert len(lines) == 1 and lines[0].startswith(PREFIX + "REFUSED: "), (name, shown(proc))
        assert REFUSED_TEXT not in proc.stderr, (name, "Q6(c)'s text from the flipped copy",
                                                 shown(proc))
    assert state.psql_calls() == [], state.psql_calls()


#: `register read`'s forms (contract section 3.6; its section 2.7's 78 row):
#: the readers', forms 1 and 3, and `--for guard`'s, forms 2 and 4.
def read_forms(family: str, state: Refusing) -> list:
    cache = str(state.root / "cache")
    pid = str(os.getpid())
    if family == "readers":
        return [["--prefetch", "--cache", cache, "--all"],
                ["--since", "0", "--cache", cache]]
    return [["--for", "guard", "--prefetch", "--cache", cache, "--pid", pid,
             "--repo", str(state.e.wip), "--lane=repoA-2"],
            ["--for", "guard", "--at", "1", "--pid", pid, "--cache", cache,
             "--lane=repoA-2"]]


@pytest.mark.parametrize("family", ["readers", "for-guard"])
def test_register_read_exits_78_under_the_refusal(estate, family):
    """`lanes-index register read`, in each of its forms, exits 78 with the
    text, never 2 (AT-14; contract section 2.7): readers and the guard learn
    the mode from it. Nothing connects, and no cache is written."""
    config_code = exit_code("EXIT_CONFIG")
    state = Refusing(estate)
    for argv in read_forms(family, state):
        proc = state.index(state.copy, "register", "read", *argv)
        assert proc.returncode == config_code, (argv, shown(proc))
        assert REFUSED_TEXT in proc.stderr, (argv, shown(proc))
    assert state.psql_calls() == [], state.psql_calls()
    assert not (state.root / "cache").exists(), "a cache was written under the refusal"


@pytest.mark.parametrize("reader", READER_CASES)
def test_readers_under_the_refusal_answer_the_78_as_a_failed_read(estate, reader):
    """The readers, run from the same estate under the refusal (AT-14; the
    delta's "Readers under the refusal"; the phase plan's "D3's refusal"):
    `register read` answers 78, and each reader answers it as a failed read.
    A read that decides exits 69 with nothing on stdout; a listing and the
    `SessionStart` block answer from the mirror, exit 0, with the `read:
    mirror` line on stderr; the prompt guard exits 2; `managed-projection`
    answers 1, UNKNOWN, never 8. The fake `psql`'s log stays empty, and the
    files and origin are unchanged."""
    state = Refusing(estate)
    bin_dir = state.root / "bin"
    edit = beside(bin_dir, state.copy)
    before = state.origin_and_head()

    def asked(proc, what):
        assert calls(bin_dir), (what, "lanes-edit.sh never asked lanes-index, so it never met "
                                      "the refusal", shown(proc))

    if reader in DECIDE_READS:
        proc = state.edit(edit, *DECIDE_READS[reader])
        asked(proc, reader)
        assert proc.returncode == READ_FAILED, (reader, shown(proc))
        assert proc.stdout == "", (reader, shown(proc))
    elif reader == "listing":
        for argv in LISTINGS:
            forget_calls(bin_dir)
            proc = state.edit(edit, *argv)
            asked(proc, argv)
            assert proc.returncode == 0, (argv, shown(proc))
            assert MIRROR_LINE.search(proc.stderr), (argv, "no `read: mirror` line", shown(proc))
            assert not MIRROR_LINE.search(proc.stdout), (argv, shown(proc))
            assert proc.stdout.strip(), (argv, "the mirror gave no answer", shown(proc))
    elif reader == "session-start":
        proc = state.edit(edit, "session-start")
        assert proc.returncode == 0, shown(proc)
        assert MIRROR_LINE.search(proc.stderr), ("no `read: mirror` line", shown(proc))
        assert not MIRROR_LINE.search(proc.stdout), shown(proc)
    elif reader == "guard":
        proc = state.edit(edit, "guard", input_text=GUARD_INPUT)
        asked(proc, "guard")
        assert proc.returncode == GUARD_REFUSED, shown(proc)
    else:
        proc = state.edit(edit, "managed-projection", "repoM-1")
        asked(proc, "managed-projection")
        assert proc.returncode == PROJECTION_UNKNOWN, shown(proc)
        assert proc.returncode != PROJECTION_NEVER, shown(proc)
        assert "UNKNOWN" in proc.stderr, shown(proc)
    assert state.psql_calls() == [], ("a reader connected under the refusal", state.psql_calls())
    assert state.origin_and_head() == before, "the files or origin moved"
