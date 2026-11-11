# SPDX-License-Identifier: Apache-2.0
"""TEST C5: THE SQL REGISTER'S READERS (feature 007, T217, L2-N4; the test
plan's AT-C5; R29; FR-033, FR-034, FR-036, FR-059).

This module supersedes lane 5's seed of the same name (T502 part 1,
`refs/l5/T502`), and keeps its one test, `lanes --decide`, by name.

WHAT IT HOLDS, by its five sources:

  * AT-C5's sixteen (the test plan, "The readers' table, the one-call
    failure, and the callers' default arms"): each reader by the design's
    S3 table with the store unreachable; each mirror read's `read: mirror`
    line; the `none` arms; the read door's classification, a hygiene test;
    the callers that act on a listing; one failed call anywhere in a caller's
    read sequence; `lane-start`'s seven read arms at 75 and 3, and at 69; the
    other callers' arms (lane 4's table, "The callers' default arms (Q9)");
    the writer's printed rerun relayed on a 3; an expectation's 2 at
    `lane-start`'s last write; `register-row-local`; `lane-worktrees`' reads;
    `--index` on primary; and `managed-projection`.
  * Lane 1's three (L1v4.5's T113 and T114): `guard_second_read_at`,
    `log_key_hex_slot` and `journal_last_pickaxe`, each `lanes-index`'s own,
    on a real engine.
  * Lane 5's nine (A5; T504 to T506 and T509), their guessed names kept.
  * Lane 4's two read verbs (R29; GB section 4.3; T401), `register-text` and
    `register-grep`, with T401's two exit-2 cases each (O21a).
  * Lane 4's `key()` trim (T259; R31; GB section 4.3; T426): the one test that
    asks `retired-identity` about spellings that differ only past the
    sixteenth digit, in files mode and on primary.
  * Lane 2's T235 (F13b's proposed task, for lane 3 to place; lane 5's
    choice (b), #165 6778955065): on primary, T505's three read sites,
    `known_lanes`, `remote_log_events` and `worktree_rows`, read the store and
    never git, by the fake `git`'s argv log, on a real engine.

THE ARMS' IDS ARE THEIR LINES AT `2a057a6d`, as the test plan names them (the
block, T217), so they move with slices 1a and 1b and are re-cited at each
landing. `test_the_other_callers_arms_pass_the_code_or_refuse_as_lane_4s_
table_gives` names each arm's script first (lane 4's question 2, #165
6752694348), `<script>-<lines at 2a057a6d>-<code>`, so `-k
'the_other_callers_arms and lane-end'`, `and lane-handoff`, `and
skill-handoff`, `and skill-restart`, `and lane-rename`, `and lane-worktrees`
and `and lane-start` each select one script's arms; the bare `lane` script's
arms are `lane-416`, `lane-444`, `lane-1058` and `lane-1144`, which a word
selects by its line (`and (lane-416 or lane-444 or lane-1058 or lane-1144)`),
since `lane-` alone also matches every other script's. Each arm's `Arm`
names its line at the base this module was built on (`a2073eae`, with
T207c), found by its text at `2a057a6d`.

TWO STORES, ONE REGISTER. Every primary case here runs the CHECKOUT's
`lanes-edit.sh`, copied beside the contract's stub `lanes-index` (T207's
`contract_stub`, CLI4.5 section 6's copy rule, at drafts 4.10 and 4.11 since
T207c), on a workstation whose configuration says `mode=primary`. The stub's
register (the "store") holds the git register's files plus one row the git
register lacks, `STORE_ONLY_LANE`; so an answer that names it came from the
store, and one that does not came from the mirror. A small wrapper in front
of the stub (`DOOR_WRAPPER`) counts the register calls and fails the ones a
case names, the way the store fails when it cannot be reached: 69, `mode
primary` on stdout, and the cause on stderr (CLI4.5 section 3.6's exits).
That is the one-call failure's counter, at the `lanes-index` seam: the fake
`psql`'s own counter is the real `lanes-index`'s, which lane 1's three use.

THE ARMS' WRAPPER (AT-C5's fixture). `ARM_EDIT` is a `LANES_EDIT` that runs
the checkout's `lanes-edit.sh` for every verb but the one under test, which
exits the code under test and prints nothing on stdout; for the rerun cases
it prints the writer's rerun line on stderr. It logs each call of the verb
under test, so every arm case first asserts that its arm was REACHED, and a
case that never reaches its arm fails on that, never vacuously.

NO NETWORK. Every remote is a bare repository under `tmp_path`, `tmux`,
`claude` and `gh` are fakes, and `$HOME` is temporary. The real-engine cases
take `pg` from `tests/pgcluster.py` and skip where no PostgreSQL 16 is found,
unless `OPENREPOTOOLS_REQUIRE_PG=1`.

WHAT EACH WAITS FOR (the block's Order): L4-A1, L5-A4 and L5-A5; lane 1's
three for L1v4.5's T113 and T114; lane 5's for T504 to T506 and T509; the
`--decide` test for T502; the read verbs' for lane 4's T401; the arms for
lane 4's T402 to T408; `key()`'s trim, on primary only, for lane 4's T426;
T235's for lane 5's T505, its three door forms included, whose oracles are
lane 3's batch 7 (#165 6780364102), by batch 5's answers 3 and 4.
Every case on `RealRegister` (lane 1's three and `managed-projection`'s RE
case) also fails until lane 2's T227 (`tmpl` built by the bootstrap) and
T228 (the `lanes_w_fx` and `lanes_r_fx` logins), each by the fixture's own
assertion (T217h).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import sql_register_helpers as helpers
from conftest import REPO
from test_lane_start_claude_current import FAKE_CLAUDE_CURRENT, Sandbox, _write
from test_lanes_index import (UUID_A1, UUID_A1B, UUID_A2, UUID_M1, Estate,
                              estate, load_indexer)

__all__ = ["estate"]  # the fixture, imported so that pytest finds it here

pytestmark = [pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                 reason="the lane tooling is bash over git")]

LANES_EDIT = REPO / "lanes-edit.sh"

#: THE STORE'S OWN ROW: a lane the store's `lanes/LANES.md` holds and the git
#: register does not, so a reader's answer says which store answered.
STORE_ONLY_LANE = "repoS-1"
STORE_ONLY_UUID = "99999999-0001-4000-8000-000000009001"
STORE_ONLY_ROW = (f"| `{STORE_ONLY_LANE}` | harness `{STORE_ONLY_UUID}` | Eagle / test / brett "
                  f"| 2026-10-05T00:00Z | none | handoffs/{STORE_ONLY_LANE}.md "
                  f"| LIVE · 2026-10-05T00:00:00Z · a row only the store holds |")
STORE_ONLY_LOG = (f"STARTED — lane {STORE_ONLY_LANE}, session {STORE_ONLY_UUID}@Eagle, "
                  f"2026-10-05T00:00:00Z, lane:{STORE_ONLY_LANE} → home opensoft/repoS; "
                  f"dir /work/repoS\n")

#: THE STORE UNREACHABLE (CLI4.5 section 3.6's exits, forms 1 and 3): a
#: failed direct read is 69, and the first stdout line is the mode.
UNREACHABLE_EXIT = 69
UNREACHABLE_STDERR = ("lanes-index: register read: refuse db could not connect to server: "
                      "No such file or directory (the test's store is unreachable)\n")

#: The `read: mirror` line (design S3, "The mirror reads"): stderr, never
#: stdout, `read: mirror at <sha12>, <k> sequences behind or unknown (sql
#: unreachable: <why>)`.
MIRROR_LINE = re.compile(r"^read: mirror at [0-9a-f]{12}, .*$", re.M)

#: THE DOOR'S WRAPPER: `lanes-index` beside the copied `lanes-edit.sh`. It
#: logs every call, counts the register calls (every call but `mode` and the
#: derived index's `sync` nudge), and fails those `lanes-index.fail` names:
#: `{"calls": [k, ...]}` or `{"all": true}`, optionally only for some forms
#: (`"forms": [1, 3]`), with the exit, stdout and stderr given. `"narrow":
#: "register,aliases"` makes a form-1 prefetch fetch only those members (a
#: read site with no prefetched file). Every other call is the contract
#: stub's, in `store/`.
DOOR_WRAPPER = r'''#!/usr/bin/env python3
# THE DOOR'S WRAPPER (T217): counts and fails register calls, else the stub.
import fcntl, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "store", "lanes-index")
args = sys.argv[1:]


def form(argv):
    if argv[:2] != ["register", "read"]:
        return 0
    rest = set(a.split("=", 1)[0] for a in argv[2:])
    if "--at" in rest:
        return 4
    if "--for" in rest:
        return 2
    if "--since" in rest:
        return 3
    return 1


def caller_verb():
    """The `lanes-edit.sh` verb whose process (or subshell) called this one."""
    try:
        with open("/proc/%d/cmdline" % os.getppid(), "rb") as handle:
            argv = [a.decode("utf-8", "replace") for a in handle.read().split(b"\0")]
    except OSError:
        return ""
    for i, a in enumerate(argv[:-1]):
        if a.endswith("lanes-edit.sh"):
            return argv[i + 1]
    return ""


counted = args[:1] not in (["mode"], ["sync"])
with open(os.path.join(HERE, "lanes-index.calls"), "a+", encoding="utf-8") as log:
    fcntl.flock(log, fcntl.LOCK_EX)
    log.seek(0)
    number = sum(1 for line in log if json.loads(line)["counted"]) + (1 if counted else 0)
    log.write(json.dumps({"argv": args, "counted": counted, "k": number if counted else 0,
                          "form": form(args), "verb": caller_verb()}) + "\n")
try:
    with open(os.path.join(HERE, "lanes-index.fail"), encoding="utf-8") as handle:
        fail = json.load(handle)
except FileNotFoundError:
    fail = {}
if os.environ.get("T217_DOOR_FAIL") == "all":       # the arms' real failure, one process
    fail = dict(fail, all=True, exit=69, stdout="mode primary\n",
                stderr="lanes-index: register read: refuse db could not connect to server\n")
if counted and fail:
    hit = fail.get("all") or number in fail.get("calls", [])
    if fail.get("forms") and form(args) not in fail["forms"]:
        hit = False
    if hit:
        sys.stdout.write(fail.get("stdout", "mode primary\n"))
        sys.stderr.write(fail.get("stderr", ""))
        sys.exit(int(fail.get("exit", 69)))
MOVED = os.path.join(HERE, "lanes-index.moved")
if fail.get("move") and form(args) == 3 and not os.path.exists(MOVED):
    # The head moves once, between the prefetch and the first second read.
    import hashlib, shutil
    open(MOVED, "w").close()
    state_path = os.path.join(HERE, "store", "lanes-index.state")
    with open(state_path, encoding="utf-8") as handle:
        state = json.load(handle)
    old = os.path.join(HERE, "store", "lanes-index.register", str(state["n"]))
    new = os.path.join(HERE, "store", "lanes-index.register", str(state["n"] + 1))
    shutil.copytree(old, new)
    rows = []
    for path, text in fail["move"].items():
        target = os.path.join(new, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(text.encode("utf-8"))
        rows.append("%s\t1\t%s" % (path, hashlib.sha256(text.encode("utf-8")).hexdigest()))
    state["n"] += 1
    state["journal"]["00000000-0000-4000-8000-%012d" % state["n"]] = {
        "seq": state["n"], "lane": "repoA-1", "verb": "log", "args_sha256": "0" * 64,
        "workstation": "Eagle", "generation": state["generation"], "files": rows}
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
if fail.get("narrow") and form(args) == 1:
    kept, skip = [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a == "--all":
            kept += ["--files", fail["narrow"]]
        elif a == "--files":
            kept += ["--files", fail["narrow"]]
            skip = True
        else:
            kept.append(a)
    args = kept
os.execv(STORE, [STORE] + args)
'''

#: THE ARMS' WRAPPER, a `LANES_EDIT` (AT-C5's fixture). `ARM_VERB` is the
#: verb under test; `ARM_MATCH`, where set, a glob its other arguments must
#: match; `ARM_NTH`, where set, the one call of it (counted from 1) that
#: fails. That call exits `ARM_CODE`, prints `ARM_STDERR` on stderr and
#: nothing on stdout, and is logged to `ARM_LOG`; every other call is the
#: real `lanes-edit.sh` at `ARM_REAL`. `ARM_REAL_FAIL`, where set, makes that
#: call the REAL verb with every store read it makes failing (the door's
#: `T217_DOOR_FAIL=all`), for a verb whose failed read has its own answer,
#: such as `managed-projection`'s 1 (lane 3's ruling, #165 6754439281, item
#: 6). `ARM_FAKE_VERB`, where set, is one
#: more verb the wrapper answers itself, 0 with `ARM_FAKE_OUT`: a scenario's
#: fact a sandbox cannot make, such as a live session in this window, which
#: `window-session` reads from a live process's record.
ARM_EDIT = r'''#!/usr/bin/env bash
# THE ARMS' WRAPPER (T217; the test plan's AT-C5 fixture).
if [ -n "${ARM_FAKE_VERB-}" ] && [ "${1-}" = "$ARM_FAKE_VERB" ]; then
  printf '%s\n' "${ARM_FAKE_OUT-}"
  exit 0
fi
if [ "${1-}" = "${ARM_VERB-}" ]; then
  arm_rest="${*:2}"
  # shellcheck disable=SC2053
  if [ -z "${ARM_MATCH-}" ] || [[ "$arm_rest" == $ARM_MATCH ]]; then
    arm_n=$(( $(cat "$ARM_LOG.count" 2>/dev/null || echo 0) + 1 ))
    printf '%s\n' "$arm_n" > "$ARM_LOG.count"
    if [ -z "${ARM_NTH-}" ] || [ "$arm_n" = "$ARM_NTH" ]; then
      printf '%s\n' "$*" >> "$ARM_LOG"
      if [ -n "${ARM_REAL_FAIL-}" ]; then
        # The verb's REAL answer to a failed read: every store read it makes fails.
        T217_DOOR_FAIL=all exec bash "$ARM_REAL" "$@"
      fi
      [ -z "${ARM_STDERR-}" ] || printf '%s\n' "$ARM_STDERR" >&2
      exit "$ARM_CODE"
    fi
  fi
fi
exec bash "$ARM_REAL" "$@"
'''

#: The writer's printed rerun on a 3 (AT-C5's fixture, "For the rerun
#: cases"), with the write id and generation a case can find in stderr.
RERUN_WRITE_ID = "77777777-0001-4000-8000-000000007001"
RERUN_GENERATION = "66666666-0001-4000-8000-000000006001"

#: A session id only this checkout's copy of a row holds (the local unions).
LOCAL_SID = "aaaaaaaa-0006-4000-8000-00000000a006"

#: The arms' sandbox's two further lanes' sessions.
UUID_A3 = "aaaaaaaa-0004-4000-8000-00000000a004"
UUID_H1 = "aaaaaaaa-0005-4000-8000-00000000a005"
UUID_N1 = "aaaaaaaa-0007-4000-8000-00000000a007"


def rerun_line(lane: str, argv: str) -> str:
    return (f"LANES_WRITE_ID={RERUN_WRITE_ID} LANES_WRITE_GENERATION={RERUN_GENERATION} "
            f"LANES_LANE={lane} LANES_SESSION={UUID_A1} lanes-edit.sh {argv}")


# ---------------------------------------------------------------- the stores
def render_set(root: Path) -> dict:
    """The render set's files under `root` (a checkout), as `contract_stub`
    takes them: `lanes/LANES.md`, `lanes/aliases.tsv`, each lane log but the
    README, and `lanes/archive/*`."""
    found = {}
    for path in sorted((root / "lanes").rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and helpers.RENDER_SET_PATH.match(rel):
            found[rel] = path.read_bytes()
    return found


class Door:
    """The primary store beside a copied `lanes-edit.sh`: the contract stub
    in `<bin>/store/`, the wrapper `<bin>/lanes-index`, and `mode=primary` in
    the configuration `lanes-index` reads."""

    def __init__(self, bin_dir: Path, register: dict, config: Path):
        self.bin = bin_dir
        self.store = bin_dir / "store"
        lanes = register.get("lanes/LANES.md", b"").decode("utf-8")
        register = dict(register)
        register["lanes/LANES.md"] = (lanes.rstrip("\n") + "\n" + STORE_ONLY_ROW + "\n").encode()
        register[f"lanes/log/{STORE_ONLY_LANE}.md"] = STORE_ONLY_LOG.encode()
        self.register = register
        helpers.contract_stub(self.store, register)
        _write(bin_dir / "lanes-index", DOOR_WRAPPER)
        config.parent.mkdir(parents=True, exist_ok=True)
        # A configuration `load_config` would accept once the constant is flipped (T217h; lane
        # 5's finding 1, #165 6771208498): `register_url=` the writer's login and `reader_url=`
        # the reader's beside it. The stub answers `mode` alone and reads none of it.
        config.write_text("mode=primary\n"
                          f"register_url=postgresql://{RealRegister.WRITER}@localhost:5432/lanes\n"
                          f"reader_url=postgresql://{RealRegister.READER}@localhost:5432/lanes\n",
                          encoding="utf-8")
        config.chmod(0o600)
        self.config = config
        self.psql_dir = bin_dir.parent / "psqlbin"
        _write(self.psql_dir / "psql", helpers.REGISTER_FAKE_PSQL)
        self.psql_log = bin_dir.parent / "psql.log"
        self.psql_answers = bin_dir.parent / "psql-answers.json"
        self.psql_answers.write_text(json.dumps([{"exit": 2, "stderr":
                                                  "psql: error: connection refused\n"}]))

    def env(self) -> dict:
        return {"LANES_INDEX_CONFIG": str(self.config), "FAKE_PSQL_LOG": str(self.psql_log),
                "FAKE_PSQL_ANSWERS": str(self.psql_answers), "LANES_INDEX": None}

    def fail(self, **spec) -> None:
        (self.bin / "lanes-index.fail").write_text(json.dumps(spec), encoding="utf-8")

    def unreachable(self, forms=None) -> None:
        spec = {"all": True, "exit": UNREACHABLE_EXIT, "stdout": "mode primary\n",
                "stderr": UNREACHABLE_STDERR}
        if forms:
            spec["forms"] = forms
        self.fail(**spec)

    def reachable(self) -> None:
        path = self.bin / "lanes-index.fail"
        if path.exists():
            path.write_text("{}", encoding="utf-8")

    def calls(self) -> list:
        path = self.bin / "lanes-index.calls"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def register_calls(self) -> list:
        return [c for c in self.calls() if c["counted"]]

    def forget_calls(self) -> None:
        for name in ("lanes-index.calls",):
            path = self.bin / name
            if path.exists():
                path.write_text("", encoding="utf-8")
        if self.psql_log.exists():
            self.psql_log.write_text("", encoding="utf-8")

    def psql_calls(self) -> list:
        if not self.psql_log.exists():
            return []
        return [line for line in self.psql_log.read_text(encoding="utf-8").splitlines() if line]

    def commit(self, files: dict) -> int:
        """Advance the store's head by one seq holding `files` (render-set
        paths to text, or None to delete), as a committed write would."""
        state_path = self.store / "lanes-index.state"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        old = self.store / "lanes-index.register" / str(state["n"])
        new = self.store / "lanes-index.register" / str(state["n"] + 1)
        shutil.copytree(old, new)
        rows = []
        for path, text in files.items():
            target = new / path
            if text is None:
                if target.exists():
                    target.unlink()
                rows.append(f"{path}\t0\t-")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = text.encode() if isinstance(text, str) else text
            target.write_bytes(data)
            import hashlib
            rows.append(f"{path}\t1\t{hashlib.sha256(data).hexdigest()}")
        state["n"] += 1
        state["journal"][f"00000000-0000-4000-8000-{state['n']:012d}"] = {
            "seq": state["n"], "lane": "repoA-1", "verb": "log", "args_sha256": "0" * 64,
            "workstation": "Eagle", "generation": state["generation"], "files": rows}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state["n"]

    def head(self) -> tuple:
        state = json.loads((self.store / "lanes-index.state").read_text(encoding="utf-8"))
        return state["n"], state["generation"]

    def rows(self, lane: str) -> int:
        """How many rows the store's `lanes/LANES.md` holds for `lane` at its head."""
        path = self.store / "lanes-index.register" / str(self.head()[0]) / "lanes" / "LANES.md"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        return sum(1 for line in text.splitlines() if line.startswith(f"| `{lane}` "))


