# SPDX-License-Identifier: Apache-2.0
"""Feature 007's AT-F7 and AT-F11: the guard under a declared outage and over
a stale mirror (L2-N3; T215; FR-037, FR-056, FR-059)
(opensoft/openRepoTools#165).

The test plan's twelve names, byte for byte. Its case ids: AT-F7's
`[floor|clamp|room]` and AT-F11's `[depth-200|depth-250]`; M11 is
`test_the_register_seq_lookup_is_timed_bounded_beside_the_unbounded_and_grep_forms`.

THE RULE TESTED IS TODAY'S (open point 31; R-B4S): with the database
unreachable the guard refuses 2, and it answers from the mirror only under a
declaration. Those refusals are the prefetch's, form 2's (contract section
3.6): `register read --for guard --prefetch --cache <file> --pid <pid> --repo
<dir> [--lane=<window>]`. The guard's second read, form 4, is noted and never
refused, and no case here reaches it.

THE DECLARATION is always written by lane 1's `lanes-index outage declare`
(T121; L1-A18), in D20's form, `--until <UTC> --why <words>`, with
`--mirror-seq <m>` where the test names `m` (lane 1, #165 comment
6754680212), never by hand. So the declaration side of every case is green
once T121 is in, and the guard side waits for lane 5's T507 (L5-A3, L5-A5).

THE GUARD is driven as T220 drives it (`test_sql_register_bounds.py`):
`bash lanes-edit.sh guard` from a copy of `lanes-edit.sh` beside T203's
flipped `lanes-index` (`flipped_copy`), the hook's JSON on stdin, a stand-in
`tmux` whose window is the lane, and `LANES_INDEX_CONFIG` naming a
`mode=primary` configuration. Two things are this module's own:

- the lane's checkout is under `$HOME/projects`, so that the guard's scope
  test (`under_projects_root`, clause (e)) lets the prompt through to the
  register read; outside it the guard returns 0 before any read;
- "exits as the mirror's answer gives" is read as: exits as the same guard,
  on the same hook input and the same checkout, exits in files mode
  (`mode=index`, the reference run, with `LANES_NO_FETCH=1` so that it moves
  no ref). The mirror's answer is then today's parser's, and no session
  record has to be forged here.

The hook's JSON is compact, as the harness sends it, since the guard's `jstr`
reads `"cwd":"<dir>"` with no blank after the colon. No live session record
is written: today's guard refuses 2 at its session-record check, clause (d),
before any register read. So a guard case reaches T507's prefetch only where
T507 reads before that check; lane 5 is to confirm where it reads.

THE STAND-INS, each first on `PATH`:

- T203's register fake `psql`, behind this module's `--version` wrapper
  (`VERSION_WRAPPER`), as T220 carries one until T203b gives the fake that
  answer. The wrapper also logs each other call's start, on the wall clock,
  to `psql-starts.log` beside it. The fake is taught to exit 2, as a stopped
  database does (`STOPPED`); the service's socket is absent, since phase 1
  has no service;
- a `git` wrapper (`GIT_WRAPPER`) that logs each call's wall-clock start and
  argv. A MIRROR CALL is a `git` call with an argument naming
  `origin/<branch>`: the guard's mirror path reads `origin/$LANES_BRANCH` as
  last fetched (contract section 3.6, "Form C"). This is the module's reading
  of "the `git` wrapper's log shows no mirror call";
- for the real-engine case, a timing wrapper in front of the real `psql`
  (`TIMING_PSQL`), whose watcher logs the call's end even where the client's
  timer kills it.

`Register-Seq` histories are written by `git fast-import` into a bare origin:
a render commit carries the trailer `Register-Seq: <k>`, a handoff commit
none.

Every case fails until L5-A3, L5-A5 and L1-A18 land, and the rollback's head
until lane 3's T304; `test_the_guard_refuses_a_ref_behind_a_rollbacks_head`
and the silent database are real-engine cases on `tests/pgcluster.py`'s `pg`.
"""

from __future__ import annotations

import errno
import json
import os
import re
import select
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

INDEXER = REPO / "lanes-index"
#: The lane, and the tmux window it runs in.
WINDOW = "repoA-2"
#: `register_label=`: the database the declaration names.
LABEL = "register-test"
#: D20's form on Brett's word (Y:3073): an expiry far ahead, and his words.
UNTIL = "2999-01-01T00:00:00Z"
WHY = "the register database is down for its host move"
#: SVC-8's shares under a declaration (AT-F7, "Ruling"): the direct read's
#: cap, the mirror path's start line, the floor, and the guard's budget.
CAP_DECLARED, CAP, START_LINE, FLOOR, BUDGET = 3.65, 3.75, 3.75, 0.5, 4.5
#: The harness's `GUARD_TIMEOUT`: the hook runs under its 5 s kill timer.
GUARD_TIMEOUT = 5
#: Form C's page (SVC-12; AT-F11, "The bounded lookup").
PAGE = 200
#: The register's schema on the session cluster (T205).
SCHEMA = "lanes_register"
#: A stopped database: every call refused at the connect.
STOPPED = [{"exit": 2, "stderr": "psql: error: connection to server at \"127.0.0.1\", port "
                                 "55432 failed: Connection refused\n"}]

VERSION_WRAPPER = r'''#!/usr/bin/env python3
# T215's `psql --version` wrapper, as T220's: the version T106 asks for once
# per process, logged apart; each other call's start (wall clock) logged to
# psql-starts.log; then T203's register fake.
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
if sys.argv[1:] == ["--version"]:
    with open(os.path.join(here, "psql-version.log"), "a", encoding="utf-8") as handle:
        handle.write("--version\n")
    sys.stdout.write("psql (PostgreSQL) 16.4\n")
    sys.exit(0)
with open(os.path.join(here, "psql-starts.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"start": time.time(), "argv": sys.argv[1:]}) + "\n")
fake = os.path.join(here, "register-fake-psql")
os.execv(fake, [fake] + sys.argv[1:])
'''

#: The `git` wrapper: one line per call, its wall-clock start and its argv,
#: each field ended by US (0x1f); then the real `git`.
GIT_WRAPPER = r'''#!/bin/sh
{ date +%s.%N | tr -d '\n'; printf '\037'; for a in "$@"; do printf '%s\037' "$a"; done; printf '\n'; } >> "$T215_GIT_LOG"
exec "$T215_REAL_GIT" "$@"
'''

#: FAKE `tmux`, as T220's: the window is the lane.
FAKE_TMUX = """#!/bin/sh
case "$*" in *display-message*) printf '%s\\n' "${T215_WINDOW:-repoA-2}" ;; esac
exit 0
"""

#: THE TIMING WRAPPER for the real-engine case: logs the call's start, then a
#: watcher in a session of its own logs the call's end once the call's
#: process is gone, whether it exited or the client's timer killed it.
TIMING_PSQL = r'''#!/usr/bin/env python3
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
real = os.environ["T215_REAL_PSQL"]
if sys.argv[1:] == ["--version"]:
    os.execv(real, [real] + sys.argv[1:])
log = os.path.join(here, "psql-timing.log")
start = time.time()
me = os.getpid()
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"call": me, "start": start}) + "\n")
if os.fork() == 0:
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    while os.getppid() == me:
        time.sleep(0.005)
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"call": me, "end": time.time()}) + "\n")
    os._exit(0)
os.execv(real, [real] + sys.argv[1:])
'''