class Primary:
    """An `Estate` (test_lanes_index's register) whose workstation is
    configured `mode=primary`, with the checkout's `lanes-edit.sh`, `lanes`,
    `repos.tsv` and `lane-start` copied beside the door (CLI4.5:885)."""

    def __init__(self, estate: Estate):
        self.e = estate
        self.bin = estate.root / "primary-bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        for name in ("lanes-edit.sh", "lanes", "repos.tsv", "lane-start", "lane-worktrees"):
            shutil.copy2(REPO / name, self.bin / name)
        self.edit_path = self.bin / "lanes-edit.sh"
        self.door = Door(self.bin, render_set(estate.wip),
                         estate.config / "openRepoTools" / "lanes-index.conf")

    def env(self, extra: dict | None = None) -> dict:
        env = {"LANES_EDIT": str(self.edit_path),
               "PATH": self.e.path_with(self.door.psql_dir)}
        env.update(self.door.env())
        env.update(extra or {})
        return env

    def edit(self, *args, env: dict | None = None, **kw) -> subprocess.CompletedProcess:
        return self.e.run("bash", self.edit_path, *args, env=self.env(env), **kw)

    def files_edit(self, *args, env: dict | None = None, **kw) -> subprocess.CompletedProcess:
        """The same read in files mode: the checkout's own `lanes-edit.sh`,
        no configuration, no door. `XDG_CONFIG_HOME` is empty, so the
        configuration falls to the estate's empty `$HOME/.config`: the
        estate's own names the folder the door's `mode=primary` file is in,
        which lane 1's T113 refuses there with 78 (T217m; lane 5's triage,
        #165 6782743644: `window-lane` answered 69, not the mirror's 8)."""
        merged = {"XDG_CONFIG_HOME": ""}
        merged.update(env or {})
        return self.e.run("bash", LANES_EDIT, *args, env=merged, **kw)

    def script(self, name: str, *args, env: dict | None = None, **kw):
        return self.e.run("bash", self.bin / name, *args, env=self.env(env), **kw)


@pytest.fixture
def primary(estate):
    return Primary(estate)


# ------------------------------------------------- AT-C5: the readers' table
#: THE READERS' TABLE (design S3, "Each reader with the database
#: unreachable"), for each reader that is a `lanes-edit.sh` arm: its argv, the
#: exit with the store unreachable, and whether 8 is barred ("never 8").
#: `lane`, `lane-end` and `lane-rename` are the callers' cases below; the
#: listings are the mirror test's; the guard reads its hook JSON on stdin.
READERS = {
    "who": (("who", "opensoft/repoA#7"), 69),
    "binding": (("binding", "repoA-1"), 69),
    "live-holder": (("live-holder", "repoA-1"), 69),
    "next-free": (("next-free", "repoA"), 69),
    "lane-last": (("lane-last", "repoA-1"), 69),
    "register-row": (("register-row", "repoC-9"), 69),
    "session-lane": (("session-lane", UUID_A2), 69),
    "canon-lane": (("canon-lane", "repoA-1"), 69),
    "resolve-home": (("resolve-home", "repoA-1"), 69),
    "register-row-local": (("register-row-local", "repoC-9"), 69),
    "managed-projection": (("managed-projection", "repoM-1"), 1),
    "guard": (("guard",), 2),
}

GUARD_INPUT = json.dumps({"session_id": UUID_A2, "prompt": "hello", "hook_event_name":
                          "UserPromptSubmit", "transcript_path": "/dev/null", "cwd": "/"})


@pytest.mark.parametrize("reader", sorted(READERS))
def test_each_reader_follows_the_table_when_the_store_is_unreachable(primary, reader):
    """Each reader in the design's S3 table, with the store unreachable,
    exits the table's code (69; 1 for `managed-projection`; 2 for the
    guard), prints no answer on stdout, and never says 8 for a read that
    failed. The door asked the store first: the read that failed is the
    store's, not a git read's."""
    argv, code = READERS[reader]
    primary.door.unreachable()
    kw = {"input_text": GUARD_INPUT} if reader == "guard" else {}
    result = primary.edit(*argv, **kw)
    assert primary.door.register_calls(), \
        (reader, "the door never asked the store", result.returncode, result.stderr)
    assert result.returncode == code, (reader, result.returncode, result.stdout, result.stderr)
    assert result.returncode != 8, (reader, result.stderr)
    if reader != "guard":
        assert result.stdout == "", (reader, result.stdout)
    if reader == "managed-projection":
        assert "UNKNOWN" in result.stderr, result.stderr
        assert "legacy" not in result.stdout + result.stderr, result.stderr


#: THE LISTINGS AND THE OFFLINE READS (AT-C5's oracle): each prints `read:
#: mirror at <sha12>, …` on stderr and exits with its own code. The fourth,
#: the launcher's bare window reads, is `window-lane` without a window,
#: which the launcher makes before any lane is bound.
MIRROR_READS = {
    "lanes": ("lanes",),
    "history": ("history", "--all"),
    "session-start": ("session-start",),
    "launcher-window-reads": ("swapped",),
}


@pytest.mark.parametrize("listing", sorted(MIRROR_READS))
def test_each_mirror_read_prints_its_line_and_keeps_its_exit(primary, listing):
    """With the store unreachable, a mirror read reads the mirror: it prints
    the `read: mirror` line on stderr, never on stdout, and exits as the same
    read does in files mode, with the mirror's answer (no row only the store
    holds). `session-start` and the bare window reads exit 0."""
    argv = MIRROR_READS[listing]
    env = {"LANES_READ_MIRROR": "1"} if listing == "launcher-window-reads" else None
    files = primary.files_edit(*argv, env=env)
    primary.door.unreachable()
    result = primary.edit(*argv, env=env)
    assert primary.door.register_calls() or listing == "session-start", \
        (listing, "the door never asked the store", result.stderr)
    assert MIRROR_LINE.search(result.stderr), (listing, result.stderr)
    assert not MIRROR_LINE.search(result.stdout), (listing, result.stdout)
    assert result.returncode == files.returncode, (listing, result.returncode, files.returncode,
                                                   result.stderr)
    assert STORE_ONLY_LANE not in result.stdout, (listing, result.stdout)
    if listing in ("session-start", "launcher-window-reads"):
        assert result.returncode == 0, (listing, result.stderr)


#: THE `none` ARMS (design, "The readers' SQL path": the L and F arms), each
#: with an argv it answers today.
NONE_ARMS = {
    "workstation": ("workstation",),
    "fetch-age": ("fetch-age",),
    "window-session": ("window-session", "testsess:@1"),
    "transcript-holders": ("transcript-holders", UUID_A1),
}


@pytest.mark.parametrize("arm", sorted(NONE_ARMS))
def test_a_none_class_arm_makes_no_register_call_with_the_store_unreachable(primary, arm):
    """A `none` arm has no door: with the store unreachable it makes no
    register call and runs no `psql`, and answers as it does in files mode.
    The control: in the same estate, a decide arm asks the store, so the
    silence is the class's and not an unconfigured workstation's."""
    primary.door.unreachable()
    control = primary.edit("register-row", "repoA-1")
    assert primary.door.register_calls(), \
        ("the configuration is not live: a decide arm asked nothing", control.stderr)
    primary.door.forget_calls()
    argv = NONE_ARMS[arm]
    files = primary.files_edit(*argv)
    result = primary.edit(*argv)
    assert primary.door.calls() == [], (arm, primary.door.calls())
    assert primary.door.psql_calls() == [], (arm, primary.door.psql_calls())
    assert (result.returncode, result.stdout) == (files.returncode, files.stdout), \
        (arm, result.returncode, result.stdout, files.returncode, files.stdout)


#: THE SIX CLASSES (design, "The readers' SQL path"; T504's class table; R46).
CLASSES = ("decide", "mirror", "guard", "projection", "none", "writer")

#: What the table must say for the arms whose class is named in the design
#: and in T504's rows, of the arms every tree has; every other arm must be in
#: exactly one class. T401's `register-text` and `register-grep`, T410's
#: `act-begin`, T427's `start-record` and T502's `guard-bind` are not named
#: here: whichever of T504 and the arm's task lands second adds the arm's
#: row, and the table is held to the dispatcher (T217n; lane 3, #165
#: 6782923063).
NAMED_CLASSES = {
    "lanes": "mirror", "history": "mirror", "session-start": "mirror",
    "guard": "guard", "managed-projection": "projection",
    "workstation": "none", "fetch-age": "none", "window-session": "none",
    "transcript-holders": "none", "canon-lane": "decide",
    "who": "decide", "binding": "decide", "register-row": "decide",
    "register-row-local": "decide",
    "add-row": "writer", "set-row-state": "writer", "log": "writer", "claim": "writer",
}

#: THE CLASS TABLE'S FORM (lane 5's answer 12, #165 6746507353): one function
#: before the dispatcher, `reg_class_of`, with one `case` arm per row, in the
#: form `register-text) REG_CLASS=decide ;;`. A row may also set
#: `REG_MIRROR_VAR=1` (item 1's ten arms), and `*)` is decide.
CLASS_FUNCTION = re.compile(r"^reg_class_of\(\)\s*\{[^\n]*$(.*?)^\}\s*$", re.M | re.S)
CLASS_ARM = re.compile(r"^\s*([A-Za-z0-9_|*-]+)\)[^\n]*?\bREG_CLASS=['\"]?"
                       r"(decide|mirror|guard|projection|none|writer)\b", re.M)


def dispatcher_arms(text: str) -> list:
    """The arms of `lanes-edit.sh`'s dispatcher: the `case "$cmd" in` that
    holds `who)`, each arm at two spaces' indent, its patterns split on
    `|`."""
    blocks = [m.start() for m in re.finditer(r'^case "\$cmd" in\s*$', text, re.M)]
    for start in reversed(blocks):
        end = re.compile(r"^esac\s*$", re.M).search(text, start)
        body = text[start:end.start() if end else len(text)]
        arms = re.findall(r"^  ([a-z][a-z0-9|-]*)\)", body, re.M)
        if "who" in arms:
            names = []
            for arm in arms:
                names += arm.split("|")
            return names
    return []


def test_every_dispatcher_arm_is_classified_for_the_read_door():
    """THE HYGIENE TEST (AT-C5; R46): every dispatcher arm of `lanes-edit.sh`
    is in exactly one of the six classes of the read door's one table,
    `writer` among them for the write guard's verbs; the arms the design
    and T504 name, of those every tree has (`NAMED_CLASSES`), have the
    class they name; and the table names no arm the dispatcher lacks."""
    text = LANES_EDIT.read_text(encoding="utf-8")
    arms = dispatcher_arms(text)
    assert len(arms) > 50 and "who" in arms, arms
    table = CLASS_FUNCTION.search(text)
    assert table, "lanes-edit.sh has no read door class table (reg_class_of)"
    seen = {}
    for patterns, klass in CLASS_ARM.findall(table.group(1)):
        for arm in patterns.split("|"):
            seen.setdefault(arm, []).append(klass)
    assert seen, ("reg_class_of holds no `<arm>) REG_CLASS=<class> ;;` row", table.group(1))
    default = seen.pop("*", [])
    assert default in ([], ["decide"]), ("the default row must be decide (answer 12)", default)
    twice = {arm: k for arm, k in seen.items() if len(k) != 1}
    assert not twice, ("arms in more than one class", twice)
    missing = sorted(set(arms) - set(seen)) if not default else []
    assert not missing, ("dispatcher arms in no class", missing)
    stray = sorted(set(seen) - set(arms))
    assert not stray, ("classes for arms the dispatcher lacks", stray)
    for arm, klass in NAMED_CLASSES.items():
        assert arm in arms, (arm, "is not a dispatcher arm")
        assert seen.get(arm, default) == [klass], (arm, seen.get(arm, default), klass)
    assert set(k for ks in seen.values() for k in ks) <= set(CLASSES), seen


# ------------------------------------------ the callers that act on a listing
@pytest.mark.parametrize("caller", ["lane", "lane-end-retire-dormant"])
def test_a_caller_that_acts_on_a_listings_answer_refuses_69_where_the_store_is_unreachable(
        primary, caller):
    """`lane` and `lane-end --retire-dormant` act on the `lanes` listing's
    answer, so they pass `--decide` and refuse 69 where the store cannot be
    read, acting on nothing: never the mirror's answer (design S3; R38)."""
    primary.door.unreachable()
    before = primary.e.tip()
    for name in ("lane", "lane-end"):
        shutil.copy2(REPO / name, primary.bin / name)
    if caller == "lane":
        result = primary.script("lane", "--all")
    else:
        result = primary.script("lane-end", "--retire-dormant", "repoA", "--yes")
    lanes_calls = [c["argv"] for c in primary.door.register_calls()]
    assert lanes_calls, (caller, "the listing never reached the store", result.stderr)
    assert result.returncode == 69, (caller, result.returncode, result.stdout, result.stderr)
    assert primary.e.tip() == before, (caller, "the register moved")
    assert "repoA-1" not in result.stdout, (caller, result.stdout)


# ----------------------------------------------------- the one-call failure
#: Each caller's run on primary, from the arms' sandbox: (script, argv).
#: Open point 14: k runs over every call of the run's sequence, or the
#: first `ONE_CALL_SAMPLE` of them and the last, where the sequence is longer.
ONE_CALL_SAMPLE = 12
CALLERS = {
    "lane-start": ("lane-start", ("repoZ", "1")),
    "lane-end": ("lane-end", ("repoA-2",)),
    "lane": ("lane", ("repoA-2",)),
    "lane-handoff": ("lane-handoff", ("--lane", "repoA-2", "the one-call test")),
    "lane-rename": ("lane-rename", ("repoA-2", "repoA-7", "the one-call test", "--no-tmux",
                                    "--no-github")),
}


@pytest.mark.parametrize("caller", sorted(CALLERS))
def test_one_failed_call_anywhere_in_a_callers_read_sequence_never_fails_open(tmp_path, caller):
    """ADV-C5: a store that fails exactly one call, run across each caller's
    read sequence. For each k the caller refuses (or notes, where round 1's 2A
    allows a note), never makes a second row, and where it refused the
    register's rows and logs are unchanged. The sequence is first measured
    with no failure: a caller on primary that makes no register call at all
    has no door yet."""
    world = PrimaryWorld(tmp_path)
    script, argv = CALLERS[caller]
    clean = world.run(script, *argv)
    sequence = world.door.register_calls()
    assert sequence, (caller, "no register call on primary", clean.returncode, clean.stderr)
    ks = list(range(1, len(sequence) + 1))
    if len(ks) > ONE_CALL_SAMPLE:
        ks = ks[:ONE_CALL_SAMPLE] + ks[-1:]
    for k in ks:
        world = PrimaryWorld(tmp_path / f"k{k}")
        before = (world.register_bytes(), world.door.head())
        world.door.fail(calls=[k], exit=UNREACHABLE_EXIT, stdout="mode primary\n",
                        stderr=UNREACHABLE_STDERR)
        result = world.run(script, *argv)
        failed = [c for c in world.door.register_calls() if c["k"] == k]
        if not failed:
            continue  # this run's sequence is shorter: the failure moved its path
        lane = caller_lane(caller)
        rows = max(world.store_rows(lane), world.door.rows(lane))
        assert rows <= 1, (caller, k, "a second row", rows)
        if failed[0].get("verb") == "managed-projection" and caller in ("lane-start", "lane-end"):
            # Lane 3's ruling (#165 6754439281, item 6): projection-class, its
            # failed read is 1, and the caller refuses 1, UNKNOWN, never 69.
            assert result.returncode == 1 and "UNKNOWN" in result.stderr, \
                (caller, k, "managed-projection's failed read", result.returncode,
                 result.stderr[-2000:])
        if result.returncode != 0:
            assert (world.register_bytes(), world.door.head()) == before, \
                (caller, k, "refused, yet wrote")
        else:
            assert "69" in result.stderr or MIRROR_LINE.search(result.stderr), \
                (caller, k, "carried on past a failed read without a word", result.stderr)


def caller_lane(caller: str) -> str:
    return {"lane-start": "repoZ-1", "lane-rename": "repoA-7"}.get(caller, "repoA-2")


# ---------------------------------------------------- the arms' sandbox
class ArmWorld(Sandbox):
    """`test_lane_start_claude_current`'s sandbox (a bare origin, a register
    clone, fake `tmux`, `claude` and `gh`), with every lifecycle script
    copied beside `lanes-edit.sh`, `ARM_EDIT` written beside them, a fake
    `codex` (a second agent, for `lane-start`'s non-`claude` read), and a
    register holding, each with its log:

      * `repoA-1` PAUSED, its log naming its directory and its last PAUSED
        transcript (a resume);
      * `repoA-2` LIVE here (an end, a handoff, a rename);
      * `repoA-3` LIVE on another workstation (`lane`'s `elsewhere` group);
      * `repoH-1` PAUSED, its log naming its home and no directory, where
        `$PROJECTS_ROOT/repoH` does not exist (`lane-start`'s `resolve-home`);
      * `repoN-1` LIVE, a row with no log (`lane-end`'s state-cell read)."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        for name in ("lane-end", "lane", "lane-handoff", "lane-rename", "lane-worktrees",
                     "lanes"):
            shutil.copy2(REPO / name, self.bin / name)
            (self.bin / name).chmod(0o755)
        self.resolver()
        self.arm_log = root / "arm.log"
        self.codex_log = root / "codex.log"
        _write(self.bin / "arm-edit", ARM_EDIT)
        _write(self.fakebin / "codex", f'#!/usr/bin/env bash\nprintf "codex %s\\n" "$*" >> "{self.codex_log}"\n')
        # `$PROJECTS_ROOT/repoA`, repoA's default directory: where a noted
        # `lane-dir` failure carries a resume on to, so the launch goes on.
        self.default_dir = self.home / "projects" / "repoA"
        self.git("init", "-q", "-b", "main", str(self.default_dir))
        self.git("-C", str(self.default_dir), "remote", "add", "origin",
                 "https://github.com/opensoft/repoA.git")
        rows = [
            f"| `repoA-1` | harness `{UUID_A1}` → `{UUID_A1B}` | Eagle / test / brett "
            f"| 2026-10-01T00:00Z | none | handoffs/repoA-1.md "
            f"| PAUSED · 2026-10-01T01:00:00Z · parked |",
            f"| `repoA-2` | harness `{UUID_A2}` | Eagle / test / brett | 2026-10-01T02:00Z "
            f"| none | handoffs/repoA-2.md | LIVE · 2026-10-01T02:00:00Z · working |",
            f"| `repoA-3` | harness `{UUID_A3}` | Falcon / test / brett | 2026-10-01T02:30Z "
            f"| none | handoffs/repoA-3.md | LIVE · 2026-10-01T02:30:00Z · working elsewhere |",
            f"| `repoH-1` | harness `{UUID_H1}` | Eagle / test / brett | 2026-10-01T03:00Z "
            f"| none | handoffs/repoH-1.md | PAUSED · 2026-10-01T03:30:00Z · parked |",
            f"| `repoN-1` | harness `{UUID_N1}` | Eagle / test / brett | 2026-10-01T04:00Z "
            f"| none | handoffs/repoN-1.md | LIVE · 2026-10-01T04:00:00Z · a row with no log |",
        ]
        lanes = self.wip / "lanes"
        (lanes / "log").mkdir(exist_ok=True)
        with open(lanes / "LANES.md", "a", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
        (lanes / "log" / "README.md").write_text("# the object logs\n", encoding="utf-8")
        (lanes / "log" / "repoA-1.md").write_text(
            f"STARTED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:00:00Z, "
            f"lane:repoA-1 → home opensoft/repoA; dir {self.lane_dir}; profile team-01a\n"
            f"PAUSED — lane repoA-1, session {UUID_A1B}@Eagle, 2026-10-01T01:00:00Z, "
            f"lane:repoA-1 → dir {self.lane_dir}; profile team-01a; agent claude; "
            f"transcript {UUID_A1B}\n", encoding="utf-8")
        (lanes / "log" / "repoA-2.md").write_text(
            f"STARTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-01T02:00:00Z, "
            f"lane:repoA-2 → home opensoft/repoA; dir {self.lane_dir}; profile team-01b\n",
            encoding="utf-8")
        (lanes / "log" / "repoA-3.md").write_text(
            f"STARTED — lane repoA-3, session {UUID_A3}@Falcon, 2026-10-01T02:30:00Z, "
            f"lane:repoA-3 → home opensoft/repoA; dir /work/repoA3; window w:@7\n",
            encoding="utf-8")
        (lanes / "log" / "repoH-1.md").write_text(
            f"STARTED — lane repoH-1, session {UUID_H1}@Eagle, 2026-10-01T03:00:00Z, "
            f"lane:repoH-1 → home opensoft/repoH\n"
            f"PAUSED — lane repoH-1, session {UUID_H1}@Eagle, 2026-10-01T03:30:00Z, "
            f"lane:repoH-1 → swap; agent claude; transcript {UUID_H1}\n", encoding="utf-8")
        self.git("-C", str(self.wip), "add", "-A")
        self.git("-C", str(self.wip), "commit", "-q", "-m", "the arms' register")
        self.git("-C", str(self.wip), "push", "-q", "origin", "main")
        self.git("-C", str(self.ws), "pull", "-q", "--ff-only")

    def arm_env(self, verb: str, code: int, match: str = "", nth: int = 0,
                stderr: str = "") -> dict:
        env = {"LANES_EDIT": str(self.bin / "arm-edit"), "ARM_REAL": str(self.bin / "lanes-edit.sh"),
               "ARM_VERB": verb, "ARM_CODE": str(code), "ARM_LOG": str(self.arm_log),
               "FAKE_CC_PATH": str(self.resolved)}
        if match:
            env["ARM_MATCH"] = match
        if nth:
            env["ARM_NTH"] = str(nth)
        if stderr:
            env["ARM_STDERR"] = stderr
        return env

    def reached(self) -> list:
        return self.arm_log.read_text(encoding="utf-8").splitlines() if self.arm_log.exists() else []

    def run(self, script: str, *args: str, env: dict | None = None,
            cwd: Path | None = None, stdin: str | None = None) -> subprocess.CompletedProcess:
        full = dict(self.env)
        full.setdefault("FAKE_CC_PATH", str(self.resolved))
        for key, value in (env or {}).items():
            if value is None:
                full.pop(key, None)
            else:
                full[key] = value
        return subprocess.run([str(self.bin / script), *args], env=full,
                              cwd=str(cwd or self.lane_dir), capture_output=True, text=True,
                              timeout=180, check=False, input=stdin,
                              stdin=None if stdin is not None else subprocess.DEVNULL)

    def register_bytes(self) -> dict:
        """The register as origin holds it: LANES.md and every log."""
        self.git("-C", str(self.wip), "fetch", "-q", "origin")
        out = self.git("-C", str(self.wip), "ls-tree", "-r", "--name-only", "origin/main",
                       "--", "lanes")
        files = {}
        for path in out.split():
            files[path] = self.git("-C", str(self.wip), "show", f"origin/main:{path}")
        return files

    def store_rows(self, lane: str) -> int:
        text = self.git("-C", str(self.wip), "show", "origin/main:lanes/LANES.md")
        return sum(1 for line in text.splitlines() if line.startswith(f"| `{lane}` "))


class PrimaryWorld(ArmWorld):
    """The arms' sandbox on primary: the copied `lanes-edit.sh` beside the
    door, `mode=primary` configured, and `LANES_EDIT` the copy."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.door = Door(self.bin, render_set(self.wip),
                         self.home / ".config" / "openRepoTools" / "lanes-index.conf")
        self.env.update({"LANES_EDIT": str(self.bin / "lanes-edit.sh"),
                         "PATH": f"{self.door.psql_dir}{os.pathsep}{self.env['PATH']}"})
        for key, value in self.door.env().items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value


@pytest.fixture
def arms(tmp_path: Path) -> ArmWorld:
    return ArmWorld(tmp_path / "arms")


# ----------------------------------------------------- the arms' table
class Arm:
    """One arm of lane 4's table ("The callers' default arms (Q9)"): the
    script and argv whose run reaches it, the verb it reads, which call of
    that verb is the arm's (`nth`, counted from 1; `match`, a glob the verb's
    other arguments must match), the arm's line at the base (`base`), the
    world it runs in (`arm`, files mode; `primary`, beside the door), and a
    verb the wrapper answers itself (`fake`, `(verb, line)`)."""

    def __init__(self, script: str, argv: tuple, verb: str, base: str, *, nth: int = 1,
                 match: str = "", world: str = "arm", fake: tuple = (), env: dict | None = None):
        self.script, self.argv, self.verb, self.base = script, argv, verb, base
        self.nth, self.match, self.world, self.fake = nth, match, world, fake
        self.env = env or {}


#: A live session in this window that the row's cell does not hold
#: (`window-session`'s five fields, `\037`-joined): what `lane-start`'s
#: `session-lane` read needs, and a sandbox cannot make from a live process.
WINDOW_SID = "aaaaaaaa-0009-4000-8000-00000000a009"
WINDOW_RECORD = "\037".join([WINDOW_SID, "testsess:@1", "claude", "99999", "team-01a"])

#: `lane-start`'s seven read arms, by their lines at `2a057a6d` (the test
#: plan's ids), each with its line at the base and a run that reaches it.
LANE_START_ARMS = {
    "1154": Arm("lane-start", ("repoA", "1"), "canon-lane", "1161"),
    "1262": Arm("lane-start", ("repoA", "1"), "swapped", "1315"),
    "1271": Arm("lane-start", ("repoA", "1"), "lane-dir", "1324"),
    "1332": Arm("lane-start", ("repoH", "1"), "resolve-home", "1385"),
    "2184-2186": Arm("lane-start", ("repoA", "1"), "session-lane", "2237",
                     fake=("window-session", WINDOW_RECORD)),
    "3079": Arm("lane-start", ("repoA", "2", "--agent", "codex"), "lane-transcript", "3132"),
    "3430": Arm("lane-start", ("repoA", "1"), "lane-transcript", "3483"),
}

#: The 69 arms (the design's table): a 69 refuses at `canon-lane` and
#: `session-lane`, and stays a note at the other four. `:1332` has no 69 row.
LANE_START_69 = {"1154": "refuse", "2184-2186": "refuse", "1262": "note", "1271": "note",
                 "3079": "note", "3430": "note"}

#: THE OTHER CALLERS' ARMS (lane 4's table), each id `<script>-<lines at
#: 2a057a6d>`, its codes, and what it must do: `refuse` (the verb's code,
#: nothing written), `code` (exit with the verb's code, never 1), `mirror`
#: (a `69)` arm that re-reads from the mirror and prints the `read: mirror`
#: line), `rename` (new text for the code), `lread` (the restart skill's
#: refusal, exit 1, for every code).
OTHER_ARMS = {
    "lane-end-930-938": (Arm("lane-end", ("repoA-2",), "canon-lane", "937"), (69, 75, 3), "refuse"),
    "lane-end-2490": (Arm("lane-end", ("repoA-2",), "log", "2543", match="ENDED*"),
                      (69, 75, 3), "code"),
    "lane-worktrees-508-524": (Arm("lane-worktrees", ("add", "repoA-2", "s1", "--dry-run"),
                                   "canon-lane", "508"), (69, 75, 3), "refuse-own-exit"),
    "lane-handoff-1463": (Arm("lane-handoff", ("--lane", "repoA-2", "the arms' test"),
                              "canon-lane", "1463", world="primary"), (69,), "mirror"),
    "lane-handoff-2817": (Arm("lane-handoff", ("--late", "--at", "2026-10-01T03:00:00Z", "--lane",
                                               "repoA-2", "the arms' late test"),
                              "log", "2817", match="PAUSED*"), (69, 75, 3), "code"),
    "skill-handoff-112": (Arm("skills/handoff/SKILL.md", ("canon-lane", "repoA-2"), "canon-lane",
                              "112", world="primary"), (69,), "mirror"),
    "skill-restart-70": (Arm("skills/restart/SKILL.md", ("binding", "repoA-1"), "binding", "70"),
                         (69, 75, 3), "lread"),
    "lane-rename-241": (Arm("lane-rename", ("repoA-2", "repoA-7", "the arms' test", "--no-tmux",
                                            "--no-github"), "rename-lane", "241"),
                        (3, 75, 69), "rename"),
    # LANE 3'S RULING (#165 6754439281, item 6; the erratum to Y:5730 and
    # TP:2832): `managed-projection` is projection-class, so a failed read
    # answers 1, and `lane-start` exits 1, UNKNOWN, never 69. Its real 1 is
    # driven, and no 69, 75 or 3 is stubbed (the arm at `:1555`, by its text).
    "lane-start-1555": (Arm("lane-start", ("repoA", "1"), "managed-projection", "1608",
                            world="primary", env={"ARM_REAL_FAIL": "1"}), (1,), "unknown"),
    "lane-start-1641-1643": (Arm("lane-start", ("repoZ", "1"), "register-row", "1694",
                                 match="repoZ-1"), (75, 3, 69), "code"),
    "lane-start-1661-1663": (Arm("lane-start", ("repoA", "1"), "register-row", "1714",
                                 match="repoA-1"), (75, 3, 69), "code"),
    "lane-start-2305": (Arm("lane-start", ("repoA", "1"), "retired-identity", "2358"),
                        (75, 3, 69), "code"),
    "lane-start-2335": (Arm("lane-start", ("repoA", "1"), "lane-last", "2388"), (75, 3, 69), "code"),
    "lane-start-2444": (Arm("lane-start", ("repoA", "1"), "binding", "2497"), (75, 3, 69), "code"),
    "lane-start-2511-2512": (Arm("lane-start", ("repoA", "3", "--request-handoff", "--dir",
                                                "{lane_dir}"),
                                 "request-handoff", "2564"), (75, 3, 69), "code"),
    "lane-start-2534": (Arm("lane-start", ("repoA", "1"), "lane-agent", "2587"), (75, 3, 69), "code"),
    "lane-start-2638": (Arm("lane-start", ("repoA", "1"), "binding", "2691", nth=2),
                        (75, 3, 69), "code"),
    "lane-end-769": (Arm("lane-end", ("--retire-dormant", "repoA", "--yes"), "lanes", "776"),
                     (75, 3, 69), "code"),
    # The same ruling's first sentence: a case where only `managed-projection`'s
    # call fails follows the erratum, so `lane-end:955` drives the real 1 too.
    "lane-end-955": (Arm("lane-end", ("repoA-2",), "managed-projection", "1008",
                         world="primary", env={"ARM_REAL_FAIL": "1"}), (1,), "unknown"),
    "lane-end-1806": (Arm("lane-end", ("repoA-2",), "lane-objects", "1859"), (75, 3, 69), "code"),
    "lane-end-1984": (Arm("lane-end", ("repoN-1",), "register-row", "2037"), (75, 3, 69), "code"),
    "lane-416": (Arm("lane", ("repoA-2",), "lanes", "416"), (75, 3, 69), "code"),
    "lane-444": (Arm("lane", ("repoA-2",), "lane-groups", "444"), (75, 3, 69), "code"),
    "lane-1058": (Arm("lane", ("repoA-3",), "binding", "1088"), (75, 3, 69), "code"),
    "lane-1144": (Arm("lane", ("--request-handoff", "repoA-3"), "request-handoff", "1174"),
                  (75, 3, 69), "code"),
}

OTHER_ARM_CASES = [pytest.param(arm_id, code, id=f"{arm_id}-{code}")
                   for arm_id, (_arm, codes, _kind) in OTHER_ARMS.items() for code in codes]


def skill_function(path: str, name: str) -> str:
    """A skill's shell function by its text: from `<name>() {` at the start of
    a line to the first `}` alone at the start of a line after it."""
    text = (REPO / path).read_text(encoding="utf-8")
    found = re.search(rf"^{re.escape(name)}\(\) *\{{.*?^\}}[ \t]*$", text, re.M | re.S)
    assert found, (path, name, "not found by its text")
    return found.group(0)


def arm_world(tmp_path: Path, arm: Arm) -> ArmWorld:
    return (PrimaryWorld if arm.world == "primary" else ArmWorld)(tmp_path / "w")


def run_arm(world: ArmWorld, arm: Arm, code: int, stderr: str = "") -> subprocess.CompletedProcess:
    """Run `arm`'s script with the verb under test exiting `code` at the
    arm's call, and assert that the arm was REACHED: its call is in the
    wrapper's log, so a case never passes or fails vacuously."""
    env = world.arm_env(arm.verb, code, match=arm.match, nth=arm.nth, stderr=stderr)
    if arm.fake:
        env.update({"ARM_FAKE_VERB": arm.fake[0], "ARM_FAKE_OUT": arm.fake[1]})
    env.update(arm.env)
    argv = [a.replace("{lane_dir}", str(world.lane_dir)) for a in arm.argv]
    if arm.script.startswith("skills/"):
        name = "lread" if "restart" in arm.script else "sread"
        script = (skill_function(arm.script, name) + "\n"
                  f'L="$ARM_SKILL_L"\n{name} answer "the arms\' test" "$@"\n'
                  'printf "%s" "$answer"\n')
        env["ARM_SKILL_L"] = env["LANES_EDIT"]
        full = dict(world.env)
        full.update(env)
        result = subprocess.run(["bash", "-c", script, "skill", *argv], env=full,
                                cwd=str(world.lane_dir), capture_output=True, text=True,
                                timeout=180, check=False, stdin=subprocess.DEVNULL)
    else:
        result = world.run(arm.script, *argv, env=env)
    assert world.reached(), (arm.script, arm.argv, arm.verb, "the arm was never reached: fix "
                             "the case's scenario", result.returncode, result.stderr[-3000:])
    return result


def launched(world: ArmWorld) -> bool:
    """Whether `lane-start` launched an agent: the fake `claude` or `codex`
    ran."""
    codex = world.codex_log.read_text(encoding="utf-8") if world.codex_log.exists() else ""
    return bool(world.claude_runs().strip() or codex.strip())


def names_the_code(stderr: str, code: int) -> bool:
    return re.search(rf"(?<![0-9]){code}(?![0-9])", stderr) is not None


LANE_START_CASES = [pytest.param(arm, code, id=f"{arm}-{code}")
                    for arm in LANE_START_ARMS for code in (75, 3)]


@pytest.mark.parametrize(("arm_id", "code"), LANE_START_CASES)
def test_75_and_3_refuse_the_launch_at_each_lane_start_arm(tmp_path, arm_id, code):
    """At each of `lane-start`'s seven read arms the verb exits 75 or 3, and
    the launch refuses: `lane-start` exits non-zero before the launch (with
    the verb's own code at `:1154`, which passes it), the fake agent never
    runs, stderr names the code and says nothing was written, and the
    register's rows and logs are unchanged (the design's S3; lane 4's table)."""
    arm = LANE_START_ARMS[arm_id]
    world = arm_world(tmp_path, arm)
    before = world.register_bytes()
    result = run_arm(world, arm, code)
    assert result.returncode != 0, (arm_id, code, "the launch went on", result.stderr[-3000:])
    if arm_id == "1154":
        assert result.returncode == code, (arm_id, code, result.returncode, result.stderr[-2000:])
    assert not launched(world), (arm_id, code, "the agent ran")
    assert names_the_code(result.stderr, code), (arm_id, code, result.stderr[-2000:])
    # T217j (lane 4's T402 finding; lane 3, 6770688147): the early refusal says "Nothing was
    # launched, renamed or written.", the late one "has written no row, no STARTED or RESUMED
    # line and no stamp"; each says nothing was written.
    assert re.search(r"(?i)\bnothing (was|has been|is)\b[^.\n]*\bwritten\b|\bwrote nothing\b|\bhas written no\b",
                     result.stderr), (arm_id, code, result.stderr[-2000:])
    assert re.search(r"(?i)\b(retry|re-?run|again)\b", result.stderr), \
        (arm_id, code, "no word that a retry is safe", result.stderr[-2000:])
    assert world.register_bytes() == before, (arm_id, code, "the register moved")


@pytest.mark.parametrize("arm_id", sorted(LANE_START_69))
def test_69_refuses_at_canon_lane_and_session_lane_and_stays_a_note_at_the_other_four_arms(
        tmp_path, arm_id):
    """A 69 refuses at `:1154` (`canon-lane`) and `:2184-2186`
    (`session-lane`), by round 1's 2A, with the register unchanged and no
    launch; at `:1262`, `:1271`, `:3079` and `:3430` it stays a note naming
    the 69, and the launch goes on."""
    arm = LANE_START_ARMS[arm_id]
    world = arm_world(tmp_path, arm)
    before = world.register_bytes()
    result = run_arm(world, arm, 69, stderr=UNREACHABLE_STDERR.rstrip("\n"))
    if LANE_START_69[arm_id] == "refuse":
        assert result.returncode == 69, (arm_id, result.returncode, result.stderr[-3000:])
        assert not launched(world), (arm_id, "the agent ran")
        assert world.register_bytes() == before, (arm_id, "the register moved")
    else:
        assert launched(world), (arm_id, "a note's 69 refused the launch", result.returncode,
                                 result.stderr[-3000:])
        assert names_the_code(result.stderr, 69), (arm_id, result.stderr[-2000:])


@pytest.mark.parametrize(("arm_id", "code"), OTHER_ARM_CASES)
def test_the_other_callers_arms_pass_the_code_or_refuse_as_lane_4s_table_gives(
        tmp_path, arm_id, code):
    """Each other caller's arm with its verb exiting `code`, as lane 4's
    table gives it: `lane-end:930-938` and `lane-worktrees:508-524` refuse
    with the verb's own code and write nothing; `lane-end:2490`,
    `lane-handoff:2817` and each arm that already refuses exit with the
    verb's code, never 1; the `69)` arm of `lane-handoff:1463` and the
    handoff skill's `sread` (`SKILL.md:112`) re-reads from the mirror and
    prints the `read: mirror` line; `lane-rename:241` prints new text for the
    code, never the note that a 3 means the commit is local; the restart
    skill's `lread` exits 1 with its REFUSED line, so it binds no window,
    writes no stamp and prints no resume command; and where only
    `managed-projection`'s call fails (`lane-start:1555`, `lane-end:955`), its
    real failed read, projection-class, gives 1, and the caller refuses 1,
    UNKNOWN, never 69 (lane 3's ruling, #165 6754439281, item 6)."""
    arm, _codes, kind = OTHER_ARMS[arm_id]
    world = arm_world(tmp_path, arm)
    before = world.register_bytes()
    result = run_arm(world, arm, code)
    if kind == "refuse":
        assert result.returncode == code, (arm_id, code, result.returncode, result.stderr[-3000:])
        assert world.register_bytes() == before, (arm_id, code, "a refusal that wrote")
    elif kind == "refuse-own-exit":
        # T217j (lane 3, 6770688147): lane-worktrees refuses with its own exit, 2 (its header's
        # exit table: lane-end's gate reads 3 as "something to retire", add's 1 as "made"),
        # naming the read's code, with nothing made.
        assert result.returncode == 2, (arm_id, code, result.returncode, result.stderr[-3000:])
        assert re.search(rf"REFUSED, nothing was made: .*exited {code}\b", result.stderr), \
            (arm_id, code, result.stderr[-2000:])
        assert world.register_bytes() == before, (arm_id, code, "a refusal that wrote")
    elif kind == "code":
        assert result.returncode == code, (arm_id, code, result.returncode, result.stderr[-3000:])
    elif kind == "mirror":
        assert result.returncode != 1, (arm_id, "the 69 died as a failed read", result.stderr[-3000:])
        assert MIRROR_LINE.search(result.stderr), (arm_id, "no `read: mirror` line",
                                                   result.stderr[-3000:])
    elif kind == "unknown":
        assert result.returncode == 1, (arm_id, "a failed projection read is 1, UNKNOWN, "
                                        "never 69", result.returncode, result.stderr[-3000:])
        assert "UNKNOWN" in result.stderr, (arm_id, result.stderr[-2000:])
        assert world.register_bytes() == before, (arm_id, "a refusal that wrote")
        if arm.script == "lane-start":
            assert not launched(world), (arm_id, "the agent ran")
    elif kind == "rename":
        assert result.returncode == code, (arm_id, code, result.returncode, result.stderr[-2000:])
        assert not re.search(r"a 3 mean", result.stderr), (arm_id, code, "the old note",
                                                           result.stderr[-2000:])
        assert names_the_code(result.stderr, code), (arm_id, code, result.stderr[-2000:])
    elif kind == "lread":
        assert result.returncode == 1, (arm_id, code, result.returncode, result.stderr)
        assert re.search(rf"^REFUSED: .*\(exit {code}\)", result.stderr, re.M), \
            (arm_id, code, result.stderr)
        assert result.stdout == "", (arm_id, code, result.stdout)
    else:
        raise AssertionError(kind)