def _script(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _private(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _render(seq: int) -> str:
    return f"render the register at seq {seq}\n\nRegister-Seq: {seq}\n"


def _handoff(i: int) -> str:
    return f"handoff {i}\n"


def _fast_import(bare: Path, messages: list, env: dict) -> None:
    """Append `messages`, one commit each, first-parent, to `bare`'s `main`
    by `git fast-import`. The first commit of an empty repository writes the
    register; every later one keeps its parent's tree."""
    git = env["T215_REAL_GIT"]
    has_main = subprocess.run([git, "--git-dir", str(bare), "rev-parse", "-q", "--verify",
                               "refs/heads/main"], capture_output=True, env=env).returncode == 0
    out = []
    register = b"# LANES.md\n"
    for i, message in enumerate(messages, 1):
        data = message.encode("utf-8")
        out.append(b"commit refs/heads/main\n")
        out.append(b"mark :%d\n" % i)
        out.append(b"committer t <t@example.invalid> %d +0000\n" % (1700000000 + i))
        out.append(b"data %d\n%s\n" % (len(data), data))
        if i > 1:
            out.append(b"from :%d\n" % (i - 1))
        elif has_main:
            out.append(b"from refs/heads/main^0\n")
        else:
            out.append(b"M 100644 inline lanes/LANES.md\ndata %d\n%s\n" % (len(register),
                                                                          register))
            out.append(b"M 100644 inline lanes/log/README.md\ndata 7\nlogs.\n\n")
    out.append(b"done\n")
    subprocess.run([git, "--git-dir", str(bare), "fast-import", "--quiet", "--done"],
                   input=b"".join(out), check=True, env=env, capture_output=True)


def _subcommand(args: list) -> str:
    """git's subcommand in `args`, past `-C <dir>`, `-c <k=v>` and the
    global flags."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a
    return ""


def _bounded(args: list) -> bool:
    """`args` is form C: `log --first-parent` limited to 200, with no
    `--grep`."""
    joined = " ".join(args)
    limited = (re.search(r"(^| )-n ?200( |$)", joined) is not None
               or "--max-count=200" in args or "-200" in args)
    return limited and "--first-parent" in args and not any(a.startswith("--grep")
                                                           for a in args)


class Estate:
    """One test's estate: a bare origin, the lane's register checkout under
    `$HOME/projects`, the copies of `lanes-edit.sh` and the flipped
    `lanes-index`, the stand-ins, and a `mode=primary` configuration."""

    def __init__(self, root: Path, origin_messages: list):
        from sql_register_helpers import REGISTER_FAKE_PSQL, flipped_copy
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        try:
            self.copy = flipped_copy(INDEXER, root / "tool", True)
        except ValueError as exc:
            raise AssertionError(f"lanes-index cannot be flipped to its git half ({exc}): "
                                 f"lane 1's RENDER_GIT_HALF (T105) has not landed, and "
                                 f"mode=primary is refused without it") from exc
        for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
            if (REPO / name).exists():
                shutil.copy2(REPO / name, root / "tool" / name)
        self.bin, self.fakebin = root / "bin", root / "fakebin"
        _script(self.bin / "tmux", FAKE_TMUX)
        _script(self.bin / "git", GIT_WRAPPER)
        _script(self.fakebin / "register-fake-psql", REGISTER_FAKE_PSQL)
        _script(self.fakebin / "psql", VERSION_WRAPPER)
        self.git_log = root / "git.log"
        self.psql_log = root / "psql.log"
        self.starts = self.fakebin / "psql-starts.log"
        self.answers = root / "psql-answers.json"
        self.answers.write_text(json.dumps(STOPPED), encoding="utf-8")
        home = root / "home"
        self.origin = root / "origin.git"
        self.wip = home / "projects" / "wip"
        self.wip.parent.mkdir(parents=True)
        (root / "t").mkdir()
        self.cache = root / "cache" / "se"
        self.cache.parent.mkdir()
        self.passfile = _private(root / "conf" / "pgpass")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("LANES_", "CLAUDE_", "TMUX", "PG", "FAKE_PSQL", "T215_"))}
        env.update(HOME=str(home), XDG_STATE_HOME=str(root / "state"),
                   XDG_CONFIG_HOME=str(root / "config"), TMPDIR=str(root / "t"),
                   LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", LANES_REPO=str(self.wip),
                   T215_REAL_GIT=shutil.which("git"), T215_GIT_LOG=str(self.git_log),
                   FAKE_PSQL_LOG=str(self.psql_log), FAKE_PSQL_ANSWERS=str(self.answers),
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                   PATH=os.pathsep.join([str(self.bin), str(self.fakebin),
                                         os.environ.get("PATH", os.defpath)]))
        self.env = env
        git = env["T215_REAL_GIT"]
        subprocess.run([git, "init", "-q", "--bare", "-b", "main", str(self.origin)],
                       check=True, env=env)
        _fast_import(self.origin, origin_messages, env)
        subprocess.run([git, "clone", "-q", str(self.origin), str(self.wip)], check=True,
                       env=env, capture_output=True)
        # THE WORKSPACE, as `test_lanes_index.py` names it (Amendment 9(a)):
        # `lanes-edit.sh workspace-root` answers with `path:`, the checkout
        # `outage declare` fetches in (lane 1's reading 1).
        (home / ".agents").mkdir()
        (home / ".agents" / "workspace.yaml").write_text(
            f"repository: {self.origin}\npath: {self.wip}\n", encoding="utf-8")

    # -------------------------------------------------------------- the estate
    def grow(self, messages: list) -> None:
        """Origin gains `messages`; the checkout's `origin/main` stays as
        last fetched."""
        _fast_import(self.origin, messages, self.env)

    def fetch(self) -> None:
        subprocess.run([self.env["T215_REAL_GIT"], "-C", str(self.wip), "fetch", "-q", "origin"],
                       check=True, env=self.env, capture_output=True)

    def tip(self) -> str:
        return subprocess.run([self.env["T215_REAL_GIT"], "-C", str(self.wip), "rev-parse",
                               "refs/remotes/origin/main"], check=True, env=self.env,
                              capture_output=True, text=True).stdout.strip()

    def config(self, mode: str = "primary", url: str | None = None,
               name: str = "conf") -> Path:
        """A configuration with both URLs on loopback (the fake's host rule),
        the label the declaration names, and `mode`."""
        url = url or "postgresql://t215_login@127.0.0.1:55432/register_db"
        return _private(self.root / name / "lanes-index.conf", "\n".join([
            f"mode={mode}", f"register_url={url}", f"register_passfile={self.passfile}",
            f"reader_url={url}", f"reader_passfile={self.passfile}",
            f"register_label={LABEL}", f"register_schema={SCHEMA}", ""]))

    # ------------------------------------------------------------ the declaration
    def declare(self, config: Path, *, mirror_seq: int | None = None,
                rollback: bool = False) -> subprocess.CompletedProcess:
        """`lanes-index outage declare` (T121), under the stopped fake, so the
        probe's database does not answer from this host."""
        argv = [sys.executable, str(self.copy), "outage", "declare"]
        if rollback:
            argv += ["--rollback"]
        else:
            argv += ["--until", UNTIL, "--why", WHY]
        if mirror_seq is not None:
            argv += ["--mirror-seq", str(mirror_seq)]
        env = dict(self.env, LANES_INDEX_CONFIG=str(config), LANES_LANE=WINDOW,
                   PATH=os.pathsep.join([str(self.fakebin), self.env["PATH"]]))
        return subprocess.run(argv, capture_output=True, text=True, env=env,
                              cwd=str(self.wip), timeout=120, stdin=subprocess.DEVNULL)

    def declared(self, config: Path, *, mirror_seq: int) -> dict:
        """Declare on Brett's word at `mirror_seq`, assert it was written, and
        return its fields."""
        proc = self.declare(config, mirror_seq=mirror_seq)
        path = config.parent / "register-outage"
        assert proc.returncode == 0 and path.exists(), (
            f"`outage declare --until --why --mirror-seq {mirror_seq}` (T121) exited "
            f"{proc.returncode} and wrote {'a' if path.exists() else 'no'} declaration: "
            f"{proc.stderr.strip()[-400:]}")
        return dict(line.split("=", 1) for line in
                    path.read_text(encoding="utf-8").splitlines() if "=" in line)

    # ------------------------------------------------------------------ the guard
    def guard_env(self, config: Path, **extra) -> dict:
        env = dict(self.env, LANES_INDEX_CONFIG=str(config), LANES_LANE=WINDOW,
                   TMUX="/tmp/t215,1,0", TMUX_PANE="%1", T215_WINDOW=WINDOW)
        env.update(extra)
        return env

    def hook_input(self) -> str:
        """The hook's JSON, compact as the harness sends it: the guard's
        `jstr` reads `"<key>":"<value>"` with no blank after the colon."""
        return json.dumps({"hook_event_name": "UserPromptSubmit",
                           "session_id": str(uuid.uuid4()), "cwd": str(self.wip),
                           "prompt": "hello"}, separators=(",", ":"))

    def guard(self, config: Path, **extra) -> dict:
        """The hook, `lanes-edit.sh guard`, under its 5 s kill timer, in a
        process group of its own. Returns its exit (None where killed), its
        output, `t0` (wall clock, at its start) and its elapsed seconds."""
        argv = ["bash", str(self.root / "tool" / "lanes-edit.sh"), "guard"]
        t0 = time.time()
        start = time.monotonic()
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, cwd=str(self.wip),
                                env=self.guard_env(config, **extra), start_new_session=True)
        killed = False
        try:
            out, err = proc.communicate(self.hook_input(), timeout=GUARD_TIMEOUT)
        except subprocess.TimeoutExpired:
            killed = True
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
        return {"exit": None if killed else proc.returncode, "killed": killed,
                "out": out + err, "t0": t0, "elapsed": time.monotonic() - start}

    def reference(self) -> int:
        """The same guard on the same checkout in files mode: the mirror's
        answer, as today's parser gives it. It fetches nothing."""
        result = self.guard(self.config(mode="index", name="conf-index"), LANES_NO_FETCH="1")
        assert not result["killed"], "the files-mode guard was killed at 5 s"
        return result["exit"]

    # --------------------------------------------------------------------- logs
    def psql_starts(self) -> list:
        if not self.starts.exists():
            return []
        return [json.loads(line) for line in self.starts.read_text(encoding="utf-8").splitlines()]

    def git_calls(self) -> list:
        if not self.git_log.exists():
            return []
        calls = []
        for line in self.git_log.read_text(encoding="utf-8", errors="replace").splitlines():
            fields = line.split("\x1f")
            calls.append({"t": float(fields[0]), "args": [f for f in fields[1:] if f != ""]})
        return calls

    def mirror_calls(self) -> list:
        return [c for c in self.git_calls() if any("origin/main" in a for a in c["args"])]

    def log_calls(self) -> list:
        return [c for c in self.git_calls() if _subcommand(c["args"]) == "log"]

    def reset_logs(self) -> None:
        for path in (self.git_log, self.psql_log, self.starts):
            if path.exists():
                path.unlink()

    # -------------------------------------------------------- the guard's client
    def client(self, config: Path, pid: int) -> tuple:
        """Form 2, the guard's prefetch, run as the guard's client with the
        pid of a stand-in for the hook. Returns (the process, its end on the
        wall clock)."""
        argv = [sys.executable, str(self.copy), "register", "read", "--for", "guard",
                "--prefetch", "--cache", str(self.cache), "--pid", str(pid),
                "--repo", str(self.wip), f"--lane={WINDOW}"]
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(self.wip),
                              env=self.guard_env(config), timeout=60,
                              stdin=subprocess.DEVNULL)
        return proc, time.time()


def _label(fields: dict) -> str:
    """The declared line the guard prints in place of the cause (D20;
    contract section 3.6, `.outage`'s `label=`)."""
    return f"(declared outage {fields['utc']}: {fields['why']})"


def _behind(seen: int, declared: int) -> str:
    """Lane 5's SVC-12 text (Y:4472-4474), up to its semicolon."""
    return f"the mirror here is at seq {seen}, behind the declared outage's seq {declared}"


def _record(what: str, measured: float, bound: float, rule: str) -> None:
    print(f"T215 {what}: {measured:.3f} s against the design's {bound:g} s ({rule}); "
          f"margin {bound - measured:+.3f} s")


def _answers_from_the_mirror(estate: Estate, result: dict, fields: dict, reference: int,
                             tip: str) -> None:
    assert not result["killed"], "the hook was killed at 5 s, and the prompt passed"
    assert f"read: mirror at {tip[:12]}" in result["out"], (
        f"the guard does not say it read the mirror at {tip[:12]}: {result['out'][-600:]}")
    assert _label(fields) in result["out"], (
        f"the guard does not print the declared line {_label(fields)!r}: "
        f"{result['out'][-600:]}")
    assert result["exit"] == reference, (
        f"the guard exited {result['exit']}, where the mirror's answer is {reference}")


# ==================================================================== AT-F7

def test_a_declared_outage_lets_the_guard_read_the_mirror_with_service_and_database_down(
        tmp_path):
    """AT-F7: with the outage declared, the service's socket absent and the
    database stopped, the guard's direct read fails, and then it answers
    from the mirror, says so with the declared line, and exits as the
    mirror's answer gives, never killed. The direct read comes first."""
    estate = Estate(tmp_path, [_render(1), _render(2), _render(3)])
    config = estate.config()
    fields = estate.declared(config, mirror_seq=3)
    estate.reset_logs()
    result = estate.guard(config)
    starts, mirror = estate.psql_starts(), estate.mirror_calls()
    assert starts, "the guard made no direct read before the mirror: the fake psql has no call"
    assert mirror, "the guard made no mirror call"
    assert mirror[0]["t"] >= starts[0]["start"], "the mirror was read before the direct read"
    _answers_from_the_mirror(estate, result, fields, estate.reference(), estate.tip())


def test_with_no_declaration_the_guard_exits_2_with_service_and_database_down(tmp_path):
    """AT-F7: with nothing declared, the service's socket absent and the
    database stopped, the guard tries its direct read, exits 2, and never
    reads the mirror."""
    estate = Estate(tmp_path, [_render(1), _render(2), _render(3)])
    config = estate.config()
    result = estate.guard(config)
    assert not result["killed"], "the hook was killed at 5 s, and the prompt passed"
    assert estate.psql_starts(), "the guard made no direct read: the fake psql has no call"
    assert result["exit"] == 2, f"the guard exited {result['exit']}: {result['out'][-600:]}"
    assert estate.mirror_calls() == [], f"the guard read the mirror: {estate.mirror_calls()}"
    assert "read: mirror" not in result["out"]


class StartupRelay:
    """D9's F2, as T220 has it: a relay on loopback, port 0, to the cluster's
    Unix socket, that forwards until the server's first ReadyForQuery and then
    goes silent, holding both ends open."""

    READY = re.compile(rb"Z\x00\x00\x00\x05[ITE]")

    def __init__(self, unix_path: str):
        self.unix_path, self.held, self.done = unix_path, [], False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        self.sock.settimeout(0.2)
        while not self.done:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            upstream.connect(self.unix_path)
            self.held += [conn, upstream]
            threading.Thread(target=self._pump, args=(conn, upstream), daemon=True).start()

    def _pump(self, client, server):
        seen, silent = b"", False
        while not self.done:
            ready, _, _ = select.select([client, server], [], [], 0.2)
            for end in ready:
                try:
                    data = end.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                if silent:
                    continue
                if end is server:
                    seen = (seen + data)[-64:]
                    client.sendall(data)
                    if self.READY.search(seen):
                        silent = True
                else:
                    server.sendall(data)

    def close(self):
        self.done = True
        for conn in self.held:
            conn.close()
        self.sock.close()


def test_under_a_declaration_a_silent_database_is_capped_and_the_mirror_answers_inside_the_budget(
        pg, tmp_path, request):
    """AT-F7, real engine: under the declaration, the direct read meets F2's
    silent host and is cut by its timer; the mirror path's first `git` call
    follows the read's end (rule 3); the cut, `T0 + 3.65 s`, and the start
    line, `T0 + 3.75 s`, are each asserted at twice their value (rule 2) and
    recorded with their margins; and the hook answers from the mirror in
    under 4.5 s, never killed (rule 1). `T0` is the hook's start."""
    estate = Estate(tmp_path, [_render(1), _render(2), _render(3)])
    fields = estate.declared(estate.config(), mirror_seq=3)
    login = f"t215_{uuid.uuid4().hex[:12]}"
    pg.psql(f"CREATE ROLE {login} LOGIN IN ROLE lanes_register_reader;")
    request.addfinalizer(lambda: pg.cluster.psql(f"DROP ROLE IF EXISTS {login};", check=False))
    timed = tmp_path / "timedbin"
    _script(timed / "psql", TIMING_PSQL)
    relay = StartupRelay(f"{pg.host}/.s.PGSQL.{pg.port}")
    try:
        config = estate.config(url=f"postgresql://{login}@127.0.0.1:{relay.port}/{pg.name}")
        estate.reset_logs()
        result = estate.guard(config, T215_REAL_PSQL=pg.psql_bin,
                              PATH=os.pathsep.join([str(estate.bin), str(timed),
                                                    os.environ.get("PATH", os.defpath)]))
    finally:
        relay.close()
    assert not result["killed"], "the hook was killed at 5 s, and the prompt passed"
    assert result["elapsed"] < BUDGET, f"the hook took {result['elapsed']:.2f} s"
    _record("hook end to end", result["elapsed"], BUDGET, "timing rule 1")
    timing = [json.loads(line) for line in
              (timed / "psql-timing.log").read_text(encoding="utf-8").splitlines()]
    starts = [t for t in timing if "start" in t]
    ends = {t["call"]: t["end"] for t in timing if "end" in t}
    assert starts, "the guard made no direct read"
    read = starts[0]
    assert read["call"] in ends, "the direct read never ended"
    cut = ends[read["call"]] - result["t0"]
    assert cut < 2 * CAP_DECLARED, f"the direct read ended {cut:.2f} s after T0"
    _record("the direct read's end after T0, its timer included", cut, CAP_DECLARED,
            "timing rule 2")
    mirror = estate.mirror_calls()
    assert mirror, "the guard made no mirror call"
    assert mirror[0]["t"] >= ends[read["call"]], "the mirror path started before the read ended"
    line = mirror[0]["t"] - result["t0"]
    assert line < 2 * START_LINE, f"the mirror path started {line:.2f} s after T0"
    _record("the mirror path's first git call after T0", line, START_LINE, "timing rule 2")
    _answers_from_the_mirror(estate, result, fields, estate.reference(), estate.tip())


def test_the_declaration_is_read_once_at_the_prefetch(tmp_path):
    """AT-F7: the shim holds the direct read on a FIFO; the test removes
    `register-outage`, then releases the read to fail; the guard still
    answers from the mirror, with the declared line. The shim hands its calls
    to the stopped fake, so no engine is needed."""
    from sql_register_helpers import PSQL_SHIM
    estate = Estate(tmp_path, [_render(1), _render(2), _render(3)])
    config = estate.config()
    fields = estate.declared(config, mirror_seq=3)
    reference = estate.reference()
    shimbin = tmp_path / "shimbin"
    _script(shimbin / "psql", PSQL_SHIM)
    fifo = tmp_path / "hold.fifo"
    os.mkfifo(fifo)
    (shimbin / "psql-shim.json").write_text(json.dumps({
        "psql": str(estate.fakebin / "psql"),
        "arms": [{"mode": "hold", "fifo": str(fifo), "match": "SELECT", "call": 1}]}),
        encoding="utf-8")
    estate.reset_logs()
    env = estate.guard_env(config, PATH=os.pathsep.join([str(estate.bin), str(shimbin),
                                                         estate.env["PATH"]]))
    hook = tmp_path / "hook.json"
    hook.write_text(estate.hook_input(), encoding="utf-8")
    with open(hook, "rb") as stdin:
        proc = subprocess.Popen(["bash", str(tmp_path / "tool" / "lanes-edit.sh"), "guard"],
                                stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, cwd=str(estate.wip), env=env,
                                start_new_session=True)
    holder, deadline = None, time.monotonic() + GUARD_TIMEOUT
    try:
        while holder is None and time.monotonic() < deadline and proc.poll() is None:
            try:
                holder = os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK)
            except OSError as exc:
                if exc.errno != errno.ENXIO:
                    raise
                time.sleep(0.01)
        held = holder is not None
        if held:
            (config.parent / "register-outage").unlink()
            os.close(holder)
        try:
            out, err = proc.communicate(timeout=max(0.1, deadline - time.monotonic()))
            killed = False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
            killed = True
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    assert held, (f"the guard ended (exit {proc.returncode}) without a direct read for the "
                  f"shim to hold: {(out + err)[-600:]}")
    assert not (config.parent / "register-outage").exists()
    result = {"exit": None if killed else proc.returncode, "killed": killed, "out": out + err}
    _answers_from_the_mirror(estate, result, fields, reference, estate.tip())