# ------------------------------------------------- the rerun on a 3, and the 2
#: Each act that carries on after a failed write (lane 4's section, F9, item
#: 2), by its line at `2a057a6d`: the run that reaches it, and the write.
RERUN_SITES = {
    "lane-start-3851": Arm("lane-start", ("repoA", "1"), "append-session-id", "3904"),
    "lane-start-3872": Arm("lane-start", ("repoA", "1"), "append-session-id", "3925",
                           match="*recovered*"),
    "lane-start-3909": Arm("lane-start", ("repoA", "1"), "append-session-id", "3962",
                           fake=("window-session", WINDOW_RECORD)),
    "lane-start-3989": Arm("lane-start", ("repoA", "1"), "set-row-state", "4042"),
    "lane-start-4022": Arm("lane-start", ("repoA", "2", "--agent", "codex"), "append-session-id",
                           "4075"),
    "lane-start-4181": Arm("lane-start", ("repoA", "1"), "log", "4234", match="STARTED*"),
    "lane-handoff-2878": Arm("lane-handoff", ("--lane", "repoA-2", "the rerun test"), "log",
                             "2878", match="PAUSED*"),
    "lane-handoff-2890": Arm("lane-handoff", ("--lane", "repoA-2", "the rerun test"), "append-line",
                             "2890"),
    "lane-handoff-2913": Arm("lane-handoff", ("--lane", "repoA-2", "the rerun test"),
                             "set-row-state", "2913", match="repoA-2 PAUSED*"),
    "lane-end-2490": Arm("lane-end", ("repoA-2",), "log", "2543", match="ENDED*"),
    "skill-738": Arm("skills/handoff/SKILL.md", (), "append-line", "743"),
}

#: The skill's `(b)` write (`SKILL.md:738-742` at `2a057a6d`), run by its
#: text with the variables its step 4 has set.
SKILL_738_LINE = re.compile(r'^"\$L" append-line "PAUSED — lane \$lane, .*$', re.M)


def rerun_argv(arm: Arm, lane: str) -> str:
    """The writer's own arguments, as its printed rerun repeats them."""
    return f"{arm.verb} lane:{lane} the-same-arguments"


def own_hints(stderr: str, verb: str) -> list:
    """The act's own rerun hints: a line, other than the writer's printed
    rerun, that tells the person to run the verb (`LANES_LANE=… <verb>`)."""
    return [line for line in stderr.splitlines()
            if "LANES_WRITE_ID=" not in line and "LANES_LANE=" in line
            and re.search(rf"(?<![A-Za-z-]){re.escape(verb)}(?![A-Za-z-])", line)]


@pytest.mark.parametrize("site", sorted(RERUN_SITES))
def test_a_carry_on_act_relays_the_writers_printed_rerun_on_a_3(tmp_path, site):
    """Each carry-on act, with its write exiting 3 and printing the writer's
    rerun line (`LANES_WRITE_ID=… LANES_WRITE_GENERATION=… LANES_LANE=…
    LANES_SESSION=… lanes-edit.sh <args>`): the act's stderr carries that
    line as printed, and none of the act's own hint, so none that reads a 3
    as written and none that leaves out `LANES_SESSION` (`lane-start:4182`
    today); `lane-handoff:2890-2891` and `:2913-2914`, which send the
    writer's stderr to `/dev/null` today, keep it; and `lane-start` carries
    on to its launch, as it did before."""
    arm = RERUN_SITES[site]
    world = arm_world(tmp_path, arm)
    lane = "repoA-2" if "2" in arm.argv[:2] or "repoA-2" in arm.argv or not arm.argv else "repoA-1"
    line = rerun_line(lane, rerun_argv(arm, lane))
    if arm.script.startswith("skills/"):
        found = SKILL_738_LINE.search((REPO / arm.script).read_text(encoding="utf-8"))
        assert found, (site, "the skill's (b) write is not found by its text")
        env = world.arm_env(arm.verb, 3, stderr=line)
        full = dict(world.env)
        full.update(env)
        full.update({"lane": "repoA-2", "uuid": UUID_A2, "ws": "Eagle", "why_text": "the rerun test"})
        script = ('L="$LANES_EDIT"; lane="$lane"; uuid="$uuid"; ws="$ws"; '
                  'why_text="$why_text"\n' + found.group(0) + "\n")
        result = subprocess.run(["bash", "-c", script], env=full, cwd=str(world.lane_dir),
                                capture_output=True, text=True, timeout=120, check=False,
                                stdin=subprocess.DEVNULL)
        assert world.reached(), (site, "the arm was never reached", result.stderr)
    else:
        result = run_arm(world, arm, 3, stderr=line)
    assert line in result.stderr.splitlines(), (site, "the writer's rerun was not relayed",
                                                result.stderr[-3000:])
    hints = own_hints(result.stderr, arm.verb)
    assert not hints, (site, "the act's own hint", hints)
    if arm.script == "lane-start":
        assert launched(world), (site, "the launch did not carry on", result.returncode,
                                 result.stderr[-2000:])


def test_an_expectation_2_at_lane_starts_last_write_dies(tmp_path):
    """Any 2 at `lane-start:4181`, its last write (the STARTED log line),
    dies with 2, an expectation's included (LR010): it is a second binding,
    a deciding refusal, never a stamp to carry on past (lane 4's table; the
    design's outcomes table)."""
    arm = RERUN_SITES["lane-start-4181"]
    world = arm_world(tmp_path, arm)
    stderr = ("ERROR:  LR010: an expectation of this act no longer holds\n"
              "DETAIL:  expectation bind:repoA-1")
    result = run_arm(world, arm, 2, stderr=stderr)
    assert result.returncode == 2, (result.returncode, result.stderr[-3000:])
    assert "LR010" in result.stderr, result.stderr[-2000:]
    assert not launched(world), "the agent ran after the 2"


# ------------------------------------------------ the read door's other cases
def test_register_row_local_reads_the_database_on_primary_and_is_69_never_8(primary):
    """`register-row-local` reads the database on primary, 8 included (D11):
    it finds the row only the store holds, and answers 8 for a lane the store
    lacks though this checkout's own copy holds it; with the store
    unreachable it exits 69 with nothing on stdout, never 8."""
    lanes = primary.e.wip / "lanes" / "LANES.md"
    local_only = "repoL-1"
    with open(lanes, "a", encoding="utf-8") as handle:     # this checkout's copy only
        handle.write(f"| `{local_only}` | harness `{UUID_M1}` | Eagle / test / brett | 2026-10-06T00:00Z "
                     f"| none | handoffs/{local_only}.md | LIVE · 2026-10-06T00:00:00Z · local |\n")
    found = primary.edit("register-row-local", STORE_ONLY_LANE)
    assert primary.door.register_calls(), ("the read never reached the store", found.stderr)
    assert found.returncode == 0 and STORE_ONLY_UUID in found.stdout, \
        (found.returncode, found.stdout, found.stderr)
    absent = primary.edit("register-row-local", local_only)
    assert absent.returncode == 8, (absent.returncode, absent.stdout, absent.stderr)
    primary.door.unreachable()
    failed = primary.edit("register-row-local", STORE_ONLY_LANE)
    assert failed.returncode == 69, (failed.returncode, failed.stdout, failed.stderr)
    assert failed.stdout == "", failed.stdout


#: `lane-worktrees`' three direct reads of the register (lane 4's T404, by
#: lane 4's line cites): the run that reaches each, and a glob its
#: `register-grep` arguments match.
WORKTREE_READS = {
    "lifecycle-events-711": (("sweep", "repoA-2", "--dry-run"), "*STARTED|PAUSED*"),
    "landed-1002": (("sweep", "repoA-2", "--dry-run"), "*LANDED*"),
    "lifecycle-events-5596": (("sweep", "--all", "--report"), "*STARTED|RESUMED*"),
}


@pytest.mark.parametrize("read", sorted(WORKTREE_READS))
def test_lane_worktrees_register_reads_go_through_a_verb_and_refuse_69(tmp_path, read):
    """Each of `lane-worktrees`' three direct reads of `origin/<branch>`
    (`:711`, `:1002`, `:5596`) goes through `register-grep`, and a 69 from it
    is the register unreadable: the sweep deletes nothing, exits non-zero
    and names the register (Y:4926; the design's S3)."""
    argv, match = WORKTREE_READS[read]
    world = ArmWorld(tmp_path / "w")
    stray = world.home / "projects" / "repoA-2-stray"
    stray.mkdir(parents=True)
    tree = world.lane_dir.parent / ".lane-worktrees" / "repoA-2" / "s1"
    if read == "lifecycle-events-711":
        # T217j (lane 4's T404 finding): with no tree the failed read is a note (T404's task
        # line, lane 3's item 2); a lane's tree is what an unreadable claim can take.
        tree.parent.mkdir(parents=True)
        world.git("-C", str(world.lane_dir), "worktree", "add", "-q", "-b", "s1", str(tree))
    env = world.arm_env("register-grep", 69, match=match, stderr=UNREACHABLE_STDERR.rstrip("\n"))
    result = world.run("lane-worktrees", *argv, env=env)
    assert world.reached(), (read, "the read never went through register-grep",
                             result.returncode, result.stderr[-3000:])
    if read == "lifecycle-events-5596":
        # T217j: the estate report changes nothing and exits 0 (its header), naming what it
        # could not read.
        assert result.returncode == 0, (read, result.stdout[-2000:], result.stderr[-2000:])
        assert re.search(r"Records the report could not read[\s\S]*register-grep` exited 69",
                         result.stdout), (read, result.stdout[-2000:])
    else:
        assert result.returncode != 0, (read, result.stdout[-2000:], result.stderr[-2000:])
        assert re.search(r"(?i)register", result.stdout + result.stderr), (read, result.stderr[-2000:])
    assert stray.is_dir(), (read, "the sweep deleted on a failed read")
    if read == "lifecycle-events-711":
        assert tree.is_dir(), (read, "the sweep deleted a tree on a failed read")


def test_index_flag_on_primary_changes_nothing_and_prints_no_index_line(primary):
    """On primary, `--index` changes nothing: with and without it, stdout
    and the exit are equal, and stderr has no index line (Wspec:641-646;
    lane 5's T509)."""
    for argv in (("lanes",), ("history",)):
        bare = primary.edit(*argv)
        assert primary.door.register_calls(), (argv, "the read never reached the store", bare.stderr)
        primary.door.forget_calls()
        flagged = primary.edit(*argv, "--index")
        assert (flagged.returncode, flagged.stdout) == (bare.returncode, bare.stdout), \
            (argv, flagged.returncode, bare.returncode, flagged.stdout[-1500:], bare.stdout[-1500:])
        new = [line for line in flagged.stderr.splitlines()
               if re.search(r"(?i)\bindex\b", line) and line not in bare.stderr.splitlines()]
        assert not new, (argv, "an index line on primary", new)


def test_managed_projection_with_the_database_unreachable_exits_1_never_legacy(primary):
    """With the database unreachable (the fake `psql` exits 2, the store's
    read fails), `managed-projection` exits 1, UNKNOWN, with nothing on
    stdout, and never answers from the legacy row (D10, S4)."""
    primary.door.unreachable()
    result = primary.edit("managed-projection", "repoM-1")
    assert primary.door.register_calls(), ("the read never reached the store", result.stderr)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stdout == "", result.stdout
    assert "UNKNOWN" in result.stderr, result.stderr
    assert not re.search(r"(?i)legacy", result.stdout + result.stderr), result.stderr


# ------------------------------------------------- the real engine's register
def _sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _lines(text: str) -> list:
    body = text[:-1] if text.endswith("\n") else text
    return body.split("\n") if body else []


_LANE1_INDEX: list = []


def lane1_index():
    """The checkout's `lanes-index` as a module (test_lanes_index's
    `load_indexer`), loaded once: lane 1's derivation helpers, which
    `RealRegister` derives its entries with (T217l)."""
    if not _LANE1_INDEX:
        _LANE1_INDEX.append(load_indexer())
    return _LANE1_INDEX[0]


class RealRegister:
    """A real register on the `pg` fixture's database (T205), brought to
    `primary` with the marker `present` by the documented functions, as
    AT-LR006's fixture does (`test-plan-v3f.md:4610-4615`): as the writer's
    login, `commit_write` with an `import` entry holding the render set, then
    a `cutover` entry, which writes `lanes/STORE` alone (ruling 1), then
    `record_marker`. Each `write(...)` is one more committed `write` entry, a
    seq more. The import and each write are the entries lane 1's own helpers
    derive (item 9). A copy of the checkout's `lanes-index` with `RENDER_GIT_HALF`
    flipped True (T203's `flipped_copy`, PC-5) reads it as the reader's
    login, through a `mode=primary` configuration that names both logins.

    T217h, lane 5's five findings (#165 6771208498) and three of lane 2's own,
    each checked against lane 1's code at `refs/l1/T114`:
      1. the configuration names `reader_url=` beside `register_url=`, which
         `load_config` requires (`_check_register_connections`), with the
         writer's login in `register_url=` and the reader's in `reader_url=`;
      2. `lanes-index` is the flipped copy, never `REPO/lanes-index`, whose
         `RENDER_GIT_HALF = False` ends 78 (`register read`) or 2 (every
         other command, `journal` included) on `mode=primary`;
      3. the client version is the register schema's own `version`, as
         `lanes-index` sends `REGISTER_SCHEMA_VERSION`: `commit_write` and
         `record_marker` refuse a client above `version` or below
         `writers_from` with LR003, and 5000 is above `version`, which
         migration 1 sets to 1;
      4. `[refusal-78]` keeps `mode=primary` and reads through a copy
         flipped False (`unflipped`), Q6(c)'s 78; `mode=files` was a refused
         configuration, 1 under `--for guard`;
      5. the template holds no register until T227: the fixture refuses that
         by its own assertion, as T222's module does, never by a psql error;
      6. (lane 2's) the groups `lanes_register_writer` and
         `lanes_register_reader` are NOLOGIN (lane 1's role block), so every
         session logs in as T228's `lanes_w_fx` or `lanes_r_fx` (the block's
         T228), refused by the fixture's own assertion until T228;
      7. (lane 2's) the superuser is `pgcluster`'s, `lanes_test`: the cluster
         has no `postgres` role, so a superuser read names no user;
      8. (lane 2's) a render set's bytes (`render_set`) are taken as UTF-8
         text, as `_commit` reads them;
      9. (T217l; lane 3's batch 7, #165 6780364102, other ask (4), on N1f's
         doubt in T217h) the entries carry the rows `register commit`
         builds: the import is lane 1's `import_entry` and each write its
         `register_commit_entry`, the one set of derivation helpers
         `register commit` and `import --at` build every row with (lane 3's
         reading 7, #165 6755386771; ERR-49), loaded from the checkout's
         `lanes-index`, over a bare repository that holds each text's blob,
         as their `git cat-file` reads it. So `lanes`, `log_lines`,
         `register_lines` and `object_holds` hold the rows a real register
         would, edits and rows agree, and a log line written after the
         cutover is stamped `primary`, where `log_lines`' CHECK refuses an
         unreadable one with 23514, as it refuses `register commit`'s: the
         cases write well-formed lines. The cutover's entry writes
         `lanes/STORE` alone, from which no row is derived, and is built as
         before. T228's logins are kept.

    So every case built on it FAILS UNTIL T227 and T228 land, beside the
    waits its own docstring names. UNVERIFIED HERE: this bench has no engine.
    The SQL names lane 1's functions as `refs/l1/T109`'s `lanes-index`
    creates them: `commit_write(bigint, uuid, integer, uuid, jsonb)`,
    `record_marker(integer, bigint, text, text)`, `schema_version.version`,
    `register_switch.generation` and `register_head.seq`."""

    #: T228's fixture logins, members of the two groups (block T228).
    WRITER = "lanes_w_fx"
    READER = "lanes_r_fx"
    #: Copied beside the flipped copy, as `Primary` copies them beside the door.
    TOOLS = ("lanes-edit.sh", "lanes", "repos.tsv", "lane-start", "lane-worktrees")
    #: Every entry's author (`journal_author_check`, `^[^<>]+ <[^<>]*>$`; T217k) and
    #: its `not_after`, as text and as the epoch seconds an attempt carries.
    AUTHOR = "T217 fixture <t217@example.invalid>"
    NOT_AFTER = "2999-12-31T00:00:00Z"
    NOT_AFTER_EPOCH = 32503593600
    #: Lane 1's derivation helpers (item 9), the names this fixture calls.
    LANE1_HELPERS = ("import_entry", "register_commit_entry", "RegisterView",
                     "register_doc_lines", "register_shipped_repos_text")

    def __init__(self, pg, root: Path, files: dict):
        self.pg, self.root = pg, root
        root.mkdir(parents=True, exist_ok=True)
        assert self._one("SELECT to_regclass('lanes_register.register_head') IS NOT NULL;") == "t", (
            "the pg fixture's database holds no lanes_register schema: lane 2's T227 builds "
            "tmpl by the bootstrap, which waits for lane 1's L1-A7 (lane 5's finding 5)")
        logins = self._one("SELECT count(*) FROM pg_roles WHERE rolcanlogin AND rolname IN "
                           f"('{self.WRITER}', '{self.READER}');")
        assert logins == "2", (
            f"no {self.WRITER} and {self.READER} logins: lane 2's T228 makes them by `lanes-index "
            "login add fx`; the groups lanes_register_writer and lanes_register_reader are NOLOGIN")
        source = helpers.LANES_INDEX.read_bytes()
        assert len(helpers.RENDER_GIT_HALF_LINE.findall(source)) == 1, (
            f"{helpers.LANES_INDEX} holds no single RENDER_GIT_HALF line to flip: lane 1's T105")
        self.lane1 = lane1_index()
        missing = [name for name in self.LANE1_HELPERS if not hasattr(self.lane1, name)]
        assert not missing, (
            f"{helpers.LANES_INDEX} has no {', '.join(missing)}: lane 1's T112 and T115 derive "
            "the rows `register commit` builds (T217l)")
        self.blobs = root / "blobs.git"
        self._blob_ids: dict = {}
        self._git("init", "-q", "--bare", str(self.blobs))
        self.entry: dict = {}
        self.bin = root / "bin"
        self.copy = helpers.flipped_copy(helpers.LANES_INDEX, self.bin, True)
        self.config = root / "config" / "openRepoTools" / "lanes-index.conf"
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(f"mode=primary\nregister_url={pg.url(self.WRITER)}\n"
                               f"reader_url={pg.url(self.READER)}\n", encoding="utf-8")
        self.config.chmod(0o600)
        self.cache = root / "cache" / "lanes-se"
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.client = int(self._one("SELECT version FROM lanes_register.schema_version;"))
        self.generation = self._one("SELECT generation FROM lanes_register.register_switch;")
        texts = {path: (data.decode("utf-8") if isinstance(data, bytes) else data)
                 for path, data in files.items()}
        self.files = dict(texts)
        self.first = self._commit("import", texts, base=-1)
        store = "mode primary\n"
        self._commit("cutover", {"lanes/STORE": store}, verb="cutover")
        self.n = self.head()
        marked = self._one(f"SELECT lanes_register.record_marker({self.client}, {self.n}, "
                           f"'{'3' * 40}', 'Eagle');", user=self.WRITER)
        assert marked == "present", ("record_marker answered", marked)

    def _one(self, sql: str, user: str | None = None) -> str:
        proc = self.pg.psql(sql) if user is None else self.pg.psql(sql, user=user)
        out = proc.stdout.strip().splitlines()
        return out[-1].strip() if out else ""

    def unflipped(self) -> Path:
        """A copy flipped False: Q6(c)'s refusal of this same `mode=primary`
        configuration, 78 from `register read` in all four forms (contract
        section 2.7), whatever the checkout's own constant says by then."""
        return helpers.flipped_copy(helpers.LANES_INDEX, self.root / "bin-78", False)

    def tools(self) -> Path:
        """The checkout's `lanes-edit.sh` and its siblings copied beside the
        flipped copy, so the copy is the `lanes-index` it runs; its path."""
        for name in self.TOOLS:
            shutil.copy2(REPO / name, self.bin / name)
        return self.bin / "lanes-edit.sh"

    def head(self) -> int:
        return int(self._one("SELECT seq FROM lanes_register.register_head;"))

    @staticmethod
    def _git(*args: str, data: bytes | None = None) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        proc = subprocess.run(["git", *args], input=data, capture_output=True, env=env,
                              timeout=60, check=False,
                              stdin=None if data is not None else subprocess.DEVNULL)
        assert proc.returncode == 0, ("git", args, proc.returncode, proc.stderr[-500:])
        return proc.stdout.decode("utf-8").strip()

    def _blob(self, data: bytes) -> str:
        """`data`'s blob id, written once into the bare repository."""
        if data not in self._blob_ids:
            self._blob_ids[data] = self._git("-C", str(self.blobs), "hash-object", "-w",
                                             "--stdin", data=data)
        return self._blob_ids[data]

    def _import_entry(self, texts: dict) -> dict:
        """Lane 1's `import_entry` of `texts`, as `import --at` derives it
        from `import_source`'s answer: `C` and its lanes tree are the old
        fixed ids, and the blobs are this fixture's repository's."""
        index = self.lane1
        data = {path: text.encode("utf-8") for path, text in texts.items()}
        source = {"commit": "1" * 40, "tree": "2" * 40,
                  "blobs": {path: self._blob(raw) for path, raw in data.items()},
                  "render": sorted(data, key=lambda p: p.encode("utf-8")), "data": data,
                  "texts": dict(texts),
                  "lines": {path: index.register_doc_lines(text) for path, text in texts.items()},
                  "warnings": []}
        return index.import_entry(source, root=str(self.blobs), lane="repoA-1",
                                  workstation="Eagle", author=self.AUTHOR,
                                  not_after=self.NOT_AFTER,
                                  shipped_repos=index.register_shipped_repos_text())

    def _write_entry(self, files: dict, verb: str) -> dict:
        """Lane 1's `register_commit_entry` of a write that turns the
        register's files into `files` (a path to its new text, or None to
        remove it), from the attempt `register commit` reads: `changes`,
        `images` and the bases at `n`, over this fixture's repository."""
        index, zero = self.lane1, "0" * 40
        tree_blobs = {path: self._blob(text.encode("utf-8")) for path, text in self.files.items()}
        changes, images, bases = {}, {}, {}
        for path, text in files.items():
            old = self.files.get(path)
            if text is None:
                if old is not None:
                    changes[path] = ("D", tree_blobs[path], zero)
                    bases[path] = old.encode("utf-8")
                continue
            if old == text:
                continue
            images[path] = text.encode("utf-8")
            if old is None:
                changes[path] = ("A", zero, self._blob(images[path]))
            else:
                changes[path] = ("M", tree_blobs[path], self._blob(images[path]))
                bases[path] = old.encode("utf-8")
        att = {"tree": str(self.blobs), "tree_blobs": tree_blobs, "changes": changes,
               "renames": {}, "images": images, "author": self.AUTHOR,
               "message": "write by T217's fixture", "act": None,
               "not_after": self.NOT_AFTER_EPOCH, "repos_blob": None}
        ident = {"verb": verb or "log", "lane": "repoA-1", "workstation": "Eagle",
                 "args_sha256": "0" * 64}
        return index.register_commit_entry(att, ident, index.RegisterView(att, bases),
                                           index.register_shipped_repos_text())

    def _commit(self, kind: str, files: dict, base: int | None = None, verb: str = "") -> int:
        if kind in ("import", "write"):
            # Lane 1's entry, its rows included (item 9; T217l).
            self.entry = (self._import_entry(files) if kind == "import"
                          else self._write_entry(files, verb))
            seq = self._post(self.entry, base)
            for path, text in files.items():
                if text is None:
                    self.files.pop(path, None)
                else:
                    self.files[path] = text
            return seq
        # The cutover's `lanes/STORE`, from which no row is derived.
        # `journal_edits.ord` starts at 1 (its CHECK `ord >= 1`; lane 1's own `edit()` counts
        # `len(edits) + 1`), as T221's and T222's modules number theirs.
        edits, rows, order = [], [], 1
        for path, text in files.items():
            if text is None:
                edits.append({"ord": order, "op": "remove", "path": path})
                rows.append({"path": path, "present": False, "sha256": None, "final_newline": None})
                order += 1
                self.files.pop(path, None)
                continue
            old = self.files.get(path) if kind == "write" else None
            if old is None:
                edits.append({"ord": order, "op": "create", "path": path})
                order += 1
                kept = []
            else:
                kept = _lines(old)
            new = _lines(text)
            if kept != new[:len(kept)]:      # not an append: rewrite the file
                if old is not None:
                    edits.append({"ord": order, "op": "remove", "path": path})
                    edits.append({"ord": order + 1, "op": "create", "path": path})
                    order += 2
                kept = []
            for line in new[len(kept):]:
                edits.append({"ord": order, "op": "append", "path": path, "new_text": line})
                order += 1
            rows.append({"path": path, "present": True, "sha256": _sha(text.encode("utf-8")),
                         "final_newline": text.endswith("\n")})
            self.files[path] = text
        return self._send(kind, edits, rows, verb, base)

    def _send(self, kind: str, edits: list, rows: list, verb: str = "",
              base: int | None = None) -> int:
        """The cutover's entry, its journal object, `edits` and the `files`
        rows, sent by `_post`; the seq it made."""
        # `journal.author` is `Name <address>` (journal_author_check, `^[^<>]+ <[^<>]*>$`).
        journal = {"kind": kind, "verb": verb or ("import" if kind == "import" else "log"),
                   "lane": "repoA-1", "workstation": "Eagle",
                   "author": self.AUTHOR,
                   "message": f"{kind} by T217's fixture", "args_sha256": "0" * 64}
        if kind == "import":
            journal.update(git_commit="1" * 40, git_tree="2" * 40)
        entry = {"journal": journal, "edits": edits, "files": rows,
                 "not_after": self.NOT_AFTER}
        return self._post(entry, base)

    def _post(self, entry: dict, base: int | None = None) -> int:
        """One `commit_write` call of `entry`, as the writer's login; the
        seq it made."""
        import uuid as _uuid
        base = self.head() if base is None else base
        sql = ("BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
               f"SELECT lanes_register.commit_write({base}, '{_uuid.uuid4()}'::uuid, {self.client}, "
               f"'{self.generation}'::uuid, $entry${json.dumps(entry)}$entry$::jsonb);\nCOMMIT;\n")
        return int(self.pg.psql(sql, user=self.WRITER).stdout.split()[0])

    def write(self, files: dict) -> int:
        self._commit("write", files)
        return self.head()

    def replace(self, path: str, line_no: int, new_text: str) -> int:
        """One committed `write` entry whose one edit is a `replace` of line
        `line_no` of `path` (`commit_write`'s step 6 checks its `old_sha256`
        against the stored line, the sha256 of its UTF-8 text without its LF),
        as lane 1's `register_line_edits` sends a write that changes that line
        alone (T217l); the seq it made."""
        lines = _lines(self.files[path])
        text = "\n".join(lines[:line_no - 1] + [new_text] + lines[line_no:]) + "\n"
        seq = self._commit("write", {path: text})
        ops = [(e["op"], e["line_no"]) for e in self.entry["edits"]]
        assert ops == [("replace", line_no)], ("not one replace", ops)
        return seq

    def env(self, extra: dict | None = None) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("LANES_", "PG", "TMUX"))}
        env.update({"HOME": str(self.root), "LANES_INDEX_CONFIG": str(self.config),
                    "XDG_CONFIG_HOME": str(self.config.parent.parent), "LANES_WORKSTATION": "Eagle"})
        env.update(extra or {})
        return env

    def index(self, *args, env: dict | None = None,
              copy: Path | None = None) -> subprocess.CompletedProcess:
        """`lanes-index` as the flipped copy, or as `copy` where one is named."""
        return subprocess.run([sys.executable, str(copy or self.copy), *args], env=self.env(env),
                              capture_output=True, text=True, timeout=60, check=False,
                              stdin=subprocess.DEVNULL)

    def read(self, *args, env: dict | None = None,
             copy: Path | None = None) -> subprocess.CompletedProcess:
        return self.index("register", "read", *args, env=env, copy=copy)

    def family(self) -> dict:
        return {p.name[len(self.cache.name):]: p.read_bytes()
                for p in self.cache.parent.glob(self.cache.name + ".*") if p.is_file()}


def well_formed(text: str, second: int) -> str:
    """A well-formed `NOTED` line of repoA-1's, its free text `text`: the
    lines the cases write after the cutover are stamped `primary`, and
    `log_lines`' CHECK refuses an unreadable primary row with 23514, as it
    refuses `register commit`'s (T217l). The rest of the line holds no `.`
    and no `X`, so a `--grep` key matches its text alone."""
    return (f"NOTED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-07T00:00:{second:02d}Z, "
            f"lane:repoA-1 — {text}\n")


#: `check_lane_name`'s class (CLI4.5 section 3.6; the stub's own copy).
LANE_CLASS_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def hex_slot(key: str) -> str:
    return "%" + key.encode("utf-8").hex()


#: The render set lane 1's three read: two lanes, their logs and the aliases.
def l1_files(extra: dict | None = None) -> dict:
    files = {
        "lanes/LANES.md": ("# LANES.md\n\n| lane | session id | workstation / env / user | started "
                           "(UTC) | objects owned | handoff path | state |\n|---|---|---|---|---|---|---|\n"
                           f"| `repoA-1` | harness `{UUID_A1}` | Eagle / test / brett | 2026-10-01T00:00Z "
                           "| none | handoffs/repoA-1.md | LIVE · 2026-10-01T00:00:00Z · working |\n"),
        "lanes/aliases.tsv": "# old\tnew\tutc\n",
        "lanes/log/repoA-1.md": (f"STARTED — lane repoA-1, session {UUID_A1}@Eagle, "
                                 "2026-10-01T00:00:00Z, lane:repoA-1 → home opensoft/repoA\n"),
    }
    files.update(extra or {})
    return files


#: `guard_second_read_at`'s cases (L1v4.5:301-310): the key, what to set up
#: after form 2 has cached the family at `n`, and the end.
GUARD_SECOND_READ = ["moved-head", "case-insensitive", "outside-the-class", "no-mirror",
                     "generation-differs", "no-head", "above-the-head", "below-the-first-seq",
                     "case-duplicates", "dash-key", "refusal-78", "refused-configuration-1",
                     "empty-lane-64"]


@pytest.mark.parametrize("case", GUARD_SECOND_READ)
def test_guard_second_read_at_its_head_writes_one_log_and_fails_open(pg, tmp_path, case):
    """FORM 4, `register read --for guard --at <n> --pid <pid> --cache <file>
    --lane=<key>`, after form 2 has cached the family at `n` (lane 1's T113;
    L1v4.5:301-310; B4): it writes its one log's pair (`.log.<key>` and
    `.logpath.<key>`, or `.log.%<hex>` and `.logpath.%<hex>` for a key outside
    `check_lane_name`'s class, O18) and nothing else, at `n`; `.head` is
    byte-identical and no `.outage` is written; and every end but 0 writes no
    `.log.<key>`. Real engine: it skips without one (T205)."""
    extra = {}
    if case == "outside-the-class":
        extra["lanes/log/a,b.md"] = "NOTED — a log whose name is outside the class\n"
    if case == "dash-key":
        extra["lanes/log/-x.md"] = "NOTED — a log whose name begins with a dash\n"
    if case == "case-duplicates":
        extra["lanes/log/RepoA-1.md"] = "NOTED — the case pair's other half\n"
    reg = RealRegister(pg, tmp_path / "real", l1_files(extra))
    pid = str(os.getpid())
    pre = reg.read("--for", "guard", "--prefetch", "--cache", str(reg.cache), "--pid", pid,
                   "--repo", str(tmp_path), "--lane=repoA-1")
    assert pre.returncode == 0 and pre.stdout.startswith("mode primary"), (pre.returncode, pre.stderr)
    n, at_n = reg.head(), reg.files["lanes/log/repoA-1.md"]
    head_before = (reg.cache.parent / (reg.cache.name + ".head")).read_bytes()
    key, at, env, expect, copy = "repoA-1", str(n), {}, 0, None
    if case == "moved-head":
        reg.write({"lanes/log/repoA-1.md": at_n + well_formed("the head moved past n", 0)})
    elif case == "case-insensitive":
        key = "REPOA-1"
    elif case == "outside-the-class":
        key = "a,b"
    elif case == "no-mirror":
        mirror = tmp_path / "mirror"
        (mirror / "lanes" / "log").mkdir(parents=True)
        (mirror / "lanes" / "log" / "repoA-1.md").write_text("ANOTHER TEXT\n", encoding="utf-8")
        mirror.chmod(0)
        env = {"LANES_REPO": str(mirror)}
    elif case == "generation-differs":
        head = reg.cache.parent / (reg.cache.name + ".head")
        head.write_bytes(re.sub(rb"(?m)^generation=.*$", b"generation=" + str(UUID_M1).encode(),
                                head.read_bytes()))
        head_before, expect = head.read_bytes(), 69
    elif case == "no-head":
        head = reg.cache.parent / (reg.cache.name + ".head")
        head.rename(head.with_name(head.name + ".aside"))
        head_before, expect = None, 69
    elif case == "above-the-head":
        at, expect = str(n + 5), 69
    elif case == "below-the-first-seq":
        at, expect = str(reg.first - 1), 69
    elif case == "case-duplicates":
        expect = 69
    elif case == "dash-key":
        key = "-x"
    elif case == "refusal-78":
        # Q6(c)'s refusal (T217h; lane 5's finding 4): the same `mode=primary` configuration, read
        # by a copy flipped False, is 78 in all four forms; `mode=files` is a refused one, 1 here.
        copy, expect = reg.unflipped(), 78
    elif case == "refused-configuration-1":
        reg.config.chmod(0o644)                                      # readable by others
        expect = 1                                                   # R09's half follows
    elif case == "empty-lane-64":
        key, expect = "", 64
    before = reg.family()
    try:
        result = reg.read("--for", "guard", "--at", at, "--pid", pid, "--cache", str(reg.cache),
                          f"--lane={key}", env=env, copy=copy)
    finally:
        if case == "no-mirror":
            (tmp_path / "mirror").chmod(0o755)
    after = reg.family()
    assert result.returncode == expect, (case, result.returncode, result.stdout, result.stderr)
    slot = key if LANE_CLASS_RE.match(key) else hex_slot(key)
    changed = sorted(k for k in after if after.get(k) != before.get(k))
    assert ".outage" not in after, (case, "an .outage was written")
    if head_before is not None:
        assert after.get(".head") == head_before, (case, ".head changed")
    if expect == 0:
        assert set(changed) <= {f".log.{slot}", f".logpath.{slot}"}, (case, changed)
        assert f".log.{slot}" in after, (case, "no log written", sorted(after))
        if case in ("moved-head", "no-mirror", "case-insensitive"):
            assert after[f".log.{slot}"] == at_n.encode("utf-8"), (case, after[f".log.{slot}"])
            assert after[f".logpath.{slot}"].strip() == b"lanes/log/repoA-1.md", \
                (case, after[f".logpath.{slot}"])
    else:
        assert not any(k.startswith(".log.") and k not in before for k in after), (case, changed)
    if case == "refused-configuration-1":
        # R09'S HALF (T217h; contract section 2.7's 1, "R09's included"): a configuration whose
        # URLs name a TCP host that is not loopback, with no `sslmode=verify-full`, refused at
        # load, before any connection.
        reg.config.write_text("mode=primary\n"
                              f"register_url=postgresql://{reg.WRITER}@db.invalid:5432/lanes\n"
                              f"reader_url=postgresql://{reg.READER}@db.invalid:5432/lanes\n",
                              encoding="utf-8")
        reg.config.chmod(0o600)
        before = reg.family()
        tls = reg.read("--for", "guard", "--at", at, "--pid", pid, "--cache", str(reg.cache),
                       f"--lane={key}")
        after = reg.family()
        assert tls.returncode == 1, (case, "R09", tls.returncode, tls.stdout, tls.stderr)
        assert ".outage" not in after, (case, "R09", "an .outage was written")
        assert after.get(".head") == head_before, (case, "R09", ".head changed")
        assert not any(k.startswith(".log.") and k not in before for k in after), \
            (case, "R09", sorted(after))


@pytest.mark.parametrize("case", ["form-3", "dash-key", "forms-1-and-2"])
def test_log_key_hex_slot_holds_a_key_outside_the_class_and_is_never_cached(pg, tmp_path, case):
    """O18 (lane 1's T113; L1v4.5:312-317): form 3 with `--log-key=<key>`,
    for keys outside the class (one holding `,`, one `/`), writes each its
    own `.log.%<hex>` and `.logpath.%<hex>`, rewritten on each read and never
    counted as cached; a key beginning with `-` is read as the key; and
    forms 1 and 2 fetch no log for such a key and refuse nothing. Real
    engine: it skips without one (T205)."""
    reg = RealRegister(pg, tmp_path / "real",
                       l1_files({"lanes/log/a,b.md": "NOTED — a comma in the name\n",
                                 "lanes/log/-x.md": "NOTED — a dash first\n"}))
    pre = reg.read("--prefetch", "--cache", str(reg.cache), "--all")
    assert pre.returncode == 0, (pre.returncode, pre.stderr)
    n = reg.head()
    if case == "forms-1-and-2":
        assert not any(k.startswith(".log.%") for k in reg.family()), sorted(reg.family())
        two = reg.read("--for", "guard", "--prefetch", "--cache", str(reg.cache) + "-g", "--pid",
                       str(os.getpid()), "--repo", str(tmp_path), "--lane=a,b")
        assert two.returncode == 0, (two.returncode, two.stderr)
        assert not list(reg.cache.parent.glob(reg.cache.name + "-g.log.*")), "form 2 fetched the log"
        return
    keys = ["a,b", "c/d"] if case == "form-3" else ["-x"]
    first = {}
    for key in keys:
        result = reg.read("--since", str(n), "--cache", str(reg.cache), f"--log-key={key}")
        assert result.returncode == 0, (case, key, result.returncode, result.stderr)
        family = reg.family()
        assert f".log.{hex_slot(key)}" in family and f".logpath.{hex_slot(key)}" in family, \
            (case, key, sorted(family))
        first[key] = (reg.cache.parent / (reg.cache.name + f".log.{hex_slot(key)}")).stat().st_mtime_ns
    head = reg.family()[".head"]
    assert b"%" not in head, ("an out-of-class slot was counted as cached", head)
    for key in keys:
        reg.read("--since", str(n), "--cache", str(reg.cache), f"--log-key={key}")
        again = (reg.cache.parent / (reg.cache.name + f".log.{hex_slot(key)}")).stat().st_mtime_ns
        assert again > first[key], (key, "not rewritten on its next read")