def _stand_in(age: float) -> subprocess.Popen:
    """A stand-in for the hook, started `age` seconds before its return: the
    client reads `T0` from its pid (SVC-8, "How the client knows `T0`")."""
    standin = subprocess.Popen(["sleep", "120"], start_new_session=True,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    born = time.monotonic()
    while time.monotonic() - born < age:
        time.sleep(0.01)
    return standin


@pytest.mark.parametrize("case", ["floor", "clamp", "room"])
def test_under_a_declaration_a_direct_read_left_under_0_5_s_does_not_start(tmp_path, case):
    """AT-F7's floor (SVC-8; V2's NIT 7), on the guard's client, form 2, run
    with the pid of a stand-in started earlier, so that it reads an age of
    about 3.3 s (`floor`), 3.7 s (`clamp`) and 2.0 s (`room`). Under a
    declaration the read's cap is `T0 + 3.65 s`:
    - `floor` and `clamp`: less than 0.5 s is left before the cap, or none;
      the client starts no direct read and exits 2, too late to verify: the
      fake's log holds no read, and the `git` wrapper's no mirror call;
    - `room`: the read starts; the fake holds it past any timer, so the
      client's timer, at most 1.65 s, ends it, and the mirror answers:
      `.outage` says `open`, with the declared line. The read's life, from
      its start to the client's end, is asserted at twice 1.65 s (rule 2)
      and recorded."""
    age = {"floor": 3.3, "clamp": 3.7, "room": 2.0}[case]
    estate = Estate(tmp_path, [_render(1), _render(2), _render(3)])
    config = estate.config()
    fields = estate.declared(config, mirror_seq=3)
    if case == "room":
        estate.answers.write_text(json.dumps([{"sleep": 30, "exit": 2}]), encoding="utf-8")
    estate.reset_logs()
    standin = _stand_in(age)
    try:
        proc, end = estate.client(config, standin.pid)
    finally:
        standin.kill()
        standin.wait()
    starts = estate.psql_starts()
    if case in ("floor", "clamp"):
        assert proc.returncode == 2, f"{case}: the client exited {proc.returncode}: {proc.stderr}"
        assert "lanes-index: too late to verify" in proc.stderr, proc.stderr
        assert starts == [], f"{case}: a direct read started: {starts}"
        assert estate.mirror_calls() == [], f"{case}: the mirror was read"
        return
    assert len(starts) == 1, f"room: {len(starts)} direct reads started"
    assert proc.returncode == 69, f"room: the client exited {proc.returncode}: {proc.stderr}"
    life = end - starts[0]["start"]
    assert life < 2 * (CAP_DECLARED - age), f"room: the read lived {life:.2f} s"
    _record("room: the direct read's timer", life, CAP_DECLARED - age, "timing rule 2")
    outage = Path(str(estate.cache) + ".outage")
    assert outage.exists(), "room: no .outage was written"
    text = outage.read_text(encoding="utf-8")
    assert "verdict=open\n" in text and f"label={_label(fields)}\n" in text, text


def test_without_a_declaration_the_same_age_still_starts_the_direct_read(tmp_path):
    """AT-F7's control: at about 3.3 s and with nothing declared, the cap is
    `T0 + 3.75 s` and no floor applies, so the direct read starts; the
    stopped database fails it, and the client exits 69, writing no
    `.outage` and never too late."""
    estate = Estate(tmp_path, [_render(1), _render(2), _render(3)])
    config = estate.config()
    standin = _stand_in(3.3)
    try:
        proc, _ = estate.client(config, standin.pid)
    finally:
        standin.kill()
        standin.wait()
    assert len(estate.psql_starts()) == 1, f"the direct read did not start: {proc.stderr}"
    assert "too late to verify" not in proc.stderr
    assert proc.returncode == 69, f"the client exited {proc.returncode}: {proc.stderr}"
    assert not Path(str(estate.cache) + ".outage").exists()


# =================================================================== AT-F11

def test_the_guard_refuses_a_mirror_older_than_the_declared_seq(tmp_path):
    """AT-F11: declared at `m`, with the guard's checkout last fetched at
    `m - 1`, the guard exits 2 with lane 5's text and does not answer from
    the mirror; fetched at `m`, it answers from the mirror."""
    m = 4
    estate = Estate(tmp_path, [_render(k) for k in range(1, m)])
    estate.grow([_render(m)])
    config = estate.config()
    fields = estate.declared(config, mirror_seq=m)
    estate.reset_logs()
    result = estate.guard(config)
    assert not result["killed"], "the hook was killed at 5 s"
    assert result["exit"] == 2, f"at m - 1 the guard exited {result['exit']}"
    assert _behind(m - 1, m) in result["out"], result["out"][-600:]
    assert "read: mirror" not in result["out"]
    estate.fetch()
    result = estate.guard(config)
    _answers_from_the_mirror(estate, result, fields, estate.reference(), estate.tip())


@pytest.mark.parametrize("case", ["depth-200", "depth-250"])
def test_the_guard_refuses_2_when_no_commit_within_the_bound_carries_register_seq(
        tmp_path, case):
    """AT-F11's bounded lookup: `origin/main`'s newest render commit at depth
    200, the first outside the bound, under 200 handoff commits, and at
    depth 250: the guard exits 2, and never finds the deeper trailer. The
    `git` wrapper's log shows one `git log` call, `--first-parent` with
    `-n 200` and no `--grep`."""
    depth = int(case.split("-")[1])
    m = 5
    estate = Estate(tmp_path, [_render(k) for k in range(1, m + 1)] +
                    [_handoff(i) for i in range(depth)])
    config = estate.config()
    estate.declared(config, mirror_seq=m)
    estate.reset_logs()
    result = estate.guard(config)
    assert not result["killed"], "the hook was killed at 5 s"
    logs = estate.log_calls()
    assert len(logs) == 1, f"{case}: {len(logs)} git log calls: {[c['args'] for c in logs]}"
    assert _bounded(logs[0]["args"]), f"{case}: not form C: {logs[0]['args']}"
    assert result["exit"] == 2, f"{case}: the guard exited {result['exit']}"
    assert "read: mirror" not in result["out"], f"{case}: the guard found the deeper trailer"


def test_the_register_seq_lookup_finds_the_trailer_at_depths_0_and_199(tmp_path):
    """AT-F11: the render commit at depth 0, and at depth 199 under 199
    handoff commits: the guard's one bounded `git log` finds it, and the
    guard answers from the mirror."""
    m = 5
    for depth in (0, 199):
        estate = Estate(tmp_path / f"depth-{depth}", [_render(k) for k in range(1, m + 1)] +
                        [_handoff(i) for i in range(depth)])
        config = estate.config()
        fields = estate.declared(config, mirror_seq=m)
        estate.reset_logs()
        result = estate.guard(config)
        logs = estate.log_calls()
        assert len(logs) == 1 and _bounded(logs[0]["args"]), (
            f"depth {depth}: {[c['args'] for c in logs]}")
        _answers_from_the_mirror(estate, result, fields, estate.reference(), estate.tip())


def test_outage_declare_takes_mirror_seq_from_a_fetch_or_the_flag_and_refuses_with_neither(
        tmp_path):
    """AT-F11 (D20, SVC-12, ops section 2.5), lane 1's T121 on Brett's word,
    the database not answering from this host:
    - with no `--mirror-seq`, `mirror-seq=` is the newest `Register-Seq` on
      `origin/main` read after a fetch: origin is at 3, and the checkout was
      last fetched at 2;
    - with the fetch failing, `--mirror-seq 7` writes `mirror-seq=7`;
    - with the fetch failing and no `--mirror-seq`, it exits 2 and writes no
      file.
    The checkout fetched is the workspace's, as `lanes-edit.sh
    workspace-root` names it (lane 1's reading 1, #165 comment 6754714549)."""
    estate = Estate(tmp_path, [_render(1), _render(2)])
    estate.grow([_render(3)])
    fetched = estate.config(name="conf-fetch")
    proc = estate.declare(fetched)
    path = fetched.parent / "register-outage"
    assert proc.returncode == 0, f"from a fetch: exit {proc.returncode}: {proc.stderr}"
    text = path.read_text(encoding="utf-8")
    assert "mirror-seq=3\n" in text, f"from a fetch: {text}"
    assert "kind=word\n" in text and f"database={LABEL}\n" in text and f"until={UNTIL}\n" in text
    assert estate.psql_log.exists(), "the probe was not sent"
    subprocess.run([estate.env["T215_REAL_GIT"], "-C", str(estate.wip), "remote", "set-url",
                    "origin", str(tmp_path / "no-such-origin.git")], check=True,
                   env=estate.env)
    flagged = estate.config(name="conf-flag")
    proc = estate.declare(flagged, mirror_seq=7)
    assert proc.returncode == 0, f"by the flag: exit {proc.returncode}: {proc.stderr}"
    assert "mirror-seq=7\n" in (flagged.parent / "register-outage").read_text(encoding="utf-8")
    neither = estate.config(name="conf-neither")
    proc = estate.declare(neither)
    assert proc.returncode == 2, f"with neither: exit {proc.returncode}: {proc.stderr}"
    assert not (neither.parent / "register-outage").exists(), "with neither: a file was written"


def test_the_guard_refuses_a_ref_behind_a_rollbacks_head(pg, tmp_path, request):
    """AT-F11, a ref behind a rollback's head (A9: phase N, on lane 3's T304,
    against this test's own database). The database is brought to primary
    and rolled back by the real commands, `import --at <C>`, `cutover
    --import <C>` and `rollback`, so its switch is at `files` with a
    `rollback` entry at `set_seq`, and `rollback` writes its declaration,
    marked as from a rollback, with `mirror-seq=<k>`. With the guard's read
    finding the switch at `files`: last fetched at `k - 1`, the guard exits 2
    with lane 5's text for seqs `k - 1` and `k`, and does not answer from the
    mirror; at `k`, it answers from the mirror, `read: mirror`."""
    estate = Estate(tmp_path, [_render(1)])
    writer = f"t215_{uuid.uuid4().hex[:12]}"
    reader = f"t215_{uuid.uuid4().hex[:12]}"
    pg.psql(f"CREATE ROLE {writer} LOGIN IN ROLE lanes_register_writer;\n"
            f"CREATE ROLE {reader} LOGIN IN ROLE lanes_register_reader;")
    request.addfinalizer(lambda: pg.cluster.psql(f"DROP ROLE IF EXISTS {writer}, {reader};",
                                                 check=False))
    config = _private(tmp_path / "conf-pg" / "lanes-index.conf", "\n".join([
        "mode=primary", f"register_url={pg.url(writer)}", f"register_passfile={estate.passfile}",
        f"reader_url={pg.url(reader)}", f"reader_passfile={estate.passfile}",
        f"register_label={LABEL}", f"register_schema={SCHEMA}", ""]))
    env = dict(estate.env, LANES_INDEX_CONFIG=str(config), LANES_LANE=WINDOW,
               PATH=os.pathsep.join([str(estate.bin), str(Path(pg.psql_bin).parent),
                                     os.environ.get("PATH", os.defpath)]))
    c = estate.tip()
    for argv in (["import", "--at", c], ["cutover", "--import", c], ["rollback"]):
        proc = subprocess.run([sys.executable, str(estate.copy), *argv], capture_output=True,
                              text=True, env=env, cwd=str(estate.wip), timeout=300,
                              stdin=subprocess.DEVNULL)
        assert proc.returncode == 0, f"`{' '.join(argv)}` exited {proc.returncode}: {proc.stderr}"
    path = config.parent / "register-outage"
    assert path.exists(), "the rollback wrote no declaration"
    fields = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())
    assert fields.get("kind") == "rollback" and "until" not in fields, fields
    k = int(fields["mirror-seq"])
    # The guard's checkout, as last fetched: a history at k - 1, then at k.
    guard_estate = Estate(tmp_path / "guard", [_render(s) for s in range(1, k)])
    guard_estate.grow([_render(k)])
    estate_config = guard_estate.config(url=pg.url(reader))
    shutil.copy2(path, estate_config.parent / "register-outage")
    real = os.pathsep.join([str(guard_estate.bin), str(Path(pg.psql_bin).parent),
                            os.environ.get("PATH", os.defpath)])
    result = guard_estate.guard(estate_config, PATH=real)
    assert result["exit"] == 2, f"at k - 1 the guard exited {result['exit']}"
    assert _behind(k - 1, k) in result["out"], result["out"][-600:]
    assert "read: mirror" not in result["out"]
    guard_estate.fetch()
    result = guard_estate.guard(estate_config, PATH=real)
    assert not result["killed"]
    assert f"read: mirror at {guard_estate.tip()[:12]}" in result["out"], result["out"][-600:]