PICKAXE = ["dot-in-name", "count-kept", "no-match", "at-bound", "at-needs-generation",
           "past-head-or-other-generation",
           # Five more, new since v3f (R-F11-1; T217i): lane 3's accepted readings of `--last`
           # for T114 (lane 1, #165 6755628366 reading 5; lane 3, 6755922262 reading 5).
           "generation-needs-at", "empty-grep", "path-empty-or-control", "at-minus-1",
           "replay-mismatch-69"]

#: The three whose 64 is `journal`'s own argument check, made "before anything
#: is read" (lane 1's `cmd_journal`; contract section 3.6), so they need no
#: register: they run the checkout's `lanes-index` and fail by their own
#: assertion here, without an engine. The other eight read the register.
PICKAXE_NO_ENGINE = ("generation-needs-at", "empty-grep", "path-empty-or-control")


def refused_before_any_connection(tmp_path: Path, case: str) -> None:
    """`journal --last`'s 64 for `case`, by the checkout's own `lanes-index`,
    with no register and no engine. Each refusal is paired with a CONTROL, the
    same argv with only the faulty part made valid, which must not end 64: so a
    `lanes-index` too old to have `journal` at all, whose 64 is "unknown
    subcommand" (F8), fails on the control and never passes for the refusal.
    The control ends at the configuration, a named file that does not exist
    (2), which is before any connection."""
    log, key, generation = "lanes/log/repoA-1.md", "aXb", str(UUID_M1)
    root = tmp_path / "no-register"
    root.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LANES_", "PG", "TMUX"))}
    env.update({"HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
                "LANES_INDEX_CONFIG": str(root / "no-such.conf"), "LANES_WORKSTATION": "Eagle"})

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(helpers.LANES_INDEX), "journal", "--last", *args],
                              env=env, capture_output=True, text=True, timeout=60, check=False,
                              stdin=subprocess.DEVNULL)

    def refused(control: tuple, *variants: tuple) -> None:
        valid = run(*control)
        assert valid.returncode != 64, (case, "the valid form is itself a usage error", control,
                                        valid.returncode, valid.stderr)
        for variant in variants:
            result = run(*variant)
            assert result.returncode == 64, (case, variant, result.returncode, result.stdout,
                                             result.stderr)
            assert result.stdout == "", (case, variant, "a usage error prints nothing on stdout",
                                         result.stdout)

    if case == "generation-needs-at":
        refused(("--path", log, "--grep", key, "--at", "5", "--generation", generation),
                ("--path", log, "--grep", key, "--generation", generation))
    elif case == "empty-grep":
        refused(("--path", log, "--grep", key),
                ("--path", log, "--grep", ""), ("--path", log, "--grep="))
    else:
        refused(("--path", log, "--grep", key),
                ("--path", "", "--grep", key),
                ("--path", "lanes/log/repoA" + chr(1) + "-1.md", "--grep", key),
                ("--path", "lanes/log/repoA" + chr(10) + "-1.md", "--grep", key))


@pytest.mark.parametrize("case", PICKAXE)
def test_journal_last_pickaxe_finds_the_newest_entry_that_changes_the_keys_count(
        request, tmp_path, case):
    """`journal --last --path <log> --grep <key> [--at <n> --generation <g>]`
    (lane 1's T114; L1v4.5:327-330; lane 5's C7, C8) gives `seq=` of the
    newest entry at or below `n` whose edits change how many times `<key>`
    occurs in the log, as a fixed string (git's `-S`). Real engine: it skips
    without one (T205), but for the three `PICKAXE_NO_ENGINE` cases, whose 64
    is decided before any connection."""
    if case in PICKAXE_NO_ENGINE:
        return refused_before_any_connection(tmp_path, case)
    log = "lanes/log/repoA-1.md"
    reg = RealRegister(request.getfixturevalue("pg"), tmp_path / "real", l1_files())
    text = reg.files[log]
    seq_axb = reg.write({log: text + well_formed("lane aXb", 1)})
    text = reg.files[log]
    seq_dot = reg.write({log: text + well_formed("lane a.b", 2)})
    text = reg.files[log]
    reg.write({log: text + well_formed("lane aXb again", 3)})
    text = reg.files[log]
    seq_kept = reg.write({log: text.replace(well_formed("lane a.b", 2),
                                            well_formed("lane a.b, reworded", 2))})

    def last(*args):
        return reg.index("journal", "--last", "--path", log, *args)

    if case == "dot-in-name":
        result = last("--grep", "a.b")
        assert result.returncode == 0 and f"seq={seq_dot}" in result.stdout.split(), \
            (result.returncode, result.stdout, result.stderr)
    elif case == "count-kept":
        result = last("--grep", "a.b")
        assert f"seq={seq_kept}" not in result.stdout.split(), (seq_kept, result.stdout)
        assert f"seq={seq_dot}" in result.stdout.split(), result.stdout
    elif case == "no-match":
        result = last("--grep", "no-such-lane")
        assert result.returncode == 0, (result.returncode, result.stderr)
        assert not re.search(r"(?m)^seq=", result.stdout), result.stdout
    elif case == "at-bound":
        result = last("--grep", "aXb", "--at", str(seq_dot), "--generation", reg.generation)
        assert result.returncode == 0 and f"seq={seq_axb}" in result.stdout.split(), \
            (result.returncode, result.stdout, result.stderr)
    elif case == "at-needs-generation":
        result = last("--grep", "aXb", "--at", str(seq_dot))
        assert result.returncode == 64, (result.returncode, result.stderr)
    elif case == "at-minus-1":
        # `--at -1` with `.head`'s generation is ACCEPTED and never 64: all this case asserts
        # until a draft states what it means (lane 1, #165 6767591676: draft 4.13's open point 3).
        result = last("--grep", "aXb", "--at", "-1", "--generation", reg.generation)
        assert result.returncode != 64, (result.returncode, result.stdout, result.stderr)
    elif case == "replay-mismatch-69":
        # A journal whose `replace` line does not match its `old_sha256` is 69, and gives no
        # rank. `commit_write` refuses a mismatched `old_sha256` when it is sent, so the entry
        # is made right and its journal row is spoiled afterwards, by the cluster's superuser.
        before = last("--grep", "aXb")
        assert before.returncode == 0 and re.search(r"(?m)^seq=[0-9]+$", before.stdout), \
            ("the journal does not replay before it is spoiled", before.returncode, before.stdout,
             before.stderr)
        line = _lines(reg.files[log])[2]
        seq = reg.replace(log, 3, line + ", reworded twice")
        reg.pg.psql("UPDATE lanes_register.journal_edits SET old_sha256 = repeat('0', 64) "
                    f"WHERE seq = {seq} AND op = 'replace';")
        spoiled = last("--grep", "aXb")
        assert spoiled.returncode == 69, (spoiled.returncode, spoiled.stdout, spoiled.stderr)
        assert not re.search(r"(?m)^seq=", spoiled.stdout), ("a rank was given", spoiled.stdout)
    else:
        above = last("--grep", "aXb", "--at", str(reg.head() + 1), "--generation", reg.generation)
        assert above.returncode == 69, (above.returncode, above.stderr)
        other = last("--grep", "aXb", "--at", str(seq_dot), "--generation", UUID_M1)
        assert other.returncode == 69, (other.returncode, other.stderr)


@pytest.mark.parametrize(("answer", "lane"), [pytest.param(0, "repoM-1", id="0"),
                                              pytest.param(1, "repoM-2", id="1"),
                                              pytest.param(8, "repoA-1", id="8")])
def test_managed_projection_answers_0_1_8_from_sql_as_files_mode_does(pg, estate, tmp_path,
                                                                      answer, lane):
    """RE (R3's N7): for a lane set up to give each of `managed-projection`'s
    answers, 0, 1 and 8, the answer and the exit on primary, read from SQL,
    equal files mode's on the same register (D10, S4). The register is the
    estate's, brought to primary on the `pg` fixture's database by AT-LR006's
    route (`RealRegister`). The primary run is the checkout's `lanes-edit.sh`
    copied beside the flipped copy, so the `lanes-index` it asks is that copy
    (T217h; lane 5's finding 2). Real engine: it skips without one (T205)."""
    files = estate.edit("managed-projection", lane)
    assert files.returncode == answer, (lane, "files mode's answer", files.returncode, files.stderr)
    reg = RealRegister(pg, tmp_path / "real", render_set(estate.wip))
    edit = reg.tools()
    sql = estate.run("bash", edit, "managed-projection", lane,
                     env={"LANES_EDIT": str(edit), "LANES_INDEX_CONFIG": str(reg.config),
                          "LANES_INDEX": None})
    assert (sql.returncode, sql.stdout) == (files.returncode, files.stdout), \
        (lane, sql.returncode, sql.stdout, sql.stderr, files.returncode, files.stdout)


# ------------------------------------------------------- lane 5's nine (A5)
#: A `git` that reads the register: `show`, `grep`, `cat-file` or `log` on a
#: `lanes/` path, as `GIT_TRACE` logs it.
GIT_REGISTER_READ = re.compile(r"trace: (?:built-in|exec): git (?:show|grep|cat-file|log)\b[^\n]*lanes")
GIT_NETWORK = re.compile(r"trace: (?:built-in|exec|run_command): git (?:fetch|ls-remote)\b")


def traced(path: Path, pattern: re.Pattern) -> list:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if pattern.search(line)]


def test_a_primary_reader_makes_one_prefetch_and_every_read_site_reads_its_cache_at_one_n(primary):
    """T505: on primary a reader makes ONE prefetch (form 1) in its main
    shell, and every read site reads the family it cached at that one `n`:
    no second read where every file it needs was prefetched, and no `git`
    read of the register. Its answer is the store's."""
    for argv in (("register-row", STORE_ONLY_LANE), ("canon-lane", STORE_ONLY_LANE)):
        trace = primary.e.root / f"git-trace-{argv[0]}"
        primary.door.forget_calls()
        result = primary.edit(*argv, env={"GIT_TRACE": str(trace)})
        calls = primary.door.register_calls()
        assert [c["form"] for c in calls] == [1], (argv, "not one prefetch alone", calls,
                                                   result.stderr[-1500:])
        assert result.returncode == 0, (argv, result.returncode, result.stderr[-1500:])
        assert STORE_ONLY_LANE in result.stdout, (argv, "not the store's answer", result.stdout)
        assert not traced(trace, GIT_REGISTER_READ), (argv, traced(trace, GIT_REGISTER_READ))


@pytest.mark.parametrize("case", ["moved-head", "case-duplicates", "failed-read"])
def test_a_read_site_with_no_prefetched_file_makes_one_more_register_read_and_never_a_git_read(
        primary, case):
    """T505 (O17's form 3; C3, C11): a read site whose file the prefetch did
    not fetch makes one more `register read`, form 3 `--since <n>`, never a
    `git` read: `[moved-head]`, the head moved past `n` before it, answers at
    `n′`; `[case-duplicates]`, two render-set logs that differ only by case,
    is 69 with nothing on stdout; `[failed-read]`, the class's failed read,
    is 69, never files mode."""
    log = f"lanes/log/{STORE_ONLY_LANE}.md"
    moved = STORE_ONLY_LOG + (f"NOTED — lane {STORE_ONLY_LANE}, session {STORE_ONLY_UUID}@Eagle, "
                              f"2026-10-05T01:00:00Z, lane:{STORE_ONLY_LANE} — the head moved\n")
    if case == "moved-head":
        primary.door.fail(narrow="register,aliases", move={log: moved})
    elif case == "case-duplicates":
        primary.door.commit({f"lanes/log/{STORE_ONLY_LANE.upper()}.md": "NOTED — the case pair\n"})
        primary.door.fail(narrow="register,aliases")
    else:
        primary.door.fail(narrow="register,aliases", all=True, forms=[3], exit=69,
                          stdout="mode primary\n", stderr=UNREACHABLE_STDERR)
    n, _gen = primary.door.head()
    trace = primary.e.root / "git-trace"
    result = primary.edit("lane-last", STORE_ONLY_LANE, env={"GIT_TRACE": str(trace)})
    calls = primary.door.register_calls()
    assert [c["form"] for c in calls].count(1) == 1, (case, calls, result.stderr[-1500:])
    thirds = [c["argv"] for c in calls if c["form"] == 3]
    assert len(thirds) == 1, (case, "not one second read", calls)
    assert thirds[0][thirds[0].index("--since") + 1] == str(n), (case, thirds[0])
    assert not traced(trace, GIT_REGISTER_READ), (case, traced(trace, GIT_REGISTER_READ))
    if case == "moved-head":
        assert result.returncode == 0, (case, result.returncode, result.stderr[-1500:])
    else:
        assert result.returncode == 69, (case, result.returncode, result.stdout, result.stderr[-1500:])
        assert result.stdout == "", (case, result.stdout)


def test_the_flush_helper_drops_the_whole_read_family(tmp_path):
    """T505 (C6): `reg_flush`, taken from `lanes-edit.sh` by its text (the
    script cannot be sourced), drops `.register`, `.aliases`, `.archive`,
    `.paths`, every `.log.*` and `.logpath.*`, and empties
    `LANES_REGISTER_CACHE`."""
    found = re.search(r"^reg_flush\(\) *\{.*?^\}[ \t]*$", LANES_EDIT.read_text(encoding="utf-8"),
                      re.M | re.S)
    assert found, "lanes-edit.sh has no reg_flush"
    cache = tmp_path / "se"
    members = [".register", ".aliases", ".archive", ".paths", ".log.repoA-1", ".logpath.repoA-1",
               ".log.%2c", ".logpath.%2c"]
    for member in members:
        (tmp_path / f"se{member}").write_text("cached\n", encoding="utf-8")
    script = (found.group(0) + '\nSE_CACHE_FILE="$1"; LANES_REGISTER_CACHE="$1.register"\n'
              'reg_flush\nprintf "[%s]" "$LANES_REGISTER_CACHE"\n')
    result = subprocess.run(["bash", "-c", script, "flush", str(cache)], capture_output=True,
                            text=True, timeout=30, check=False, stdin=subprocess.DEVNULL)
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert result.stdout == "[]", result.stdout
    left = [m for m in members if (tmp_path / f"se{m}").exists()]
    assert not left, ("the family is not all dropped", left)


def test_swapped_ranks_through_journal_last_on_primary(primary):
    """T506 (C7, C8): on primary, `swapped`'s rank is the head less
    `lanes-index journal --last --path <log> --grep <key> --at <n>
    --generation <g>`, with `.head`'s `n` and generation, never `git log -S`."""
    helpers.stub_outcome(primary.door.store, "journal --last", exit=0, stdout="seq=1\n")
    trace = primary.e.root / "git-trace"
    result = primary.edit("swapped", env={"GIT_TRACE": str(trace)})
    lasts = [c["argv"] for c in primary.door.calls() if c["argv"][:2] == ["journal", "--last"]]
    assert lasts, ("swapped never asked journal --last", result.returncode, result.stderr[-1500:])
    n, generation = primary.door.head()
    for argv in lasts:
        assert argv[argv.index("--path") + 1].startswith("lanes/log/"), argv
        assert "--grep" in argv, argv
        assert argv[argv.index("--at") + 1] == str(n), (argv, n)
        assert argv[argv.index("--generation") + 1] == generation, (argv, generation)
    assert not traced(trace, re.compile(r"git log\b[^\n]*-S")), traced(trace, re.compile(r"git log"))


#: Readers whose files-mode run calls `log_sync`, which fetches: the first
#: that fetches in files mode is the case's.
LOG_SYNC_READS = (("history",), ("lanes", "--fetch"), ("lane-last", "repoA-1"))


def test_log_sync_on_primary_makes_no_fetch_and_no_flush(primary):
    """T506: `log_sync` on primary makes no fetch and no flush: the read
    that fetches in files mode makes no `git fetch` and no `ls-remote` on
    primary, and its one prefetch is never made again (a flush would empty
    the family and refetch it)."""
    chosen = None
    for argv in LOG_SYNC_READS:
        trace = primary.e.root / f"files-trace-{argv[0]}"
        primary.files_edit(*argv, env={"GIT_TRACE": str(trace)})
        if traced(trace, GIT_NETWORK):
            chosen = argv
            break
    assert chosen, "no reader fetched in files mode: the control found no log_sync"
    trace = primary.e.root / "primary-trace"
    result = primary.edit(*chosen, env={"GIT_TRACE": str(trace)})
    calls = primary.door.register_calls()
    assert [c["form"] for c in calls].count(1) == 1, (chosen, calls, result.stderr[-1500:])
    assert not traced(trace, GIT_NETWORK), (chosen, traced(trace, GIT_NETWORK))


def test_the_local_file_unions_are_skipped_on_primary(primary):
    """T506 (W:4865): on primary the local-file unions are skipped, since a
    primary write is in SQL before it returns. `row_of_lane_local` is the
    union's source: a session id only this checkout's copy of a row holds is
    in files mode's `register-row-local` answer (the control), and not in
    primary's, which answers the register's row."""
    lanes = primary.e.wip / "lanes" / "LANES.md"
    text = lanes.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `repoA-2` |"))
    lanes.write_text(text.replace(row, row.replace(f"`{UUID_A2}`", f"`{UUID_A2}` → `{LOCAL_SID}`", 1)),
                     encoding="utf-8")                         # this checkout's copy only
    local = primary.files_edit("register-row-local", "repoA-2")
    assert local.returncode == 0 and LOCAL_SID in local.stdout, \
        ("the control: files mode did not read this checkout's row", local.returncode, local.stdout)
    result = primary.edit("register-row-local", "repoA-2")
    assert primary.door.register_calls(), ("the read never reached the store", result.stderr)
    assert result.returncode == 0 and UUID_A2 in result.stdout, (result.returncode, result.stdout)
    assert LOCAL_SID not in result.stdout, ("a local row's id on primary", result.stdout)


def test_the_lanes_footer_on_primary_names_the_register_and_claims_no_local_read(primary):
    """T509 (R43): on primary the `lanes` script's footer says the listing
    is as of the register at seq `<n>` and claims no local read."""
    result = primary.script("lanes")
    assert primary.door.register_calls(), ("the listing never reached the store", result.stderr)
    n, _gen = primary.door.head()
    out = result.stdout + result.stderr
    assert re.search(rf"(?i)register at seq {n}\b", out), out[-1500:]
    assert not re.search(r"(?i)\blocally\b", out), out[-1500:]


def test_lanes_fetch_on_primary_prints_no_no_fetch_note(primary):
    """T509: on primary the `lanes` arm makes no fetch, so `--fetch` prints
    no "NO FETCH WAS MADE" note, where files mode, its origin gone, does (the
    control)."""
    origin = primary.e.origin
    origin.rename(origin.with_name("origin-aside.git"))
    files = primary.files_edit("lanes", "--fetch")
    assert "NO FETCH WAS MADE" in files.stderr, ("the control", files.stderr[-1500:])
    result = primary.edit("lanes", "--fetch")
    assert primary.door.register_calls(), ("the listing never reached the store", result.stderr)
    assert "NO FETCH WAS MADE" not in result.stdout + result.stderr, result.stderr[-1500:]


MIRROR_ROW = re.compile(r"^\s*([A-Za-z0-9_|-]+)\)[^\n]*\bREG_MIRROR_VAR=1\b", re.M)


def test_the_read_mirror_variable_lowers_each_read_that_names_the_lane_on_primary(primary):
    """T504 (R-L4Q1; the reads are T275's list): `LANES_READ_MIRROR=1`
    lowers each read whose row in the class table sets `REG_MIRROR_VAR=1`,
    `window-lane` and `swapped` among them, to a mirror read on primary: with
    the store unreachable each prints the `read: mirror` line and exits as
    files mode does. Every other arm ignores the variable, `who` and
    `lane-last` among them (B14 tasks:737): `lane-last`, a read that names
    the lane and no row of the table, still refuses 69 (T217m; lane 5's
    triage, #165 6782743644: `register-row`, the arm here before, is one of
    the table's)."""
    table = CLASS_FUNCTION.search(LANES_EDIT.read_text(encoding="utf-8"))
    assert table, "lanes-edit.sh has no read door class table (reg_class_of)"
    marked = {arm for row in MIRROR_ROW.findall(table.group(1)) for arm in row.split("|")}
    assert {"window-lane", "swapped"} <= marked, marked
    assert "lane-last" not in marked, marked
    primary.door.unreachable()
    for argv in (("window-lane", "Eagle", "@1"), ("swapped",)):
        files = primary.files_edit(*argv)
        result = primary.edit(*argv, env={"LANES_READ_MIRROR": "1"})
        assert MIRROR_LINE.search(result.stderr), (argv, result.stderr[-1500:])
        assert result.returncode == files.returncode, (argv, result.returncode, files.returncode)
    other = primary.edit("lane-last", "repoA-1", env={"LANES_READ_MIRROR": "1"})
    assert other.returncode == 69, (other.returncode, other.stderr[-1500:])
    assert not MIRROR_LINE.search(other.stderr), other.stderr[-1500:]


# --------------------------------------------- T502's `lanes --decide` test
#: Lane 5's seed (refs/l5/T502), kept: each row's age column is masked, the
#: one value that moves between two reads.
COLUMNS = 17
AGE_COLUMN = 8
AGE_SHAPE = re.compile(r"[0-9]+h [0-9]{2}m|age unknown")
LISTINGS = [(), ("--all",), ("--closed",), ("--lane", "repoA-1")]
REFUSED = [("--no-such-flag",), ("--decided",), ("--decide", "--no-such-flag")]


def _masked(stdout: str) -> str:
    out = []
    for line in stdout.splitlines(keepends=True):
        body = line.rstrip("\n")
        fields = body.split("\t")
        assert len(fields) == COLUMNS, (len(fields), line)
        assert AGE_SHAPE.fullmatch(fields[AGE_COLUMN]), (fields[AGE_COLUMN], line)
        fields[AGE_COLUMN] = "<AGE>"
        out.append("\t".join(fields) + line[len(body):])
    return "".join(out)


def test_lanes_accepts_decide_and_reads_as_without_it(estate, primary):
    """`lanes --decide` IS `lanes` UNTIL T509 (T502, R38 as lane 3 amended
    it; lane 5's seed, kept by name): in files mode and on primary the arm
    takes the flag and answers as if it were not there, the same exit,
    stdout byte for byte with the age column masked, and the same stderr. Its
    unknown-argument `die` still meets every other argument, before
    `--decide` or after it, with 64."""
    for where, edit in (("files", estate.edit), ("primary", primary.edit)):
        bare = edit("lanes")
        assert bare.returncode == 0 and bare.stdout, (where, bare.returncode, bare.stderr)
        closed = edit("lanes", "--closed")
        assert closed.returncode == 0, (where, closed.returncode, closed.stderr)
        assert _masked(closed.stdout) != _masked(bare.stdout), (where, closed.stdout)
        for listing in LISTINGS:
            without = edit("lanes", *listing)
            assert without.returncode == 0 and without.stdout, \
                (where, listing, without.returncode, without.stderr)
            for argv in dict.fromkeys([(*listing, "--decide"), ("--decide", *listing)]):
                with_it = edit("lanes", *argv)
                assert with_it.returncode == without.returncode, \
                    (where, argv, with_it.returncode, with_it.stdout, with_it.stderr)
                assert _masked(with_it.stdout) == _masked(without.stdout), \
                    (where, argv, with_it.stdout, without.stdout)
                assert with_it.stderr == without.stderr, (where, argv, with_it.stderr, without.stderr)
        for argv in REFUSED:
            refused = edit("lanes", *argv)
            assert refused.returncode == 64, (where, argv, refused.returncode, refused.stderr)
            assert refused.stdout == "", (where, argv, refused.stdout)
            assert f"unknown argument '{argv[-1]}' for lanes" in refused.stderr, \
                (where, argv, refused.stderr)


# ------------------------------- T235: T505's three read sites (F13b, proposed)
#: THE FAKE `git`'S ARGV LOG (T235): a `git` in front of the real one that
#: appends each call's argv, its words joined by US, one call a line, to
#: `$T235_GIT_LOG`, then runs the real one at `$T235_REAL_GIT`.
LOGGING_GIT = r'''#!/usr/bin/env bash
# THE LOGGING GIT (T235): log this call's argv in one write, then run the real git.
t235_line="$(printf '%s\037' "$@")"
printf '%s\n' "$t235_line" >> "$T235_GIT_LOG"
exec "$T235_REAL_GIT" "$@"
'''

#: The log directory `known_lanes`, `remote_log_events` and `worktree_rows`'
#: pin read by git off primary (P2's `lanes-edit.sh`, `LANES_LOG_PREFIX`).
LOG_DIR = "lanes/log"

#: T235's ids (F13c's block, T235): four the text writes whole, and three run
#: through the module's door (`DOOR_WRAPPER`), whose oracles are lane 3's
#: batch 7 (#165 6780364102), by batch 5's answers 3 and 4 (6778890211). No
#: id holds the word `worktrees`, which lane 4's T404 word
#: `sql_register_readers and worktrees` (B12b tasks:886) would otherwise
#: select.
T235_CASES = ["known-lanes", "remote-log-events-lanes", "remote-log-events-history",
              "worktree-rows", "case-pair", "out-of-class", "failed-second-read"]
T235_LATER = ("case-pair", "out-of-class", "failed-second-read")

#: Lines only the store's logs hold (T235): a `dir` for repoA-2, and a note.
T235_DIR = "/work/t235-only-in-the-store"
T235_NOTE = "T235: a note only the store holds"

#: `[case-pair]`'s two logs (C11; CLI:674), which differ only by case.
T235_PAIR = ("lanes/log/repoP-1.md", "lanes/log/RepoP-1.md")
#: `[out-of-class]`'s log (O18; CLI:670-672, :729), a stem outside the class,
#: and its own event, a well-formed line naming a lane (batch 7); its lane is
#: the file's, `a,b` (Amendment 16(e)).
T235_OUT_KEY = "a,b"
T235_OUT_LOG = f"lanes/log/{T235_OUT_KEY}.md"
T235_OUT_NOTE = "T235: an event only the log outside the class holds"
T235_OUT_LINE = (f"NOTED — lane repoO-1, session {STORE_ONLY_UUID}@Eagle, "
                 f"2026-10-06T00:00:01Z, lane:repoO-1 — {T235_OUT_NOTE}\n")
#: `lanes`' fence for the logs a read could not read (`lanes_rows`), and the
#: two reads each door form makes.
T235_FENCE = "these published logs could not be read, so no lane of theirs is classed DORMANT:"
T235_RUNS = (("lanes", "--all", "--closed"), ("history", "--all"))


def git_log_reads(log: Path, upto: re.Pattern | None = None) -> list:
    """The calls in the fake `git`'s argv log that read `lanes/log` by git:
    an `ls-tree` naming it, or a `show` of a path under it. Each call's line
    holds US. Where the log is also the run's stderr (`[failed-second-read]`),
    every other line is stderr's, and `upto`, where given, ends the scan at
    the first of those it matches."""
    if not log.exists():
        return []
    found = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\037" not in line:
            if upto is not None and upto.search(line):
                break
            continue
        argv = line.split("\037")
        if argv and argv[-1] == "":
            argv = argv[:-1]
        rest, i = [], 0
        while i < len(argv):
            if argv[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
                i += 2
                continue
            if argv[i].startswith("-"):
                i += 1
                continue
            rest = argv[i:]
            break
        if not rest:
            continue
        verb, args = rest[0], rest[1:]
        if verb == "ls-tree" and any(LOG_DIR in a for a in args):
            found.append(argv)
        elif verb == "show" and any(a.startswith(LOG_DIR) or f":{LOG_DIR}" in a for a in args):
            found.append(argv)
    return found


def _rows(stdout: str) -> dict:
    """A listing's rows by their first column, the lane."""
    return {line.split("\t", 1)[0]: line for line in stdout.splitlines() if line}


def asked_logs(argv: list) -> list:
    """How one `register read` call asks for logs (CLI:670-672, :729): `("=",
    <key>)` for each `--log-key=<key>`, `(" ", <key>)` for a `--log-key <key>`,
    and `("files", <list>)` for each `--files` list, whole, since a key that
    holds `,` would be split across its items."""
    found = []
    for i, arg in enumerate(argv):
        after = argv[i + 1] if i + 1 < len(argv) else ""
        if arg.startswith("--log-key="):
            found.append(("=", arg[len("--log-key="):]))
        elif arg == "--log-key":
            found.append((" ", after))
        elif arg.startswith("--files="):
            found.append(("files", arg[len("--files="):]))
        elif arg == "--files":
            found.append(("files", after))
    return found


def files_names_log(value: str, key: str) -> bool:
    """Whether a `--files` list names `key`'s log, `log:<key>`, in any case."""
    return re.search(rf"(?:^|,)log:{re.escape(key)}(?:,|$)", value, re.I) is not None


def unreadable_notes(stderr: str, path: str) -> int:
    """How many `unreadable log: <path> — ` notes stderr holds, as `note`
    prints them, `lanes-edit: ` first, the form `lanes_rows`' and
    `worktree_rows`' `sed` patterns read back."""
    return len(re.findall(rf"(?m)^lanes-edit: unreadable log: {re.escape(path)} — ", stderr))


@pytest.mark.parametrize("case", T235_CASES)
def test_on_primary_known_lanes_remote_log_events_and_worktree_rows_read_the_store_and_never_git(
        pg, estate, tmp_path, case):
    """T235 (lane 5's T505 plan, #165 6774988528, question 12; lane 5's
    choice (b), 6778955065; placed in B14, 6779844884; FR-033, FR-034): on
    primary, `known_lanes`, `remote_log_events` and `worktree_rows` read the
    store and never git. Each id asserts the store's answer, and that no `git
    ls-tree` and no `git show` of `lanes/log` ran, by the fake `git`'s argv
    log (`LOGGING_GIT`):

      * `[known-lanes]`: a lane's log with no register row, only in the store,
        which `known_lanes` lists from the family (`lanes --all --closed`);
      * `[remote-log-events-lanes]` and `[remote-log-events-history]`: events
        only the store holds, which `remote_log_events` returns through
        `lanes` without `--lane`, and through `history --all`;
      * `[worktree-rows]`: the `worktrees` arm on primary, through
        `worktree_rows` and its log-set pin (P2's `lanes-edit.sh:17222`): a
        tree under a `dir` only the store's log names.

    The three door forms run through the module's door in front of the
    flipped copy, which logs every register call, and their oracles are lane
    3's batch 7 (#165 6780364102), by batch 5's answers 3 and 4 (6778890211):

      * `[case-pair]`, the store holding `lanes/log/repoP-1.md` and
        `lanes/log/RepoP-1.md` (C11; CLI:674): `lanes --all --closed` and
        `history --all` exit 0, never 69; no form 3 names either log, as
        `log:<key>` in `--files` or as `--log-key=`, by the door's call log
        with failures off; stderr carries one `unreadable log: <path> — `
        note per path, its reason words T505's, which both `sed` patterns
        must accept; `lanes` prints its fence naming both paths; the other
        lanes' rows are the store's answer; and no git read;
      * `[out-of-class]`, `lanes/log/a,b.md` (O18; CLI:670-672, :729): every
        form 3 that asks for it carries `--log-key=a,b`, in the `=` form,
        and none puts it inside `--files`; its own event is in `history
        --all`; exit 0, no `unreadable log:` note for it, and no git read;
      * `[failed-second-read]`, every form 3 failing 69, with `a,b.md` in
        `.paths`: `lanes` and `history` print `read: mirror at <sha12>` on
        stderr and then the mirror's answer, files mode's (its exit, and its
        stdout, `lanes`' age column masked), never the store's answer with
        `a,b`'s lines silently missing. The no-git check holds only up to
        that label, since the mirror read is a git read: the fake `git`'s
        log and the run's stderr are one file, appended in the order written.

    The register is the estate's, brought to primary on the `pg` fixture's
    database by AT-LR006's route (`RealRegister`), with the store-only files
    in its import; the run is the checkout's `lanes-edit.sh` copied beside
    the flipped copy, as `managed-projection`'s RE case runs. FAILS UNTIL
    lane 5's T505, and, with the module's other real-register cases, until
    lane 2's T227 and T228. Real engine: it skips without one (T205)."""
    files = render_set(estate.wip)
    a2 = files["lanes/log/repoA-2.md"].decode("utf-8")
    a2_dir = (f"STARTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-06T00:00:00Z, "
              f"lane:repoA-2 → home opensoft/repoA; dir {T235_DIR}; profile team-01b\n")
    a2_note = (f"NOTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-06T00:00:00Z, "
               f"lane:repoA-2 — {T235_NOTE}\n")
    trees = tmp_path / "t235-roots"
    if case == "known-lanes":
        files[f"lanes/log/{STORE_ONLY_LANE}.md"] = STORE_ONLY_LOG.encode()
    elif case == "remote-log-events-lanes":
        files["lanes/log/repoA-2.md"] = (a2 + a2_dir).encode()
    elif case == "remote-log-events-history":
        files["lanes/log/repoA-2.md"] = (a2 + a2_note).encode()
    elif case == "worktree-rows":
        # `lane_control_root`: a `dir` whose parent is there gives `<parent>/.lane-state/<lane>`,
        # and a sidecar of a schema no reader knows is listed by its id and path, never parsed.
        sidecar = trees / ".lane-state" / STORE_ONLY_LANE / "trees" / "t235.yaml"
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(f"schema: t235-a-schema-no-reader-knows\ntree: t235-store-tree\n"
                           f"path: {trees / 'tree'}\n", encoding="utf-8")
        files[f"lanes/log/{STORE_ONLY_LANE}.md"] = (
            f"STARTED — lane {STORE_ONLY_LANE}, session {STORE_ONLY_UUID}@Eagle, "
            f"2026-10-05T00:00:00Z, lane:{STORE_ONLY_LANE} → home opensoft/repoS; "
            f"dir {trees / 'repoS-1'}\n").encode()
    elif case == "case-pair":
        files["lanes/log/repoA-2.md"] = (a2 + a2_dir + a2_note).encode()
        files[T235_PAIR[0]] = ("STARTED — lane repoP-1, session "
                               f"{STORE_ONLY_UUID}@Eagle, 2026-10-05T00:00:00Z, "
                               "lane:repoP-1 → home opensoft/repoP\n").encode()
        files[T235_PAIR[1]] = "NOTED — the case pair's other half\n".encode()
    elif case == "out-of-class":
        files[T235_OUT_LOG] = T235_OUT_LINE.encode()
    else:                                                    # failed-second-read
        files["lanes/log/repoA-2.md"] = (a2 + a2_dir + a2_note).encode()
        files[T235_OUT_LOG] = T235_OUT_LINE.encode()
    reg = RealRegister(pg, tmp_path / "real", files)
    edit = reg.tools()
    door = None
    if case in T235_LATER:
        # The module's door in front of a flipped copy, which logs every register call ("count
        # this from the door's call log, with failures off"); for [failed-second-read] every
        # second read (form 3) fails 69.
        door = tmp_path / "real" / "door"
        helpers.flipped_copy(helpers.LANES_INDEX, door / "store", True)
        _write(door / "lanes-index", DOOR_WRAPPER)
        for name in RealRegister.TOOLS:
            shutil.copy2(REPO / name, door / name)
        if case == "failed-second-read":
            (door / "lanes-index.fail").write_text(json.dumps(
                {"all": True, "forms": [3], "exit": UNREACHABLE_EXIT, "stdout": "mode primary\n",
                 "stderr": UNREACHABLE_STDERR}), encoding="utf-8")
        edit = door / "lanes-edit.sh"
    shim = tmp_path / "t235-git"
    real_git = shutil.which("git")
    _write(shim / "git", LOGGING_GIT)

    def git_env(log: Path) -> dict:
        return {"LANES_EDIT": str(edit), "LANES_INDEX_CONFIG": str(reg.config), "LANES_INDEX": None,
                "PATH": str(shim) + os.pathsep + estate.env["PATH"],
                "T235_GIT_LOG": str(log), "T235_REAL_GIT": real_git}

    # THE CONTROL: the fake `git` is the one on PATH, and its log shows the read the sites
    # make off primary, so a run that logs none made none (a T505 run may log no call at all).
    control = tmp_path / "t235-git-control.log"
    listed = estate.run("git", "-C", estate.wip, "ls-tree", "--name-only", "origin/main", "--",
                        f"{LOG_DIR}/", env=git_env(control))
    assert listed.returncode == 0 and git_log_reads(control), (
        "the control: the fake git logged no ls-tree of lanes/log", listed.stderr)

    def run(*argv: str) -> subprocess.CompletedProcess:
        log = tmp_path / f"t235-git-{'-'.join(argv)}.log"
        result = estate.run("bash", edit, *argv, env=git_env(log))
        assert not git_log_reads(log), (case, argv, "git read lanes/log", git_log_reads(log),
                                        result.stderr[-1500:])
        return result

    def run_in_order(*argv: str) -> tuple:
        """The run with the fake `git`'s log and its stderr in ONE file, each
        line appended as it is written, so that a git call can be placed
        before or after a line of stderr: the result, stderr, and the file."""
        both = tmp_path / f"t235-order-{'-'.join(argv)}.log"
        child = dict(estate.env)
        for key, value in git_env(both).items():
            if value is None:
                child.pop(key, None)
            else:
                child[key] = value
        with open(both, "ab") as err:                        # O_APPEND, as the shim's `>>`
            result = subprocess.run(["bash", str(edit), *argv], stdout=subprocess.PIPE,
                                    stderr=err, text=True, env=child, cwd=str(estate.root),
                                    timeout=120, stdin=subprocess.DEVNULL, check=False)
        lines = both.read_text(encoding="utf-8", errors="replace").splitlines()
        return result, "\n".join(line for line in lines if "\037" not in line), both

    if case == "known-lanes":
        result = run("lanes", "--all", "--closed")
        assert result.returncode == 0, (case, result.returncode, result.stderr[-1500:])
        rows = _rows(result.stdout)
        assert "repoB-1" in rows, (case, "the control: a log with no row in both stores",
                                   result.stdout)
        assert STORE_ONLY_LANE in rows, (case, "not the store's answer", result.stdout)
    elif case == "remote-log-events-lanes":
        result = run("lanes", "--all", "--closed")
        assert result.returncode == 0, (case, result.returncode, result.stderr[-1500:])
        rows = _rows(result.stdout)
        assert "repoA-2" in rows, (case, result.stdout)
        assert T235_DIR in rows["repoA-2"], (case, "not the store's answer", rows["repoA-2"])
    elif case == "remote-log-events-history":
        result = run("history", "--all")
        assert result.returncode == 0, (case, result.returncode, result.stderr[-1500:])
        assert T235_NOTE in result.stdout, (case, "not the store's answer", result.stdout)
    elif case == "worktree-rows":
        result = run("worktrees")
        assert result.returncode == 0, (case, result.returncode, result.stdout,
                                        result.stderr[-1500:])
        assert "t235-store-tree" in result.stdout, (case, "not the store's answer", result.stdout)
    elif case == "case-pair":
        for argv in T235_RUNS:
            result = run(*argv)
            assert result.returncode == 0, (case, argv, "exit 0, never 69", result.returncode,
                                            result.stderr[-1500:])
            for path in T235_PAIR:
                assert unreadable_notes(result.stderr, path) == 1, (
                    case, argv, path, "one `unreadable log:` note per path", result.stderr[-1500:])
            if argv[0] == "lanes":
                fence = [line.split(T235_FENCE, 1)[1].split()
                         for line in result.stderr.splitlines() if T235_FENCE in line]
                assert fence and all(path in fence[0] for path in T235_PAIR), (
                    case, "lanes fences both logs", fence, result.stderr[-1500:])
                rows = _rows(result.stdout)
                assert T235_DIR in rows.get("repoA-2", ""), (
                    case, "the other lanes' rows are not the store's answer", result.stdout)
            else:
                assert T235_NOTE in result.stdout, (case, "not the store's answer", result.stdout)
        for argv in (c["argv"] for c in door_second_reads(door)):
            for how, value in asked_logs(argv):
                named = (files_names_log(value, "repoP-1") if how == "files"
                         else value.lower() == "repop-1")
                assert not named, (case, "a form 3 asked for a log of the case pair", argv)
    elif case == "out-of-class":
        for argv in T235_RUNS:
            result = run(*argv)
            assert result.returncode == 0, (case, argv, result.returncode, result.stderr[-1500:])
            assert unreadable_notes(result.stderr, T235_OUT_LOG) == 0, (
                case, argv, "an `unreadable log:` note for it", result.stderr[-1500:])
            if argv[0] == "history":
                assert T235_OUT_NOTE in result.stdout, (
                    case, "its event is not in history --all", result.stdout)
        seconds = [c["argv"] for c in door_second_reads(door)]
        assert any(("=", T235_OUT_KEY) in asked_logs(argv) for argv in seconds), (
            case, "no form 3 asked for it as --log-key=a,b", seconds)
        for argv in seconds:
            for how, value in asked_logs(argv):
                assert not (how == "files" and files_names_log(value, T235_OUT_KEY)), (
                    case, "asked for inside --files", argv)
                assert not (how == " " and value == T235_OUT_KEY), (
                    case, "asked for, but not in the `=` form", argv)
    else:                                                    # failed-second-read
        for argv in T235_RUNS:
            mirror = estate.edit(*argv)                      # the mirror's answer: files mode's
            result, stderr, both = run_in_order(*argv)
            reads = git_log_reads(both, upto=MIRROR_LINE)
            assert not reads, (case, argv, "git read lanes/log before the mirror's label", reads,
                               stderr[-1500:])
            assert MIRROR_LINE.search(stderr), (case, argv, "no `read: mirror at` line",
                                                stderr[-1500:])
            assert not MIRROR_LINE.search(result.stdout), (case, argv, result.stdout)
            assert result.returncode == mirror.returncode, (
                case, argv, result.returncode, mirror.returncode, stderr[-1500:])
            for only in (T235_DIR, T235_NOTE, T235_OUT_NOTE):
                assert only not in result.stdout, (
                    case, argv, "the store's answer, not the mirror's", only, result.stdout)
            if argv[0] == "lanes":
                assert _masked(result.stdout) == _masked(mirror.stdout), (
                    case, argv, result.stdout, mirror.stdout)
            else:
                assert result.stdout == mirror.stdout, (case, argv, result.stdout, mirror.stdout)
        assert door_second_reads(door), (case, "no second read was made, so none failed")


def door_second_reads(door: Path) -> list:
    """The form-3 calls the door in `door` was asked (`DOOR_WRAPPER`'s log)."""
    path = door / "lanes-index.calls"
    if not path.exists():
        return []
    calls = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [c for c in calls if c.get("form") == 3]


# ------------------------------------------------- lane 4's two read verbs
#: The set both verbs answer (O21 (a)): the render set without the archive.
VERB_PATHS = ("lanes/LANES.md", "lanes/aliases.tsv", "lanes/log/repoA-2.md")
OUTSIDE_PATHS = {"other-path": "lanes/repos.tsv", "log-readme": "lanes/log/README.md"}
LOG_PATHSPEC = (":(glob)lanes/log/*.md", ":(exclude)lanes/log/README.md")


def index_env(estate: Estate) -> dict:
    """`mode=index`, by its own configuration file beside the estate's."""
    path = estate.config / "openRepoTools" / "lanes-index-index-mode.conf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("mode=index\n", encoding="utf-8")
    path.chmod(0o600)
    return {"LANES_INDEX_CONFIG": str(path)}


def origin_text(estate: Estate, path: str) -> str:
    return estate._git("show", f"origin/main:{path}")


def mode_runs(estate: Estate, primary: Primary) -> dict:
    """The three modes' runs of `lanes-edit.sh`: files, `mode=index`, and
    primary with the store reachable (the contract stub, R2f4-S14)."""
    return {"files": lambda *a: estate.edit(*a),
            "index": lambda *a: estate.edit(*a, env=index_env(estate)),
            "primary": lambda *a: primary.edit(*a)}


def store_asks(primary: Primary) -> int:
    """How many register calls the door has put to the store so far (the
    wrapper's counted calls, as the one-call failure counts them). A read
    verb on primary answers from the register through the door, never from
    the checkout's files or from git (FR-034; T401's primary branch,
    `reg_image` and `reg_paths`), so a primary run that answered leaves this
    count higher than it was before the run. Where it stays put the run read
    the files, as files mode does, and a case that loops over all three modes
    passes without having tested primary."""
    return len(primary.door.register_calls())


def strip_end(text: str) -> str:
    """`.register` normalizes trailing newlines and files mode's `cat` does
    not (lane 5's note on answer 14), so a byte case holds up to them."""
    return text.rstrip("\n")


@pytest.mark.parametrize("case", ["files", "index", "primary", "failed-read", "other-path",
                                  "log-readme"])
def test_register_text_answers_the_bytes_the_scripts_read_today_and_69_on_a_failed_read(
        estate, primary, case):
    """`register-text <path>` (lane 4's T401; GB section 4.3): in files and
    `mode=index` the bytes the scripts read today, on primary the image at
    the door's `n` (`reg_image`); 69 on a failed read in every mode; and 2,
    with nothing on stdout, for a path outside the set (`lanes/repos.tsv`,
    and `lanes/log/README.md`, O21 (a)) in every mode, the store reachable on
    primary. Each 2 case first shows the verb answers in its mode, and on
    primary that the answer came through the register: the door asked the
    store for it, as FR-034 has it, and the files did not answer (T217g)."""
    runs = mode_runs(estate, primary)
    if case in ("files", "index"):
        for path in VERB_PATHS:
            result = runs[case]("register-text", path)
            assert result.returncode == 0, (case, path, result.returncode, result.stderr)
            assert strip_end(result.stdout) == strip_end(origin_text(estate, path)), (case, path)
    elif case == "primary":
        for path in VERB_PATHS:
            result = runs["primary"]("register-text", path)
            assert result.returncode == 0, (path, result.returncode, result.stderr)
            assert strip_end(result.stdout) == strip_end(primary.door.register[path].decode()), path
        assert STORE_ONLY_ROW in runs["primary"]("register-text", "lanes/LANES.md").stdout
    elif case == "failed-read":
        primary.door.unreachable()
        result = runs["primary"]("register-text", "lanes/LANES.md")
        assert (result.returncode, result.stdout) == (69, ""), (result.returncode, result.stderr)
        gone = estate.edit("register-text", "lanes/LANES.md",
                           env={"LANES_REPO": str(estate.root / "no-such-checkout")})
        assert (gone.returncode, gone.stdout) == (69, ""), (gone.returncode, gone.stderr)
    else:
        for mode, run in runs.items():
            asked = store_asks(primary)
            control = run("register-text", "lanes/LANES.md")
            assert control.returncode == 0, (case, mode, "the verb does not answer",
                                             control.returncode, control.stderr)
            if mode == "primary":
                assert store_asks(primary) > asked, \
                    (case, mode, "the primary answer never came through the register: the door "
                     "asked the store nothing, so it read the files, which FR-034 forbids",
                     primary.door.calls())
            result = run("register-text", OUTSIDE_PATHS[case])
            assert (result.returncode, result.stdout) == (2, ""), \
                (case, mode, result.returncode, result.stdout, result.stderr)


def git_grep(estate: Estate, ere: str, *paths: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "grep", "-E", "-e", ere, "origin/main", "--", *paths],
                          cwd=str(estate.wip), env=estate.env, capture_output=True, text=True,
                          check=False)