def test_the_register_seq_lookup_is_timed_bounded_beside_the_unbounded_and_grep_forms(tmp_path):
    """M11 (section 5.1), recorded and never asserted: on a checkout of
    30,000 first-parent commits made by `git fast-import`, with a
    commit-graph, the bounded lookup (form C) is timed beside the unbounded
    form and the `--grep` form, 30 warm runs and the first; the three find
    the same `Register-Seq`. The build time is recorded beside the figures.
    Then the bounded form is shown to be the one the guard runs."""
    total, newest_depth, m = 30000, 37, 9000
    started = time.monotonic()
    messages = []
    seq = 0
    for i in range(total):
        depth = total - 1 - i
        if depth == newest_depth or (depth > newest_depth and depth % 1000 == 0):
            seq = m if depth == newest_depth else seq + 1
            messages.append(_render(seq))
        else:
            messages.append(_handoff(i))
    estate = Estate(tmp_path, messages)
    git = estate.env["T215_REAL_GIT"]
    subprocess.run([git, "-C", str(estate.wip), "commit-graph", "write", "--reachable"],
                   check=True, env=estate.env, capture_output=True)
    built = time.monotonic() - started
    print(f"T215 M11: the checkout of {total} first-parent commits, with its commit-graph, "
          f"built in {built:.2f} s")
    fmt = "--format=%H%x00%(trailers:key=Register-Seq,valueonly)"
    forms = {
        "bounded": ["log", "--first-parent", "-n", str(PAGE), fmt, "origin/main", "--"],
        "unbounded": ["log", "--first-parent", fmt, "origin/main", "--"],
        "grep": ["log", "--first-parent", "-n", "1", "--grep=^Register-Seq: ", fmt,
                 "origin/main", "--"],
    }

    def first_seq(out: str) -> str:
        commit = ""
        for line in out.split("\n"):
            if "\x00" in line:
                commit, _, line = line.partition("\x00")
            if commit and line.strip():
                return line.strip()
        return ""

    for name, args in forms.items():
        times, found = [], set()
        for _ in range(31):
            t = time.monotonic()
            out = subprocess.run([git, "-C", str(estate.wip), *args], check=True, env=estate.env,
                                 capture_output=True, text=True).stdout
            times.append(time.monotonic() - t)
            found.add(first_seq(out))
        assert found == {str(m)}, f"M11 {name}: found {found}, not {m}"
        warm = sorted(times[1:])
        print(f"T215 M11 {name}: first {times[0] * 1000:.1f} ms; 30 warm: median "
              f"{statistics.median(warm) * 1000:.1f} ms, p95 {warm[28] * 1000:.1f} ms")
    config = estate.config()
    estate.declared(config, mirror_seq=m)
    estate.reset_logs()
    estate.guard(config)
    logs = estate.log_calls()
    assert len(logs) == 1 and _bounded(logs[0]["args"]), (
        f"the guard's lookup is not the bounded form: {[c['args'] for c in logs]}")