def image_grep(images: dict, ere: str, prefix: str = "origin/main") -> str:
    """What `register-grep` prints on primary (lane 5's answer 14): each
    log's matching lines, `origin/main:<path>:<line>`, in `.paths`' bytewise
    order, each path once."""
    pattern = re.compile(ere)
    out = []
    for path in sorted(p for p in images if re.match(r"^lanes/log/[^/]+\.md$", p)):
        for line in _lines(images[path].decode("utf-8")):
            if pattern.search(line):
                out.append(f"{prefix}:{path}:{line}")
    return "".join(f"{line}\n" for line in out)


@pytest.mark.parametrize("case", ["files", "index", "primary", "no-match", "failed-read",
                                  "other-path", "log-readme", "log-dir-skips-readme", "case-pair"])
def test_register_grep_prints_what_git_grep_prints_and_1_with_no_match(estate, primary, case):
    """`register-grep [-h] -E <ERE> -- <path>…` (lane 4's T401; GB section
    4.3): what `git grep` prints today on `origin/<branch>` in files and
    `mode=index`, and the same shape from the images on primary; 1 with no
    match; 69 on a failed read; 2 for a path outside the set; `-- lanes/log`
    greps the lane logs alone, never `lanes/log/README.md`; and on primary a
    case pair of logs is 69 with nothing on stdout, while the same store
    answers `register-text` (Q-W11-4 (A); R2f4-S14). In `[no-match]`,
    `[other-path]`, `[log-readme]` and `[log-dir-skips-readme]` the primary
    run also asks the store through the door, since the files answer the same
    1, 2 or lines and so prove nothing about primary (T217g)."""
    runs = mode_runs(estate, primary)
    ere = "^(STARTED|NOTED) "
    if case in ("files", "index"):
        result = runs[case]("register-grep", "-E", ere, "--", "lanes/log")
        expect = git_grep(estate, ere, *LOG_PATHSPEC)
        assert (result.returncode, result.stdout) == (0, expect.stdout), \
            (case, result.returncode, result.stdout, expect.stdout, result.stderr)
    elif case == "primary":
        result = runs["primary"]("register-grep", "-E", ere, "--", "lanes/log")
        assert result.returncode == 0, (result.returncode, result.stderr)
        assert result.stdout == image_grep(primary.door.register, ere), result.stdout
        assert f"lanes/log/{STORE_ONLY_LANE}.md:" in result.stdout, result.stdout
    elif case == "no-match":
        for mode, run in runs.items():
            asked = store_asks(primary)
            result = run("register-grep", "-E", "^NO SUCH LINE$", "--", "lanes/log")
            assert (result.returncode, result.stdout) == (1, ""), (mode, result.returncode,
                                                                  result.stderr)
            if mode == "primary":
                assert store_asks(primary) > asked, \
                    (case, mode, "the primary 1 never came through the register: the door asked "
                     "the store nothing, so it grepped git, which FR-034 forbids",
                     primary.door.calls())
    elif case == "failed-read":
        primary.door.unreachable()
        result = runs["primary"]("register-grep", "-E", ere, "--", "lanes/log")
        assert (result.returncode, result.stdout) == (69, ""), (result.returncode, result.stderr)
        # `register-grep` never reads `LANES_REPO` (that is `register-text`'s
        # knob, above): it greps `origin/<branch>` in `$LANES_WS_ROOT`, the
        # workspace root `LANES_WORKSPACE_ROOT` or `workspace.yaml`'s `path:`
        # names, the same root `lane-worktrees` greps (T401; lane 4's INV401).
        # So the missing checkout goes in the variable the verb reads.
        gone = estate.edit("register-grep", "-E", ere, "--", "lanes/log",
                           env={"LANES_WORKSPACE_ROOT": str(estate.root / "no-such-checkout")})
        assert (gone.returncode, gone.stdout) == (69, ""), (gone.returncode, gone.stderr)
    elif case in OUTSIDE_PATHS:
        for mode, run in runs.items():
            asked = store_asks(primary)
            control = run("register-grep", "-E", ere, "--", "lanes/log")
            assert control.returncode == 0, (case, mode, "the verb does not answer",
                                             control.returncode, control.stderr)
            if mode == "primary":
                assert store_asks(primary) > asked, \
                    (case, mode, "the primary answer never came through the register: the door "
                     "asked the store nothing, so it grepped git, which FR-034 forbids",
                     primary.door.calls())
            result = run("register-grep", "-E", ere, "--", OUTSIDE_PATHS[case])
            assert (result.returncode, result.stdout) == (2, ""), \
                (case, mode, result.returncode, result.stdout, result.stderr)
    elif case == "log-dir-skips-readme":
        readme_ere = "^(# the object logs|STARTED )"
        for mode, run in runs.items():
            asked = store_asks(primary)
            result = run("register-grep", "-E", readme_ere, "--", "lanes/log")
            assert result.returncode == 0, (mode, result.returncode, result.stderr)
            if mode == "primary":
                assert store_asks(primary) > asked, \
                    (case, mode, "the primary answer never came through the register: the door "
                     "asked the store nothing, so it grepped git, which FR-034 forbids",
                     primary.door.calls())
            assert "README.md" not in result.stdout, (mode, result.stdout)
            assert "lanes/log/repoA-2.md:" in result.stdout, (mode, result.stdout)
    else:
        primary.door.commit({"lanes/log/REPOA-2.md": "NOTED — the other half of a case pair\n"})
        result = runs["primary"]("register-grep", "-E", ere, "--", "lanes/log")
        assert (result.returncode, result.stdout) == (69, ""), (result.returncode, result.stdout,
                                                               result.stderr)
        text = runs["primary"]("register-text", "lanes/LANES.md")
        assert text.returncode == 0 and STORE_ONLY_ROW in text.stdout, \
            ("the store did not answer: the 69 may be a failed prefetch", text.returncode,
             text.stderr)


# ------------------------------------------------- lane 4's key() trim (T426)
#: THE CASES (T259; R31; the design's S3, "The normalized `archive:` key"; the
#: test plan's AT-LR010, "a long digit run"). `retired-identity <lane>` prints
#: each archived spelling that `RETIRED_ROWS_AWK` matches, and exits 0; it
#: matches by the lane's name in any case, or by `key()`; where none matches
#: it exits 8. `key()` is the name before its last `-`, lower-cased, a `-`, and
#: the digits after it (less one trailing letter) without their leading zeros.
#: v2.5's SQL trims those zeros as text, a lone `0` kept. The awk's `p + 0` is
#: a double, so two runs that differ only past the 15th digit key alike, and
#: it matches a row that no SQL key names (the design: `foo-9007199254740993`
#: keys to `foo-9007199254740992` under mawk 1.3.4, and a run of 30 prints with
#: an exponent). Lane 4's T426 trims as text on primary, and keeps `(p + 0)`
#: in files mode (spec:59; review m7), so the two columns differ on the last
#: three rows alone, and those three in files mode are the answers today.
#:
#: Each row is (case, the archived spelling, the lane asked, whether files mode
#: answers it, whether primary does). Each case has a repository name of its
#: own, so that one archive holds them all and no row answers another's
#: question. The first five are the controls: both modes answer them, so a
#: no-answer further down is the key's and not a verb that answers nothing.
KEY_ROWS = (
    ("leading-zeros", "keya-0007", "keya-7", True, True),
    ("lone-zero", "keyb-000", "keyb-0", True, True),
    ("trailing-letter", "keyc-0012b", "keyc-12", True, True),
    ("padded-16-digits", "keyd-0009007199254740993", "keyd-9007199254740993", True, True),
    ("padded-30-digits", "keye-000123456789012345678901234567890",
     "keye-123456789012345678901234567890", True, True),
    ("16-digits-differ-in-the-last", "keyf-9007199254740992", "keyf-9007199254740993",
     True, False),
    ("16-digits-differ-the-other-way", "keyg-9007199254740993", "keyg-9007199254740992",
     True, False),
    ("30-digits-differ-in-the-last", "keyh-123456789012345678901234567890",
     "keyh-123456789012345678901234567891", True, False),
)

#: An archived row as the register writes it (`archive-rows`): the lane in
#: backticks in its first cell. The state cell's separator is built, not typed.
KEY_ARCHIVE_ROW = ("| `{lane}` | harness `{uuid}` | Eagle / test / brett | 2026-10-01T00:00Z "
                   "| none | handoffs/{lane}.md | RETIRED " + chr(0xB7) + " 2026-09-02T00:00:00Z "
                   + chr(0xB7) + " retired |")


def sql_key(name: str) -> str:
    """v2.5's key of an archived name, by the design's S3 rule: the name before
    its last `-`, lower-cased, `-`, and the digits after it, less one trailing
    letter, trimmed of leading zeros as text (`0` stays `0`); `""` where there
    is no key (no `-`, or what follows is not all digits)."""
    found = re.match(r"^(.*)-([0-9]+)[A-Za-z]?$", name)
    if not found:
        return ""
    return found.group(1).lower() + "-" + (found.group(2).lstrip("0") or "0")


def seed_key_archive(estate: Estate) -> None:
    """Retire each `KEY_ROWS` spelling into the estate's archive, committed and
    pushed, so that files mode reads it from `origin/main` and the primary
    store, built from this checkout's render set afterwards, holds it too."""
    archive = estate.wip / "lanes" / "archive" / "LANES-retired.md"
    rows = [KEY_ARCHIVE_ROW.format(lane=spelling, uuid=f"eeeeeeee-0002-4000-8000-{n:012d}")
            for n, (_, spelling, _, _, _) in enumerate(KEY_ROWS, 1)]
    archive.write_text(archive.read_text(encoding="utf-8").rstrip("\n") + "\n"
                       + "\n".join(rows) + "\n", encoding="utf-8")
    estate._git("add", "-A")
    estate._git("commit", "-q", "-m", "retire the spellings the key() case asks about")
    estate._git("push", "-q", "origin", "main")


@pytest.mark.parametrize("mode", ["primary", "files"])
def test_retired_rows_key_trims_leading_zeros_as_text_on_primary(estate, mode):
    """`RETIRED_ROWS_AWK`'s `key()` trims a number's leading zeros as text on
    primary (lane 4's T426; R31; GB section 4.3), so `retired-identity` reads
    the archive by the keys v2.5 gives it; files mode keeps `(p + 0)`, byte
    for byte as today (spec:59). The archive holds the `KEY_ROWS` spellings,
    and each is asked about by its lane.
    `[primary]`: a run of 16 digits or more that differs from an archived one
    in its last digit is NOT retired (exit 8, nothing on stdout), and a run
    padded with zeros still is (exit 0, the archived spelling). The expected
    answers are first held to v2.5's own key (`sql_key`), so that the table is
    the contract's and not a guess. It fails until T426 trims on primary, and
    until `reg_open` sets `retired-identity`'s mode as a reader (T504).
    `[files]`: the same questions, answered as `(p + 0)` answers them today,
    the three near-duplicates included: they are retired, by the double's
    rounding. It passes at the base and must pass after T426."""
    seed_key_archive(estate)
    primary = Primary(estate) if mode == "primary" else None
    run = primary.edit if primary else estate.edit
    if primary:
        for case, spelling, asked, _, answers in KEY_ROWS:
            sql = spelling.lower() == asked.lower() or (
                sql_key(asked) != "" and sql_key(spelling) == sql_key(asked))
            assert answers == sql, (case, "the table disagrees with v2.5's key", spelling, asked)
    for case, spelling, asked, in_files, on_primary in KEY_ROWS:
        answers = on_primary if primary else in_files
        result = run("retired-identity", asked)
        where = (mode, case, "exit", result.returncode, "calls at the door:",
                 len(primary.door.calls()) if primary else "-", spelling, asked,
                 result.stdout, result.stderr)
        if answers:
            assert (result.returncode, result.stdout) == (0, spelling + "\n"), where
        else:
            assert (result.returncode, result.stdout) == (8, ""), where
    if primary:
        assert primary.door.calls(), ("the primary run never reached the door, so it read as "
                                      "files mode does", primary.door.calls())
