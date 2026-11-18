# SPDX-License-Identifier: Apache-2.0
"""lane-collision-protocol Amendment 14 — THE DERIVED INDEX, and the eight tests
its adoption act 2 names (opensoft/openRepoTools#160).

The register's truth stays where it is: `lanes/LANES.md`, `lanes/log/*.md`,
`lanes/aliases.tsv` and `lanes/archive/` in the workspace repository, written
only by `lanes-edit.sh`. `lanes-index` keeps a DERIVED copy, written behind the
sources by itself alone, read only by tooling that decides nothing, and never a
gate. What these tests hold it to:

  * OFFLINE NO-READ — every act's answer is byte-identical with the index
    configured at a store nobody can reach;
  * POISONED INDEX — an index with WRONG rows changes no act's answer, which is
    the proof that acts do not read it (unreachability alone cannot give it);
  * WIPED-INDEX RECONCILE — the rebuild equals a synced index, row for row;
  * REPLAY — a second sync changes nothing;
  * MONOTONIC PROVENANCE — a sync from a commit that does not descend from the
    indexed one writes nothing;
  * A HUNG INDEXER delays no writer beyond the fork;
  * THE MANAGED SEAM — valid, malformed and plain rows index as `managed
    <owner>`, `unknown` and `legacy`, every one of them through #97's own
    `managed-projection`;
  * FALLBACK — each way the index can fail to answer says `read: sources` and
    returns the source read's own answer.

NO REAL DATABASE AND NO NETWORK. Every store is a SQLite file under `tmp_path`;
the Postgres path is a fake `psql` that records what it was asked; every remote
is a bare repository in a temporary directory and every `$HOME` is temporary.
The real `~/.local/bin` is taken OFF `PATH` wherever it carries a `lanes-index`,
so an installed indexer is never what a case runs.

PYTEST_DONT_REWRITE: pytest does not rewrite this module's asserts (lane 2's SHOULD 1 of
opensoft/openRepoTools-code#89 comment 6955285249, IN by lane 3's 6955397261), so a failing
assert prints its own message, which each case scrubs of the planted secret, and never its
operands; the cases that hold a secret take their rows by id.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import textwrap
import time
import unicodedata
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

LANES_EDIT = REPO / "lanes-edit.sh"
LANES = REPO / "lanes"
INDEXER = REPO / "lanes-index"

UUID_A1 = "aaaaaaaa-0001-4000-8000-00000000a001"
UUID_A1B = "aaaaaaaa-0002-4000-8000-00000000a002"
UUID_A2 = "aaaaaaaa-0003-4000-8000-00000000a003"
UUID_B1 = "bbbbbbbb-0001-4000-8000-00000000b001"
UUID_M1 = "cccccccc-0001-4000-8000-00000000c001"
UUID_M2 = "cccccccc-0002-4000-8000-00000000c002"
UUID_C1 = "dddddddd-0001-4000-8000-00000000d001"
UUID_Z1 = "eeeeeeee-0001-4000-8000-00000000e001"
UUID_T1 = "ffffffff-0001-4000-8000-00000000f001"

#: Lines the grammar has to agree with `LOG_AWK` on, the awkward ones included:
#: a payload behind `←`, free text with no payload, a text-only `— `, a second
#: ` — ` inside the text, a tab, a minutes-only stamp, and every way a line can
#: be UNREADABLE — each of which `LOG_AWK` names in its own words.
NASTY_LOG = "\n".join([
    "# lane repoA-1 — object log (lane-collision-protocol Amendment 7)",
    f"STARTED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:00:00Z, lane:repoA-1 → home opensoft/repoA; dir /work/repoA; profile team-01a; window sess:1 @3",
    f"CLAIMED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:01:00Z, opensoft/repoA#12 — no-github",
    f"NOTED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:02:00Z, lane:repoA-1 — found the bug — and a second dash",
    f"RULED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:03Z, lane:repoA-1 → opensoft/repoA#12 — Brett Heap, verbatim \"take it\"",
    f"OPENED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:04:00Z, opensoft/repoA#13 ← opensoft/repoA#12",
    f"NOTED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:05:00Z, lane:repoA-1\tTAB — a tab in the object",
    "",
    "this line is not the grammar at all",
    f"NOTED—lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:06:00Z, lane:repoA-1 — no spaces round the dash",
    f"TWO WORDS — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:07:00Z, lane:repoA-1 — verb",
    f"NOTED — lane repoA-1 session {UUID_A1}@Eagle, 2026-10-01T00:08:00Z, lane:repoA-1 — no comma",
    f"NOTED — lane repoA-1, {UUID_A1}@Eagle, 2026-10-01T00:09:00Z, lane:repoA-1 — no session word",
    f"NOTED — lane repoA-1, session {UUID_A1}@Eagle 2026-10-01T00:10:00Z, lane:repoA-1 — no comma after the session",
    f"NOTED — lane repoA-1, session {UUID_A1}@Eagle, yesterday, lane:repoA-1 — no stamp",
    f"NOTED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:11:00Z lane:repoA-1 — no comma after the stamp",
    f"NOTED — banana repoA-1, session {UUID_A1}@Eagle, 2026-10-01T00:12:00Z, lane:repoA-1 — no lane word",
    f"PAUSED — lane repoA-1, session {UUID_A1B}@Eagle, 2026-10-01T01:00:00Z, lane:repoA-1 → dir /work/repoA; profile team-01a; agent claude; transcript {UUID_A1B}",
    "",
])


def _sanitized_path() -> str:
    """The caller's PATH without any directory that holds a `lanes-index`:
    an INSTALLED indexer must never be what a case runs or is nudged."""
    keep = []
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if part and not os.path.exists(os.path.join(part, "lanes-index")):
            keep.append(part)
    return os.pathsep.join(keep)


def _row(lane: str, ids: str, state: str, started: str = "2026-10-01T00:00Z",
         ws: str = "Eagle / test / brett", objects: str = "none") -> str:
    return f"| `{lane}` | harness {ids} | {ws} | {started} | {objects} | handoffs/{lane}.md | {state} |"


class Estate:
    """A whole workspace in `tmp_path`: a bare origin, its clone, the pointer
    file that joins them, fake `tmux`/`psql`, and the environment every
    command here is run in."""

    def __init__(self, root: Path):
        self.root = root
        self.home = root / "home"
        self.agents = self.home / ".agents"
        self.origin = root / "origin.git"
        self.wip = self.home / "projects" / "wip"
        self.fakebin = root / "fakebin"
        self.indexbin = root / "indexbin"
        self.state = root / "state"
        self.config = root / "config"
        for d in (self.home, self.agents, self.fakebin, self.indexbin, self.state, self.config,
                  root / "tmp"):
            d.mkdir(parents=True, exist_ok=True)
        (self.fakebin / "tmux").write_text("#!/bin/sh\nexit 1\n")
        (self.fakebin / "tmux").chmod(0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("LANES_", "CLAUDE_", "WORKBENCHES_", "TMUX", "XDG_", "PG",
                                    "AGENT_PROTOCOL_ROOT", "PROJECTS_"))}
        env.update(
            HOME=str(self.home), AGENT_PROTOCOL_ROOT=str(self.agents), TMPDIR=str(root / "tmp"),
            XDG_STATE_HOME=str(self.state), XDG_CONFIG_HOME=str(self.config),
            CLAUDE_CONFIG_DIR=str(self.home / ".claude"), LANES_WORKSTATION="Eagle",
            LANES_HOST="eagle", LANES_OS="linux", LANES_CONTAINER="none",
            LANES_IN_CONTAINER="0", LANES_NO_GITHUB="1", LANES_EDIT=str(LANES_EDIT),
            GIT_AUTHOR_NAME="lanes-index tests", GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_NAME="lanes-index tests", GIT_COMMITTER_EMAIL="test@example.invalid",
            PATH=str(self.fakebin) + os.pathsep + _sanitized_path())
        self.env = env
        self._seed()

    # ------------------------------------------------------------ the seed
    def _git(self, *args: str, cwd: Path | None = None) -> str:
        proc = subprocess.run(["git", *args], cwd=str(cwd or self.wip), capture_output=True,
                              text=True, env=self.env, check=False)
        assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
        return proc.stdout

    def _seed(self) -> None:
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)],
                       check=True, env=self.env)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.wip)],
                       check=True, env=self.env, capture_output=True)
        lanes = self.wip / "lanes"
        (lanes / "log").mkdir(parents=True)
        (lanes / "archive").mkdir()
        register = [
            "# LANES.md — the test register",
            "",
            "| lane | session id | workstation / env / user | started (UTC) | objects owned | handoff path | state |",
            "|---|---|---|---|---|---|---|",
            _row("repoA-1", f"`{UUID_A1}` → `{UUID_A1B}`", "PAUSED · 2026-10-01T01:00:00Z · parked for the night"),
            _row("repoA-2", f"`{UUID_A2}`", "LIVE · 2026-10-01T02:00:00Z · working"),
            _row("repoM-1", f"`{UUID_M1}`", "LIVE · 2026-10-04T00:00:00Z · managed-owner mode=managed daemon=ledger-1 generation=3 bound-lane=repoM-1"),
            _row("repoM-2", f"`{UUID_M2}`", "LIVE · 2026-10-04T00:00:00Z · managed-owner mode=managed daemon=ledger-1 generation=0 bound-lane=repoM-2"),
            _row("repoC-1", f"`{UUID_C1}`", "ENDED · 2026-09-01T00:00:00Z · a row with no log", started="2026-09-01"),
            "",
            f"LANDING — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T02:00:00Z, PR #7 into opensoft/repoA main",
            f"LANDED — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T02:05:00Z, PR #7 into opensoft/repoA main → abc1234",
            "HOLD — lane repoA-2 (Eagle), window w, 2026-10-01T03:00:00Z: opensoft/repoA main 0123456789abcdef0123456789abcdef01234567 for a frozen window",
            "HOLD RELEASED — lane repoA-2 (Eagle), 2026-10-01T03:30:00Z: opensoft/repoA main 0123456789abcdef0123456789abcdef01234567",
            "",
        ]
        (lanes / "LANES.md").write_text("\n".join(register), encoding="utf-8")
        (lanes / "log" / "README.md").write_text("# the object logs\n", encoding="utf-8")
        (lanes / "log" / "repoA-1.md").write_text(NASTY_LOG, encoding="utf-8")
        (lanes / "log" / "repoA-2.md").write_text("\n".join([
            "# lane repoA-2 — object log (lane-collision-protocol Amendment 7)",
            f"STARTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-01T02:00:00Z, lane:repoA-2 → home opensoft/repoA; dir /work/repoA2; profile team-01b",
            f"NOTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-01T02:10:00Z, lane:repoA-2 — second lane's note",
            ""]), encoding="utf-8")
        (lanes / "log" / "repoB-1.md").write_text("\n".join([
            "# lane repoB-1 — object log (lane-collision-protocol Amendment 7)",
            f"STARTED — lane repoB-1, session {UUID_B1}@Eagle, 2026-10-01T00:30:00Z, lane:repoB-1 → home opensoft/repoB; dir /work/repoB; profile team-02a",
            f"OPENED — lane repoB-1, session {UUID_B1}@Eagle, 2026-10-01T00:31:00Z, opensoft/repoB#3",
            f"NOTED — lane repoB-1, session {UUID_B1}@Eagle, 2026-10-01T00:32:00Z, lane:repoB-1 — a log with no row",
            ""]), encoding="utf-8")
        for lane, uid in (("repoM-1", UUID_M1), ("repoM-2", UUID_M2)):
            (lanes / "log" / f"{lane}.md").write_text(
                f"STARTED — lane {lane}, session {uid}@Eagle, 2026-10-04T00:00:00Z, lane:{lane} → home opensoft/repoM; dir /work/repoM\n",
                encoding="utf-8")
        (lanes / "aliases.tsv").write_text("# old\tnew\tutc\nrepoOld-1\trepoA-2\t2026-09-30T00:00:00Z\n",
                                           encoding="utf-8")
        (lanes / "archive" / "LANES-retired.md").write_text("\n".join([
            "# retired rows (Amendment 19(d))", "",
            _row("repoZ-1", f"`{UUID_Z1}`", "RETIRED · 2026-09-02T00:00:00Z · retired"),
            ""]), encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "seed the test register")
        self._git("push", "-q", "origin", "main")
        # AMENDMENT 23 S5: W, the readers' copy that workspace.yaml names, takes
        # no write, and a write that resolves by default goes through the lane's
        # own checkout beside it. These cases are about the indexer, so their
        # writes name `self.wip` by the explicit seam (`LANES_REPO`, ort186 Q9).
        # W is a VIEW of `self.wip` outside the projects root: its `.git` names
        # `self.wip`'s, and its `lanes` is a link into it. That is because
        # `lanes-index sync` reads W's own `origin/<branch>`, which a separate
        # clone would leave behind every write these cases make.
        self.ws = self.root / "ro" / "wip"
        self.ws.mkdir(parents=True)
        (self.ws / ".git").write_text(f"gitdir: {os.path.realpath(self.wip / '.git')}\n",
                                      encoding="utf-8")
        (self.ws / "lanes").symlink_to(self.wip / "lanes")
        (self.agents / "workspace.yaml").write_text(
            f"repository: {self.origin}\npath: {self.ws}\n", encoding="utf-8")
        self.env["LANES_REPO"] = str(self.wip)

    # ------------------------------------------------------------ running
    def run(self, *argv, env: dict | None = None, timeout: float = 120,
            input_text: str | None = None) -> subprocess.CompletedProcess:
        child = dict(self.env)
        for key, value in (env or {}).items():
            if value is None:
                child.pop(key, None)
            else:
                child[key] = value
        return subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                              env=child, timeout=timeout, cwd=str(self.root),
                              input=input_text, stdin=None if input_text is not None else subprocess.DEVNULL)

    def edit(self, *args, env: dict | None = None, **kw) -> subprocess.CompletedProcess:
        return self.run("bash", LANES_EDIT, *args, env=env, **kw)

    def note(self, lane: str, text: str, env: dict | None = None,
             **kw) -> subprocess.CompletedProcess:
        """`log NOTED` as that lane — one write, one commit, one push."""
        merged = {"LANES_LANE": lane}
        merged.update(env or {})
        return self.edit("log", "NOTED", f"lane:{lane}", text, env=merged, **kw)

    def index(self, *args, env: dict | None = None, **kw) -> subprocess.CompletedProcess:
        merged = {"LANES_EDIT": str(LANES_EDIT)}
        merged.update(env or {})
        return self.run(sys.executable, INDEXER, *args, env=merged, **kw)

    @property
    def sqlite(self) -> Path:
        return self.state / "openRepoTools" / "lanes-index.sqlite"

    def tip(self) -> str:
        return self._git("rev-parse", "origin/main").strip()

    def head_text(self, path: str) -> str:
        """`path` as HEAD holds it, read out of git and not off the disk."""
        return self._git("show", f"HEAD:{path}")

    def commit_paths(self, files: dict, message: str) -> None:
        """Commit and push `files` ({repository path: whole content}) THROUGH
        GIT ALONE - `hash-object` and `update-index --cacheinfo` - and never
        through the working tree. Two paths one case apart are two files to
        git on every platform, and ONE file on a case-insensitive filesystem
        (macOS's default): a fixture written to disk there merges the two logs
        it was built to keep apart (#164's gate, darwin). The indexer and
        `who` both read what was PUSHED, so the working tree does not enter."""
        for path, text in files.items():
            sha = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=str(self.wip),
                                 input=text, capture_output=True, text=True, env=self.env,
                                 check=True).stdout.strip()
            # `core.ignorecase` is what a clone on a case-insensitive disk
            # turns on; off here, the index keeps the path as it was spelled.
            self._git("-c", "core.ignorecase=false", "update-index", "--add", "--cacheinfo",
                      f"100644,{sha},{path}")
        self._git("-c", "core.ignorecase=false", "commit", "-q", "-m", message)
        self._git("push", "-q", "origin", "main")

    def write_config(self, text: str, name: str = "lanes-index.conf", mode: int = 0o600) -> Path:
        path = self.config / "openRepoTools" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        return path

    def install_indexer(self) -> Path:
        """A copy of `lanes-index` ON PATH, as `--install` would place it, for
        the cases that need the nudge to find one."""
        target = self.indexbin / "lanes-index"
        shutil.copy2(INDEXER, target)
        target.chmod(0o755)
        return target

    def path_with(self, *dirs: Path) -> str:
        return os.pathsep.join([str(d) for d in dirs] + [self.env["PATH"]])


def _duplicate_ids(name: str, ids: list) -> str:
    """The import-time message of a parametrized table whose ids repeat (lane 2's F-1 of
    opensoft/openRepoTools-code#89 comment 6957946822, IN by lane 3's 6958469496). Each case
    takes the id alone as its argument and its row from a dict built once at import, in
    `PSQL_QUOTE_ROWS`'s form; a dict keeps one row per id, so each table's assert beside its
    dict fails at import when an id repeats, and its message is this: the table's name and the
    repeated ids alone. It is given the ids and never a row, so no planted value is in its
    frame or its message."""
    return f"{name}: duplicate ids {sorted({i for i in ids if ids.count(i) > 1})}"


@pytest.fixture
def estate(tmp_path):
    return Estate(tmp_path / "e")


def dump(db: Path, *, with_utc: bool = False) -> dict:
    """Every row of every table, ordered, for a row-for-row comparison."""
    conn = sqlite3.connect(str(db))
    out = {}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    for table in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        keep = [c for c in cols if with_utc or c not in ("indexed_utc", "applied_utc")]
        out[table] = conn.execute(
            f"SELECT {', '.join(keep)} FROM {table} ORDER BY {', '.join(keep)}").fetchall()
    conn.close()
    return out


HEX = re.compile(r"[0-9a-f]{7,}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?Z")
#: THE CLOCK'S, NOT THE READ'S: the listing's AGE column and its footer's "last
#: heard from origin <n>s ago". Both are computed by the same code, at the
#: moment of the read, out of the same stamps, so two reads a second apart can
#: differ there and nowhere else.
AGE = re.compile(r"\b[0-9]+h [0-9]{2}m\b|\b[0-9]+[smhd] ago\b")


def normal(text: str, *roots: Path) -> str:
    """The parts of an answer that are the CLOCK's or the TEMPORARY DIRECTORY's
    and not the act's: a stamp, a commit id, an age, and the sandbox's paths."""
    for root in roots:
        text = text.replace(str(root), "<ROOT>")
    text = UTC.sub("<UTC>", text)
    text = AGE.sub("<AGE>", text)
    return HEX.sub("<HEX>", text)


def load_indexer():
    """`lanes-index` as a module, for the one case that drives a store directly."""
    import importlib.util
    loader = SourceFileLoader("lanes_index_module", str(INDEXER))
    spec = importlib.util.spec_from_loader("lanes_index_module", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _log_awk() -> str:
    text = LANES_EDIT.read_text(encoding="utf-8")
    # A single-quoted shell string carries no `'` of its own, so the program
    # ends at the first quote that closes a line.
    m = re.search(r"^LOG_AWK='\n(.*?)'\n", text, re.S | re.M)
    assert m, "lanes-edit.sh no longer declares LOG_AWK='…' the way this test reads it"
    return m.group(1)


# ====================================================== the parser's parity

def test_the_log_parser_is_log_awk_line_for_line(estate):
    """THE ONE GRAMMAR. `history --index` may print only what `history` prints,
    so the indexer's parse of a log must be `LOG_AWK`'s, field for field and
    warning for warning — over a log written to be awkward. `LOG_AWK` is read
    out of `lanes-edit.sh` itself and run over the same bytes."""
    assert estate.index("sync").returncode == 0
    out = estate.root / "exp"
    out.mkdir()
    res = estate.index("export", "--out", out)
    assert res.returncode == 0, res.stderr
    logs = (out / "logs").read_text().splitlines()
    assert logs == ["lanes/log/repoA-1.md", "lanes/log/repoA-2.md", "lanes/log/repoB-1.md",
                    "lanes/log/repoM-1.md", "lanes/log/repoM-2.md"]
    program = _log_awk()
    want_events, want_warn = [], []
    for rel in logs:
        proc = subprocess.run(["awk", "-v", f"FN={rel}", program],
                              input=(estate.wip / rel).read_text(encoding="utf-8"),
                              capture_output=True, text=True, check=True)
        want_events.append(proc.stdout)
        want_warn.append(proc.stderr)
    assert (out / "events").read_text(encoding="utf-8") == "".join(want_events)
    assert (out / "warn").read_text(encoding="utf-8") == "".join(want_warn)
    assert "unreadable: lanes/log/repoA-1.md:9 (no \" — \" after the verb)" in \
        (out / "warn").read_text(encoding="utf-8")


# ============================================================ replay, digests

def test_replay_a_second_sync_changes_nothing(estate):
    """REPLAY (14(d)): an upsert bearing the stored digest changes nothing, so a
    second sync of the same commit writes not one byte — `indexed_utc`
    included — and a sync after ONE more write upserts only what that write
    moved, leaving every other row's provenance where it was."""
    first = estate.index("sync")
    assert first.returncode == 0, first.stderr
    assert "upserted" in first.stdout
    before = dump(estate.sqlite, with_utc=True)
    time.sleep(1.1)
    second = estate.index("sync")
    assert second.returncode == 0, second.stderr
    assert "nothing to write" in second.stdout
    assert dump(estate.sqlite, with_utc=True) == before

    write = estate.note("repoA-2", "one more note")
    assert write.returncode == 0, write.stderr
    third = estate.index("sync")
    assert third.returncode == 0, third.stderr
    m = re.search(r"(\d+) upserted, (\d+) removed", third.stdout)
    assert m, third.stdout
    # one log line, and the file record whose blob moved — nothing else
    assert (int(m.group(1)), int(m.group(2))) == (2, 0), third.stdout
    conn = sqlite3.connect(str(estate.sqlite))
    tip = estate.tip()
    moved = conn.execute("SELECT COUNT(*) FROM log_lines WHERE provenance = ?", (tip,)).fetchone()[0]
    assert moved == 1
    assert conn.execute("SELECT commit_sha FROM provenance").fetchone()[0] == tip


def test_reconcile_finds_and_rights_a_row_changed_by_hand(estate):
    """RECONCILE READS THE CONTENT. A row somebody edited in the store still
    carries its old digest, so a digest compare passes over it; `reconcile`
    recomputes the digest from what the row SAYS, and puts it right."""
    assert estate.index("sync").returncode == 0
    clean = dump(estate.sqlite)
    conn = sqlite3.connect(str(estate.sqlite))
    conn.execute("UPDATE lanes SET state_phrase = 'LIVE · forged' WHERE lane = 'repoA-1'")
    conn.commit()
    conn.close()
    assert estate.index("sync").stdout.count("nothing to write") == 1
    dry = estate.index("reconcile", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert re.search(r"lanes\s+\d+ kept\s+1 upserted", dry.stdout), dry.stdout
    assert "nothing written (--dry-run)" in dry.stdout
    res = estate.index("reconcile")
    assert res.returncode == 0, res.stderr
    assert dump(estate.sqlite) == clean


# ===================================================== wiped-index reconcile

def test_wiped_index_reconcile_equals_a_synced_index_row_for_row(estate):
    """WIPED-INDEX RECONCILE (14(d)): on a wiped index, the rebuild — and it is
    the same index a sync made, row for row and digest for digest."""
    assert estate.index("sync").returncode == 0
    synced = dump(estate.sqlite)
    estate.sqlite.unlink()
    dry = estate.index("reconcile", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert not estate.sqlite.exists(), "a dry run created the store"
    res = estate.index("reconcile")
    assert res.returncode == 0, res.stderr
    assert dump(estate.sqlite) == synced
    # AND A WIPE THAT LEFT THE TABLES: the provenance row alone gone
    conn = sqlite3.connect(str(estate.sqlite))
    conn.execute("DELETE FROM provenance")
    conn.execute("DELETE FROM log_lines")
    conn.commit()
    conn.close()
    assert estate.index("reconcile").returncode == 0
    assert dump(estate.sqlite) == synced


# ====================================================== monotonic provenance

def test_a_sync_from_a_commit_that_does_not_descend_writes_nothing(estate):
    """MONOTONIC PROVENANCE (14(d)): the indexed commit only moves forward. A
    checkout BEHIND the index, one that has DIVERGED from it, and one that has
    never fetched the indexed commit each write nothing."""
    t1 = estate.tip()
    assert estate.note("repoA-2", "the second commit").returncode == 0
    t2 = estate.tip()
    assert estate.index("sync").returncode == 0
    synced = dump(estate.sqlite, with_utc=True)

    estate._git("update-ref", "refs/remotes/origin/main", t1)
    behind = estate.index("sync")
    assert behind.returncode == 0, behind.stderr
    assert "does not descend from the indexed" in behind.stdout
    assert "BEHIND" in behind.stdout
    assert dump(estate.sqlite, with_utc=True) == synced

    estate._git("checkout", "-q", "-b", "side", t1)
    (estate.wip / "lanes" / "log" / "repoB-1.md").write_text("rewritten\n", encoding="utf-8")
    estate._git("commit", "-q", "-am", "a history the index never saw")
    side = estate._git("rev-parse", "HEAD").strip()
    estate._git("update-ref", "refs/remotes/origin/main", side)
    diverged = estate.index("sync")
    assert diverged.returncode == 1, diverged.stdout
    assert "diverged" in diverged.stdout
    assert dump(estate.sqlite, with_utc=True) == synced
    recon = estate.index("reconcile")
    assert recon.returncode == 1 and "nothing written" in recon.stdout
    assert dump(estate.sqlite, with_utc=True) == synced

    conn = sqlite3.connect(str(estate.sqlite))
    conn.execute("UPDATE provenance SET commit_sha = ?", ("f" * 40,))
    conn.commit()
    conn.close()
    estate._git("update-ref", "refs/remotes/origin/main", t2)
    ahead = estate.index("sync")
    assert ahead.returncode == 0
    assert "another workstation is ahead" in ahead.stdout
    conn = sqlite3.connect(str(estate.sqlite))
    assert conn.execute("SELECT commit_sha FROM provenance").fetchone()[0] == "f" * 40


def test_the_compare_and_swap_refuses_a_provenance_that_moved(estate):
    """THE CAS IS IN THE TRANSACTION: a writer that read one provenance and
    finds another at commit time writes NOTHING — rows included."""
    assert estate.index("sync").returncode == 0
    mod = load_indexer()
    cfg = {"sqlite": str(estate.sqlite), "store": "sqlite"}
    store = mod.SqliteStore(cfg)
    store.open_write()
    source = [p["source"] for p in store.all_provenance()][0]
    before = dump(estate.sqlite, with_utc=True)
    stale = {"commit_sha": "0" * 40}
    upserts = {"lane_aliases": {"999": {"old_name": "x", "new_name": "y", "utc": None,
                                        "ordinal": 999, "raw": "x\ty", "digest": "d"}}}
    with pytest.raises(mod.CasLost):
        store.apply(source, stale, "1" * 40, upserts, {})
    assert dump(estate.sqlite, with_utc=True) == before


def _export_image(out: Path) -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(out.iterdir())}


@pytest.mark.parametrize("journal,wait", [("wal", 60.0), ("delete", 5.0)])
def test_an_export_is_one_commits_image_when_a_sync_lands_mid_read(estate, monkeypatch,
                                                                     journal, wait):
    """ONE READ SNAPSHOT (opensoft/openRepoTools#166 item 1): `export` read the
    provenance and each table as statements of their own, so a sync landing
    between two of them wrote rows of two commits under a `meta` naming the
    first. A sync is landed after the export's FIRST table - in WAL mode it
    commits at once, and the export keeps its snapshot; in the rollback
    journal it waits for the export's read lock (`wait` bounds how long this
    case waits for it to finish first) and lands after - and the export is the
    old commit's image or the new one, never a mix of the two."""
    assert estate.index("sync").returncode == 0
    conn = sqlite3.connect(str(estate.sqlite))
    assert conn.execute(f"PRAGMA journal_mode={journal}").fetchone()[0] == journal
    conn.close()
    old = estate.root / "old"
    old.mkdir()
    assert estate.index("export", "--out", old).returncode == 0
    assert estate.note("repoA-2", "a note a sync lands mid-export").returncode == 0
    _as_estate(monkeypatch, estate)
    mod = load_indexer()
    real_rows = mod.SqliteStore.rows
    syncs: list = []

    def rows_then_a_sync(self, table, source, columns):
        got = real_rows(self, table, source, columns)
        if not syncs:
            syncs.append(subprocess.Popen(
                [sys.executable, str(INDEXER), "sync"], cwd=str(estate.root),
                env=dict(estate.env, LANES_EDIT=str(LANES_EDIT)), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            try:
                syncs[0].wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass  # its commit is waiting on this export's read lock
        return got

    monkeypatch.setattr(mod.SqliteStore, "rows", rows_then_a_sync)
    got = estate.root / "got"
    got.mkdir()
    assert mod.cmd_export(str(got), None) == 0
    out, err = syncs[0].communicate(timeout=60)
    assert syncs[0].returncode == 0 and "upserted" in out, (out, err)
    new = estate.root / "new"
    new.mkdir()
    assert estate.index("export", "--out", new).returncode == 0
    images = {"old": _export_image(old), "new": _export_image(new)}
    assert images["old"] != images["new"], "the sync landed nothing: vacuous"
    assert _export_image(got) in images.values(), "the export mixed two commits' rows"


# ============================================================ the hung indexer

STUB = """#!/bin/sh
# A HUNG INDEXER: it says it started, says what its stdin was, and sleeps.
printf '%s\\n' "$$" > "$LANES_INDEX_STUB_MARK.pid"
if IFS= read -r line; then echo data > "$LANES_INDEX_STUB_MARK.stdin"; else echo eof > "$LANES_INDEX_STUB_MARK.stdin"; fi
printf '%s\\n' "$*" > "$LANES_INDEX_STUB_MARK.argv"
sleep 30
"""


def _wait_for(path: Path, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return True
        time.sleep(0.05)
    return False


def test_a_hung_indexer_delays_no_writer_beyond_the_fork(estate):
    """A HUNG INDEXER (14(d)): the nudge is DETACHED — stdin closed, its output
    on /dev/null, never waited — so a `lanes-index` that sleeps thirty seconds
    costs a write no more than the fork. Measured against the same write with
    the nudge switched off, and proved non-vacuous: the stub DID start, with an
    empty stdin, asked to `sync`, and was still running when the writer had
    already returned."""
    stubdir = estate.root / "stub"
    stubdir.mkdir()
    (stubdir / "lanes-index").write_text(STUB)
    (stubdir / "lanes-index").chmod(0o755)
    mark = estate.root / "stubmark"
    path = estate.path_with(stubdir)

    t0 = time.monotonic()
    control = estate.note("repoA-2", "control write",
                          env={"PATH": path, "LANES_INDEX": "off",
                               "LANES_INDEX_STUB_MARK": str(mark)})
    control_s = time.monotonic() - t0
    assert control.returncode == 0, control.stderr
    assert not _wait_for(Path(str(mark) + ".pid"), 1.0), "LANES_INDEX=off still nudged"

    t0 = time.monotonic()
    nudged = estate.note("repoA-2", "nudged write",
                         env={"PATH": path, "LANES_INDEX": None,
                              "LANES_INDEX_STUB_MARK": str(mark)}, timeout=25)
    nudged_s = time.monotonic() - t0
    assert nudged.returncode == 0, nudged.stderr
    pid_file = Path(str(mark) + ".pid")
    assert _wait_for(pid_file, 10.0), "the nudge never started the indexer"
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, 0)
        alive = True
    except OSError:
        alive = False
    try:
        assert alive, "the stub was not running when the writer returned — was it waited?"
        assert nudged_s < control_s + 3.0, (
            f"the nudged write took {nudged_s:.2f}s against {control_s:.2f}s without "
            f"the nudge: a thirty-second indexer is delaying the writer")
        assert _wait_for(Path(str(mark) + ".stdin"), 5.0)
        assert Path(str(mark) + ".stdin").read_text().strip() == "eof"
        # THE STUB WRITES `.stdin` BEFORE `.argv` (the review of #289): seen
        # the instant `.stdin` is, `.argv` may not be there yet.
        assert _wait_for(Path(str(mark) + ".argv"), 5.0)
        assert Path(str(mark) + ".argv").read_text().strip() == "sync"
        assert "lanes-index" not in nudged.stdout + nudged.stderr
    finally:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    print(f"\nmeasured: write with LANES_INDEX=off {control_s:.3f}s; with a 30 s "
          f"indexer on PATH {nudged_s:.3f}s")


def test_a_read_never_nudges_and_no_indexer_costs_nothing(estate):
    """ONLY A PUSH THAT LANDED NUDGES. A read with an indexer on PATH starts
    none; and a write with NO indexer on PATH prints exactly what it prints
    with the nudge switched off — the absent case costs nothing and says
    nothing."""
    stubdir = estate.root / "stub"
    stubdir.mkdir()
    (stubdir / "lanes-index").write_text(STUB)
    (stubdir / "lanes-index").chmod(0o755)
    mark = estate.root / "stubmark"
    res = estate.edit("who", "opensoft/repoA#12",
                      env={"PATH": estate.path_with(stubdir), "LANES_INDEX": None,
                           "LANES_INDEX_STUB_MARK": str(mark)})
    assert res.returncode == 0, res.stderr
    assert not _wait_for(Path(str(mark) + ".pid"), 1.0), "a read nudged the indexer"
    off = estate.note("repoA-2", "the same note", env={"LANES_INDEX": "off"})
    absent = estate.note("repoA-2", "the same note")
    assert (off.returncode, normal(off.stdout), normal(off.stderr)) == \
        (absent.returncode, normal(absent.stdout), normal(absent.stderr))


# ============================================================ the managed seam

def test_the_owner_column_is_managed_projections_answer(estate):
    """THE MANAGED SEAM (14(e)): a valid marker indexes as `managed <owner>`, a
    malformed one as `unknown` — never downgraded to `legacy` — and a plain
    row as `legacy`; and every one of the three was ASKED of #97's own
    `managed-projection`, which the indexer carries no copy of."""
    calls = estate.root / "mp-calls"
    wrapper = estate.root / "lanes-edit-wrapper"
    wrapper.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {calls}\nexec bash {LANES_EDIT} \"$@\"\n")
    wrapper.chmod(0o755)
    res = estate.index("sync", env={"LANES_EDIT": str(wrapper)})
    assert res.returncode == 0, res.stderr
    conn = sqlite3.connect(str(estate.sqlite))
    owners = dict(conn.execute("SELECT lane, owner FROM lanes"))
    assert owners["repoM-1"] == "managed ledger-1"
    assert owners["repoM-2"] == "unknown"
    assert owners["repoA-1"] == "legacy"
    assert owners["repoB-1"] == "legacy"
    asked = calls.read_text().splitlines()
    for lane in ("repoM-1", "repoM-2", "repoA-1"):
        assert f"managed-projection {lane}" in asked, asked
    source = INDEXER.read_text(encoding="utf-8")
    for vocabulary in ("mode=managed", "managed-owner", "bound-lane"):
        assert vocabulary not in source, (
            f"lanes-index carries `{vocabulary}`: a parser of the marker of its own, "
            f"which clause (e) forbids")
    # and the ledger half's tables exist EMPTY, with T058's columns
    cols = [r[1] for r in conn.execute("PRAGMA table_info(swap_states)")]
    assert {"lane", "parent_uuid", "generation", "state"} <= set(cols)
    assert conn.execute("SELECT COUNT(*) FROM swap_states").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_summaries").fetchone()[0] == 0
    # and #161's worktree inventory table, RESERVED: its columns, no rows
    cols = [r[1] for r in conn.execute("PRAGMA table_info(worktrees)")]
    assert {"workstation", "lane", "owner", "path", "branch", "base", "lifecycle",
            "generation", "operation", "writer_live", "last_seen_utc", "last_commit",
            "dirty_count", "unpushed_count", "pr_number", "pr_state"} <= set(cols)
    assert conn.execute("SELECT COUNT(*) FROM worktrees").fetchone()[0] == 0


def test_the_schema_holds_what_clause_e_names(estate):
    """What is indexed: every lane (a log with no row, and an archived row,
    included), every log line with the unreadable ones kept by file and line,
    the register's four kinds of line, the transcript pointers, and holds as a
    VIEW in file order."""
    assert estate.index("sync").returncode == 0
    conn = sqlite3.connect(str(estate.sqlite))
    lanes = {r[0]: r for r in conn.execute(
        "SELECT lane, aliases, home, last_session, archived, session_ids, state_phrase FROM lanes")}
    assert set(lanes) >= {"repoA-1", "repoA-2", "repoB-1", "repoM-1", "repoM-2", "repoC-1", "repoZ-1"}
    assert json.loads(lanes["repoA-2"][1]) == ["repoOld-1"]
    assert lanes["repoA-1"][2] == "opensoft/repoA"
    assert lanes["repoA-1"][3] == UUID_A1B
    assert json.loads(lanes["repoA-1"][5]) == [UUID_A1, UUID_A1B]
    assert lanes["repoZ-1"][4] == 1
    assert lanes["repoA-1"][6] == "PAUSED · 2026-10-01T01:00:00Z · parked for the night"
    bad = conn.execute("SELECT file, ordinal, unreadable_why FROM log_lines WHERE unreadable = 1 "
                       "ORDER BY ordinal").fetchall()
    assert len(bad) == 9 and bad[0][:2] == ("lanes/log/repoA-1.md", 9)
    kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM register_lines GROUP BY kind"))
    assert kinds == {"LANDING": 1, "LANDED": 1, "HOLD": 1, "HOLD RELEASED": 1}
    landed = conn.execute("SELECT pr, repo, tip FROM register_lines WHERE kind = 'LANDED'").fetchone()
    assert landed == ("7", "opensoft/repoA", "abc1234")
    holds = conn.execute("SELECT lane, object, verb FROM holds ORDER BY lane, object").fetchall()
    assert holds == [("repoA-1", "opensoft/repoA#12", "CLAIMED"),
                     ("repoA-1", "opensoft/repoA#13", "OPENED"),
                     ("repoB-1", "opensoft/repoB#3", "OPENED")]
    paused = conn.execute("SELECT transcript_id, agent FROM transcript_pointers "
                          "WHERE kind = 'paused'").fetchall()
    assert paused == [(UUID_A1B, "claude")]
    fields = json.loads(conn.execute(
        "SELECT payload_fields FROM log_lines WHERE verb = 'STARTED' AND lane = 'repoA-1'").fetchone()[0])
    assert fields["home"] == "opensoft/repoA" and fields["window"] == "sess:1 @3"
    assert conn.execute("SELECT version FROM schema_version").fetchall() == [(1,)]


# ================================================== the read flag, and its fallback

def _pair(estate, argv, *, env=None):
    src = estate.run(*argv, env=env)
    idx = estate.run(*argv, "--index", env=env)
    return src, idx


READS = [
    ("bash", LANES_EDIT, "history", "repoA-1"),
    ("bash", LANES_EDIT, "history", "--all"),
    ("bash", LANES_EDIT, "history", "--repo", "opensoft/repoA"),
    ("bash", LANES_EDIT, "history", "repoOld-1"),
    ("bash", LANES_EDIT, "lanes", "--all", "--closed"),
    ("bash", LANES, "--all"),
    ("bash", LANES, "--all", "--closed"),
]


def test_the_index_read_is_byte_identical_to_the_source_read(estate):
    """`--index` ANSWERS EXACTLY WHAT THE SOURCES ANSWER where the index is
    current — the listing's AGE column, which is the clock's, the one
    permitted difference — and says so on stderr. Then a write the index has
    not followed: the lag is SAID, never refused.

    STDERR TOO (opensoft/openRepoTools#166 item 3): `history repoA-1` prints
    LOG_AWK's warnings for its log's nine unreadable lines AND the count that
    closes them, and `history repoA-1 --index` said the nine without the
    count. Two lines are the flag's own and are set aside on both sides: the
    `read:` line, and `history`'s no-fetch note where the index answered - the
    read is the index's, so that arm fetches nothing in front of it."""
    assert estate.index("sync").returncode == 0
    sha12 = estate.tip()[:12]

    def told(stderr: str) -> str:
        return "".join(line for line in stderr.splitlines(keepends=True)
                       if not line.startswith("read: ")
                       and "not fetching; reading origin/" not in line)

    for argv in READS:
        src, idx = _pair(estate, argv)
        assert idx.returncode == src.returncode, (argv, idx.stderr)
        assert AGE.sub("<AGE>", idx.stdout) == AGE.sub("<AGE>", src.stdout), argv
        assert f"read: index (sqlite) at register@{sha12}; 0 commits behind" in idx.stderr, (argv, idx.stderr)
        assert "read: " not in src.stderr
        assert told(idx.stderr) == told(src.stderr), (argv, idx.stderr, src.stderr)
    src, _idx = _pair(estate, ("bash", LANES_EDIT, "history", "repoA-1"))
    assert "9 unreadable line(s) above" in src.stderr, "the fixture lost its unreadable lines: vacuous"
    assert estate.note("repoA-1", "a note the index has not seen").returncode == 0
    src, idx = _pair(estate, ("bash", LANES_EDIT, "history", "repoA-1"))
    assert idx.returncode == 0
    assert "1 commits behind" in idx.stderr
    assert "a note the index has not seen" in src.stdout
    assert "a note the index has not seen" not in idx.stdout


def _fallback_setups():
    def missing(e):
        return {}

    def unreachable(e):
        fake = e.root / "pgfake"
        fake.mkdir(exist_ok=True)
        (fake / "psql").write_text("#!/bin/sh\necho 'psql: error: connection to server at \"db.invalid\" failed' >&2\nexit 2\n")
        (fake / "psql").chmod(0o755)
        pw = e.config / "pgpass"
        pw.write_text("*:*:*:*:never-read\n")
        pw.chmod(0o600)
        e.write_config(f"url=postgresql://lanes_writer@db.invalid/qa\npassfile={pw}\n"
                       f"reader_url=postgresql://lanes_reader@db.invalid/qa\n")
        return {"PATH": e.path_with(fake)}

    def wiped(e):
        assert e.index("sync").returncode == 0
        conn = sqlite3.connect(str(e.sqlite))
        conn.execute("DELETE FROM provenance")
        conn.commit()
        return {}

    def unknown_schema(e):
        assert e.index("sync").returncode == 0
        conn = sqlite3.connect(str(e.sqlite))
        conn.execute("UPDATE schema_version SET version = 99")
        conn.commit()
        return {}

    def refused(e):
        e.write_config("store=sqlite\n", mode=0o644)
        return {}

    def off(e):
        assert e.index("sync").returncode == 0
        return {"LANES_INDEX": "off"}

    return [("missing", missing), ("unreachable", unreachable), ("wiped", wiped),
            ("unknown-schema", unknown_schema), ("refused", refused), ("off", off)]


@pytest.mark.parametrize("kind,setup", _fallback_setups(), ids=[k for k, _ in _fallback_setups()])
def test_each_failure_falls_back_to_the_sources_and_says_so(estate, kind, setup):
    """FALLBACK (14(b)): missing, unreachable, wiped, of an unknown schema,
    refused, or switched off — each says `read: sources (index <why>)` and
    returns the source read's own answer and exit."""
    env = setup(estate)
    for argv in READS:
        src = estate.run(*argv, env=env)
        idx = estate.run(*argv, "--index", env=env)
        assert idx.returncode == src.returncode, (kind, argv, idx.stderr)
        assert AGE.sub("<AGE>", idx.stdout) == AGE.sub("<AGE>", src.stdout), (kind, argv)
        assert f"read: sources (index {kind}" in idx.stderr, (kind, argv, idx.stderr)


def test_the_flag_is_never_taken_from_the_environment(estate):
    """`--index` IS TYPED, never inherited: a variable of the seam's own name in
    the environment changes nothing, and neither does a configured store."""
    assert estate.index("sync").returncode == 0
    forged = estate.root / "forged"
    forged.mkdir()
    (forged / "register").write_text("| `forged-1` | x | y | z | none | h | LIVE |\n")
    res = estate.edit("lanes", "--all", env={"LANES_IDX_DIR": str(forged), "LANES_INDEX": None})
    assert res.returncode == 0
    assert "forged-1" not in res.stdout
    assert "read: " not in res.stderr


# ======================================================= offline no-read, poison

#: The acts and the reads an act makes for itself, each one run against two
#: fresh copies of the same estate. A WRITE is followed by its nudge where an
#: indexer is on PATH — which is the point: it runs, it fails against the
#: configured store, and the act's answer does not move.
ACTS = [
    ("claim", "opensoft/repoA#40"),
    ("log", "NOTED", "lane:repoA-2", "an offline note"),
    ("set-row-state", "repoA-2", "PAUSED · parked offline"),
    ("release", "opensoft/repoA#12", "done with it"),
    ("who", "--landing", "opensoft/repoA"),
    ("who", "opensoft/repoA#12"),
    ("who", "--lane", "repoA-1"),
    ("lane-objects", "repoA-1"),
    ("managed-projection", "repoA-1"),
    ("managed-projection", "repoM-1"),
    ("managed-projection", "repoM-2"),
    ("binding", "repoA-1"),
    ("live-holder", "repoA-2"),
    ("register-row", "repoA-1"),
    ("canon-lane", "repoOld-1"),
    ("history", "repoA-1"),
    ("lanes", "--all", "--closed"),
]


def _act_env(e: Estate, act: tuple) -> dict:
    env = {}
    if act[0] in ("claim", "log", "set-row-state", "release"):
        env["LANES_LANE"] = "repoA-2" if act[0] != "release" else "repoA-1"
        env["LANES_SESSION"] = UUID_A2 if act[0] != "release" else UUID_A1B
    return env


def _run_act(e: Estate, act: tuple, extra: dict) -> tuple:
    env = _act_env(e, act)
    env.update(extra)
    res = e.edit(*act, env=env)
    return (res.returncode, normal(res.stdout, e.root), normal(res.stderr, e.root))


def test_offline_no_read_every_act_is_byte_identical_against_an_unreachable_index(tmp_path):
    """OFFLINE NO-READ (14(b), (f)): with an indexer installed and configured at
    a Postgres nobody can reach, every act answers byte for byte as it does
    with no index at all — and the writes' nudges DID reach for that store,
    which is what makes the sameness a finding rather than an absence."""
    control_root = tmp_path / "control"
    index_root = tmp_path / "index"
    control = Estate(control_root)
    indexed = Estate(index_root)
    indexed.install_indexer()
    fake = indexed.root / "pgfake"
    fake.mkdir()
    psql_log = indexed.root / "psql.log"
    # THE STORE IT REACHED FOR, rebuilt from the `PG*` variables as FAKE_PSQL
    # rebuilds it (Question 11; L2-0c), so `lanes_writer` below can only have
    # come from `PGUSER`, never from an argument.
    (fake / "psql").write_text(
        "#!/bin/sh\n"
        "printf 'postgresql://%s@%s%s/%s\\n' \"$PGUSER\" \"$PGHOST\" \"${PGPORT:+:$PGPORT}\" "
        f"\"$PGDATABASE\" >> {psql_log}\n"
        "echo 'psql: error: connection to server at \"lanes-index.invalid\" failed' >&2\nexit 2\n")
    (fake / "psql").chmod(0o755)
    pw = indexed.config / "pgpass"
    pw.write_text("*:*:*:*:never-read\n")
    pw.chmod(0o600)
    indexed.write_config(f"url=postgresql://lanes_writer@lanes-index.invalid/qa\npassfile={pw}\n")
    extra = {"PATH": indexed.path_with(indexed.indexbin, fake), "LANES_INDEX": None}
    for act in ACTS:
        a = _run_act(control, act, {})
        b = _run_act(indexed, act, extra)
        assert normal(a[1], control_root) == normal(b[1], index_root), act
        assert (a[0], normal(a[2], control_root)) == (b[0], normal(b[2], index_root)), (act, b[2])
    assert _wait_for(psql_log, 15.0), "no nudge ever reached for the configured store"
    assert "lanes_writer" in psql_log.read_text()


def test_a_poisoned_index_changes_no_acts_answer(tmp_path):
    """POISONED INDEX (14(b)): an index carrying WRONG rows — a forged hold, a
    forged owner, a forged state, forged narrative — changes no act's answer.
    Unreachability cannot prove that acts do not read the index; wrong rows
    that nothing repeats can. And the poison is REAL: `--index` reads it."""
    control = Estate(tmp_path / "control")
    poisoned = Estate(tmp_path / "poisoned")
    res = poisoned.index("sync")
    assert res.returncode == 0, res.stderr
    conn = sqlite3.connect(str(poisoned.sqlite))
    conn.execute("UPDATE lanes SET owner = 'managed evil', state_phrase = 'LIVE · poisoned', "
                 "session_ids = '[\"99999999-9999-4999-8999-999999999999\"]', "
                 "last_session = '99999999-9999-4999-8999-999999999999'")
    conn.execute("UPDATE log_lines SET free_text = 'POISONED' WHERE verb = 'NOTED'")
    conn.execute("UPDATE log_lines SET verb = 'CLAIMED', object = 'opensoft/repoA#40' "
                 "WHERE verb = 'NOTED' AND lane = 'repoB-1'")
    conn.execute("UPDATE register_lines SET kind = 'LANDING', raw = 'LANDING — poisoned'")
    conn.commit()
    conn.close()
    extra = {"LANES_INDEX": None}
    for act in ACTS:
        a = _run_act(control, act, {})
        b = _run_act(poisoned, act, extra)
        assert normal(a[1], control.root) == normal(b[1], poisoned.root), act
        assert (a[0], normal(a[2], control.root)) == (b[0], normal(b[2], poisoned.root)), (act, b[2])
    seen = poisoned.edit("history", "repoB-1", "--index", env=extra)
    assert "read: index (sqlite)" in seen.stderr
    assert "POISONED" in seen.stdout or seen.returncode == 8, seen.stdout
    told = poisoned.edit("history", "repoA-1", "--index", env=extra)
    assert "POISONED" in told.stdout, "the poison never reached the index read: vacuous"


# ============================================================ history across lanes

def test_history_across_lanes_reads_the_sources_on_one_timeline(estate):
    """`history --all` and `history --repo <r>` (14(g) act 2): every lane's
    `NOTED`/`RULED` on ONE timeline, by UTC and then file order, with the lane
    named — from the SOURCES, no flag needed; and the selectors refuse to be
    combined."""
    res = estate.edit("history", "--all")
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    stamps = [line.split()[0] for line in lines]
    padded = [s if len(s) == 20 else s[:16] + ":00Z" for s in stamps]
    assert padded == sorted(padded)
    assert any(" repoB-1 " in line for line in lines)
    assert any(" repoA-2 " in line for line in lines)
    repo = estate.edit("history", "--repo", "opensoft/repoB")
    assert repo.returncode == 0, repo.stderr
    assert repo.stdout.splitlines() and all(" repoB-1 " in l for l in repo.stdout.splitlines())
    none = estate.edit("history", "--repo", "opensoft/nowhere")
    assert none.returncode == 8 and none.stdout == ""
    since = estate.edit("history", "--all", "--since", "2026-10-01T00:30Z")
    assert all(l.split()[0] >= "2026-10-01T00:30" for l in since.stdout.splitlines())
    for bad in (("history", "repoA-1", "--all"), ("history", "--all", "--repo", "x/y"),
                ("history",)):
        refused = estate.edit(*bad)
        assert refused.returncode == 64, (bad, refused.stderr)


# ================================================================ the store's rules

@pytest.mark.parametrize("text,mode,where,why", [
    ("store=sqlite\n", 0o644, "config", "mode 644"),
    ("url=postgresql://w:secret@db.invalid/qa\n", 0o600, "config", "carries a password"),
    ("url=postgresql://w@db.invalid/qa?password=secret\n", 0o600, "config", "carries a password"),
    ("url=host=db.invalid user=w password=secret\n", 0o600, "config", "carries a password"),
    ("store=oracle\n", 0o600, "config", "the store is"),
    ("colour=blue\n", 0o600, "config", "does not know"),
    ("store=postgres\n", 0o600, "config", "names no `url=`"),
    ("store=sqlite\n", 0o600, "worktree", "inside the git work tree"),
    ("store=sqlite\n", 0o600, "agents", "which on a"),
])
def test_the_configuration_is_refused_on_clause_c_grounds(estate, text, mode, where, why):
    """THE CONFIGURATION (14(c)): per workstation, 0600, never committed and
    never under `~/.agents/`, and no password in a URL. Each refusal is exit 2
    and writes nothing."""
    if where == "config":
        path = estate.write_config(text, mode=mode)
        env = {}
    elif where == "worktree":
        path = estate.wip / "lanes-index.conf"
        path.write_text(text)
        path.chmod(mode)
        env = {"LANES_INDEX_CONFIG": str(path)}
    else:
        path = estate.agents / "lanes-index.conf"
        path.write_text(text)
        path.chmod(mode)
        env = {"LANES_INDEX_CONFIG": str(path)}
    res = estate.index("sync", env=env)
    assert res.returncode == 2, (res.stdout, res.stderr)
    assert why in res.stderr, res.stderr
    assert not estate.sqlite.exists()


def test_a_named_configuration_that_is_not_there_and_a_store_in_a_work_tree_refuse(estate):
    missing = estate.index("sync", env={"LANES_INDEX_CONFIG": str(estate.root / "nope.conf")})
    assert missing.returncode == 2 and "does not exist" in missing.stderr
    estate.write_config(f"sqlite={estate.wip / 'lanes-index.sqlite'}\n")
    inside = estate.index("sync")
    assert inside.returncode == 2 and "never inside a work tree" in inside.stderr
    pw = estate.config / "loose-pgpass"
    pw.write_text("*:*:*:*:x\n")
    pw.chmod(0o644)
    estate.write_config(f"url=postgresql://w@db.invalid/qa\npassfile={pw}\n")
    loose = estate.index("sync")
    assert loose.returncode == 2 and "password file" in loose.stderr


# ======================================================== no refusal echoes a value
#
# T104's follow-up, on Codex's exact-head review of P10 at 079a34d8 (BLOCKING
# lanes-index:549, with :551 and :560): contracts/config.md section 4 (:119) has
# each refusal name the file, the line or the key, and what is wrong, and print no
# URL and no password, but a value in the wrong key, such as a URL with its password
# in `mode=`, was printed whole. One row for each refusal family a line's value
# reaches, each value the fake secret, in a URL or alone. `lanes-index mode` reads
# only the configuration (T105), so each is refused before anything connects.

#: The fake secret, as a URL's password and alone. Neither is real.
CONFIG_SECRET = "t104-FAKE-not-a-secret"
CONFIG_HOST = "h.invalid"
CONFIG_URI = f"postgresql://u:{CONFIG_SECRET}@{CONFIG_HOST}/d"
#: A negative whole number, which R14 refuses as under 2 and which a misplaced
#: password could be: its digits are on neither stream (round 4, Codex's BLOCKING 1,
#: lane 3's ruling, opensoft/openRepoTools#165 6938005990). Not a secret.
CONFIG_NUMBER = "-900000001"

#: (id, the configuration, the exit, words its refusal holds)
NO_ECHO_REFUSALS = [
    ("R5-url", f"url={CONFIG_URI}\n", 2, "`url=`"),
    ("R5-register_url", f"register_url={CONFIG_URI}\n", 2, "`register_url=`"),
    ("R5-query-password",
     f"register_url=postgresql://u@h.invalid/d?password={CONFIG_SECRET}\n", 2,
     "carries a password"),
    ("R7-mode", f"mode={CONFIG_URI}\n", 2, "`mode=`"),
    ("R10-no-reader",
     f"register_url=postgresql://u@h.invalid/d\nregister_label={CONFIG_SECRET}\n", 2,
     "has no `reader_url=`"),
    ("R11-register_passfile", f"register_passfile={CONFIG_URI}\n", 2,
     "(`register_passfile=`)"),
    ("R11-render_key", f"render_key=password={CONFIG_SECRET}\n", 2, "(`render_key=`)"),
    ("R12-register_schema", f"register_schema={CONFIG_URI}\n", 2, "`register_schema=`"),
    ("R13-parameter-name", f"register_url=postgresql://u@h.invalid/d?{CONFIG_SECRET}=x\n", 2,
     "a name that is not a libpq keyword"),
    ("R13-parameter-value",
     f"register_url=postgresql://u@h.invalid/d?application_name={CONFIG_SECRET}\n", 2,
     "`application_name=`"),
    ("R14-connect_timeout",
     f"register_url=postgresql://u@h.invalid/d?connect_timeout={CONFIG_SECRET}\n", 2,
     "`connect_timeout=`"),
    ("R14-connect_timeout-negative",
     f"register_url=postgresql://u@h.invalid/d?connect_timeout={CONFIG_NUMBER}\n", 2,
     "carries a `connect_timeout=` under 2"),
    ("R15-host",
     f"register_url=postgresql://u@{CONFIG_SECRET}.invalid/d\n"
     f"reader_url=postgresql://r@h.invalid/d\n", 2, "not loopback"),
    ("R16-register_addresses", f"register_addresses={CONFIG_URI}\n", 2,
     "`register_addresses=`"),
    ("R16-register_rtt_ms", f"register_rtt_ms=password={CONFIG_SECRET}\n", 2,
     "`register_rtt_ms=`"),
    ("R17-primary", f"mode=primary\nregister_label={CONFIG_SECRET}\n", 78,
     "is not available in this build"),
    # Amendment 14 act 2's own refusals (opensoft/openRepoTools#160's, R4 and R6:
    # lanes-index:662, :665, :688 and :693 at 079a34d8), in their own follow-up,
    # which lane 3 ruled in (opensoft/openRepoTools#165 6932114864).
    ("R4-not-key-value", f"{CONFIG_URI}\n", 2, "is not `key=value`"),
    ("R4-unknown-key", f"{CONFIG_URI}?sslmode=require\n", 2,
     "names a key that is not a plain lower-case word, which this indexer does not know"),
    ("R4-unknown-key-value", f"colour={CONFIG_URI}\n", 2,
     "names `colour=`, which this indexer does not know"),
    ("R6-store", f"store={CONFIG_URI}\n", 2, "`store=`"),
    ("R6-schema", f"schema=password={CONFIG_SECRET}\n", 2, "`schema=`"),
    ("R6-passfile", f"passfile={CONFIG_URI}\n", 2, "(`passfile=`)"),
    ("R6-reader_passfile", f"reader_passfile={CONFIG_URI}\n", 2, "(`reader_passfile=`)"),
]
NO_ECHO_REFUSAL_ROWS = {row[0]: row[1:] for row in NO_ECHO_REFUSALS}
assert len(NO_ECHO_REFUSAL_ROWS) == len(NO_ECHO_REFUSALS), _duplicate_ids(
    "NO_ECHO_REFUSALS", [row[0] for row in NO_ECHO_REFUSALS])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in NO_ECHO_REFUSALS])
def test_no_configuration_refusal_echoes_a_value(estate, ident):
    """NO REFUSAL ECHOES A VALUE (contracts/config.md section 4, :119): the
    fake secret, in a URL or alone, in each family's value, is refused by
    `lanes-index mode` with the family's code and words, nothing on stdout,
    and the secret on neither stream, nor R14's negative number's digits."""
    text, code, words = NO_ECHO_REFUSAL_ROWS[ident]
    estate.write_config(text)
    res = estate.index("mode")
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>")
            .replace(CONFIG_NUMBER.lstrip("-"), "<the number>"))
    assert res.returncode == code, f"exit {res.returncode}, not {code}:\n{said}"
    assert CONFIG_SECRET not in res.stdout + res.stderr, f"the value was echoed:\n{said}"
    # R14's number, with or without its sign (round 4, Codex's BLOCKING 1)
    assert CONFIG_NUMBER.lstrip("-") not in res.stdout + res.stderr, (
        f"the number was echoed:\n{said}")
    # no URL either (config.md:119): the sentinel URL's host is on neither stream
    # (lane 2's note 2, opensoft/openRepoTools#165 6932953810).
    assert CONFIG_HOST not in res.stdout + res.stderr, f"the URL's host was echoed:\n{said}"
    assert words in res.stderr, said
    assert res.stdout == "", said


# =========================================== the SQLite store and a key's private file
#
# Round 3's commit 8, on lane 3's rulings (opensoft/openRepoTools#165 6933409373 and
# 6934430226) on lane 2's note 1 (6932953810): the SQLite work-tree refusal (R6,
# Amendment 14 act 2) printed the store's absolute path, so a URL or a `password=` value
# typed into `sqlite=` and run inside a git work tree reached stderr whole. It names the
# file only where `sqlite=`'s value holds no `://`, no `@` and no `=`, and otherwise the
# key alone. Its rows run with a work-tree cwd. Lane 2's note 3 adds two ids for
# `_check_private_file`'s other branches, which name the key.

SQLITE_KEY_ALONE = "the SQLite store `sqlite=` names would be inside the git work tree"

#: (id, `sqlite=`'s value, words the refusal holds, whether the store's file is named)
SQLITE_IN_A_WORK_TREE = [
    ("sqlite-uri", CONFIG_URI, SQLITE_KEY_ALONE, False),
    # one row for each mark alone, so that dropping any one of the three is caught
    ("sqlite-scheme", f"postgresql://{CONFIG_HOST}/d", SQLITE_KEY_ALONE, False),
    ("sqlite-at", f"u:{CONFIG_SECRET}@{CONFIG_HOST}/d", SQLITE_KEY_ALONE, False),
    ("sqlite-eq", f"password={CONFIG_SECRET}", SQLITE_KEY_ALONE, False),
    ("sqlite-path", "lanes-index.sqlite", "lanes-index.sqlite would be inside the git work "
     "tree", True),
]
SQLITE_IN_A_WORK_TREE_ROWS = {row[0]: row[1:] for row in SQLITE_IN_A_WORK_TREE}
assert len(SQLITE_IN_A_WORK_TREE_ROWS) == len(SQLITE_IN_A_WORK_TREE), _duplicate_ids(
    "SQLITE_IN_A_WORK_TREE", [row[0] for row in SQLITE_IN_A_WORK_TREE])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in SQLITE_IN_A_WORK_TREE])
def test_the_sqlite_work_tree_refusal_names_no_url(estate, ident):
    """THE STORE'S FILE, OR ITS KEY (config.md section 4, R6 and :119): run from
    inside a git work tree, `sqlite=` relative to it is refused with 2. A URL with
    its password, or a `password=` value, is named by its key alone, with neither
    the password nor the URL's host on either stream; a plain path is still
    named."""
    value, words, named = SQLITE_IN_A_WORK_TREE_ROWS[ident]
    estate.write_config(f"sqlite={value}\n")
    child = dict(estate.env, LANES_EDIT=str(LANES_EDIT))
    res = subprocess.run([sys.executable, str(INDEXER), "mode"], capture_output=True, text=True,
                         env=child, cwd=str(estate.wip), timeout=120,
                         stdin=subprocess.DEVNULL)
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    assert words in res.stderr, said
    stored = os.path.abspath(os.path.join(os.path.realpath(estate.wip), value))
    assert (stored in res.stderr) == named, said
    assert CONFIG_SECRET not in res.stdout + res.stderr, f"the value was echoed:\n{said}"
    assert CONFIG_HOST not in res.stdout + res.stderr, f"the URL's host was echoed:\n{said}"
    assert res.stdout == "", said


@pytest.mark.parametrize("kind, words", [
    pytest.param("mode", "(`register_passfile=`) is mode 644", id="mode"),
    pytest.param("not-regular", "(`register_passfile=`) is not a regular file",
                 id="not-regular")])
def test_a_private_file_refusal_names_the_key_not_the_path(estate, kind, words):
    """THE KEY, NOT THE PATH (R11; `_check_private_file`'s `shown=False`): a
    `register_passfile=` whose path holds the fake URL, a file with mode 644 or a
    directory, is refused with 2, naming the key and what is wrong, with neither
    the password nor the URL's host on either stream (lane 2's note 3)."""
    target = estate.root / "postgresql:" / f"u:{CONFIG_SECRET}@{CONFIG_HOST}" / "d"
    if kind == "mode":
        target.parent.mkdir(parents=True)
        target.write_text("*:*:*:*:x\n", encoding="utf-8")
        target.chmod(0o644)
    else:
        target.mkdir(parents=True)
    estate.write_config(f"register_passfile={target}\n")
    res = estate.index("mode")
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    assert words in res.stderr, said
    assert CONFIG_SECRET not in res.stdout + res.stderr, f"the path was echoed:\n{said}"
    assert CONFIG_HOST not in res.stdout + res.stderr, f"the path was echoed:\n{said}"
    assert res.stdout == "", said


# ================================================= mode and classify echo no argument
#
# T105's and T122's follow-up, on Codex's exact-head review of P10 at 079a34d8
# (BLOCKING lanes-index:736 and :1263): neither command takes an argument, and its
# usage line quoted the one it was given, so a misplaced URL or `password=` value
# reached stderr. Nothing secret reaches stderr (register-cli.md section 2.6): the
# line now names no argument, and the exit stays 64.

#: The usage lines, whole.
MODE_USAGE = "lanes-index: mode takes no argument - see lanes-index --help\n"
CLASSIFY_USAGE = ("lanes-index: register classify takes no argument: it reads register lines "
                  "on stdin - see lanes-index --help\n")

#: (id, the arguments after `lanes-index`, the usage line)
NO_ARGUMENT_USAGES = [
    ("mode-uri", ("mode", CONFIG_URI), MODE_USAGE),
    ("mode-key-value", ("mode", f"password={CONFIG_SECRET}"), MODE_USAGE),
    ("classify-uri", ("register", "classify", CONFIG_URI), CLASSIFY_USAGE),
    ("classify-key-value", ("register", "classify", f"password={CONFIG_SECRET}"),
     CLASSIFY_USAGE),
]
NO_ARGUMENT_USAGE_ROWS = {row[0]: row[1:] for row in NO_ARGUMENT_USAGES}
assert len(NO_ARGUMENT_USAGE_ROWS) == len(NO_ARGUMENT_USAGES), _duplicate_ids(
    "NO_ARGUMENT_USAGES", [row[0] for row in NO_ARGUMENT_USAGES])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in NO_ARGUMENT_USAGES])
def test_mode_and_register_classify_echo_no_argument(estate, ident):
    """USAGE, WITH NOTHING READ (contract sections 3.1 and 3.5): given a URL or
    a `password=` value, each exits 64 with its usage line alone, and the
    value is on neither stream. Nothing is read or connected: the
    configuration, which would be refused with 2 since its line is not
    `key=value`, is never reached; the register line on stdin is not
    classified; and no `psql` runs."""
    argv, usage = NO_ARGUMENT_USAGE_ROWS[ident]
    estate.write_config("this line is not a key and its value\n")
    fake = estate.root / "pgfake"
    fake.mkdir()
    ran = estate.root / "psql-ran.txt"
    (fake / "psql").write_text(f"#!/bin/sh\necho ran >> {shlex.quote(str(ran))}\nexit 1\n")
    (fake / "psql").chmod(0o755)
    line = (f"LANDING — lane repoA-1, session {UUID_A1}@Eagle, 2026-10-01T02:00:00Z, PR #7 "
            f"into opensoft/repoA main\n")
    res = estate.index(*argv, env={"PATH": estate.path_with(fake)}, input_text=line)
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert res.returncode == 64, f"exit {res.returncode}, not 64:\n{said}"
    assert CONFIG_SECRET not in res.stdout + res.stderr, f"the argument was echoed:\n{said}"
    assert res.stderr == usage, said
    assert res.stdout == "", said
    assert not ran.exists(), f"psql was run:\n{said}"


# ======================================== an unknown word, and the bootstrap's schema
#
# Round 3's commit 7, on lane 3's ruling (opensoft/openRepoTools#165 6932662633): the
# three echoes left after Codex's exact-head review of P10 at 079a34d8, under its rule
# for every subcommand (exit-codes.md:57, nothing secret on stderr). An unknown
# subcommand (T105) or argument (Amendment 14 act 2) is named in exit-codes.md section
# 3.3's form (lane 3's ruling 6894208108): quoted only where all of it matches
# `--?[A-Za-z][A-Za-z-]{0,30}`, else as not one of the tool's subcommands or flags. A
# subcommand is also quoted where all of it matches `[a-z][a-z-]{0,30}`, so `sycn` is
# named back, and an argument is not (lane 3's ruling 6933409373).
# The bootstrap's own refusal of a reserved `register_schema=` (T109) names the key
# alone, as `load_config`'s R12 now does.

#: (id, the arguments after `lanes-index`, the usage line, whole)
NO_ECHO_WORDS = [
    ("subcommand-uri", (CONFIG_URI,),
     "lanes-index: unknown subcommand that is not one of its subcommands: this build does "
     "not have it - see lanes-index --help\n"),
    ("subcommand-key-value", (f"password={CONFIG_SECRET}",),
     "lanes-index: unknown subcommand that is not one of its subcommands: this build does "
     "not have it - see lanes-index --help\n"),
    ("subcommand-bare-word", ("sycn",),
     "lanes-index: unknown subcommand 'sycn': this build does not have it - see "
     "lanes-index --help\n"),
    ("subcommand-word", ("--frob",),
     "lanes-index: unknown subcommand '--frob': this build does not have it - see "
     "lanes-index --help\n"),
    ("argument-uri", ("status", CONFIG_URI),
     "lanes-index: unknown argument that is not one of its flags for status - see "
     "lanes-index --help\n"),
    ("argument-key-value", ("status", f"password={CONFIG_SECRET}"),
     "lanes-index: unknown argument that is not one of its flags for status - see "
     "lanes-index --help\n"),
    ("argument-word", ("status", "--frob"),
     "lanes-index: unknown argument '--frob' for status - see lanes-index --help\n"),
    ("argument-bare-word", ("status", "sycn"),
     "lanes-index: unknown argument that is not one of its flags for status - see "
     "lanes-index --help\n"),
]
NO_ECHO_WORD_ROWS = {row[0]: row[1:] for row in NO_ECHO_WORDS}
assert len(NO_ECHO_WORD_ROWS) == len(NO_ECHO_WORDS), _duplicate_ids(
    "NO_ECHO_WORDS", [row[0] for row in NO_ECHO_WORDS])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in NO_ECHO_WORDS])
def test_an_unknown_subcommand_or_argument_is_named_in_readys_form(estate, ident):
    """READY'S FORM FOR AN UNKNOWN WORD (exit-codes.md section 3.3): a URL or a
    `password=` value as the subcommand, or as an unknown argument of `status`,
    is usage (64), with the usage line whole and the value on neither stream; a
    word that matches the pattern, `--frob`, is still quoted, and so is a bare
    subcommand, `sycn`, while a bare argument is not. Nothing is read: no `psql`
    runs."""
    argv, usage = NO_ECHO_WORD_ROWS[ident]
    fake = estate.root / "pgfake"
    fake.mkdir()
    ran = estate.root / "psql-ran.txt"
    (fake / "psql").write_text(f"#!/bin/sh\necho ran >> {shlex.quote(str(ran))}\nexit 1\n")
    (fake / "psql").chmod(0o755)
    res = estate.index(*argv, env={"PATH": estate.path_with(fake)})
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert res.returncode == 64, f"exit {res.returncode}, not 64:\n{said}"
    assert CONFIG_SECRET not in res.stdout + res.stderr, f"the word was echoed:\n{said}"
    assert res.stderr == usage, said
    assert res.stdout == "", said
    assert not ran.exists(), f"psql was run:\n{said}"


#: A reserved schema name that the bootstrap's own check refuses: a plain identifier,
#: which `load_config`'s R12 lets through, standing in for a value the refusal must
#: not show.
SCHEMA_SENTINEL = "pg_t109_fake_not_a_secret"

#: (id, the `register_schema=` value, words the refusal holds)
NO_ECHO_SCHEMAS = [
    ("schema-uri", CONFIG_URI, "`register_schema=` in"),
    ("schema-key-value", f"password={CONFIG_SECRET}", "`register_schema=` in"),
    ("schema-reserved", SCHEMA_SENTINEL,
     "bootstrap: register_schema= is the index half's schema or a name PostgreSQL reserves"),
]
NO_ECHO_SCHEMA_ROWS = {row[0]: row[1:] for row in NO_ECHO_SCHEMAS}
assert len(NO_ECHO_SCHEMA_ROWS) == len(NO_ECHO_SCHEMAS), _duplicate_ids(
    "NO_ECHO_SCHEMAS", [row[0] for row in NO_ECHO_SCHEMAS])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in NO_ECHO_SCHEMAS])
def test_the_bootstrap_names_a_refused_register_schema_by_its_key(estate, ident):
    """THE SCHEMA'S KEY, NOT ITS VALUE: with every flag in order, a
    `register_schema=` that is a URL or a `password=` value is refused with 2 by
    `load_config`'s R12, and a reserved name, `pg_...`, by the bootstrap's own
    check; each names `register_schema=` and shows no value, prints nothing on
    stdout, and runs no `psql`."""
    value, words = NO_ECHO_SCHEMA_ROWS[ident]
    estate.write_config(f"register_schema={value}\n")
    fake = estate.root / "pgfake"
    fake.mkdir()
    ran = estate.root / "psql-ran.txt"
    (fake / "psql").write_text(f"#!/bin/sh\necho ran >> {shlex.quote(str(ran))}\nexit 1\n")
    (fake / "psql").chmod(0o755)
    res = estate.index("bootstrap", "--admin-service", "t109admin", "--label", "t109-label",
                       "--repository", "opensoft/t109-workspace", "--lane", "t109-operator",
                       "--no-passwords", env={"PATH": estate.path_with(fake)})
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>").replace(SCHEMA_SENTINEL, "<the name>"))
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    shown = res.stdout + res.stderr
    assert CONFIG_SECRET not in shown and SCHEMA_SENTINEL not in shown, (
        f"the value was echoed:\n{said}")
    assert words in res.stderr, said
    assert res.stdout == "", said
    assert not ran.exists(), f"psql was run:\n{said}"


# ================================== a `--source` or an `--out` value, never echoed
#
# Round 4's commit 10, on lane 3's ruling (opensoft/openRepoTools#165 6938005990) of
# Codex's BLOCKING 2 in its exact-head review of P10 at 2d9247f7: `resolve_source`'s
# three refusals, `inventory_source`'s and `export`'s line for an `--out` that is not a
# directory (Amendment 14 act 2's, and opensoft/openRepoTools#171's for the inventory)
# printed the value given, so a URL or a `password=` value reached stderr, or `export`'s
# `why` file. Each names the flag, or the source's kind, and no value (exit-codes.md:57;
# register-cli.md section 2.6). Every exit is kept.

#: Where an `export` row's `--out` directory goes in its arguments.
OUT_DIR = "<the out directory>"

#: The words of each refusal, whole where they name no path.
SOURCE_NOT_THIS_REGISTER = "not the source `--source` names"
SOURCE_NOT_THIS_INVENTORY = ("this workstation's inventory is inventory:Eagle, not the "
                             "inventory `--source` names")
SOURCE_A_LEDGER = "`--source` names the managed ledger's half"
SOURCE_AN_INVENTORY = "`--source` names a worktree inventory"
OUT_NOT_A_DIRECTORY = "lanes-index: --out is not a directory\n"

#: (id, the arguments after `lanes-index`, the exit, the words, and where they are:
#: stderr, or `export`'s `why` file)
NO_ECHO_SOURCES = [
    ("sync-uri", ("sync", "--source", CONFIG_URI), 2, SOURCE_NOT_THIS_REGISTER, "stderr"),
    ("sync-key-value", ("sync", "--source", f"password={CONFIG_SECRET}"), 2,
     SOURCE_NOT_THIS_REGISTER, "stderr"),
    ("sync-inventory-key-value", ("sync", "--source", f"inventory:password={CONFIG_SECRET}"),
     2, SOURCE_NOT_THIS_INVENTORY, "stderr"),
    ("sync-ledger-key-value", ("sync", "--source", f"ledger:password={CONFIG_SECRET}"), 2,
     SOURCE_A_LEDGER, "stderr"),
    ("reconcile-uri", ("reconcile", "--source", CONFIG_URI), 2, SOURCE_NOT_THIS_REGISTER,
     "stderr"),
    ("reconcile-key-value", ("reconcile", "--source", f"password={CONFIG_SECRET}"), 2,
     SOURCE_NOT_THIS_REGISTER, "stderr"),
    ("reconcile-inventory-uri", ("reconcile", "--source", f"inventory:{CONFIG_URI}"), 2,
     SOURCE_NOT_THIS_INVENTORY, "stderr"),
    ("reconcile-ledger-uri", ("reconcile", "--source", f"ledger:{CONFIG_URI}"), 2,
     SOURCE_A_LEDGER, "stderr"),
    ("export-out-uri", ("export", "--out", CONFIG_URI), 64, OUT_NOT_A_DIRECTORY, "stderr"),
    ("export-out-key-value", ("export", "--out", f"password={CONFIG_SECRET}"), 64,
     OUT_NOT_A_DIRECTORY, "stderr"),
    ("export-source-uri", ("export", "--out", OUT_DIR, "--source", CONFIG_URI), 2,
     SOURCE_NOT_THIS_REGISTER, "why"),
    ("export-source-key-value",
     ("export", "--out", OUT_DIR, "--source", f"password={CONFIG_SECRET}"), 2,
     SOURCE_NOT_THIS_REGISTER, "why"),
    ("export-source-inventory-key-value",
     ("export", "--out", OUT_DIR, "--source", f"inventory:password={CONFIG_SECRET}"), 2,
     SOURCE_AN_INVENTORY, "why"),
]
NO_ECHO_SOURCE_ROWS = {row[0]: row[1:] for row in NO_ECHO_SOURCES}
assert len(NO_ECHO_SOURCE_ROWS) == len(NO_ECHO_SOURCES), _duplicate_ids(
    "NO_ECHO_SOURCES", [row[0] for row in NO_ECHO_SOURCES])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in NO_ECHO_SOURCES])
def test_a_source_or_out_value_is_never_echoed(estate, ident):
    """THE FLAG OR THE SOURCE'S KIND, NEVER THE VALUE (exit-codes.md:57): a URL or a
    `password=` value given to `sync` or `reconcile` as `--source`, plain or after
    `inventory:` or `ledger:`, is refused with 2 before anything is read or written; as
    `export`'s `--out`, it is usage, 64; as `export`'s `--source`, it is refused with 2
    in the `why` file. Each names the flag, or the source's kind: the value is on
    neither stream nor in `why`, stdout is empty, no `psql` runs and no store is made."""
    argv, code, words, where = NO_ECHO_SOURCE_ROWS[ident]
    out = estate.root / "exp"
    out.mkdir()
    fake = estate.root / "pgfake"
    fake.mkdir()
    ran = estate.root / "psql-ran.txt"
    (fake / "psql").write_text(f"#!/bin/sh\necho ran >> {shlex.quote(str(ran))}\nexit 1\n")
    (fake / "psql").chmod(0o755)
    res = estate.index(*[str(out) if a == OUT_DIR else a for a in argv],
                       env={"PATH": estate.path_with(fake)})
    why = (out / "why").read_text(encoding="utf-8") if (out / "why").exists() else ""
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}\nwhy:\n{why}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert res.returncode == code, f"exit {res.returncode}, not {code}:\n{said}"
    for shown in (res.stdout, res.stderr, why):
        assert CONFIG_SECRET not in shown, f"the value was echoed:\n{said}"
        assert CONFIG_HOST not in shown, f"the URL's host was echoed:\n{said}"
    if where == "why":
        assert words in why and res.stderr == "", said
    elif words.endswith("\n"):
        assert res.stderr == words, said
    else:
        assert words in res.stderr, said
    assert res.stdout == "", said
    assert not ran.exists(), f"psql was run:\n{said}"
    assert not estate.sqlite.exists(), f"a store was made:\n{said}"


# ============================ an unresolved source, and this workstation's own register
#
# Round 4's commit 11, on lane 3's ruling (opensoft/openRepoTools-code#89 comment
# 6939379549) of lane 1's two residual points: `_record_error` filed a `--source` it
# could not resolve under the value given, which `status` then printed on stdout; and the
# refusal that names this workstation's own register named it as `workspace.yaml` or
# `origin` spells it, a user, a password or a token included (Amendment 14 act 2's code,
# and opensoft/openRepoTools#171's for the inventory).

#: (id, the arguments after `lanes-index`, what the unresolved source is filed as)
UNRESOLVED_SOURCES = [
    ("sync-register", ("sync", "--source", f"password={CONFIG_SECRET}"), "register:?"),
    ("sync-inventory", ("sync", "--source", f"inventory:password={CONFIG_SECRET}"),
     "inventory:?"),
    ("reconcile-register", ("reconcile", "--source", CONFIG_URI), "register:?"),
    ("reconcile-inventory", ("reconcile", "--source", f"inventory:{CONFIG_URI}"),
     "inventory:?"),
]
UNRESOLVED_SOURCE_ROWS = {row[0]: row[1:] for row in UNRESOLVED_SOURCES}
assert len(UNRESOLVED_SOURCE_ROWS) == len(UNRESOLVED_SOURCES), _duplicate_ids(
    "UNRESOLVED_SOURCES", [row[0] for row in UNRESOLVED_SOURCES])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in UNRESOLVED_SOURCES])
def test_an_unresolved_source_is_filed_without_its_value(estate, ident):
    """FILED AS `register:?` OR `inventory:?` (lane 3's ruling): with a `lanes-edit.sh`
    that cannot answer, a `sync` or `reconcile` whose `--source` holds a URL or a
    `password=` value cannot resolve it and fails with 1, nothing written; the attempt is
    filed under `register:?` or `inventory:?`, which a later `status` names. The value is
    in neither the status file nor either stream of either run."""
    argv, filed = UNRESOLVED_SOURCE_ROWS[ident]
    stub = estate.root / "no-workspace" / "lanes-edit.sh"
    stub.parent.mkdir()
    stub.write_text("#!/bin/sh\necho 'no workspace here' >&2\nexit 3\n")
    stub.chmod(0o755)
    first = estate.index(*argv, env={"LANES_EDIT": str(stub)})
    status = estate.index("status", env={"LANES_EDIT": str(stub)})
    kept = estate.state / "openRepoTools" / "lanes-index.status.json"
    text = kept.read_text(encoding="utf-8") if kept.exists() else ""
    said = (f"{' '.join(argv[:1])} exit {first.returncode}:\nstdout:\n{first.stdout}\n"
            f"stderr:\n{first.stderr}\nstatus exit {status.returncode}:\nstdout:\n"
            f"{status.stdout}\nstderr:\n{status.stderr}\nstatus file:\n{text}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert first.returncode == 1, said
    assert status.returncode == 1, said
    for shown in (first.stdout, first.stderr, status.stdout, status.stderr, text):
        assert CONFIG_SECRET not in shown, f"the value was kept or shown:\n{said}"
        assert CONFIG_HOST not in shown, f"the URL's host was kept or shown:\n{said}"
    assert f'"{filed}"' in text, said
    assert f"source {filed}\n" in status.stdout, said


#: Sentinels for the host and the path of the URLs below; neither is real.
REGISTER_HOST = "t104-fake-host.invalid"
REGISTER_PATH = "t104-fake-path"

#: The refusal's words, whole.
REGISTER_BY_ITS_REMOTE = ("this workstation's register is the one `workspace.yaml` or the "
                          "checkout's `origin` names, not the source `--source` names")

#: (id, `origin`'s URL or None, `workspace.yaml`'s `repository:` or None)
REGISTER_FROM_A_URL = [
    ("origin-userinfo",
     f"https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r.git", None),
    ("origin-token", f"https://{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r.git", None),
    ("origin-scp", f"{CONFIG_SECRET}@{REGISTER_HOST}:{REGISTER_PATH}/r.git", None),
    ("workspace-yaml-url", None,
     f"https://u:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r"),
]
REGISTER_FROM_A_URL_ROWS = {row[0]: row[1:] for row in REGISTER_FROM_A_URL}
assert len(REGISTER_FROM_A_URL_ROWS) == len(REGISTER_FROM_A_URL), _duplicate_ids(
    "REGISTER_FROM_A_URL", [row[0] for row in REGISTER_FROM_A_URL])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in REGISTER_FROM_A_URL])
def test_the_register_is_named_by_its_remote_and_no_url(estate, ident):
    """THE REMOTE'S NAME, NO URL IN ANY FORM (lane 3's rulings): this workstation's
    register, read from `origin` or from `workspace.yaml`'s `repository:`, a URL with
    a user and a password, or a token, a host and a path, is named in the refusal of
    another `--source` only by where it is read. The refusal's words and its exit, 2,
    are kept; stdout is empty, and none of the userinfo, the host and the path is on
    either stream."""
    origin, repository = REGISTER_FROM_A_URL_ROWS[ident]
    root = estate.root / "credentialed"
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=estate.env,
                   capture_output=True)
    if origin is not None:
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", origin],
                       check=True, env=estate.env, capture_output=True)
    agents = estate.root / "agents-credentialed"
    agents.mkdir()
    (agents / "workspace.yaml").write_text(
        (f"repository: {repository}\n" if repository else "") + f"path: {root}\n",
        encoding="utf-8")
    stub = estate.root / "credentialed-edit" / "lanes-edit.sh"
    stub.parent.mkdir()
    stub.write_text(f"#!/bin/sh\n[ \"$1\" = workspace-root ] && echo {shlex.quote(str(root))} "
                    f"&& exit 0\nexit 3\n")
    stub.chmod(0o755)
    res = estate.index("sync", "--source", "register:someone/else",
                       env={"LANES_EDIT": str(stub), "AGENT_PROTOCOL_ROOT": str(agents)})
    said = (f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    for part, what in ((CONFIG_SECRET, "userinfo"), (REGISTER_HOST, "host"),
                       (REGISTER_PATH, "path")):
        assert part not in res.stdout + res.stderr, f"the URL's {what} was shown:\n{said}"
    assert REGISTER_BY_ITS_REMOTE in res.stderr, said
    assert res.stdout == "", said


# ===================================== a credentialed register: its key, its status, CasLost
#
# Round 4's commit 12, on lane 3's ruling (opensoft/openRepoTools-code#89 comment
# 6940341452) of lane 1's sites 1 to 4: no credential reaches `status`'s "source" line,
# `export`'s `source=`, the store's key or the status file's key, and `CasLost`'s stderr
# text carries no URL in any form. A source with no credential keeps today's key.
# Codex's two further sites of the class (comment 6940769355), the `sync` and
# `reconcile` label on stdout and `export`'s `why` for a source with no provenance,
# print the same key; and an identified register is filed under it, never as
# `register:?` (lane 2's note 2 on commit 11, comment 6940663109).

#: (id, `workspace.yaml`'s `repository:`, the index's key for it)
REGISTER_KEYS = [
    ("https-userinfo", f"https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"),
    ("https-token", f"https://{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"),
    ("ssh-password", f"ssh://u:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:ssh://{REGISTER_HOST}/{REGISTER_PATH}/r"),
    # controls: no credential, so today's key exactly; the last one's `@` stands past
    # the end of its authority (its `?`), so it has no userinfo
    ("https-plain", f"https://{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"),
    ("ssh-login", f"ssh://git@{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:ssh://git@{REGISTER_HOST}/{REGISTER_PATH}/r"),
    ("owner-repo", "opensoft/t104-fake-repo", "register:opensoft/t104-fake-repo"),
    ("https-query-at", f"https://{REGISTER_HOST}?{REGISTER_PATH}@x/r",
     f"register:https://{REGISTER_HOST}?{REGISTER_PATH}@x/r"),
    # lane 2's two rows (opensoft/openRepoTools-code#89 comment 6944553219): a password
    # holding a raw `@`, where the authority's LAST `@` ends the userinfo; and a token
    # under an upper-case scheme
    ("https-raw-at", f"https://u:p@{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"),
    ("https-upper-token", f"HTTPS://{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r",
     f"register:HTTPS://{REGISTER_HOST}/{REGISTER_PATH}/r"),
]
REGISTER_KEY_ROWS = {row[0]: row[1:] for row in REGISTER_KEYS}
assert len(REGISTER_KEY_ROWS) == len(REGISTER_KEYS), _duplicate_ids(
    "REGISTER_KEYS", [row[0] for row in REGISTER_KEYS])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in REGISTER_KEYS])
def test_a_credentialed_register_is_keyed_and_shown_without_it(estate, monkeypatch, ident):
    """NO CREDENTIAL IN A KEY OR A NAME (lane 3's ruling): with `workspace.yaml`'s
    `repository:` a URL with a user and a password, a token, or an ssh password, the
    index's key - the store's and the status file's, as `resolve_source` gives it - is
    the URL without its credential; a provenance under it is exported with that
    `source=`, and no file of the state folder holds the credential. `status` names the
    key so, once, and names a name an earlier build filed with the credential without
    it.
    The fake secret is on no stream and not in `meta`. A source with no credential
    keeps today's key."""
    repository, key = REGISTER_KEY_ROWS[ident]
    agents = estate.root / "agents-c12"
    agents.mkdir()
    (agents / "workspace.yaml").write_text(f"repository: {repository}\npath: {estate.ws}\n",
                                           encoding="utf-8")
    env = {"AGENT_PROTOCOL_ROOT": str(agents), "LANES_WORKSPACE_ROOT": str(estate.ws)}
    monkeypatch.setenv("AGENT_PROTOCOL_ROOT", str(agents))
    monkeypatch.setenv("XDG_STATE_HOME", str(estate.state))
    mod = load_indexer()
    assert mod.resolve_source(None, str(estate.ws)) == key
    store = mod.SqliteStore({"sqlite": str(estate.sqlite), "store": "sqlite"})
    store.open_write()
    store.apply(key, None, "1" * 40, {}, {})
    out = estate.root / "exp"
    out.mkdir()
    ex = estate.index("export", "--out", out, env=env)
    for path in sorted(estate.state.rglob("*")):
        if path.is_file():
            assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path} keeps it"
    st = estate.index("status", env=env)
    # an entry an earlier build filed under the credentialed name, for `status` to show
    mod.write_status(f"register:{repository}", last_error="an earlier build's entry")
    again = estate.index("status", env=env)
    meta = (out / "meta").read_text(encoding="utf-8") if (out / "meta").exists() else ""
    why = (out / "why").read_text(encoding="utf-8") if (out / "why").exists() else ""
    said = (f"status:\n{st.stdout}{st.stderr}\nagain:\n{again.stdout}{again.stderr}\n"
            f"export {ex.returncode}:\n{ex.stdout}{ex.stderr}\nmeta:\n{meta}\nwhy:\n{why}"
            .replace(CONFIG_SECRET, "<the secret>"))
    assert ex.returncode == 0, said
    assert f"source={key}" in meta.splitlines(), said
    # this workstation's key, once: the store's and `status`'s own are one key
    assert st.stdout.count(f"source {key}\n") == 1, said
    assert f"source {key}\n" in again.stdout, said
    for shown in (st.stdout, st.stderr, again.stdout, again.stderr, ex.stdout, ex.stderr,
                  meta, why):
        assert CONFIG_SECRET not in shown, f"the credential was shown:\n{said}"


#: (id, the key a sync passes to `SqliteStore.apply`, whether `CasLost` names it)
CAS_KEYS = [
    ("cas-legacy-key", f"register:https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}"
                       f"/{REGISTER_PATH}/r", False),
    ("cas-url-key", f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r", False),
    ("cas-scp-key", f"register:git@{REGISTER_HOST}:{REGISTER_PATH}/r", False),
    ("cas-owner-repo", "register:opensoft/t104-fake-repo", True),
    ("cas-inventory", "inventory:Eagle", True),
]
CAS_KEY_ROWS = {row[0]: row[1:] for row in CAS_KEYS}
assert len(CAS_KEY_ROWS) == len(CAS_KEYS), _duplicate_ids(
    "CAS_KEYS", [row[0] for row in CAS_KEYS])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in CAS_KEYS])
def test_the_compare_and_swap_refusal_names_no_url(estate, ident):
    """`CasLost` NAMES NO URL (exit-codes.md:57; lane 3's ruling): a compare-and-swap
    that finds the provenance moved is refused, nothing written, with its words; a
    plain `register:` or `inventory:` key is named as before, and a key that is a URL
    in any form, with or without a credential, is not: none of its credential, host
    and path is in the text."""
    key, named = CAS_KEY_ROWS[ident]
    mod = load_indexer()
    store = mod.SqliteStore({"sqlite": str(estate.sqlite), "store": "sqlite"})
    store.open_write()
    with pytest.raises(mod.CasLost) as caught:
        store.apply(key, {"commit_sha": "0" * 40}, "1" * 40, {}, {})
    text = str(caught.value)
    said = text.replace(CONFIG_SECRET, "<the secret>")
    assert "moved under this sync" in text and "nothing was written" in text, said
    assert (key in text) == named, said
    for part in (CONFIG_SECRET, REGISTER_HOST, REGISTER_PATH):
        assert part not in text, text.replace(CONFIG_SECRET, "<the secret>")


def _store_keys(db: Path) -> set:
    """The `source` of every row of every table of the store that has the column."""
    conn = sqlite3.connect(str(db))
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
        keys: set = set()
        for table in tables:
            if "source" in [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]:
                keys |= {r[0] for r in conn.execute(f"SELECT DISTINCT source FROM {table}")}
        return keys
    finally:
        conn.close()


#: (id, `workspace.yaml`'s `repository:`, its key: today's, `register:` and the repository
#: less its `.git`, where it has no userinfo; that less its credential where it has one)
SYNCED_SOURCES = [
    ("https-host-path", f"https://{REGISTER_HOST}/{REGISTER_PATH}/r.git",
     f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"),
    ("owner-repo", "opensoft/t104-fake-repo", "register:opensoft/t104-fake-repo"),
    ("https-userinfo",
     f"https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r.git",
     f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"),
]
SYNCED_SOURCE_ROWS = {row[0]: row[1:] for row in SYNCED_SOURCES}
assert len(SYNCED_SOURCE_ROWS) == len(SYNCED_SOURCES), _duplicate_ids(
    "SYNCED_SOURCES", [row[0] for row in SYNCED_SOURCES])


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in SYNCED_SOURCES])
def test_an_identified_register_is_synced_and_filed_under_its_key(estate, ident):
    """AN IDENTIFIED SOURCE IS FILED AS BEFORE, AND NO CREDENTIAL IS PRINTED (lane 2's
    note 2 on commit 11, opensoft/openRepoTools-code#89 comment 6940663109; lane 3's
    ruling and its limit 2, comment 6940341452; Codex's two further sites, comment
    6940769355): with `workspace.yaml`'s `repository:` a URL with no userinfo, GitHub's
    `owner/repo` or a URL with a token, `export` before any sync says in `why` that the
    key has no provenance; `sync` files every row of the store under the key - today's
    key exactly where the source has no userinfo - and names it in its label, as a
    second `sync` and a `reconcile --dry-run` do; a `reconcile` that then fails with its
    source identified files its error under the key in the status file, not as
    `register:?`; and `status` names the key once. The credential is on no stream, in no
    file of the state folder and in no row of the store."""
    repository, key = SYNCED_SOURCE_ROWS[ident]
    agents = estate.root / "agents-synced"
    agents.mkdir()
    (agents / "workspace.yaml").write_text(f"repository: {repository}\npath: {estate.ws}\n",
                                           encoding="utf-8")
    env = {"AGENT_PROTOCOL_ROOT": str(agents), "LANES_WORKSPACE_ROOT": str(estate.ws)}
    # a store with no provenance in it, for `export`'s `why`
    load_indexer().SqliteStore({"sqlite": str(estate.sqlite), "store": "sqlite"}).open_write()
    out = estate.root / "exp-none"
    out.mkdir()
    none = estate.index("export", "--out", out, env=env)
    why = (out / "why").read_text(encoding="utf-8") if (out / "why").exists() else ""
    first = estate.index("sync", env=env)
    keys = _store_keys(estate.sqlite)
    again = estate.index("sync", env=env)
    dry = estate.index("reconcile", "--dry-run", env=env)
    # the register's tree unreadable: the source resolves, and the read after it fails
    with _unreadable(estate, "origin/main:lanes"):
        failed = estate.index("reconcile", env=env)
    status = estate.index("status", env=env)
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    kept = json.loads(filed.read_text(encoding="utf-8")) if filed.exists() else {}
    runs = {"export": none, "sync": first, "sync again": again, "reconcile --dry-run": dry,
            "reconcile": failed, "status": status}
    said = ("\n".join(f"{name} exit {res.returncode}:\n{res.stdout}{res.stderr}"
                      for name, res in runs.items())
            + f"\nwhy: {why}\nstore keys: {sorted(keys)}\nstatus file: {sorted(kept)}"
            ).replace(CONFIG_SECRET, "<the secret>")
    assert none.returncode == 3 and f"no provenance for {key} in the " in why, said
    assert first.returncode == 0 and f"sync: {key} at register@" in first.stdout, said
    assert keys == {key}, said
    assert again.returncode == 0 and f"sync: {key} at register@" in again.stdout, said
    assert "nothing to write" in again.stdout, said
    assert dry.returncode == 0 and f"reconcile: {key} at register@" in dry.stdout, said
    assert failed.returncode == 1, said
    assert sorted(kept) == [key] and kept[key].get("last_error"), said
    assert status.stdout.count(f"source {key}\n") == 1, said
    assert _store_keys(estate.sqlite) == {key}, said
    for name, res in runs.items():
        assert CONFIG_SECRET not in res.stdout + res.stderr, f"{name} showed it:\n{said}"
    assert CONFIG_SECRET not in why, said
    for path in sorted(estate.state.rglob("*")):
        if path.is_file():
            assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path} keeps it:\n{said}"


# ============== a legacy source: a key an earlier build filed with a credential in it
#
# Round 4's commit 13, on lane 3's ruling (opensoft/openRepoTools-code#89 comment
# 6941833120) of BLOCKING 1 in its Codex review of ac4e0935. v1.1.0 and v1.2.0 keyed a
# source as `source_of` read it, a credential included, in both stores and in the
# status file, and SQLite's `CasLost` put that key in the `last_error` that
# `_record_error` saved. `status` never prints such an entry's error, and the first
# `sync` or `reconcile` removes the source from every table and from the status file.

#: What `status` prints in place of a whole entry whose key no form of this build files.
LEGACY_SOURCE_LINE_WORDS = ("source not shown: an earlier build filed an entry under a key "
                            "this build does not file, which may hold a credential; the next "
                            "sync or reconcile removes it")
#: What `status` prints in place of a legacy entry's last error, whole.
LEGACY_ENTRY_WORDS = ("not shown: an earlier build filed this entry under a key that held "
                      "a credential, and the next sync or reconcile removes it")
#: The key v1.2.0 filed for `workspace.yaml`'s `repository:` as an https URL with a
#: token, and the key this build files for it.
LEGACY_KEY = (f"register:https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}/"
              f"{REGISTER_PATH}/r")
CLEAN_KEY = f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/r"
#: A source with no userinfo that no sync here touches: the control, kept byte for byte.
CONTROL_KEY = f"register:https://{REGISTER_HOST}/{REGISTER_PATH}/control"
#: The raw `--source` values v1.1.0 and v1.2.0 `_record_error` filed as status keys
#: (BLOCKING 1 of opensoft/openRepoTools-code#89 comment 6944416906): a URL with a
#: token, a `password=` value, the inventory's `password=` form, a bare token, and an
#: inventory key holding a URL's userinfo. The URL is in the store's every table too, as
#: a key no form of this build files.
RAW_URL_KEY = f"https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r"
RAW_KEYS = [RAW_URL_KEY, f"password={CONFIG_SECRET}", f"inventory:password={CONFIG_SECRET}",
            f"tok-{CONFIG_SECRET}", f"inventory:https://{CONFIG_SECRET}@{REGISTER_HOST}/x"]
#: A clean key of EVERY form this build files (lane 3's ruling, comment 6944673181), none of
#: them this workstation's: each stays, in the store and the status file, byte for byte.
CLEAN_FORMS = ["register:opensoft/t104-other-repo",
               f"register:ssh://git@{REGISTER_HOST}/{REGISTER_PATH}/other",
               f"register:git@{REGISTER_HOST}:{REGISTER_PATH}/other",
               f"register:HTTPS://{REGISTER_HOST}/{REGISTER_PATH}/other",
               f"register:https://{REGISTER_HOST}?{REGISTER_PATH}@x/other",
               "register:/srv/t104/other", "register:?", "inventory:Heron", "inventory:?",
               "ledger:Heron"]


class _IndexTables:
    """The index's store behind `lanes-index`'s back, as an upgrade case seeds and
    reads it: SQLite's file, or the cluster's `t109_db` as its superuser, in the
    schema `lanes_index`. Every value here is the test's own, so it goes into the SQL
    as a literal."""

    def __init__(self, estate: Estate, cluster=None):
        self.estate, self.cluster = estate, cluster

    def sql(self, *statements: str) -> list:
        """The statements in one connection; the rows they answer, as text."""
        if self.cluster is None:
            conn = sqlite3.connect(str(self.estate.sqlite))
            try:
                # AS A BUILD WITHOUT `SQLITE_SECURE_DELETE` WRITES: what an update moves
                # stays in the file's free space
                conn.execute("PRAGMA secure_delete = OFF")
                out = []
                for statement in statements:
                    out += ["|".join("" if v is None else str(v) for v in row)
                            for row in conn.execute(statement).fetchall()]
                conn.commit()
                return out
            finally:
                conn.close()
        text = self.cluster.psql("SET search_path TO lanes_index;\n" +
                                 "".join(f"{s};\n" for s in statements), dbname="t109_db").stdout
        return [line for line in text.splitlines() if line]

    def tables(self) -> list:
        """Every table of the store with a `source` column, as the store has them, not
        as `lanes-index` lists them."""
        if self.cluster is None:
            return [t for t in self.sql("SELECT name FROM sqlite_master WHERE type = 'table' "
                                        "ORDER BY name")
                    if "source" in self.sql(f"SELECT name FROM pragma_table_info('{t}')")]
        return self.sql("SELECT c.table_name FROM information_schema.columns c "
                        "JOIN information_schema.tables t USING (table_schema, table_name) "
                        "WHERE c.table_schema = 'lanes_index' AND c.column_name = 'source' "
                        "AND t.table_type = 'BASE TABLE' ORDER BY 1")

    def copy(self, tables: list, old: str, new: str) -> None:
        """Every row of `old`, filed again under `new`."""
        for t in tables:
            self.sql(f"CREATE TEMP TABLE copy_{t} AS SELECT * FROM {t} WHERE source = '{old}'",
                     f"UPDATE copy_{t} SET source = '{new}'",
                     f"INSERT INTO {t} SELECT * FROM copy_{t}")

    def rename(self, tables: list, old: str, new: str) -> None:
        """Every row of `old`, filed under `new` in its place."""
        for t in tables:
            self.sql(f"UPDATE {t} SET source = '{new}' WHERE source = '{old}'")

    def touch(self, tables: list, source: str) -> None:
        """Every row of `source` written again, longer, as a later v1.2.0 sync wrote
        it: the copies the old rows leave in SQLite's free space hold the key too."""
        for t in tables:
            self.sql(f"UPDATE {t} SET indexed_utc = indexed_utc || ' (v1.2.0)' "
                     f"WHERE source = '{source}'")

    def rows(self, tables: list, source: str) -> list:
        """Every row of `source`, table by table, as text, in a fixed order."""
        return [(t, self.sql(f"SELECT * FROM {t} WHERE source = '{source}' ORDER BY 1, 2"))
                for t in tables]

    def text(self, tables: list) -> str:
        """Every row of every table, as text."""
        return "\n".join(line for t in tables for line in self.sql(f"SELECT * FROM {t}"))

    def seed_every(self, tables: list, source: str) -> None:
        """A row of `source` in each table that has none of it, so that `source` is in
        EVERY table that keys on a source (lane 3's SHOULD, comment 6944606779)."""
        for t in tables:
            if t != "provenance":
                self.sql(f"INSERT INTO {t} (source, record_id, digest, indexed_utc, "
                         f"schema_version) SELECT '{source}', 't104-seed', 'd', "
                         f"'2026-11-01T00:00:00Z', 1 WHERE NOT EXISTS "
                         f"(SELECT 1 FROM {t} WHERE source = '{source}')")

    def leave_in_free_space(self, text: str) -> None:
        """`text` in a page of SQLite's free list, which no DELETE of a row touches, as
        an earlier build's own writes leave a page: a table filled and dropped with
        `secure_delete` off. Only a VACUUM takes it out of the file."""
        self.sql("CREATE TABLE t104_gone (x TEXT)", f"INSERT INTO t104_gone VALUES ('{text}')",
                 "DROP TABLE t104_gone")


def _an_upgrade(estate: Estate, store: _IndexTables, env: dict, first: str) -> None:
    """THE UPGRADE CASE, on either store. This build's first `sync` files the clean
    key; the case then leaves the store and the status file as v1.2.0 would have:
    those rows under the credentialed key too (`beside-clean`) or in place of the
    clean key's (`legacy-only`), the status entry under the credentialed key with
    SQLite's `CasLost` text as `_record_error` saved it, the key whole in it, and a
    control with no userinfo. `status` prints the fixed line in place of that error;
    `first`, `reconcile` or `sync`, removes the credentialed key from every table and
    from the status file. `sync` keeps the clean key's own rows and entry, and
    `reconcile` rebuilds its rows. The control is as it was, byte for byte, and the
    secret is on no stream, in the status file and in no row of the store. On
    SQLite the case seeds with `secure_delete` off and rewrites the credentialed
    rows once, so that copies of the key sit in the file's free space, and no file of
    the state folder may hold it afterwards."""
    agents = estate.root / "agents-upgrade"
    agents.mkdir()
    (agents / "workspace.yaml").write_text(
        f"repository: https://{REGISTER_HOST}/{REGISTER_PATH}/r.git\npath: {estate.ws}\n",
        encoding="utf-8")
    env = dict(env, AGENT_PROTOCOL_ROOT=str(agents), LANES_WORKSPACE_ROOT=str(estate.ws))
    seeded = estate.index("sync", env=env)
    assert seeded.returncode == 0, seeded.stdout + seeded.stderr
    tables = store.tables()
    assert "provenance" in tables and "lanes" in tables, tables
    assert len(tables) == 10, tables
    beside = first != "reconcile"
    store.copy(tables, CLEAN_KEY, CONTROL_KEY)
    for form in CLEAN_FORMS:
        store.copy(tables, CLEAN_KEY, form)
    if beside:
        store.copy(tables, CLEAN_KEY, LEGACY_KEY)
    else:
        store.rename(tables, CLEAN_KEY, LEGACY_KEY)
    store.copy(tables, CONTROL_KEY, RAW_URL_KEY)
    for key in (LEGACY_KEY, RAW_URL_KEY):
        store.seed_every(tables, key)
        # IN EVERY TABLE THAT KEYS ON A SOURCE (lane 3's SHOULD, comment 6944606779)
        assert all(rows for _t, rows in store.rows(tables, key)), [
            (table, len(rows)) for table, rows in store.rows(tables, key)]
    store.touch(tables, LEGACY_KEY)
    if store.cluster is None:
        store.leave_in_free_space(LEGACY_KEY)
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    status = json.loads(filed.read_text(encoding="utf-8"))
    clean_entry = status.pop(CLEAN_KEY)
    status[LEGACY_KEY] = dict(clean_entry, last_error=(
        f"2026-11-01T00:00:00Z the provenance of {LEGACY_KEY} moved under this sync (it read "
        f"111111111111, the store now holds 000000000000); nothing was written"))
    status[CONTROL_KEY] = {"last_attempt_utc": "2026-11-01T00:00:00Z",
                           "last_error": "2026-11-01T00:00:00Z the control's own error"}
    # v1.2.0's raw `--source` keys, each with the error `_record_error` saved naming it
    for key in RAW_KEYS:
        status[key] = {"last_attempt_utc": "2026-11-01T00:00:00Z",
                       "last_error": f"2026-11-01T00:00:00Z unreachable: {key} - nothing written"}
    for form in CLEAN_FORMS:
        status[form] = {"last_attempt_utc": "2026-11-01T00:00:00Z",
                        "last_error": f"2026-11-01T00:00:00Z the clean form {form}'s own error"}
    if beside:
        status[CLEAN_KEY] = dict(clean_entry, t104="the clean key's own entry")
    filed.write_text(json.dumps(status, indent=1, sort_keys=True), encoding="utf-8")
    control = store.rows(tables, CONTROL_KEY)
    forms = [store.rows(tables, form) for form in CLEAN_FORMS]
    clean_rows = store.rows(tables, CLEAN_KEY) if beside else None
    control_entry = json.dumps(status[CONTROL_KEY], sort_keys=True)
    form_entries = [json.dumps(status[form], sort_keys=True) for form in CLEAN_FORMS]
    assert CONFIG_SECRET in store.text(tables), "the seed holds no secret: the case is vacuous"
    before = estate.index("status", env=env)

    def files() -> dict:
        return {str(p.relative_to(estate.state)): p.read_bytes()
                for p in sorted(estate.state.rglob("*")) if p.is_file()}
    # SHOULD 6 (comment 6944416906): a DRY RUN on the legacy state removes nothing and
    # prints nothing raw - every table, the status file and the state folder as they were
    rows_then, files_then = store.text(tables), files()
    dry = estate.index("reconcile", "--dry-run", env=env)
    assert store.text(tables) == rows_then and files() == files_then, (
        "the dry run changed the store, the status file or the state folder")
    assert dry.returncode == 0 and "source(s) from the index" not in dry.stdout, (
        dry.stdout + dry.stderr).replace(CONFIG_SECRET, "<the secret>")
    # AND THE INVENTORY'S DRY RUN (lane 2's SHOULD 3 of comment 6947728883, IN by lane 3's
    # comment 6947826234): no status file replaced, no store row, no legacy key printed
    dry_inventory = estate.index("reconcile", "--source", "inventory", "--dry-run", env=env)
    assert store.text(tables) == rows_then and files() == files_then, (
        "the inventory's dry run changed the store, the status file or the state folder")
    assert (dry_inventory.returncode == 0 and
            "source(s) from the index" not in dry_inventory.stdout), (
        dry_inventory.stdout + dry_inventory.stderr).replace(CONFIG_SECRET, "<the secret>")
    act = {"inventory-sync": ("sync", "--source", "inventory"),
           "inventory-reconcile": ("reconcile", "--source", "inventory")}.get(first, (first,))
    run = estate.index(*act, env=env)
    after = estate.index("status", env=env)
    kept = json.loads(filed.read_text(encoding="utf-8"))
    said = (f"status before, exit {before.returncode}:\n{before.stdout}{before.stderr}\n"
            f"{first}, exit {run.returncode}:\n{run.stdout}{run.stderr}\n"
            f"status after, exit {after.returncode}:\n{after.stdout}{after.stderr}\n"
            f"status file: {sorted(kept)}").replace(CONFIG_SECRET, "<the secret>")
    assert f"  last error:  {LEGACY_ENTRY_WORDS}\n" in before.stdout, said
    # A KEY NO FORM OF THIS BUILD FILES: one fixed line in place of its whole entry, for
    # each raw key (the URL's store rows and status entry are one name)
    assert before.stdout.count(LEGACY_SOURCE_LINE_WORDS + "\n") == len(RAW_KEYS), said
    assert run.returncode == 0, said
    assert (f"removed 2 source(s) from the index and {1 + len(RAW_KEYS)} entry(s) from the "
            f"status file" in run.stdout), said
    own = ["inventory:Eagle"] if first.startswith("inventory") else []
    assert sorted(kept) == sorted([CLEAN_KEY, CONTROL_KEY] + CLEAN_FORMS + own), said
    for key in (LEGACY_KEY, RAW_URL_KEY):
        assert all(rows == [] for _table, rows in store.rows(tables, key)), said
    # EVERY CLEAN FORM STAYS, BYTE FOR BYTE (lane 3's ruling, comment 6944673181)
    assert [store.rows(tables, form) for form in CLEAN_FORMS] == forms, said
    assert [json.dumps(kept[form], sort_keys=True) for form in CLEAN_FORMS] == form_entries, said
    assert LEGACY_SOURCE_LINE_WORDS not in after.stdout, said
    if beside:
        # THE CLEAN KEY'S OWN ROWS AND ENTRY ARE KEPT: the sync finds its rows at the
        # tip, its rows are as they were, byte for byte, and its status entry keeps a
        # field of its own; the inventory's acts leave the register's rows alone
        if first == "sync":
            assert "the index is at the tip; nothing to write" in run.stdout, said
        assert store.rows(tables, CLEAN_KEY) == clean_rows, (
            f"the clean key's rows moved:\n{said}")
        assert kept[CLEAN_KEY].get("t104") == "the clean key's own entry", said
    else:
        # REBUILT UNDER THE CLEAN KEY: as many rows in each table as the control's, a
        # copy of what the first sync filed
        assert f"reconcile: {CLEAN_KEY} at register@" in run.stdout, said
        assert ([(t, len(rows)) for t, rows in store.rows(tables, CLEAN_KEY)] ==
                [(t, len(rows)) for t, rows in control]), said
    assert store.rows(tables, CONTROL_KEY) == control, f"the control moved:\n{said}"
    assert json.dumps(kept[CONTROL_KEY], sort_keys=True) == control_entry, said
    assert LEGACY_ENTRY_WORDS not in after.stdout, said
    for shown in (before.stdout, before.stderr, dry.stdout, dry.stderr, dry_inventory.stdout,
                  dry_inventory.stderr, run.stdout, run.stderr, after.stdout, after.stderr):
        assert CONFIG_SECRET not in shown, f"the secret was shown:\n{said}"
    assert CONFIG_SECRET.encode() not in filed.read_bytes(), said
    assert CONFIG_SECRET not in store.text(tables), f"a row keeps the secret:\n{said}"
    if store.cluster is None:
        # NOR IN THE FILE'S FREE SPACE: no file of the state folder holds it
        for path in sorted(estate.state.rglob("*")):
            if path.is_file():
                assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path}:\n{said}"


@pytest.mark.parametrize("first", ["reconcile", "sync", "inventory-sync", "inventory-reconcile"],
                         ids=["legacy-only", "beside-clean", "inventory-sync", "inventory-reconcile"])
def test_an_upgrade_removes_a_legacy_credentialed_source(estate, first):
    """AN UPGRADE FROM v1.2.0 LEAVES NO CREDENTIAL, ON SQLITE (lane 3's ruling,
    opensoft/openRepoTools-code#89 comment 6941833120): `_an_upgrade`'s case, and no
    file of the state folder holds the secret afterwards."""
    _an_upgrade(estate, _IndexTables(estate), {}, first)


@pytest.mark.parametrize("first", ["reconcile", "sync", "inventory-sync", "inventory-reconcile"],
                         ids=["legacy-only", "beside-clean", "inventory-sync", "inventory-reconcile"])
def test_an_upgrade_removes_a_legacy_credentialed_source_from_postgres(t109_engine, tmp_path,
                                                                      first):
    """THE SAME UPGRADE ON POSTGRESQL 16: `url=` and `reader_url=` name the cluster's
    `t109_db` as its superuser. The schema `lanes_index` is made first, as the bootstrap
    makes it, since the index's own DDL makes its tables and not its schema."""
    import pgcluster
    cluster, _bootstrap = t109_engine
    estate = Estate(tmp_path / "up")
    cluster.psql("CREATE SCHEMA lanes_index;", dbname="t109_db")
    url = pgcluster.Database(cluster, "t109_db").url()
    estate.write_config(f"url={url}\nreader_url={url}\n")
    env = {"PATH": os.pathsep.join([str(cluster.bindir), estate.env["PATH"]])}
    _an_upgrade(estate, _IndexTables(estate, cluster), env, first)


def _sql_text(script: str) -> str:
    """`script` less the rows of each `COPY ... FROM STDIN`, which are data: its SQL."""
    out, data = [], False
    for line in script.splitlines():
        if data:
            data = line != "\\."
            continue
        data = bool(re.fullmatch(r"COPY [a-z_]+ \([a-z_, ]+\) FROM STDIN;", line))
        out.append(line)
    return "\n".join(out)


@pytest.mark.parametrize("case", ["empty-schema", "legacy-held", "cas-lost"])
def test_a_postgres_sync_reads_its_sources_in_the_provenance_call(estate, case):
    """A LEGACY SOURCE COSTS A POSTGRESQL SYNC NO psql CALL OF ITS OWN, on FAKE_PSQL
    (lane 1's hosted run 44046351293 of commit 13's previous build): the store's sources
    are read in the provenance's one call, and a DELETE goes only for a source to
    remove. [empty-schema]: the schema is as the bootstrap leaves it, with no table,
    and the version read fails as psql 16 says it under `VERBOSITY=sqlstate`, one
    located line of severity and SQLSTATE; the sync fills the schema, writes, and sends
    no DELETE. [legacy-held]: the store answers a legacy source and a control; ONE
    transaction takes the legacy source from every table that keys on a source, the
    control stays, and the secret is on no stream; and the removal comes BEFORE the
    label, the write and the compare-and-swap (SHOULD 7 of comment 6944416906).
    [cas-lost]: the write after the removal fails as the compare-and-swap's RAISE does,
    and the removal - the store's and the status file's - had already happened, which
    the run says, with no "nothing was written". NO SOURCE KEY IS IN ANY SQL TEXT
    (lane 3's ruling, comment 6944673181): every key reaches psql as COPY data alone,
    and a legacy key's rows are chosen by the server's rule, with no digest of it."""
    held = case != "empty-schema"
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log, vfile = estate.root / "psql.jsonl", estate.root / "version"
    vfile.write_text("1\n" if held else "")
    estate.write_config("url=postgresql://lanes_writer@db.invalid/qa\n"
                        "reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    if case == "cas-lost":
        filed.parent.mkdir(parents=True, exist_ok=True)
        filed.write_text(json.dumps({LEGACY_KEY: {"last_error": f"t {LEGACY_KEY} moved"}}),
                         encoding="utf-8")
    env = {"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log),
           "FAKE_PSQL_VERSION_FILE": str(vfile), "FAKE_PSQL_NO_TABLE": "1",
           "FAKE_PSQL_SOURCES": f"{CONTROL_KEY}\n{LEGACY_KEY}\n" if held else "",
           "FAKE_PSQL_CAS_LOST": "1" if case == "cas-lost" else ""}
    res = estate.index("sync", env=env)
    said = (res.stdout + res.stderr).replace(CONFIG_SECRET, "<the secret>")
    assert res.returncode == (1 if case == "cas-lost" else 0), said
    assert CONFIG_SECRET not in res.stdout + res.stderr, said
    calls = [json.loads(line)["stdin"] for line in log.read_text().splitlines()]
    legacy_digest = hashlib.sha256(LEGACY_KEY.encode("utf-8")).hexdigest()
    rule = load_indexer().PG_LEGACY_SQL
    for call in calls:
        # the removal's rule names the filed prefixes, and no key
        sql = _sql_text(call).replace(rule, "<the rule>")
        for mark in ("register:", "inventory:", "ledger:", CONFIG_SECRET, legacy_digest):
            assert mark not in sql, f"a key in the SQL:\n{call}".replace(
                CONFIG_SECRET, "<the secret>")
    assert any("CREATE TABLE IF NOT EXISTS" in c for c in calls) != held, said
    writes = [c for c in calls if "INSERT INTO lanes" in c]
    assert len(writes) == 1 and "lanes_index_cas" in writes[0], said
    reads = [c for c in calls if "UNION SELECT source FROM" in c]
    assert len(reads) == 1 and ("FROM provenance WHERE encode(sha256(convert_to(source, "
                                "'UTF8')), 'hex') = '") in reads[0], said
    drops = [c for c in calls if "DELETE FROM provenance WHERE" in c]
    if not held:
        assert drops == [] and "source(s) from the index" not in res.stdout, said
        return
    # THE REMOVAL FIRST: after the one read, before the write and its compare-and-swap,
    # and its line before the label
    assert len(drops) == 1, said
    assert calls.index(reads[0]) < calls.index(drops[0]) < calls.index(writes[0]), said
    filed_entries = 1 if case == "cas-lost" else 0
    removed = f"removed 1 source(s) from the index and {filed_entries} entry(s)"
    assert removed in res.stdout, said
    lines = drops[0].splitlines()
    tables = ["provenance", "source_files", "lanes", "log_lines", "register_lines",
              "lane_aliases", "transcript_pointers", "swap_states", "job_summaries", "worktrees"]
    assert lines[:3] == ["SET standard_conforming_strings = on;", "BEGIN;",
                         'SET LOCAL search_path TO "lanes_index";'], said
    assert lines[-1] == "COMMIT;", said
    # CHOSEN BY THE SERVER'S RULE, with no value made from a legacy key in the script
    assert sorted(lines[3:-1]) == sorted(f"DELETE FROM {t} WHERE {rule};" for t in tables), said
    if case == "legacy-held":
        assert res.stdout.index(removed) < res.stdout.index(" at register@"), said
        return
    # [cas-lost]: the compare-and-swap failed AFTER the removal, which stands
    kept = json.loads(filed.read_text(encoding="utf-8"))
    assert LEGACY_KEY not in kept, said
    assert ("provenance of this workstation's source moved under this sync; nothing more "
            "written; the removal said above stands") in res.stderr, said
    assert "nothing was written" not in res.stderr and "nothing written" not in res.stderr, said
    for entry in kept.values():
        assert CONFIG_SECRET not in json.dumps(entry), said


def _stopped(sqlstate: str) -> str:
    return f"psql stopped the index's script with SQLSTATE {sqlstate} (exit 3)"


#: (id, the call that fails - the provenance's `read` or the compare-and-swap's `write` -,
#: psql's exit, its stderr as psql 16 says it under VERBOSITY=sqlstate - each message one
#: located line, its severity and SQLSTATE alone (lane 3's ruling, question 1 of
#: opensoft/openRepoTools-code#89 comment 6955397261) -, the fixed words the run says). The
#: LAST located line decides.
PSQL_QUOTES = [
    # a localized NOTICE, then a localized error 42601: the last line, not the first
    ("localized", "read", 3,
     "psql:<stdin>:2: HINWEIS:  42P07\npsql:<stdin>:4: FEHLER:  42601\n", _stopped("42601")),
    # 42P01 read as `wiped`, after a NOTICE
    ("localized-42p01", "read", 3,
     "psql:<stdin>:2: HINWEIS:  42P07\npsql:<stdin>:3: FEHLER:  42P01\n",
     "psql: a table or schema the index needs does not exist (SQLSTATE 42P01)"),
    # P0001 and 23505 in the compare-and-swap's write: `CasLost`
    ("localized-cas-write", "write", 3, "psql:<stdin>:5: FEHLER:  P0001\n",
     "the provenance of this workstation's source moved under this sync; nothing written"),
    ("cas-23505-write", "write", 3, "psql:<stdin>:5: ERROR:  23505\n",
     "the provenance of this workstation's source moved under this sync; nothing written"),
    # any other code by its five characters, on a write
    ("copy-row-write", "write", 3, "psql:<stdin>:9: ERROR:  22P04\n", _stopped("22P04")),
    # lane 2's SHOULD 6b: the exit-2 and no-SQLSTATE branches
    ("exit-2", "read", 2,
     'psql: error: connection to server at "db.invalid" (192.0.2.1), port 5432 failed: '
     f'FATAL:  28P01: password authentication failed for user "{CONFIG_SECRET}"\n',
     "psql could not connect to the index's database, or lost its connection (exit 2); "
     "psql's own words are not shown"),
    ("no-sqlstate", "read", 3,
     f'psql:<stdin>:4: ERROR:  syntax error at or near "{CONFIG_SECRET}"\n',
     "psql exited 3 with no SQLSTATE; psql's own words are not shown, since they can quote "
     "the script"),
    # a located psql-side error, with no code, after a NOTICE: no SQLSTATE, not the NOTICE's
    ("psql-error-after-notice", "read", 3,
     "psql:<stdin>:2: NOTICE:  42P07\npsql:<stdin>:3: error: invalid command \\t104\n",
     "psql exited 3 with no SQLSTATE; psql's own words are not shown, since they can quote "
     "the script"),
    # the LAST LOCATED line, not the last line (lane 2's N3 of comment 6956694290): a located
    # line with a code, then a line with no locus, reads the located line's code
    ("unlocated-last-line", "read", 3,
     "psql:<stdin>:3: ERROR:  42P01\na line psql says with no locus\n",
     "psql: a table or schema the index needs does not exist (SQLSTATE 42P01)"),
    # a line in the verbose form, code then text: no SQLSTATE
    ("verbose-form", "read", 3,
     f'psql:<stdin>:4: ERROR:  42P01: relation "{CONFIG_SECRET}" does not exist\n'
     f'LINE 1: SELECT 1 FROM "{CONFIG_SECRET}"\n',
     "psql exited 3 with no SQLSTATE; psql's own words are not shown, since they can quote "
     "the script"),
]
PSQL_QUOTE_ROWS = {row[0]: row[1:] for row in PSQL_QUOTES}


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in PSQL_QUOTES])
def test_no_line_of_psqls_text_is_said_or_filed(estate, ident):
    """A FAILED INDEX CALL IS SAID IN FIXED WORDS (BLOCKING 5 of
    opensoft/openRepoTools-code#89 comment 6944416906): under `VERBOSITY=sqlstate` (lane
    3's ruling on comment 6955397261) psql's stderr is located lines of severity and
    SQLSTATE, and the LAST located line decides, not the last line; the sync fails with
    that SQLSTATE alone. No stream, no `last_error`, no file of the state folder and no
    line `status` prints holds the secret, and no stream and no `last_error` holds psql's
    locus (lane 2's N4 of comment 6956694290); the exit-2 and no-SQLSTATE branches say
    their own fixed words. The row is taken by its id, so no argument holds the secret
    (lane 2's SHOULD 1)."""
    on, code, stderr, words = PSQL_QUOTE_ROWS[ident]
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    quoted = estate.root / "quoted-stderr"
    quoted.write_text(stderr, encoding="utf-8")
    estate.write_config("url=postgresql://lanes_writer@db.invalid/qa\n"
                        "reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    env = {"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(estate.root / "psql.jsonl"),
           "FAKE_PSQL_STDERR_FILE": str(quoted), "FAKE_PSQL_STDERR_ON": on,
           "FAKE_PSQL_STDERR_EXIT": str(code)}
    res = estate.index("sync", env=env)
    st = estate.index("status", env=env)
    said = (f"{res.stdout}{res.stderr}\nstatus:\n{st.stdout}{st.stderr}"
            ).replace(CONFIG_SECRET, "<the secret>")
    assert res.returncode == 1, said
    assert words in res.stderr, said
    for shown in (res.stdout, res.stderr, st.stdout, st.stderr):
        assert CONFIG_SECRET not in shown and "ERROR:" not in shown, said
        # NO STREAM HOLDS psql's LOCUS (lane 2's N4 of comment 6956694290), so the checks are
        # not vacuous for the rows that carry a code
        assert "psql:<stdin>" not in shown, said
    kept = json.loads((estate.state / "openRepoTools" / "lanes-index.status.json")
                      .read_text(encoding="utf-8"))
    assert any(words in e.get("last_error", "") for e in kept.values()), said
    assert "psql:<stdin>" not in json.dumps(kept), said
    for path in sorted(estate.state.rglob("*")):
        if path.is_file():
            assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path}:\n{said}"


@pytest.mark.parametrize("case", ["unreadable", "unparseable", "unparseable-dry-run",
                                  "unparseable-first-write", "dangling-symlink", "symlink",
                                  "fifo", "wrong-shape-list", "wrong-shape-entry",
                                  "unparseable-inventory", "dry-run-then-failure",
                                  "preflight-failure", "dry-run-then-failure-inventory",
                                  "unreplaceable"])
def test_the_status_file_is_read_strictly(estate, case):
    """THE STATUS FILE, STRICTLY (lane 3's ruling on item 3, opensoft/openRepoTools-code#89
    comment 6944673181). [unreadable]: a status file that cannot be read fails the run
    with fixed words, and no store is made. [unparseable]: one that can be read and not
    parsed, a credential in its bytes, is replaced with an empty one as the run's first
    write, with one fixed WARNING line, and the sync goes on. [unparseable-dry-run]: a
    dry run says the same line, writes nothing and leaves the file as it is.
    [unparseable-first-write]: the store cannot be opened, so the sync fails at its next
    step; the file is already replaced, and the store's path is as it was. No byte of the
    file is printed. NOTHING BUT A REGULAR FILE, A DRY RUN THAT FILES NOTHING, AND THE ONE
    WARNING ON EVERY REPLACE (lane 3's ruling, B4 of comment 6947619546):
    [dangling-symlink], [symlink] and [fifo]: a path that is not a regular file fails the
    run as [unreadable] does and is left as it is, the symlink's target, which holds the
    key, too; a FIFO never holds the run. [wrong-shape-list] and [wrong-shape-entry]
    (lane 2's SHOULD 5a of comment 6947728883, IN by lane 3's 6947826234): JSON that is
    not an object of objects is replaced as [unparseable] is. [unparseable-inventory]
    (5b): the inventory's own sync replaces it so, its own check the first. [dry-run-then-
    failure]: a dry run that then fails at the store files nothing, its error included:
    the file's bytes are as they were, and the WARNING is said once. [preflight-failure]:
    a run that fails before its check (its `origin/<branch>` unread) files its error over
    the file with the one WARNING, never silently. W116's pre-review of commit 15:
    [dry-run-then-failure-inventory], the inventory's dry run that fails at the store files
    nothing either; [unreplaceable], a file the run cannot replace (its folder 0500) fails
    the run with fixed words, and the WARNING is said once, though both the cleanup and
    `_record_error` meet the file."""
    mod = load_indexer()
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    filed.parent.mkdir(parents=True, exist_ok=True)
    garbage = ('{"' + LEGACY_KEY + '": {"last_error": "' + CONFIG_SECRET + '"').encode("utf-8")
    target = estate.root / "t104-status-target.json"
    target_text = json.dumps({LEGACY_KEY: {"last_error": CONFIG_SECRET}})
    if case == "wrong-shape-list":
        garbage = json.dumps([LEGACY_KEY, {"last_error": CONFIG_SECRET}]).encode("utf-8")
    if case == "wrong-shape-entry":
        garbage = json.dumps({LEGACY_KEY: CONFIG_SECRET, "register:?": {}}).encode("utf-8")
    if case == "unreadable":
        filed.mkdir()
    elif case == "dangling-symlink":
        filed.symlink_to(estate.root / "t104-no-such-status.json")
    elif case == "symlink":
        target.write_text(target_text, encoding="utf-8")
        filed.symlink_to(target)
    elif case == "fifo":
        os.mkfifo(filed)
    else:
        filed.write_bytes(garbage)
    if case in ("unparseable-first-write", "dry-run-then-failure",
                "dry-run-then-failure-inventory"):
        estate.sqlite.mkdir(parents=True)
    act = {"unparseable-dry-run": ("reconcile", "--dry-run"),
           "dry-run-then-failure": ("reconcile", "--dry-run"),
           "dry-run-then-failure-inventory": ("reconcile", "--source", "inventory", "--dry-run"),
           "unparseable-inventory": ("sync", "--source", "inventory")}.get(case, ("sync",))
    env = {"LANES_BRANCH": "t104-no-such-branch"} if case == "preflight-failure" else {}
    if case == "unreplaceable":
        if os.geteuid() == 0:
            pytest.skip("root writes into a 0500 folder")
        (filed.parent / "lanes-index.lock").write_text("", encoding="utf-8")
        filed.parent.chmod(0o500)
    try:
        res = estate.index(*act, env=env, timeout=60)
    finally:
        if case == "unreplaceable":
            filed.parent.chmod(0o700)
    said = (res.stdout + res.stderr).replace(CONFIG_SECRET, "<the secret>")
    assert CONFIG_SECRET not in res.stdout + res.stderr, said
    if case in ("unreadable", "dangling-symlink", "symlink", "fifo"):
        assert res.returncode == 1, said
        assert f"unreachable: {mod.STATUS_UNREADABLE} - nothing written" in res.stderr, said
        assert not estate.sqlite.exists(), said
        if case in ("dangling-symlink", "symlink"):
            assert filed.is_symlink(), said
        if case == "symlink":
            assert target.read_text(encoding="utf-8") == target_text, said
        if case == "fifo":
            assert stat.S_ISFIFO(os.lstat(filed).st_mode), said
        return
    if case == "unreplaceable":
        # THE ONE WARNING, ONCE; the file as it was, and no copy of it left beside it
        assert res.returncode == 1 and res.stderr.count(mod.STATUS_UNPARSEABLE_WARNING) == 1, said
        assert f"unreachable: {mod.STATUS_UNREPLACEABLE} - nothing written" in res.stderr, said
        assert filed.read_bytes() == garbage, said
        assert sorted(p.name for p in filed.parent.iterdir()) == [
            "lanes-index.lock", "lanes-index.status.json"], said
        return
    if case.startswith("dry-run-then-failure"):
        # A DRY RUN FILES NOTHING, ITS ERROR INCLUDED: no `_record_error` over the file
        assert res.returncode == 1 and res.stderr.count(mod.STATUS_UNPARSEABLE_WARNING) == 1, said
        assert filed.read_bytes() == garbage, said
        assert estate.sqlite.is_dir() and list(estate.sqlite.iterdir()) == [], said
        return
    if case == "preflight-failure":
        # REPLACED BY `_record_error`, WITH THE ONE WARNING: only the error's own entry
        assert res.returncode == 1 and res.stderr.count(mod.STATUS_UNPARSEABLE_WARNING) == 1, said
        kept = json.loads(filed.read_text(encoding="utf-8"))
        assert LEGACY_KEY not in kept and len(kept) == 1, said
        assert all(name.startswith("register:") for name in kept), said
        for path in sorted(estate.state.rglob("*")):
            if path.is_file():
                assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path}:\n{said}"
        return
    if case == "unparseable-first-write":
        # THE RUN'S FIRST WRITE: replaced before the store was opened, which then failed
        assert res.returncode == 1 and res.stderr.count(mod.STATUS_UNPARSEABLE_WARNING) == 1, said
        assert estate.sqlite.is_dir() and list(estate.sqlite.iterdir()) == [], said
        kept = json.loads(filed.read_text(encoding="utf-8"))
        assert LEGACY_KEY not in kept and CONFIG_SECRET not in json.dumps(kept), said
        return
    assert res.returncode == 0, said
    assert res.stderr.count(mod.STATUS_UNPARSEABLE_WARNING) == 1, said
    if case == "unparseable-dry-run":
        assert filed.read_bytes() == garbage, said
        return
    kept = json.loads(filed.read_text(encoding="utf-8"))
    assert LEGACY_KEY not in kept and len(kept) == 1, said
    if case == "unparseable-inventory":
        assert list(kept) == ["inventory:Eagle"], said
    for path in sorted(estate.state.rglob("*")):
        if path.is_file():
            assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path}:\n{said}"


def _pg_rule(sql: str):
    """`PG_LEGACY_SQL` as Python reads it, for the shapes it holds: `source LIKE 'x%'` as a
    prefix, `~` and `!~` as a regex search (PostgreSQL's ARE and Python's re agree on these
    bracket classes, anchors and backslash-u escapes), and NOT, AND and OR. No `~*` is read:
    the rule holds none, and one would be a split this reading must not hide (lane 3's
    ruling on comment 6955397261)."""
    ops = {"~": "bool(re.search({0!r}, s))", "!~": "(not re.search({0!r}, s))"}
    py = re.sub(r"source LIKE '([^'%]*)%'", lambda m: f"s.startswith({m.group(1)!r})", sql)
    py = re.sub(r"source (!~|~\*|~) '([^']*)'", lambda m: ops[m.group(1)].format(m.group(2)), py)
    py = py.replace("NOT ", "not ").replace(" OR ", " or ").replace(" AND ", " and ")
    assert "source" not in py, py
    return lambda s: eval(py, {"re": re, "s": s})


def _rule_keys() -> list:
    """Every key the cases here file or seed, legacy and clean, and a few more shapes."""
    return ([LEGACY_KEY, CLEAN_KEY, CONTROL_KEY] + RAW_KEYS + CLEAN_FORMS +
            [f"register:{repository}" for _i, repository, _k in REGISTER_KEYS] +
            [key for _i, key, _k in REGISTER_KEYS] + [key for _i, key, _n in CAS_KEYS] +
            ["REGISTER:opensoft/x", "register:ssh://u:p@h/x", "register:git+https://t@h/x",
             "ledger:https://u@h/x", "inventory:Eagle", "ledger:Eagle", "register:x?Password=1",
             "register:https://h/p@x", "register:ssh://h:22/x", "",
             # B1'S EDGES (lane 3's ruling, comment 6947619546): a control character, and
             # `password`, optional spaces, then `=` or `%3D`, in any case; and near misses.
             # PostgreSQL's text holds no NUL, so the server's class begins at 0x01.
             "register:h/x\x1by", "inventory:Eagle\x7f", "ledger:a\nb", "register:a\tb",
             "register:h/x?PassWord  %3Dz", "inventory:password %3d1", "register:x?PASSWORD=1",
             "inventory:Pass Word=1", "register:x?passwordX=1", "register:x?password-=1",
             "register:x?password%3E1", "inventory:Eagle-password", "register:h/x#password",
             # C1 control characters (W116's pre-review of commit 15), and a no-break space,
             # which is none
             "register:h/x\x85y", "inventory:Eagle\x9b", "register:h/x\xa0y"] +
            # question 2 of lane 3's ruling on comment 6955397261, and its table
            [key for key, _legacy in PASSWORD_RULE_TABLE])


#: The characters `str.isspace()` holds that are not control characters: the 19 of the
#: ruling's 29 that the control-character term does not already refuse.
NON_CONTROL_SPACES = [c for c in range(sys.maxunicode + 1)
                      if chr(c).isspace() and not unicodedata.category(chr(c)).startswith("C")]
#: (key, legacy) - lane 3's ruling, question 2 of opensoft/openRepoTools-code#89 comment
#: 6955397261, and lane 2's SHOULD 3 of 6955285249: each separator before `=`, `+` and
#: percent-escapes legacy; the word itself literal, so its near misses stay clean
PASSWORD_RULE_TABLE = (
    [(f"register:x?password{chr(c)}=1", True) for c in NON_CONTROL_SPACES] +
    [("register:x?password+=1", True), ("register:x?password%20=1", True),
     ("register:x?password%09=1", True), ("register:x?password%2B=1", True),
     ("register:x?password%20%3d1", True), ("register:x?PASSWORD + %3D1", True),
     ("register:x?p%61ssword=1", False), ("register:x?pa\u017fsword=1", False)])


def test_the_key_rules_password_term_is_the_rulings():
    """THE KEY RULE'S `password` TERM, BY ITS ANSWERS (lane 3's ruling, question 2 of
    opensoft/openRepoTools-code#89 comment 6955397261; lane 2's SHOULD 3): each of the 19
    non-control separators before `=`, `+`, `%20`, `%09`, `%2B`, `%20%3d` and
    `PASSWORD + %3D` are legacy, and `p%61ssword=` and `pa` U+017F `sword=` are clean. THE
    CONSTANT: one ASCII raw text with no backslash-x, whose separator bracket holds exactly
    `+` and the characters `str.isspace()` holds, 29, written as backslash-u escapes."""
    mod = load_indexer()
    assert len(NON_CONTROL_SPACES) == 19, NON_CONTROL_SPACES
    wrong = [key for key, legacy in PASSWORD_RULE_TABLE if mod._is_legacy(key) is not legacy]
    assert wrong == [], [k.encode("unicode_escape").decode() for k in wrong]
    text = mod.PASSWORD_RULE
    assert text.isascii() and "\\x" not in text and "(?i" not in text, text
    head = "[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd](["
    assert text.startswith(head) and text.endswith("+]|%[0-9A-Fa-f]{2})*(=|%3[Dd])"), text
    bracket = text[len(head):text.index("+]|")]
    assert re.fullmatch(r"(\\u[0-9a-f]{4})+", bracket), bracket
    chars = {int(bracket[n + 2:n + 6], 16) for n in range(0, len(bracket), 6)}
    spaces = {c for c in range(sys.maxunicode + 1) if chr(c).isspace()}
    assert len(bracket) == 6 * 29 and chars == spaces and len(spaces) == 29, sorted(chars ^ spaces)
    assert f"source ~ '{text}'" in mod.PG_LEGACY_SQL and "~*" not in mod.PG_LEGACY_SQL


def test_the_servers_legacy_rule_is_the_indexers():
    """THE POSTGRESQL REMOVAL'S RULE IS `_is_legacy` (lane 1's coordinator, on commit 14's
    design): for every key the cases here file or seed, legacy and clean, and a few more
    shapes, `PG_LEGACY_SQL` read term by term answers as `_is_legacy` does."""
    mod = load_indexer()
    rule = _pg_rule(mod.PG_LEGACY_SQL)
    keys = _rule_keys()
    differ = [k for k in keys if rule(k) != mod._is_legacy(k)]
    assert differ == [], [k.replace(CONFIG_SECRET, "<the secret>") for k in differ]
    assert any(mod._is_legacy(k) for k in keys) and not all(mod._is_legacy(k) for k in keys)


def test_the_servers_legacy_rule_is_the_indexers_on_postgres(t109_engine):
    """THE SAME KEYS, CHOSEN BY POSTGRESQL 16 ITSELF (B1's edges, lane 3's ruling on
    opensoft/openRepoTools-code#89 comment 6947619546): each key a row of a table of its
    own, `PG_LEGACY_SQL` chooses exactly the rows `_is_legacy` calls legacy, so the server
    reads the rule's backslash-u escapes and its classes as Python does, with no `~*` in
    it (lane 3's ruling on comment 6955397261). Each key reaches the server as hex, so no
    quoting stands between the two."""
    cluster, _bootstrap = t109_engine
    mod = load_indexer()
    keys = _rule_keys()
    rows = ",\n".join(f"({n}, convert_from(decode('{key.encode('utf-8').hex()}', 'hex'), "
                       f"'UTF8'))" for n, key in enumerate(keys))
    script = ("CREATE TEMP TABLE t104_keys (n integer, source text);\n"
              f"INSERT INTO t104_keys VALUES\n{rows};\n"
              f"SELECT n FROM t104_keys WHERE {mod.PG_LEGACY_SQL} ORDER BY n;\n")
    chosen = [int(line) for line in cluster.psql(script, dbname="t109_db").stdout.split()]
    expected = [n for n, key in enumerate(keys) if mod._is_legacy(key)]
    assert chosen == expected, [keys[n].replace(CONFIG_SECRET, "<the secret>")
                                for n in sorted(set(chosen) ^ set(expected))]


def test_a_status_file_that_cannot_be_replaced_fails_the_cleanup(estate, monkeypatch):
    """A REPLACE THAT FAILS IS A FAILED RUN (BLOCKING 3 of
    opensoft/openRepoTools-code#89 comment 6944416906): with the status file's replace
    refused, the cleanup of a legacy entry raises `StoreUnusable` with fixed words, and
    so does the replace of a file that cannot be parsed; a dry run replaces nothing."""
    monkeypatch.setenv("XDG_STATE_HOME", str(estate.state))
    mod = load_indexer()
    mod._replace_status({LEGACY_KEY: {"last_error": f"t {LEGACY_KEY} moved"},
                         CLEAN_KEY: {"last_result": "current"}})

    def refuse(_data):
        raise PermissionError(13, "t104: the state folder refuses the replace")
    monkeypatch.setattr(mod, "_replace_status", refuse)
    with pytest.raises(mod.StoreUnusable) as caught:
        mod.drop_legacy_status()
    assert caught.value.detail == mod.STATUS_UNREPLACEABLE, caught.value
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    filed.write_text("{", encoding="utf-8")
    with pytest.raises(mod.StoreUnusable) as caught:
        mod.check_status_file(False)
    assert caught.value.detail == mod.STATUS_UNREPLACEABLE, caught.value
    mod.check_status_file(True)
    assert filed.read_text(encoding="utf-8") == "{"


class _VacuumFails:
    """A store connection whose VACUUM fails, as a full disk or a reader's lock fails it,
    after the removal's COMMIT: every time, or only the first `times` tries; `tries`
    counts them."""

    def __init__(self, conn, times=None):
        self.conn, self.times, self.tries = conn, times, 0

    def execute(self, sql, *args):
        if sql.strip().upper() == "VACUUM":
            self.tries += 1
            if self.times is None or self.tries <= self.times:
                raise sqlite3.OperationalError("t104: the VACUUM failed")
        return self.conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def _held_in(root: Path) -> list:
    return [str(p) for p in sorted(root.rglob("*"))
            if p.is_file() and CONFIG_SECRET.encode() in p.read_bytes()]


@pytest.mark.parametrize("journal", ["delete", "wal", "persist", "wal-frames", "retried"])
def test_a_scrub_that_fails_after_the_commit_is_finished_by_the_next_write(estate, monkeypatch,
                                                                           journal):
    """BLOCKING 4 of opensoft/openRepoTools-code#89 comment 6944416906: a removal whose
    VACUUM fails after its COMMIT leaves the scrub mark, which holds no key; the status
    file's cleanup has already happened; the run says no "nothing written"; and the next
    writer's cleanup, which removes nothing more, finishes the scrub, so that no file of
    the state folder holds the key.
    [delete]: the default journal. [wal]: the store set to WAL explicitly, and a
    reader's idle connection open through the next sync, so that only the scrub's TRUNCATE
    checkpoint empties the WAL. [persist]: the seed's last write made in the PERSIST
    journal, which keeps the old pages in the journal file; THE CASE SHOWS THE END STATE
    (lane 2's SHOULD 4b of comment 6947728883, IN by lane 3's 6947826234): a PERSIST
    journal does not outlive its connection, since a new connection reads `delete` and
    its first commit removes the stale journal, so the scrub's journal step is not what
    clears it here. [wal-frames] (lane 2's SHOULD 4a): a reader that has read, in a process
    of its own, holds the WAL from before the seed through the next sync, so no
    connection's close checkpoints it: the key is in the WAL's frames at the scrub, and
    only the scrub's TRUNCATE checkpoint takes it out. THE BOUNDED RETRY (lane 3's ruling,
    B2 of comment 6947619546): the failing run tries the VACUUM `SCRUB_ATTEMPTS` times,
    more than once, and only then exits 1 saying a scrub is pending; [retried]: a VACUUM
    that fails once is tried again in the same run, which ends 0 with the mark gone and no
    file holding the key."""
    assert estate.index("sync").returncode == 0
    store = _IndexTables(estate)
    tables = store.tables()
    own = store.sql("SELECT source FROM provenance")
    assert len(own) == 1, own
    if journal in ("wal", "wal-frames"):
        assert store.sql("PRAGMA journal_mode = WAL") == ["wal"]
    holder = None
    if journal == "wal-frames":
        # A READER IN A PROCESS OF ITS OWN, WHICH HAS READ: POSIX drops a process's locks on a
        # file at any close of it, and this case reads the store's files, so a reader in this
        # process would stop holding the WAL at the first `_held_in`
        holder = subprocess.Popen([sys.executable, "-I", "-c", _WAL_HOLDER, str(estate.sqlite)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        assert holder.stdout.readline() == "ready\n"
    try:
        _a_scrub_that_fails(estate, monkeypatch, journal, store, tables, own)
    finally:
        if holder is not None:
            holder.stdin.close()
            holder.wait(timeout=60)


#: A reader that opens the store, reads it once, says so, and holds it open until its stdin ends.
_WAL_HOLDER = ("import sqlite3, sys\n"
               "conn = sqlite3.connect(sys.argv[1])\n"
               "conn.execute('SELECT count(*) FROM sqlite_master').fetchall()\n"
               "print('ready', flush=True)\n"
               "sys.stdin.read()\n"
               "conn.close()\n")


def _a_scrub_that_fails(estate: Estate, monkeypatch, journal: str, store: _IndexTables,
                        tables: list, own: list) -> None:
    store.copy(tables, own[0], LEGACY_KEY)
    store.seed_every(tables, LEGACY_KEY)
    store.leave_in_free_space(LEGACY_KEY)
    if journal == "persist":
        conn = sqlite3.connect(str(estate.sqlite))
        conn.execute("PRAGMA secure_delete = OFF")
        assert conn.execute("PRAGMA journal_mode = PERSIST").fetchone()[0] == "persist"
        for t in tables:
            conn.execute(f"UPDATE {t} SET indexed_utc = indexed_utc || ' (v1.2.0)' "
                         f"WHERE source = ?", (LEGACY_KEY,))
        conn.commit()
        conn.close()
        journal_file = Path(str(estate.sqlite) + "-journal")
        assert CONFIG_SECRET.encode() in journal_file.read_bytes(), "the journal holds no key"
    else:
        store.touch(tables, LEGACY_KEY)
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    status = json.loads(filed.read_text(encoding="utf-8"))
    status[LEGACY_KEY] = {"last_error": f"2026-11-01T00:00:00Z the provenance of {LEGACY_KEY} moved"}
    filed.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setenv("XDG_STATE_HOME", str(estate.state))
    mod = load_indexer()
    monkeypatch.setattr(mod, "_record_error", lambda *args, **kwargs: None)
    live = mod.SqliteStore({"sqlite": str(estate.sqlite), "store": "sqlite"})
    live.open_write()
    live.conn = _VacuumFails(live.conn, 1 if journal == "retried" else None)
    _old, sources = live.provenance_and_sources(own[0])
    out, err = io.StringIO(), io.StringIO()
    # THE PAUSES, RECORDED (lane 2's SHOULD 2 of comment 6955285249)
    pauses: list = []
    real_sleep = mod.time.sleep
    monkeypatch.setattr(mod.time, "sleep", pauses.append)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod._guarded(lambda: mod._drop_legacy(live, "sync", sources), None)
    # THE ORIGINAL, NOT THE RECORDER (lane 2's N1 of comment 6956694290; lane 1's W116 NIT)
    monkeypatch.setattr(mod.time, "sleep", real_sleep)
    tries = live.conn.tries
    live.conn.close()
    said = f"{out.getvalue()}{err.getvalue()}".replace(CONFIG_SECRET, "<the secret>")
    mark = Path(str(estate.sqlite) + "-scrub")
    if journal == "retried":
        # `_guarded` hands back what the act returns, and `_drop_legacy` returns nothing
        assert rc is None and tries == 2, f"exit {rc}, tries {tries}:\n{said}"
        assert pauses == [0.5], pauses
        assert "a scrub is pending" not in said and not mark.exists(), said
        assert _held_in(estate.state) == [], said
        return
    assert rc == 1, said
    # WITHIN A BOUND, MORE THAN ONCE, THEN THE FIXED LINE THAT A SCRUB IS PENDING
    assert tries == mod.SCRUB_ATTEMPTS > 1, f"tries {tries}:\n{said}"
    assert pauses == [0.5, 1.0], pauses
    assert "a scrub is pending" in err.getvalue(), said
    assert "removed 1 source(s) from the index and 1 entry(s)" in out.getvalue(), said
    assert (f"unreachable: {mod.SCRUB_UNFINISHED} - nothing more written; the removal said "
            f"above stands") in err.getvalue(), said
    assert "nothing written" not in err.getvalue(), said
    assert mark.read_text(encoding="utf-8") == mod.SCRUB_MARK_TEXT, said
    assert LEGACY_KEY not in json.loads(filed.read_text(encoding="utf-8")), said
    assert all(rows == [] for _t, rows in store.rows(tables, LEGACY_KEY)), said
    # the free space still holds the key: the scrub is due, and the case is not vacuous
    assert _held_in(estate.state), said
    if journal == "wal-frames":
        # IN THE WAL'S FRAMES, AT THE SCRUB
        assert any(p.endswith("-wal") for p in _held_in(estate.state)), said
    holder = sqlite3.connect(str(estate.sqlite)) if journal == "wal" else None
    try:
        again = estate.index("sync")
        said += (f"\nthe next sync, exit {again.returncode}:\n{again.stdout}{again.stderr}"
                 .replace(CONFIG_SECRET, "<the secret>"))
        assert again.returncode == 0, said
        assert not mark.exists(), said
        assert _held_in(estate.state) == [], said
    finally:
        if holder is not None:
            holder.close()


def test_a_removal_that_fails_takes_nothing(estate):
    """ONE TRANSACTION (lane 1's addition A2 to opensoft/openRepoTools-code#89 comment
    6944416906): a trigger refuses the last table's DELETE of the legacy key, so the
    whole removal goes back. Every row of the key, its provenance's among them, is
    still there; the status file keeps its entry, since the store's removal comes first;
    and the run says "nothing written", truthfully, with no removal line."""
    assert estate.index("sync").returncode == 0
    store = _IndexTables(estate)
    tables = store.tables()
    own = store.sql("SELECT source FROM provenance")
    assert len(own) == 1, own
    store.copy(tables, own[0], LEGACY_KEY)
    store.seed_every(tables, LEGACY_KEY)
    held = store.rows(tables, LEGACY_KEY)
    assert all(rows for _t, rows in held), [(table, len(rows)) for table, rows in held]
    assert "worktrees" in tables, tables
    store.sql("CREATE TRIGGER t104_refuse BEFORE DELETE ON worktrees BEGIN "
              "SELECT RAISE(ABORT, 't104: the last table refused'); END")
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    status = json.loads(filed.read_text(encoding="utf-8"))
    status[LEGACY_KEY] = {"last_error": f"2026-11-01T00:00:00Z the provenance of {LEGACY_KEY} moved"}
    filed.write_text(json.dumps(status), encoding="utf-8")
    res = estate.index("sync")
    said = (res.stdout + res.stderr).replace(CONFIG_SECRET, "<the secret>")
    assert res.returncode == 1, said
    assert store.rows(tables, LEGACY_KEY) == held, said
    assert store.sql(f"SELECT count(*) FROM provenance WHERE source = '{LEGACY_KEY}'") == ["1"]
    assert LEGACY_KEY in json.loads(filed.read_text(encoding="utf-8")), said
    assert "source(s) from the index" not in res.stdout, said
    assert "- nothing written" in res.stderr, said
    assert CONFIG_SECRET not in res.stdout + res.stderr, said


def _a_legacy_source_held(estate: Estate) -> tuple:
    """A store whose own source is copied, row for row, under `LEGACY_KEY`, with a row of it
    in every table, its copies in the file's free space, and a status entry under it: (the
    store's tables, its own source, the status file, the legacy key's rows)."""
    assert estate.index("sync").returncode == 0
    store = _IndexTables(estate)
    tables = store.tables()
    own = store.sql("SELECT source FROM provenance")
    assert len(own) == 1, own
    store.copy(tables, own[0], LEGACY_KEY)
    store.seed_every(tables, LEGACY_KEY)
    store.leave_in_free_space(LEGACY_KEY)
    store.touch(tables, LEGACY_KEY)
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    status = json.loads(filed.read_text(encoding="utf-8"))
    status[LEGACY_KEY] = {"last_error": f"2026-11-01T00:00:00Z the provenance of {LEGACY_KEY} moved"}
    filed.write_text(json.dumps(status), encoding="utf-8")
    return store, tables, own[0], filed, store.rows(tables, LEGACY_KEY)


def _loaded_for_a_drop(estate: Estate, monkeypatch):
    """The indexer, loaded in this process with the estate's state folder, its
    `_record_error` a no-op, for `_run_drop`."""
    monkeypatch.setenv("XDG_STATE_HOME", str(estate.state))
    mod = load_indexer()
    monkeypatch.setattr(mod, "_record_error", lambda *args, **kwargs: None)
    return mod


def _run_drop(mod, estate: Estate, own: str, wrap=None) -> tuple:
    """`_drop_legacy` as a `sync` runs it, in this process, on SQLite, its connection
    wrapped by `wrap`: (its `_guarded` exit, stdout, stderr)."""
    live = mod.SqliteStore({"sqlite": str(estate.sqlite), "store": "sqlite"})
    live.open_write()
    if wrap is not None:
        live.conn = wrap(live.conn)
    _old, sources = live.provenance_and_sources(own)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod._guarded(lambda: mod._drop_legacy(live, "sync", sources), None)
    live.conn.close()
    return rc, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("scrub", ["scrubbed", "mark-kept"])
def test_a_status_file_that_cannot_be_replaced_still_scrubs(estate, monkeypatch, scrub):
    """THE STATUS FILE DOES NOT HOLD THE SCRUB BACK (lane 3's ruling, B2 of
    opensoft/openRepoTools-code#89 comment 6947619546, its second part): the store's
    removal commits, the status file's replace then fails, and the run still takes the
    scrub's steps before it exits 1 with the replace's fixed words. [scrubbed]: no file
    of the store holds the key, and the mark is gone. [mark-kept]: a VACUUM that fails at
    every try leaves the mark, the run also says the constant line that a scrub is
    pending, and the next writer finishes the scrub. The status file, never replaced,
    keeps its legacy entry until that next writer removes it."""
    store, tables, own, filed, _held = _a_legacy_source_held(estate)
    mod = _loaded_for_a_drop(estate, monkeypatch)

    def refuse(_data):
        raise PermissionError(13, "t104: the state folder refuses the replace")
    monkeypatch.setattr(mod, "_replace_status", refuse)
    rc, out, err = _run_drop(mod, estate, own, _VacuumFails if scrub == "mark-kept" else None)
    said = f"{out}{err}".replace(CONFIG_SECRET, "<the secret>")
    assert rc == 1, said
    assert "removed 1 source(s) from the index" in out, said
    assert (f"unreachable: {mod.STATUS_UNREPLACEABLE} - nothing more written; the removal "
            f"said above stands") in err, said
    assert LEGACY_KEY in json.loads(filed.read_text(encoding="utf-8")), said
    assert all(rows == [] for _t, rows in store.rows(tables, LEGACY_KEY)), said
    mark = Path(str(estate.sqlite) + "-scrub")
    in_store = [p for p in _held_in(estate.state) if p != str(filed)]
    if scrub == "scrubbed":
        assert not mark.exists() and in_store == [], said
        assert "a scrub is pending" not in err, said
    else:
        assert mark.read_text(encoding="utf-8") == mod.SCRUB_MARK_TEXT and in_store, said
        # THE FIXED LINE THAT A SCRUB IS PENDING, BESIDE THE REPLACE'S ERROR
        assert f"unreachable: {mod.SCRUB_UNFINISHED}" in err, said
    again = estate.index("sync")
    said += (f"\nthe next sync, exit {again.returncode}:\n{again.stdout}{again.stderr}"
             .replace(CONFIG_SECRET, "<the secret>"))
    assert again.returncode == 0 and not mark.exists(), said
    assert _held_in(estate.state) == [], said


@pytest.mark.parametrize("case", ["folder-sync", "mark-sync", "mark-file", "reused",
                                  "mark-symlink"])
def test_a_scrub_mark_that_cannot_be_made_removes_nothing(estate, monkeypatch, case):
    """THE MARK AND ITS FOLDER ARE SYNCED BEFORE THE TRANSACTION BEGINS (lane 3's ruling, B3
    of opensoft/openRepoTools-code#89 comment 6947619546; lane 2's SHOULD 4c of comment
    6947728883, IN by lane 3's 6947826234). [folder-sync]: the folder's fsync fails;
    [mark-file]: the mark's path is a folder, so no mark can be written. Either is the
    fixed `SCRUB_UNMARKED`, the run exits 1 saying "nothing written", truthfully, and NO
    REMOVAL BEGAN: every row of the legacy key is there, and the status file keeps its
    entry. A mark that was written is 0600 and holds no key. [reused]: a mark an earlier
    run left, 0644 and of other text, is made 0600 again and rewritten, which a VACUUM that
    fails keeps to be seen. [mark-symlink] (W116's pre-review of commit 15): the mark's path
    is a link to another file, which is neither written, truncated nor made 0600: the
    mark cannot be made, as in [mark-file]. [mark-sync] (lane 2's BLOCKING 1 of comment
    6955285249, IN as a SHOULD by lane 3's 6955397261): the mark's own fsync fails, which
    is `SCRUB_UNMARKED` too, the rows held and the entry kept."""
    store, tables, own, filed, held = _a_legacy_source_held(estate)
    mark = Path(str(estate.sqlite) + "-scrub")
    if case == "mark-file":
        mark.mkdir()
    if case == "reused":
        mark.write_text("t104: an earlier run's mark\n", encoding="utf-8")
        mark.chmod(0o644)
    target = estate.root / "t104-mark-target"
    if case == "mark-symlink":
        target.write_text("t104: not the mark\n", encoding="utf-8")
        target.chmod(0o644)
        mark.symlink_to(target)
    mod = _loaded_for_a_drop(estate, monkeypatch)
    if case == "folder-sync":
        real = os.fsync

        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(5, "t104: the folder's fsync failed")
            return real(fd)
        monkeypatch.setattr(mod.os, "fsync", fsync)
    if case == "mark-sync":
        real_sync = os.fsync

        def fsync_file(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError(5, "t104: the mark's fsync failed")
            return real_sync(fd)
        monkeypatch.setattr(mod.os, "fsync", fsync_file)
    rc, out, err = _run_drop(mod, estate, own, _VacuumFails if case == "reused" else None)
    said = f"{out}{err}".replace(CONFIG_SECRET, "<the secret>")
    assert rc == 1, said
    if case == "reused":
        assert stat.S_IMODE(mark.stat().st_mode) == 0o600, said
        assert mark.read_text(encoding="utf-8") == mod.SCRUB_MARK_TEXT, said
        assert all(rows == [] for _t, rows in store.rows(tables, LEGACY_KEY)), said
        return
    assert f"unreachable: {mod.SCRUB_UNMARKED} - nothing written" in err, said
    assert "source(s) from the index" not in out, said
    assert store.rows(tables, LEGACY_KEY) == held, said
    assert LEGACY_KEY in json.loads(filed.read_text(encoding="utf-8")), said
    if case == "folder-sync":
        assert stat.S_IMODE(mark.stat().st_mode) == 0o600, said
        assert mark.read_text(encoding="utf-8") == mod.SCRUB_MARK_TEXT, said
    if case == "mark-symlink":
        assert mark.is_symlink(), said
        assert target.read_text(encoding="utf-8") == "t104: not the mark\n", said
        assert stat.S_IMODE(target.stat().st_mode) == 0o644, said


#: (id, the store, the source's kind, the value given): B1's refused forms (lane 3's ruling,
#: opensoft/openRepoTools-code#89 comment 6947619546), a register as `workspace.yaml`'s
#: `repository:` names it and a workstation's name as `LANES_WORKSTATION` gives it to
#: `lanes-edit.sh workstation`, which answers it as it stands
LEGACY_INPUTS = [
    ("register-password", "postgres", "register", f"password={CONFIG_SECRET}"),
    ("register-spaced-encoded", "sqlite", "register",
     f"https://{REGISTER_HOST}/{REGISTER_PATH}/r?PassWord  %3D{CONFIG_SECRET}"),
    ("register-control", "postgres", "register",
     f"https://{REGISTER_HOST}/{REGISTER_PATH}/r\x1b{CONFIG_SECRET}"),
    ("inventory-password", "sqlite", "inventory", f"password={CONFIG_SECRET}"),
    ("inventory-userinfo", "postgres", "inventory", f"https://{CONFIG_SECRET}@{REGISTER_HOST}/x"),
    ("inventory-control", "sqlite", "inventory", f"Eagle\x7f{CONFIG_SECRET}"),
    # C1 control characters (W116's pre-review of commit 15)
    ("register-c1", "sqlite", "register",
     f"https://{REGISTER_HOST}/{REGISTER_PATH}/r\x85{CONFIG_SECRET}"),
    ("inventory-c1", "postgres", "inventory", f"Eagle\x9b{CONFIG_SECRET}"),
]


@pytest.mark.parametrize("ident", [pytest.param(row[0], id=row[0]) for row in LEGACY_INPUTS])
def test_a_source_this_build_would_call_legacy_is_refused(estate, ident):
    """NOTHING TODAY'S CODE FILES IS LEGACY (lane 3's ruling, B1 of
    opensoft/openRepoTools-code#89 comment 6947619546): a register or a workstation's name
    that `_is_legacy` would call legacy - `password=`, `password` and spaces then `%3D` in
    another case, a control character, an inventory name holding URL userinfo - is
    refused with exit 2 and fixed words that do not echo it, BEFORE anything is printed,
    filed or sent, by every act that makes the key: `sync`, `reconcile` and its dry run,
    `export` and `status`. No stream, no file of the state folder and, on PostgreSQL (a
    FAKE psql), no call holds the secret or the key's digest; the writers make no psql
    call at all, and `status`'s reads name no key. The row is taken by its id, so no
    argument holds the secret (lane 2's SHOULD 1 of comment 6955285249)."""
    store_kind, kind, value = {row[0]: row[1:] for row in LEGACY_INPUTS}[ident]
    mod = load_indexer()
    env: dict = {}
    if kind == "register":
        # the helper finds the workspace by `LANES_WORKSPACE_ROOT`, as `_an_upgrade`'s does,
        # so that `workspace.yaml`'s `repository:` is read by `source_of` alone
        (estate.agents / "workspace.yaml").write_text(
            f"repository: {value}\npath: {estate.ws}\n", encoding="utf-8")
        env.update(LANES_WORKSPACE_ROOT=str(estate.ws))
        words = mod.REGISTER_KEY_REFUSED
        acts = [("sync",), ("reconcile", "--dry-run"), ("reconcile",), ("export", "--out")]
    else:
        env.update(LANES_WORKSTATION=value)
        words = mod.INVENTORY_KEY_REFUSED
        acts = [("sync", "--source", "inventory"),
                ("reconcile", "--source", "inventory", "--dry-run"),
                ("reconcile", "--source", "inventory")]
    log = estate.root / "psql.jsonl"
    if store_kind == "postgres":
        fake = estate.root / "pgfake"
        fake.mkdir()
        (fake / "psql").write_text(FAKE_PSQL)
        (fake / "psql").chmod(0o755)
        estate.write_config("url=postgresql://lanes_writer@db.invalid/qa\n"
                            "reader_url=postgresql://lanes_reader@db.invalid/qa\n")
        env.update(PATH=estate.path_with(fake), FAKE_PSQL_LOG=str(log))
    out = estate.root / "t104-out"
    out.mkdir()
    said = ""
    for act in acts + [("status",)]:
        args = act + ((out,) if act[0] == "export" else ())
        res = estate.index(*args, env=env)
        shown = res.stdout + res.stderr
        said += f"\n{' '.join(act)}, exit {res.returncode}:\n{shown}".replace(
            CONFIG_SECRET, "<the secret>")
        assert res.returncode == 2, said
        assert CONFIG_SECRET not in shown, said
        if act[0] == "export":
            assert (out / "why").read_text(encoding="utf-8") == f"refused: {words}\n", said
        else:
            assert words in shown, said
        if act[0] != "status":
            # NOTHING SENT: no psql call at all, before `status`'s own reads
            assert not log.exists(), said
    keys = [f"{kind}:{value}", f"register:{value}", f"inventory:{value}"]
    digests = [hashlib.sha256(key.encode("utf-8")).hexdigest() for key in keys]
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    for mark in [CONFIG_SECRET] + digests:
        assert mark not in calls, f"a psql call holds the key:\n{said}"
    for path in sorted(estate.state.rglob("*")) + sorted(out.rglob("*")):
        if path.is_file():
            assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path}:\n{said}"
    assert not estate.sqlite.exists(), said


def test_the_workspace_helpers_words_are_not_relayed(estate):
    """NO CREDENTIAL THROUGH THE HELPER'S WORDS (lane 1, under B1 of
    opensoft/openRepoTools-code#89 comment 6947619546): where `workspace.yaml`'s
    `repository:` is not the checkout's, `lanes-edit.sh workspace-root` names both as they
    stand, and its first line went to the run's streams and, through `_record_error`, the
    status file, before any key was made. `workspace.yaml` names a URL with a token that
    is not this checkout's: `sync`, `status` and `export` say fixed words, and no stream,
    no file of the state folder and no file `export` writes holds the token."""
    (estate.agents / "workspace.yaml").write_text(
        f"repository: https://x-access-token:{CONFIG_SECRET}@{REGISTER_HOST}/{REGISTER_PATH}/r"
        f".git\npath: {estate.ws}\n", encoding="utf-8")
    out = estate.root / "t104-out"
    out.mkdir()
    words = "`lanes-edit.sh workspace-root` exited 1: the workspace repository could not be found"
    said = ""
    for act in (("sync",), ("status",), ("export", "--out", out)):
        res = estate.index(*act)
        shown = res.stdout + res.stderr
        said += f"\n{act[0]}, exit {res.returncode}:\n{shown}".replace(CONFIG_SECRET, "<the secret>")
        assert res.returncode == (3 if act[0] == "export" else 1), said
        assert CONFIG_SECRET not in shown, said
        assert words in (shown if act[0] != "export" else
                         (out / "why").read_text(encoding="utf-8")), said
    for path in sorted(estate.state.rglob("*")) + sorted(out.rglob("*")):
        if path.is_file():
            assert CONFIG_SECRET.encode() not in path.read_bytes(), f"{path}:\n{said}"


def test_export_reads_no_legacy_inventory_source(estate):
    """`export --worktrees` READS NO LEGACY INVENTORY SOURCE (lane 3's ruling, S6 of
    opensoft/openRepoTools-code#89 comment 6947619546): the store holds, beside a clean
    `inventory:Heron`, an `inventory:password=` source and an inventory key holding URL
    userinfo, each with a provenance row and a worktree whose path holds the secret. The
    export writes the clean source's tree and names it, and no file it writes holds the
    secret or the legacy sources' lane."""
    assert estate.index("sync").returncode == 0
    legacy = [f"inventory:password={CONFIG_SECRET}",
              f"inventory:https://{CONFIG_SECRET}@{REGISTER_HOST}/x"]
    conn = sqlite3.connect(str(estate.sqlite))
    for source in legacy + ["inventory:Heron"]:
        lane = "t104-clean" if source == "inventory:Heron" else "t104-legacy"
        path = f"/w/{lane}" if source == "inventory:Heron" else f"/w/{lane}/{CONFIG_SECRET}"
        conn.execute("INSERT INTO provenance (source, commit_sha, generation, indexed_utc, "
                     "schema_version) VALUES (?, ?, 1, '2026-11-01T00:00:00Z', 1)",
                     (source, "a" * 64))
        conn.execute("INSERT INTO worktrees (source, record_id, workstation, lane, path, branch, "
                     "digest, indexed_utc, schema_version) VALUES (?, ?, 'Heron', ?, ?, ?, 'd', "
                     "'2026-11-01T00:00:00Z', 1)", (source, f"{lane}-tree", lane, path, f"lane/{lane}"))
    conn.commit()
    conn.close()
    out = estate.root / "t104-exp"
    out.mkdir()
    exp = estate.index("export", "--out", out, "--worktrees")
    written = {p.name: p.read_text(encoding="utf-8") for p in sorted(out.iterdir())}
    said = f"exit {exp.returncode}:\n{exp.stdout}{exp.stderr}\n{written}".replace(
        CONFIG_SECRET, "<the secret>")
    assert exp.returncode == 0, said
    text = "".join(written.values())
    assert "t104-clean" in text and "inventory:Heron" in text, said
    assert "t104-legacy" not in text and CONFIG_SECRET not in text, said
    assert CONFIG_SECRET not in exp.stdout + exp.stderr, said


@pytest.mark.parametrize("ending", ["no-change", "unknown-prior", "not-a-descendant",
                                    "inventory-no-change"])
def test_no_line_says_nothing_written_after_a_removal(estate, ending):
    """NO "nothing written" AFTER A REMOVAL, ON A NORMAL EXIT EITHER (lane 3's ruling, S7 of
    opensoft/openRepoTools-code#89 comment 6947619546): a legacy source is held, the run
    removes it, and then ends by a path that writes nothing of its own: [no-change], a
    `reconcile` that finds nothing differs; [unknown-prior], a `sync` whose provenance
    names a commit this checkout lacks; [not-a-descendant], a `sync` whose provenance
    names a commit off the branch's line, which exits 1; [inventory-no-change], the
    inventory's `reconcile` that finds nothing differs. Each says the removal, then
    "nothing more written; the removal said above stands", and never "nothing written",
    on its streams or in the status file."""
    inventory = ending.startswith("inventory")
    first = ("sync", "--source", "inventory") if inventory else ("sync",)
    assert estate.index(*first).returncode == 0
    store = _IndexTables(estate)
    tables = store.tables()
    own = store.sql("SELECT source FROM provenance")
    assert len(own) == 1, own
    store.copy(tables, own[0], LEGACY_KEY)
    store.seed_every(tables, LEGACY_KEY)
    if ending == "unknown-prior":
        store.sql(f"UPDATE provenance SET commit_sha = '{'f' * 40}' WHERE source = '{own[0]}'")
    if ending == "not-a-descendant":
        tree = estate._git("rev-parse", "HEAD^{tree}").strip()
        orphan = estate._git("commit-tree", tree, "-m", "t104: off the branch's line").strip()
        store.sql(f"UPDATE provenance SET commit_sha = '{orphan}' WHERE source = '{own[0]}'")
    act = {"no-change": ("reconcile",),
           "inventory-no-change": ("reconcile", "--source", "inventory")}.get(ending, ("sync",))
    res = estate.index(*act)
    filed = estate.state / "openRepoTools" / "lanes-index.status.json"
    kept = filed.read_text(encoding="utf-8")
    said = f"exit {res.returncode}:\n{res.stdout}{res.stderr}\nstatus file: {kept}".replace(
        CONFIG_SECRET, "<the secret>")
    assert res.returncode == (1 if ending == "not-a-descendant" else 0), said
    assert "removed 1 source(s) from the index" in res.stdout, said
    assert "nothing more written; the removal said above stands" in res.stdout, said
    assert "nothing written" not in res.stdout + res.stderr, said
    assert "nothing written" not in kept and LEGACY_KEY not in json.loads(kept), said
    assert all(rows == [] for _t, rows in store.rows(tables, LEGACY_KEY)), said


@pytest.mark.parametrize("act", ["sync", "reconcile"])
def test_origin_moving_after_a_removal_says_nothing_more_written(estate, monkeypatch, act):
    """S7'S CLASS WHERE origin KEEPS MOVING (W116's pre-review of commit 15): a run that
    removed a legacy source and then reads origin moving under it at every round ends
    saying "nothing more written; the removal said above stands", and never "nothing
    written": [sync] after its five rounds, [reconcile] after its three reads. The run's
    act is replaced by one that removes and then reads origin moving."""
    helper = estate.root / "t104-helper"
    helper.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    helper.chmod(0o755)
    monkeypatch.setenv("XDG_STATE_HOME", str(estate.state))
    monkeypatch.setenv("LANES_EDIT", str(helper))
    monkeypatch.delenv("LANES_INDEX", raising=False)
    mod = load_indexer()

    def removed_then_moved(mode, requested, dry_run):
        mod._REMOVED["any"] = True
        raise mod.SourceMoved(f"origin/main moved from {'a' * 12} while the owners were read; "
                              f"nothing was written from that read")
    monkeypatch.setattr(mod, "run_index", removed_then_moved)
    monkeypatch.setattr(mod, "_record_error", lambda *args, **kwargs: None)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod.cmd_sync(None) if act == "sync" else mod.cmd_reconcile(None, False)
    said = out.getvalue() + err.getvalue()
    assert rc == (0 if act == "sync" else 1), said
    assert "kept moving through" in said, said
    assert "nothing more written; the removal said above stands" in said, said
    assert "nothing written" not in said, said


@pytest.mark.parametrize("case", ["lock-held", "mark-pending"])
def test_a_legacy_register_is_refused_before_the_lock(estate, case):
    """A PLAIN `sync` REFUSES A LEGACY REGISTER BEFORE THE LOCK (W116's pre-review of commit
    15, under B1 of opensoft/openRepoTools-code#89 comment 6947619546): `workspace.yaml`
    names a `password=` register, and `sync` has no `--source`. [lock-held]: another
    process holds the lock, and the sync exits 2 with the refusal, not 0 with a mark of its
    own left. [mark-pending]: an inventory sync's mark is on the disk, and the sync exits 2
    with that mark where it was, for the inventory's next sync."""
    import fcntl
    (estate.agents / "workspace.yaml").write_text(
        f"repository: password={CONFIG_SECRET}\npath: {estate.ws}\n", encoding="utf-8")
    folder = estate.state / "openRepoTools"
    folder.mkdir(parents=True, exist_ok=True)
    mark = folder / "lanes-index.rerun-inventory"
    holder = None
    if case == "lock-held":
        holder = open(folder / "lanes-index.lock", "a+")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        mark.write_text("2026-11-17T00:00:00Z\n", encoding="utf-8")
    try:
        res = estate.index("sync", env={"LANES_WORKSPACE_ROOT": str(estate.ws)})
    finally:
        if holder is not None:
            holder.close()
    said = (res.stdout + res.stderr).replace(CONFIG_SECRET, "<the secret>")
    assert res.returncode == 2 and load_indexer().REGISTER_KEY_REFUSED in res.stderr, said
    assert "another sync holds" not in said, said
    assert CONFIG_SECRET not in res.stdout + res.stderr, said
    assert not (folder / "lanes-index.rerun").exists(), said
    if case == "mark-pending":
        assert mark.read_text(encoding="utf-8") == "2026-11-17T00:00:00Z\n", said


def test_a_refused_register_mark_leaves_the_marks_behind_it_synced(estate):
    """A HOLDER THAT TAKES A REFUSED REGISTER'S MARK STILL SYNCS THE MARKS BEHIND IT
    (W116's re-check of commit 15, its exp/lock3, through the real path): `workspace.yaml`
    names a `password=` register. An inventory sync holds the lock; while it lists the
    worktrees, a plain `sync` whose `lanes-edit.sh workspace-root` cannot answer gets past
    the check before the lock and leaves a register mark, and an inventory sync leaves an
    inventory mark, each exiting 0. The holder's next round takes both, the register's
    first: it says the refusal and exits 2, and it syncs the inventory for the mark it
    took, so the helper lists the worktrees a second time. No mark is left, and the key is
    on no stream."""
    (estate.agents / "workspace.yaml").write_text(
        f"repository: password={CONFIG_SECRET}\npath: {estate.ws}\n", encoding="utf-8")
    log = estate.root / "helper.log"
    spawned = estate.root / "spawned"
    plain, inventory = estate.root / "plain.out", estate.root / "inventory.out"
    run = f"{shlex.quote(sys.executable)} -I -B {shlex.quote(str(INDEXER))}"
    stub = estate.root / "lock-helper" / "lanes-edit.sh"
    stub.parent.mkdir()
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> {shlex.quote(str(log))}\n'
        'case "$1" in\n'
        "  workspace-root)\n"
        f'    if [ -n "${{T104_WS_OK:-}}" ]; then echo {shlex.quote(str(estate.ws))}; exit 0; fi\n'
        "    echo 'the workspace repository could not be found' >&2; exit 1 ;;\n"
        "  workstation) printf 'Eagle\\tseam\\n'; exit 0 ;;\n"
        "  worktrees)\n"
        f"    if [ ! -e {shlex.quote(str(spawned))} ]; then\n"
        f"      : > {shlex.quote(str(spawned))}\n"
        f"      env -u T104_WS_OK -u LANES_INDEX {run} sync > {shlex.quote(str(plain))} 2>&1\n"
        f'      echo "exit $?" >> {shlex.quote(str(plain))}\n'
        f"      env -u LANES_INDEX {run} sync --source inventory > "
        f"{shlex.quote(str(inventory))} 2>&1\n"
        f'      echo "exit $?" >> {shlex.quote(str(inventory))}\n'
        "    fi\n"
        "    exit 8 ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n", encoding="utf-8")
    stub.chmod(0o755)
    res = estate.index("sync", "--source", "inventory",
                       env={"LANES_EDIT": str(stub), "T104_WS_OK": "1"})
    later = {path.name: path.read_text(encoding="utf-8") if path.exists() else ""
             for path in (plain, inventory)}
    asked = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    said = (f"holder exit {res.returncode}:\n{res.stdout}{res.stderr}\n"
            + "".join(f"{name}:\n{text}\n" for name, text in later.items())
            + "helper:\n" + "\n".join(asked)).replace(CONFIG_SECRET, "<the secret>")
    for text in later.values():
        assert "another sync holds" in text and text.endswith("exit 0\n"), said
    assert res.returncode == 2 and load_indexer().REGISTER_KEY_REFUSED in res.stderr, said
    assert asked.count("worktrees --all") == 2, said
    folder = estate.state / "openRepoTools"
    assert sorted(path.name for path in folder.glob("lanes-index.rerun*")) == [], said
    for shown in (res.stdout, res.stderr, *later.values()):
        assert CONFIG_SECRET not in shown, said


def test_the_index_runs_psql_with_the_rulings_arguments(estate):
    """THE INDEX'S psql ARGUMENTS, WHOLE (lane 3's ruling, question 1 of
    opensoft/openRepoTools-code#89 comment 6955397261): every call a sync makes on a
    PostgreSQL store passes exactly these, `VERBOSITY=sqlstate` among them."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log = estate.root / "psql.jsonl"
    estate.write_config("url=postgresql://lanes_writer@db.invalid/qa\n"
                        "reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    res = estate.index("sync", env={"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log)})
    assert res.returncode == 0, res.stderr.replace(CONFIG_SECRET, "<the secret>")
    calls = [json.loads(line)["args"] for line in log.read_text().splitlines()]
    assert calls and all(args == ["--no-psqlrc", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-v",
                                  "VERBOSITY=sqlstate", "-v", "SHOW_CONTEXT=never", "-f", "-"]
                         for args in calls), calls


def test_the_register_path_keeps_verbosity_verbose():
    """THE REGISTER PATH KEEPS `VERBOSITY=verbose` (lane 3's ruling on comment 6955397261,
    whose register contract reads DETAIL; lane 2's N3 of comment 6956694290): only the
    index's psql takes `sqlstate`."""
    mod = load_indexer()
    args = list(mod.REGISTER_PSQL_ARGS)
    pairs = list(zip(args, args[1:]))
    assert ("-v", "VERBOSITY=verbose") in pairs, args
    assert not any(a.startswith("VERBOSITY=") and a != "VERBOSITY=verbose" for a in args), args
    assert ("-v", "VERBOSITY=sqlstate") in list(
        zip(mod.INDEX_PSQL_ARGS, mod.INDEX_PSQL_ARGS[1:])), mod.INDEX_PSQL_ARGS


def test_a_failed_status_replace_leaves_no_copy_behind(estate, monkeypatch):
    """NO COPY OF THE STATUS FILE IS LEFT (W116's pre-review of commit 15): a replace whose
    rename fails takes the file it made with it, which held what the replace was to write,
    a legacy key among it."""
    monkeypatch.setenv("XDG_STATE_HOME", str(estate.state))
    mod = load_indexer()

    reached = []

    def refuse(_src, dst):
        reached.append(Path(dst).name)
        raise PermissionError(13, "t104: the rename is refused")
    monkeypatch.setattr(mod.os, "replace", refuse)
    with pytest.raises(OSError):
        mod._replace_status({LEGACY_KEY: {"last_error": f"t {LEGACY_KEY} moved"}})
    monkeypatch.undo()
    # THE REFUSED RENAME WAS REACHED (lane 2's NIT 3 of comment 6955285249)
    assert reached == ["lanes-index.status.json"], reached
    left = sorted(p.name for p in (estate.state / "openRepoTools").iterdir())
    assert left == [], left


#: (id, the script, the SQLSTATE `_failure` reads) on psql 16 itself, with the index's own
#: arguments (lane 3's ruling, question 1 of opensoft/openRepoTools-code#89 comment
#: 6955397261)
PSQL16_CASES = {
    "english": ("SELECT 1;\nSELECT x FROM t104_no_such_table;\n", "42P01"),
    "german": ("SELECT 1;\nSELECT x FROM t104_no_such_table;\n", "42P01"),
    # a NOTICE (42P07), then the error: the last located line, not the first
    "notice-then-error": ("CREATE TEMP TABLE IF NOT EXISTS t104_n (n integer);\n"
                          "CREATE TEMP TABLE IF NOT EXISTS t104_n (n integer);\n"
                          "SELECT x FROM t104_no_such_table;\n", "42P01"),
    # a value whose text holds a newline and a whole located line, cast to integer
    "newline-value": ("SELECT (E'1\\npsql:<stdin>:1: ERROR:  42P01')::integer;\n", "22P02"),
    # a RAISE whose message forges a located line
    "raise-forged": ("DO $$BEGIN RAISE EXCEPTION E'x\\npsql:<stdin>:1: ERROR:  42P01'; END$$;\n",
                     "P0001"),
}


@pytest.mark.parametrize("case", list(PSQL16_CASES))
def test_the_index_reads_psql_16s_own_error_line(t109_engine, case):
    """THE INDEX'S psql ON psql 16 ITSELF (lane 3's ruling, question 1 of
    opensoft/openRepoTools-code#89 comment 6955397261): with `INDEX_PSQL_ARGS`
    (`VERBOSITY=sqlstate`, the script as `-f -`), each message is one located line of
    severity and SQLSTATE, with no text: [english]'s stderr is exactly
    `psql:<stdin>:2: ERROR:  42P01`; [notice-then-error] reads the error's code, not the
    NOTICE's; a value holding a newline and a whole located line reads 22P02, and a RAISE
    forging one reads P0001. [german] keeps its skip where the cluster takes no German
    `lc_messages`, and carries no parse of its own."""
    import pgcluster
    cluster, _bootstrap = t109_engine
    mod = load_indexer()
    script, want = PSQL16_CASES[case]
    env = pgcluster._client_env(cluster.root, pgcluster.SUPERUSER, "t109_db", "pytest",
                                cluster.bindir)
    if case == "german":
        env["PGOPTIONS"] = "-c lc_messages=de_DE.UTF-8"
    proc = subprocess.run([cluster.tool("psql"), *mod.INDEX_PSQL_ARGS], input=script,
                          capture_output=True, encoding="utf-8", errors="replace", env=env,
                          timeout=120, check=False)
    if case == "german" and proc.returncode == 2:
        pytest.skip("not established: the cluster takes no German lc_messages")
    assert proc.returncode == 3, proc.returncode
    # NEVER psql 16's RAW STDERR, its line count and its codes alone (lane 2's SHOULD 2 of
    # comment 6956694290, IN by lane 3's 6956711531)
    said = (f"{len(proc.stderr.splitlines())} line(s), codes "
            f"{re.findall(r':  ([0-9A-Z]{5})$', proc.stderr, re.M)}")
    if case == "english":
        assert proc.stderr == "psql:<stdin>:2: ERROR:  42P01\n", said
    if case == "notice-then-error":
        lines = proc.stderr.splitlines()
        assert len(lines) == 2 and lines[0].endswith(":  42P07"), said
    assert "t104_no_such_table" not in proc.stderr, said
    assert mod.PostgresStore._failure(proc.returncode, proc.stderr, False).sqlstate == want


FAKE_PSQL = r"""#!/usr/bin/env python3
# A FAKE psql: it records what it was asked and answers the few queries
# lanes-index makes as an EMPTY schema-1 store would. No database exists.
import json, os, re, sys
# The schema version it answers is "1" unless FAKE_PSQL_VERSION_FILE names a
# file holding another (empty: no row, a wiped store); the bootstrap DDL
# writes "1" into that file, as a real one would create the row.
log = os.environ["FAKE_PSQL_LOG"]
vfile = os.environ.get("FAKE_PSQL_VERSION_FILE", "")
version = open(vfile).read().strip() if vfile else "1"
args = sys.argv[1:]
# psql's error line carries its SQLSTATE only under VERBOSITY=verbose, as a real psql's does;
# under VERBOSITY=sqlstate it is the severity and the SQLSTATE ALONE, with no text (lane 3's
# ruling on opensoft/openRepoTools-code#89 comment 6955397261), which the index runs
verbose = "VERBOSITY=verbose" in args
sqlstate_only = "VERBOSITY=sqlstate" in args
# psql's LOCUS, AS psql 16 PRINTS IT (W116's pre-review of commit 15; command.c's
# process_file and logging.c): a script read through `-f -` is the file `<stdin>`, and each
# message psql reports begins `psql:<stdin>:<line>: `; a script piped with no `-f` is logged
# tersely, with no locus. Every stderr this fake writes is said through `said`.
as_file = any(a == "-f" and b == "-" for a, b in zip(args, args[1:]))


def said(text):
    return text if as_file else re.sub(r"^psql:<stdin>:[0-9]+: ", "", text, flags=re.M)


# THE CONNECTION IN `PG*` VARIABLES ALONE (Question 11; L2-0c): an argument
# that is `-d` or `--dbname`, or that carries a URL, is refused with psql's own
# fatal-error 1 before anything is recorded, since `/proc` shows a process's
# arguments for its life. The URL recorded is rebuilt from `PGUSER`, `PGHOST`,
# `PGPORT` and `PGDATABASE`, with no port where `PGPORT` is unset, so each URL
# a test configures reads back unchanged.
if any(a.startswith(("-d", "--dbname")) or "://" in a for a in args):
    sys.stderr.write("FAKE psql: an argument carries the connection (-d, --dbname or a URL);"
                     " psql takes it from PG* variables only (Question 11)\n")
    sys.exit(1)
port = os.environ.get("PGPORT", "")
url = ("postgresql://" + os.environ.get("PGUSER", "") + "@" + os.environ.get("PGHOST", "")
       + (":" + port if port else "") + "/" + os.environ.get("PGDATABASE", ""))
stdin = sys.stdin.read()
with open(log, "a") as handle:
    handle.write(json.dumps({"url": url, "passfile": os.environ.get("PGPASSFILE", ""),
                             "pgpassword": "PGPASSWORD" in os.environ, "stdin": stdin,
                             "args": args}) + "\n")
if vfile and "CREATE TABLE IF NOT EXISTS" in stdin:
    with open(vfile, "w") as handle:
        handle.write("1\n")
# A SCHEMA WITH NO TABLE, AS psql 16 SAYS IT (lane 1's hosted run 44046351293): with
# FAKE_PSQL_NO_TABLE set and no version filed, the version read fails with the
# error's line, the statement's line and a caret under the table's name, exit 3.
if (os.environ.get("FAKE_PSQL_NO_TABLE") and vfile and not version
        and "COPY (SELECT version" in stdin):
    if sqlstate_only:
        sys.stderr.write(said("psql:<stdin>:2: ERROR:  42P01\n"))
        sys.exit(3)
    sys.stderr.write(said('psql:<stdin>:2: ERROR:  ' + ("42P01: " if verbose else "") +
                     'relation "lanes_index.schema_version" does '
                     'not exist\nLINE 1: COPY (SELECT version FROM '
                     '"lanes_index".schema_version) TO S...\n' + " " * 34 + "^\n" +
                     ("LOCATION:  parserOpenTable, parse_relation.c:1449\n" if verbose else "")))
    sys.exit(3)
# THE COMPARE-AND-SWAP'S RAISE (FAKE_PSQL_CAS_LOST): the write fails as psql 16 says it
if os.environ.get("FAKE_PSQL_CAS_LOST") and "lanes_index_cas" in stdin:
    if sqlstate_only:
        sys.stderr.write(said("psql:<stdin>:5: ERROR:  P0001\n"))
        sys.exit(3)
    sys.stderr.write(said("psql:<stdin>:5: ERROR:  " + ("P0001: " if verbose else "") +
                          "lanes-index: provenance moved under this sync; nothing was written\n"))
    sys.exit(3)
# FAKE_PSQL_STDERR_FILE: the provenance's read, or with FAKE_PSQL_STDERR_ON=write the
# compare-and-swap's write, fails with that file's text on stderr, exit
# FAKE_PSQL_STDERR_EXIT (3 where it is unset)
failing = ("lanes_index_cas" if os.environ.get("FAKE_PSQL_STDERR_ON") == "write"
           else "UNION SELECT source FROM")
if os.environ.get("FAKE_PSQL_STDERR_FILE") and failing in stdin:
    sys.stderr.write(said(open(os.environ["FAKE_PSQL_STDERR_FILE"]).read()))
    sys.exit(int(os.environ.get("FAKE_PSQL_STDERR_EXIT") or 3))


def echo(text):
    # `\echo` AS psql's OWN LEXER READS IT (opensoft/openRepoTools#166 item 4;
    # psqlscanslash.l's `xslashquote`): words split on blanks, a quoted run
    # taken whole, and inside the quotes `''`, `\n \t \b \r \f`, octal
    # `\ooo` and hex `\xhh` decoded - so the marker the indexer sends is the
    # marker its parser reads back, and a wrong escape is wrong here too.
    words, word, quoted, i = [], "", False, 0
    while i < len(text):
        ch = text[i]
        if not quoted and ch in " \t":
            if word:
                words.append(word)
                word = ""
            i += 1
        elif ch == "'" and quoted and text[i + 1:i + 2] == "'":
            word, i = word + "'", i + 2
        elif ch == "'":
            quoted, i = not quoted, i + 1
        elif quoted and ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            octal = len(text[i + 1:i + 4]) - len(text[i + 1:i + 4].lstrip("01234567"))
            hexes = len(text[i + 2:i + 4]) - len(text[i + 2:i + 4].lstrip("0123456789abcdefABCDEF"))
            if nxt in "ntbrf":
                word, i = word + {"n": "\n", "t": "\t", "b": "\b", "r": "\r", "f": "\f"}[nxt], i + 2
            elif octal:
                word, i = word + chr(int(text[i + 1:i + 1 + octal], 8)), i + 1 + octal
            elif nxt == "x" and hexes:
                word, i = word + chr(int(text[i + 2:i + 2 + hexes], 16)), i + 2 + hexes
            else:
                word, i = word + nxt, i + 2
        else:
            word, i = word + ch, i + 1
    if word:
        words.append(word)
    return " ".join(words)


for line in stdin.splitlines():
    if line.startswith("COPY (SELECT version"):
        if version:
            print(version)
    elif line.startswith("COPY (SELECT source FROM provenance UNION "):
        # FAKE_PSQL_SOURCES: the sources the store answers, one a line
        for held in os.environ.get("FAKE_PSQL_SOURCES", "").splitlines():
            print(held)
    elif line.startswith("\\echo"):
        print(echo(line[len("\\echo"):]))
sys.exit(0)
"""


def test_the_fake_psql_decodes_echo_as_psql_does(tmp_path):
    """THE FAKE DOES NOT HARD-CODE THE MARKER (opensoft/openRepoTools#166 item
    4): it prints what psql would for each `\\echo`, so `\\036` arrives as byte
    0x1E only because psql's escapes say so - and an argument that is not the
    marker is not the marker."""
    fake = tmp_path / "psql"
    fake.write_text(FAKE_PSQL)
    fake.chmod(0o755)
    script = "\n".join([
        "\\echo '\\036LANES-INDEX-NEXT'",
        "\\echo 'it''s' two   words",
        "\\echo 'a\\tb\\x41\\101\\q'",
        "\\echo plain",
        ""])
    res = subprocess.run([sys.executable, str(fake)],
                         input=script, capture_output=True, text=True, check=False,
                         env=dict(os.environ, FAKE_PSQL_LOG=str(tmp_path / "log"),
                                  PGHOST="db.invalid", PGDATABASE="qa", PGUSER="x"))
    assert res.returncode == 0, res.stderr
    assert res.stdout.split("\n") == ["\x1eLANES-INDEX-NEXT", "it's two words", "a\tbAAq",
                                      "plain", ""], res.stdout


def test_postgres_takes_the_writer_to_write_and_the_reader_to_read(estate):
    """TWO ROLES (14(c)): `sync` connects as the `url=` WRITER and `export`
    and `status` as the `reader_url=` READER, each with its own 0600 password
    file and never a `PGPASSWORD`; and the sync's writes are ONE transaction
    whose first act is the provenance compare-and-swap."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log = estate.root / "psql.jsonl"
    wpw = estate.config / "writer.pgpass"
    rpw = estate.config / "reader.pgpass"
    for p in (wpw, rpw):
        p.write_text("*:*:*:*:x\n")
        p.chmod(0o600)
    estate.write_config(
        f"url=postgresql://lanes_writer@db.invalid/qa\npassfile={wpw}\n"
        f"reader_url=postgresql://lanes_reader@db.invalid/qa\nreader_passfile={rpw}\n")
    env = {"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log),
           "PGPASSWORD": "inherited-and-never-used"}
    res = estate.index("sync", env=env)
    assert res.returncode == 0, res.stderr
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    assert calls and all(c["url"] == "postgresql://lanes_writer@db.invalid/qa" for c in calls)
    assert all(c["passfile"] == str(wpw) and not c["pgpassword"] for c in calls)
    writes = [c["stdin"] for c in calls if "INSERT INTO lanes" in c["stdin"]]
    assert len(writes) == 1, "the rows went in more than one transaction"
    script = writes[0]
    assert script.index("BEGIN;") < script.index("lanes_index_cas") < script.index("INSERT INTO lanes")
    assert script.rstrip().endswith("COMMIT;")
    assert "IS NOT DISTINCT FROM NULL" in script
    log.unlink()
    out = estate.root / "exp"
    out.mkdir()
    exp = estate.index("export", "--out", out, env=env)
    assert exp.returncode == 3 and (out / "why").read_text().startswith("wiped")
    st = estate.index("status", env=env)
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    assert calls and all(c["url"] == "postgresql://lanes_reader@db.invalid/qa" for c in calls)
    assert all(c["passfile"] == str(rpw) for c in calls)
    assert not any("INSERT" in c["stdin"] or "CREATE" in c["stdin"] for c in calls)
    assert "postgres" in st.stdout


def test_a_postgres_export_is_one_repeatable_read_transaction(estate):
    """ONE READ SNAPSHOT ON POSTGRES TOO (opensoft/openRepoTools#166 item 1):
    each `rows()` was a `psql` session of its own. The export's provenance and
    its five tables now go in ONE `psql` call, inside `BEGIN ISOLATION LEVEL
    REPEATABLE READ READ ONLY` ... `COMMIT`, which is one snapshot."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log = estate.root / "psql.jsonl"
    estate.write_config("url=postgresql://lanes_writer@db.invalid/qa\n"
                        "reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    out = estate.root / "exp"
    out.mkdir()
    exp = estate.index("export", "--out", out,
                       env={"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log)})
    # the fake holds no provenance, so the answer is `wiped` - read in the batch
    assert exp.returncode == 3 and (out / "why").read_text().startswith("wiped"), exp.stderr
    calls = [json.loads(l)["stdin"] for l in log.read_text().splitlines()]
    reads = [c for c in calls if "FROM provenance" in c]
    assert len(reads) == 1, calls
    script = reads[0]
    assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script, script
    begin = script.index("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
    end = script.rindex("COMMIT;")
    assert begin < script.index("FROM provenance WHERE") < end, script
    for table in ("source_files", "lanes", "register_lines", "lane_aliases", "log_lines"):
        assert begin < script.index(f"FROM {table} WHERE") < end, (table, script)


def test_a_read_never_connects_with_the_writers_credential(estate):
    """THE READER OR NOTHING (14(c); Copilot round 1 on #164): a Postgres
    configuration with a writer `url=` and no `reader_url=` REFUSES the reads
    — `export` says `refused` and the read flags answer from the sources,
    `status` exits 2 — and not one of them reaches `psql` at all, so the
    writer's credential is never presented by a session typing `--index`."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log = estate.root / "psql.jsonl"
    wpw = estate.config / "writer.pgpass"
    wpw.write_text("*:*:*:*:x\n")
    wpw.chmod(0o600)
    estate.write_config(f"url=postgresql://lanes_writer@db.invalid/qa\npassfile={wpw}\n")
    env = {"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log)}
    out = estate.root / "exp"
    out.mkdir()
    exp = estate.index("export", "--out", out, env=env)
    assert exp.returncode == 2, exp.stderr
    assert (out / "why").read_text().startswith("refused:")
    assert "reader_url" in (out / "why").read_text()
    for argv in (("bash", LANES_EDIT, "history", "repoA-1"), (LANES, "--all")):
        src = estate.run(*argv, env=env)
        idx = estate.run(*argv, "--index", env=env)
        assert "read: sources (index refused" in idx.stderr, (argv, idx.stderr)
        assert idx.returncode == src.returncode, (argv, idx.stderr)
        assert AGE.sub("<AGE>", idx.stdout) == AGE.sub("<AGE>", src.stdout), argv
    st = estate.index("status", env=env)
    assert st.returncode == 2 and "reader_url" in st.stderr, st.stderr
    assert not log.exists(), "a read reached psql: " + log.read_text()
    # the WRITER is still the indexer's, untouched by the rule
    assert estate.index("sync", env=env).returncode == 0
    assert all(json.loads(l)["url"] == "postgresql://lanes_writer@db.invalid/qa"
               for l in log.read_text().splitlines())


def test_a_symlink_is_judged_where_it_points(estate):
    """RESOLVED BEFORE IT IS JUDGED (14(c); Copilot round 1 on #164): a 0600
    configuration reached through a symlink that lives outside every
    repository but points INTO a work tree is a file in that work tree, and is
    refused; so is a SQLite store whose directory is a link into one."""
    inside = estate.wip / "lanes-index.conf"
    inside.write_text("store=sqlite\n", encoding="utf-8")
    inside.chmod(0o600)
    link = estate.config / "openRepoTools" / "lanes-index.conf"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(inside)
    res = estate.index("sync")
    assert res.returncode == 2 and "inside the git work tree" in res.stderr, res.stderr
    assert not estate.sqlite.exists()
    link.unlink()
    door = estate.root / "door"
    door.symlink_to(estate.wip)
    estate.write_config(f"sqlite={door / 'lanes-index.sqlite'}\n")
    res = estate.index("sync")
    assert res.returncode == 2 and "never inside a work tree" in res.stderr, res.stderr
    assert not (estate.wip / "lanes-index.sqlite").exists()


def test_two_logs_one_case_apart_keep_two_transcript_pointers(estate):
    """KEYED AS THE LOG LINES ARE (Copilot round 1 on #164): two logs whose
    names differ only by case, each with a PAUSED carrying a transcript at
    the SAME line, are two pointers — the second keyed by its file — never one
    overwritten by the other."""
    tid = "ffffffff-0002-4000-8000-00000000f002"
    paused = (f"PAUSED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-01T04:00:00Z, "
              f"lane:repoA-2 → dir /work/repoA2; agent claude; transcript {{}}")
    lower = "lanes/log/repoA-2.md"
    estate.commit_paths({
        "lanes/log/REPOA-2.md": "\n".join([
            "# lane repoA-2 — object log, the other spelling",
            f"STARTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-01T02:00:00Z, lane:repoA-2 → home opensoft/repoA",
            f"NOTED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-01T02:10:00Z, lane:repoA-2 — padding",
            paused.format(UUID_T1), ""]),
        lower: estate.head_text(lower) + paused.format(tid) + "\n",
    }, "two spellings of one log")
    tree = estate._git("ls-tree", "--name-only", "origin/main", "lanes/log/").split()
    assert {"lanes/log/REPOA-2.md", lower} <= set(tree), tree
    res = estate.index("sync")
    assert res.returncode == 0, res.stderr
    conn = sqlite3.connect(str(estate.sqlite))
    rows = conn.execute("SELECT record_id, transcript_id FROM transcript_pointers "
                        "WHERE kind = 'paused' AND transcript_id IN (?, ?)",
                        (UUID_T1, tid)).fetchall()
    assert {t for _, t in rows} == {UUID_T1, tid}, rows
    assert len({r for r, _ in rows}) == 2, rows
    # NOT VACUOUS: the two PAUSED lines sit at the SAME line of their files,
    # so the first-choice id collides and the second is keyed by its file.
    where = conn.execute("SELECT lane, ordinal FROM log_lines WHERE verb = 'PAUSED' "
                         "AND file IN ('lanes/log/REPOA-2.md', ?)", (lower,)).fetchall()
    assert len(where) == 2 and where[0][1] == where[1][1], where


def _as_estate(monkeypatch, estate) -> None:
    """This process's environment made the estate's, for the cases that drive
    `lanes-index` as a module; `monkeypatch` puts it back."""
    for key in list(os.environ):
        if key.startswith(("LANES_", "CLAUDE_", "WORKBENCHES_", "TMUX", "XDG_", "PG",
                           "AGENT_PROTOCOL_ROOT", "PROJECTS_")):
            monkeypatch.delenv(key, raising=False)
    for key, value in estate.env.items():
        monkeypatch.setenv(key, value)


def test_a_source_that_moves_while_the_owners_are_asked_writes_nothing(estate, monkeypatch,
                                                                         capsys):
    """ONE COMMIT'S ROWS, ONE COMMIT'S OWNERS (14(d); Copilot round 1 on
    #164): `managed-projection` reads `origin/<branch>` as it stands, so the
    indexer asks the ref again once the owners are in; a ref that moved
    meanwhile writes NOTHING, and `sync` reads the new tip whole."""
    _as_estate(monkeypatch, estate)
    mod = load_indexer()
    real_tip = mod.tip_of
    asked = []

    def moving(root):
        asked.append(root)
        return "f" * 40 if len(asked) == 2 else real_tip(root)

    monkeypatch.setattr(mod, "tip_of", moving)
    with pytest.raises(mod.SourceMoved):
        mod.run_index("sync", None, False)
    conn = sqlite3.connect(str(estate.sqlite))
    assert conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM lanes").fetchone()[0] == 0
    conn.close()
    asked.clear()
    assert mod.cmd_sync(None) == 0
    captured = capsys.readouterr()
    assert "moved from" in captured.err, captured.err
    assert len(asked) == 4, asked
    conn = sqlite3.connect(str(estate.sqlite))
    assert conn.execute("SELECT commit_sha FROM provenance").fetchone()[0] == estate.tip()
    assert conn.execute("SELECT COUNT(*) FROM lanes").fetchone()[0] > 0


def test_a_rerun_marked_as_the_holder_lets_go_is_never_lost(estate, monkeypatch):
    """THE HANDSHAKE (14(d); Codex on #164): a mark written after the holder's
    last look but before it released is found by the holder's look AFTER the
    release, and synced; and a sync that finds the lock held, marks, and then
    finds it free takes it itself — no mark is left with nobody to read it."""
    _as_estate(monkeypatch, estate)
    mod = load_indexer()
    runs = []
    monkeypatch.setattr(mod, "run_index", lambda *a: runs.append(a) or 0)
    real_release = mod.SyncLock.release
    released = []

    def release_late_marked(self):
        if not released and self.handle is not None:
            self.mark_rerun()  # the contender's mark, after the holder last looked
        released.append(1)
        real_release(self)

    monkeypatch.setattr(mod.SyncLock, "release", release_late_marked)
    assert mod.cmd_sync(None) == 0
    assert len(runs) == 2, runs
    lock = mod.SyncLock()
    assert not os.path.exists(lock.rerun)
    monkeypatch.setattr(mod.SyncLock, "release", real_release)

    runs.clear()
    answers = iter([False, True])  # held at the first look, free at the second

    def acquire_second_time(self, wait_seconds):
        return next(answers, True)

    monkeypatch.setattr(mod.SyncLock, "acquire", acquire_second_time)
    assert mod.cmd_sync(None) == 0
    assert len(runs) == 1, "the contender found the lock free on its second look and did not sync"
    assert not os.path.exists(lock.rerun)


def test_an_unknown_owner_is_asked_again_at_the_same_commit(estate):
    """`unknown` IS NOT AN ANSWER TO KEEP (14(e); Codex on #164): an owner
    that read as `unknown` because `managed-projection` failed is asked again
    by the next sync even when the index is already at the tip, and only the
    row it clears is written."""
    wrapper = estate.root / "lanes-edit-failing"
    wrapper.write_text("#!/bin/sh\n"
                       "if [ \"$1\" = managed-projection ] && [ \"$2\" = repoA-1 ]; then\n"
                       "  echo 'managed-projection: could not read origin' >&2; exit 1\nfi\n"
                       f"exec bash {LANES_EDIT} \"$@\"\n")
    wrapper.chmod(0o755)
    assert estate.index("sync", env={"LANES_EDIT": str(wrapper)}).returncode == 0
    conn = sqlite3.connect(str(estate.sqlite))
    assert dict(conn.execute("SELECT lane, owner FROM lanes"))["repoA-1"] == "unknown"
    conn.close()
    again = estate.index("sync")
    assert again.returncode == 0, again.stderr
    assert "1 upserted, 0 removed" in again.stdout, again.stdout
    conn = sqlite3.connect(str(estate.sqlite))
    owners = dict(conn.execute("SELECT lane, owner FROM lanes"))
    assert owners["repoA-1"] == "legacy"
    assert owners["repoM-2"] == "unknown"  # a malformed marker stays what it is
    conn.close()
    before = dump(estate.sqlite, with_utc=True)
    third = estate.index("sync")
    assert third.returncode == 0 and "nothing to write" in third.stdout, third.stdout
    assert dump(estate.sqlite, with_utc=True) == before


def test_the_holds_view_answers_as_who_does(estate):
    """THE VIEW IS `holders_of` (14(e); Copilot round 2 on #164): a lane's own
    last line on an object — the lane compared case-insensitively, "last" in
    file order — holds while its verb is open, and NOT while another lane's own
    last line there is a TAKEOVER. Checked object by object against `who`."""
    lines = {
        "repoA-1.md": [
            f"CLAIMED — lane repoA-1, session {UUID_A1B}@Eagle, 2026-10-02T00:00:00Z, opensoft/repoA#20 — mine",
            f"CLAIMED — lane repoA-1, session {UUID_A1B}@Eagle, 2026-10-02T00:30:00Z, opensoft/repoA#21 — mine again, after it came back"],
        "repoA-2.md": [
            f"TAKEOVER — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-02T00:05:00Z, opensoft/repoA#20 — a stale claim",
            f"TAKEOVER — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-02T00:10:00Z, opensoft/repoA#21 — taken",
            f"RELEASED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-02T00:20:00Z, opensoft/repoA#21 — handed back",
            f"RELEASED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-02T00:40:00Z, opensoft/repoA#22 — done with it"],
        # the same lane under another spelling: byte order puts this file
        # FIRST, so its CLAIMED is not the lane's last line on #22
        "REPOA-2.md": [
            "# lane repoA-2 — object log, the other spelling",
            f"CLAIMED — lane repoA-2, session {UUID_A2}@Eagle, 2026-10-02T00:35:00Z, opensoft/repoA#22 — under the other spelling"],
    }
    files = {}
    for name, add in lines.items():
        path = f"lanes/log/{name}"
        old = estate.head_text(path) if name != "REPOA-2.md" else ""
        files[path] = old + "\n".join(add) + "\n"
    estate.commit_paths(files, "a takeover, a hand-back and two spellings")
    tree = estate._git("ls-tree", "--name-only", "origin/main", "lanes/log/").split()
    assert {"lanes/log/REPOA-2.md", "lanes/log/repoA-2.md"} <= set(tree), tree
    assert estate.index("sync").returncode == 0
    conn = sqlite3.connect(str(estate.sqlite))
    view: dict = {}
    for lane, obj in conn.execute("SELECT lane, object FROM holds"):
        view.setdefault(obj, set()).add(lane.lower())
    objects = [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM log_lines WHERE unreadable = 0 "
        "AND object NOT LIKE 'lane:%' ORDER BY object")]
    conn.close()
    assert {"opensoft/repoA#20", "opensoft/repoA#21", "opensoft/repoA#22"} <= set(objects)
    for obj in objects:
        res = estate.edit("who", obj)
        assert res.returncode == 0, (obj, res.stderr)
        who = {m.lower() for m in re.findall(r"^HOLDS +lane (\S+)", res.stdout, re.M)}
        assert view.get(obj, set()) == who, (obj, view.get(obj), res.stdout)
    assert view["opensoft/repoA#20"] == {"repoa-2"}
    assert view["opensoft/repoA#21"] == {"repoa-1"}
    assert "opensoft/repoA#22" not in view


def test_the_holds_view_follows_file_order_not_the_clock(estate):
    """"LAST" IS THE LAST LINE IN THE FILE (R14; the macOS gate on #164): two
    lines of one lane on one object, written OUT OF UTC ORDER, are ordered by
    their position in the log - and line 10 comes after line 9, compared as
    numbers. A view that ordered by the UTC field, or by the line as text,
    answers both objects the other way round; `who` is asked as well."""
    path = "lanes/log/repoA-2.md"
    head = estate.head_text(path)
    assert len(head.split("\n")) == 4  # header, STARTED, NOTED, and the final newline
    say = lambda verb, utc, obj, text: (
        f"{verb} — lane repoA-2, session {UUID_A2}@Eagle, {utc}, {obj} — {text}")
    add = [
        say("CLAIMED", "2026-10-03T09:00:00Z", "opensoft/repoA#30", "line 4, the LATEST stamp"),
        say("RELEASED", "2026-10-03T23:00:00Z", "opensoft/repoA#31", "line 5, the LATEST stamp"),
    ] + [say("NOTED", f"2026-10-03T1{n}:00:00Z", "lane:repoA-2", f"padding {n}") for n in range(4)] + [
        say("RELEASED", "2026-10-03T01:00:00Z", "opensoft/repoA#30", "line 10, an EARLIER stamp"),
        say("CLAIMED", "2026-10-03T00:30:00Z", "opensoft/repoA#31", "line 11, an EARLIER stamp"),
    ]
    estate.commit_paths({path: head + "\n".join(add) + "\n"}, "two objects out of UTC order")
    assert estate.index("sync").returncode == 0
    conn = sqlite3.connect(str(estate.sqlite))
    placed = dict(conn.execute(
        "SELECT object || ' ' || verb, ordinal FROM log_lines WHERE file = ? "
        "AND object IN ('opensoft/repoA#30', 'opensoft/repoA#31')", (path,)).fetchall())
    assert placed == {"opensoft/repoA#30 CLAIMED": 4, "opensoft/repoA#31 RELEASED": 5,
                      "opensoft/repoA#30 RELEASED": 10, "opensoft/repoA#31 CLAIMED": 11}, placed
    held = dict(conn.execute("SELECT object, verb FROM holds "
                             "WHERE object IN ('opensoft/repoA#30', 'opensoft/repoA#31')"))
    assert held == {"opensoft/repoA#31": "CLAIMED"}, held
    for obj, state in (("opensoft/repoA#30", "FREE"), ("opensoft/repoA#31", "HELD")):
        res = estate.edit("who", obj)
        assert res.returncode == 0, res.stderr
        assert re.search(rf"^state +{state}\b", res.stdout, re.M), (obj, res.stdout)


def test_the_store_is_made_private_on_every_write(estate):
    """0600 EVERY TIME (14(c); Copilot round 2 on #164): a SQLite store whose
    mode drifted is made private again by the next sync, not only at birth."""
    assert estate.index("sync").returncode == 0
    estate.sqlite.chmod(0o644)
    assert estate.index("sync").returncode == 0
    assert stat.S_IMODE(estate.sqlite.stat().st_mode) == 0o600


def test_a_postgres_store_of_another_schema_is_not_touched(estate):
    """NEVER WRITTEN, NOT EVEN BY THE BOOTSTRAP (14(d); Copilot round 2 on
    #164): the version is read before any DDL, so a schema-2 store is refused
    with no CREATE sent at all; and an absent schema is still bootstrapped."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log = estate.root / "psql.jsonl"
    wpw = estate.config / "writer.pgpass"
    wpw.write_text("*:*:*:*:x\n")
    wpw.chmod(0o600)
    estate.write_config(f"url=postgresql://lanes_writer@db.invalid/qa\npassfile={wpw}\n"
                        f"reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    vfile = estate.root / "pg-version"
    env = {"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log),
           "FAKE_PSQL_VERSION_FILE": str(vfile)}
    vfile.write_text("2\n")
    res = estate.index("sync", env=env)
    assert res.returncode == 1 and "unknown-schema" in res.stderr, res.stderr
    calls = [json.loads(l)["stdin"] for l in log.read_text().splitlines()]
    assert calls and not any("CREATE" in c or "INSERT" in c for c in calls), calls
    log.unlink()
    vfile.write_text("")
    res = estate.index("sync", env=env)
    assert res.returncode == 0, res.stderr
    calls = [json.loads(l)["stdin"] for l in log.read_text().splitlines()]
    assert sum("CREATE TABLE IF NOT EXISTS" in c for c in calls) == 1
    assert sum("INSERT INTO lanes" in c for c in calls) == 1


def test_out_belongs_to_export_alone(estate):
    """`--out` is `export`'s, as `--dry-run` is `reconcile`'s (Copilot round 2
    on #164): `sync --out <dir>` is a usage error, not a silent write."""
    out = estate.root / "exp"
    out.mkdir()
    for verb in ("sync", "reconcile", "status"):
        res = estate.index(verb, "--out", out)
        assert res.returncode == 64 and "unknown argument" in res.stderr, (verb, res.stderr)
    assert not estate.sqlite.exists()


def test_a_fetch_that_falls_back_keeps_the_read_line_off_stdout(estate):
    """`lanes --fetch --index` WHERE THE FETCH FALLS BACK (14(b); Copilot round
    3 on #164): the wrapper prints the helper's notes on stdout under that
    footer, and the `read:` line is not one of them - it is said once, on
    stderr, and the listing is the source read's."""
    assert estate.index("sync").returncode == 0
    # THE HELPER IN THAT STATE, as the shell suite builds it: it says the fetch
    # fell back, on stderr, and answers from the local refs, exit 0.
    stub = estate.root / "fetchfallback"
    stub.write_text("#!/usr/bin/env bash\n"
                    "if [ \"${1-}\" = lanes ]; then\n"
                    "  printf 'lanes-edit: fetch failed — reading the logs as they stand locally\\n' >&2\n"
                    "  shift; ff=()\n"
                    "  for a in \"$@\"; do [ \"$a\" = --fetch ] || ff+=(\"$a\"); done\n"
                    f"  exec bash {LANES_EDIT} lanes ${{ff[@]+\"${{ff[@]}}\"}}\n"
                    "fi\n"
                    f"exec bash {LANES_EDIT} \"$@\"\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {"LANES_EDIT": str(stub)}
    src = estate.run("bash", LANES, "--all", "--fetch", env=env)
    idx = estate.run("bash", LANES, "--all", "--fetch", "--index", env=env)
    assert "reading the logs as they stand locally" in src.stdout, src.stdout
    assert idx.stderr.count("read: index (sqlite)") == 1, idx.stderr
    assert "read: " not in idx.stdout, idx.stdout
    assert idx.returncode == src.returncode
    assert normal(idx.stdout, estate.root) == normal(src.stdout, estate.root)


def test_no_inherited_password_file_reaches_psql(estate):
    """THE CONFIGURED PASSWORD FILE OR NONE (14(c); Copilot on #164): an
    inherited `PGPASSFILE` is never handed on. With `passfile=` set, libpq is
    given that file; without one, an EMPTY 0600 file of the indexer's own -
    never the inherited file, and never `~/.pgpass` by default."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text(FAKE_PSQL)
    (fake / "psql").chmod(0o755)
    log = estate.root / "psql.jsonl"
    ambient = estate.root / "ambient.pgpass"
    ambient.write_text("*:*:*:*:the-wrong-secret\n")
    ambient.chmod(0o600)
    estate.write_config("url=postgresql://lanes_writer@db.invalid/qa\n"
                        "reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    env = {"PATH": estate.path_with(fake), "FAKE_PSQL_LOG": str(log),
           "PGPASSFILE": str(ambient), "PGPASSWORD": "inherited"}
    assert estate.index("sync", env=env).returncode == 0
    assert estate.index("status", env=env).returncode == 0
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    assert calls and not any(c["pgpassword"] for c in calls)
    used = {c["passfile"] for c in calls}
    assert len(used) == 1 and str(ambient) not in used, used
    empty = Path(used.pop())
    assert empty.parent == estate.state / "openRepoTools", empty
    assert empty.read_text() == "" and stat.S_IMODE(empty.stat().st_mode) == 0o600


def test_an_unreachable_store_writes_nothing_waits_on_nothing_and_says_so(estate):
    fake = estate.root / "pgfake"
    fake.mkdir()
    (fake / "psql").write_text("#!/bin/sh\necho 'psql: error: could not connect' >&2\nexit 2\n")
    (fake / "psql").chmod(0o755)
    pw = estate.config / "pgpass"
    pw.write_text("*:*:*:*:x\n")
    pw.chmod(0o600)
    estate.write_config(f"url=postgresql://lanes_writer@db.invalid/qa\npassfile={pw}\n"
                        f"reader_url=postgresql://lanes_reader@db.invalid/qa\n")
    env = {"PATH": estate.path_with(fake)}
    t0 = time.monotonic()
    res = estate.index("sync", env=env)
    assert res.returncode == 1 and "unreachable" in res.stderr
    assert time.monotonic() - t0 < 30
    st = estate.index("status", env=env)
    assert st.returncode == 1
    assert "unreachable" in st.stdout
    assert "could not connect" in st.stdout


def test_status_says_the_lag_and_a_second_sync_waits_for_nobody(estate):
    assert estate.index("sync").returncode == 0
    assert estate.note("repoA-1", "unindexed").returncode == 0
    st = estate.index("status")
    assert st.returncode == 0, st.stderr
    assert "lag:         1 commit(s)" in st.stdout
    assert "last error:  none" in st.stdout
    # ONE SYNC AT A TIME: a sync that finds the lock held returns at once and
    # leaves the holder a mark to sync again.
    import fcntl
    lock = estate.state / "openRepoTools" / "lanes-index.lock"
    with open(lock, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        t0 = time.monotonic()
        busy = estate.index("sync")
        assert time.monotonic() - t0 < 10
    assert busy.returncode == 0 and "another sync holds" in busy.stdout
    assert (estate.state / "openRepoTools" / "lanes-index.rerun").exists()
    assert estate.index("sync").returncode == 0
    assert not (estate.state / "openRepoTools" / "lanes-index.rerun").exists()


def test_export_never_creates_a_store_and_the_store_is_private(estate):
    out = estate.root / "exp"
    out.mkdir()
    res = estate.index("export", "--out", out)
    assert res.returncode == 3
    assert (out / "why").read_text().startswith("missing:")
    assert not estate.sqlite.exists()
    assert estate.index("sync").returncode == 0
    assert stat.S_IMODE(estate.sqlite.stat().st_mode) & 0o077 == 0
    assert estate.index("sync", "--source", "ledger:Eagle").returncode == 2
    assert estate.index("sync", "--source", "register:someone/else").returncode == 2
    assert estate.index("bogus").returncode == 64


# =================================== the inventory source (opensoft/openRepoTools#161)
#
# THIS WORKSTATION'S #97 WORKTREE INVENTORY, AS THE INDEX'S SECOND SOURCE. Each
# lane's sidecars are written here by the REAL writers (`set-lane-state`,
# `set-lane-tree`) over REAL worktrees of a repository whose origin is a bare
# repository in `tmp_path`; the two managed lanes' sidecars are written by hand,
# because every legacy writer refuses a managed lane — which is exactly how a
# managed lane comes to have leftovers from before its enrolment.

WT_COLS = ["workstation", "lane", "owner", "path", "branch", "base", "lifecycle", "generation",
           "operation", "writer_live", "last_seen_utc", "last_commit", "dirty_count",
           "unpushed_count", "pr_number", "pr_state"]


#: `tree_id_for`'s shape: a `cksum` of the path, then the path folded.
TREE_ID = re.compile(r"\bc[0-9]+-[A-Za-z0-9._-]+")


class Inventory:
    """An Estate with an inventory: repoA-1 RUNNING with one clean tree and one
    dirty, unpushed one; repoA-2 SWAPPING with one tree and a LIVE session;
    repoM-1 (a valid marker) and repoM-2 (a malformed one) each with a sidecar
    left over from before enrolment."""

    def __init__(self, root: Path):
        self.e = Estate(root)
        self.root = root
        self.lsr = root / "lane-state"
        self.e.env["LANES_LANE_STATE_ROOT"] = str(self.lsr)
        self.repo = root / "repos" / "repoA"
        self.origin = root / "repos" / "repoA.git"
        self.trees = self.repo / ".claude" / "worktrees"
        g = self._g
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)],
                       check=True, env=self.e.env)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)],
                       check=True, env=self.e.env, capture_output=True)
        (self.repo / "a.txt").write_text("seed\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "the lane's first commit")
        g(self.repo, "push", "-q", "origin", "main")
        self.trees.mkdir(parents=True)
        self.run_tree = self.trees / "w-run"
        g(self.repo, "worktree", "add", "-q", "-b", "feat/run", str(self.run_tree))
        g(self.run_tree, "push", "-q", "-u", "origin", "feat/run")
        self.dirty_tree = self.trees / "w-dirty"
        g(self.repo, "worktree", "add", "-q", "-b", "feat/dirty", str(self.dirty_tree))
        g(self.dirty_tree, "push", "-q", "-u", "origin", "feat/dirty")
        (self.dirty_tree / "b.txt").write_text("committed, not pushed\n")
        g(self.dirty_tree, "add", "b.txt")
        g(self.dirty_tree, "commit", "-q", "-m", "work not yet pushed")
        (self.dirty_tree / "c.txt").write_text("not even committed\n")
        self.a2_tree = self.trees / "w-a2"
        g(self.repo, "worktree", "add", "-q", "-b", "feat/a2", str(self.a2_tree))
        self.ok("set-lane-state", "repoA-1", "RUNNING", "--operation", "op-test-a1")
        self.ok("set-lane-tree", "repoA-1", str(self.run_tree), "--checkout", str(self.repo))
        self.ok("set-lane-tree", "repoA-1", str(self.dirty_tree), "--checkout", str(self.repo))
        self.ok("set-lane-state", "repoA-2", "RUNNING", "--operation", "op-test-a2")
        self.ok("set-lane-state", "repoA-2", "SWAPPING", "--operation", "op-test-a2s")
        self.ok("set-lane-tree", "repoA-2", str(self.a2_tree), "--checkout", str(self.repo),
                "--generation", "2", "--operation", "op-test-a2s")
        for lane, head in (("repoM-1", "1" * 40), ("repoM-2", "2" * 40)):
            trees = self.lsr / lane / "trees"
            trees.mkdir(parents=True)
            (trees / f"c0-{lane}.yaml").write_text("\n".join([
                "schema: 1", f"lane: {lane}", f"tree: c0-{lane}",
                f"path: /nowhere/{lane}/w", "checkout: unknown", f"branch: feat/{lane}",
                f"head: {head}", "upstream: none", "dirty: 0", "unpushed: 0",
                "writer: none", "generation: 0", "operation: none",
                "observed: 2026-10-04T00:00:00Z", ""]))
        # repoA-2's session is LIVE on this workstation: the listing's own read.
        self.sleeper = subprocess.Popen(["sleep", "600"])
        sessions = self.e.home / ".claude" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "live.json").write_text(
            '{"pid":%d,"sessionId":"%s","kind":"interactive","status":"busy"}\n'
            % (self.sleeper.pid, UUID_A2))

    def _g(self, cwd: Path, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                              env=self.e.env, check=False)
        assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
        return proc.stdout.strip()

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        res = self.e.edit(*args)
        assert res.returncode == 0, (args, res.stdout, res.stderr)
        return res

    def sync(self, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return self.e.index("sync", "--source", "inventory", *extra, env=env)

    def rows(self) -> dict:
        conn = sqlite3.connect(str(self.e.sqlite))
        conn.row_factory = sqlite3.Row
        out = {r["record_id"]: dict(r) for r in conn.execute(
            "SELECT * FROM worktrees WHERE source = 'inventory:Eagle'")}
        conn.close()
        return out

    def norm(self, text: str) -> str:
        """An answer with what is the SANDBOX's taken out: its paths (as given
        and resolved), a tree id - `c<cksum>-<the folded path>`, whose tail
        alone survives a path longer than 180 bytes - and the live session's
        pid. THE ROOT GOES FIRST (#334): a root whose own path holds what another
        rule matches (`rv-c302-309-work` for the tree id, the pid as a segment)
        is cut up by that rule and leaves no root to take out."""
        text = text.replace(os.path.realpath(self.root), str(self.root))
        text = text.replace(str(self.root), "<ROOT>")
        text = TREE_ID.sub("<TREE>", text)
        text = re.sub(rf"\b{self.sleeper.pid}\b", "<PID>", text)
        return normal(text)

    def close(self) -> None:
        self.sleeper.kill()
        self.sleeper.wait()


@pytest.fixture
def inv(tmp_path):
    made = Inventory(tmp_path / "i")
    yield made
    made.close()


#: The live session's pid in the next test: a number no `pytest-<n>` folder reaches.
NORM_PID = 987654

#: THE SHAPES OF A SANDBOX ROOT `Inventory.norm` HAS TO TAKE OUT (#334): each row is
#: (id, the root as the sandbox is given it, the folder that root resolves to), both
#: below the test's `tmp_path`. The plain root is what a rule that runs first leaves
#: whole; the others hold what such a rule matches - a segment like `rv-c302-309-work`
#: for `TREE_ID` (in the third row only in the resolved path, since the root is a link)
#: and the live session's pid for the pid rule.
NORM_ROOTS = [
    ("plain", "i", "i"),
    ("tree-id-segment", "rv-c302-309-work/i", "rv-c302-309-work/i"),
    ("tree-id-segment-in-the-resolved-path-only", "link", "rv-c302-309-work/i"),
    ("pid-segment", f"{NORM_PID}/i", f"{NORM_PID}/i"),
]


def _norm_of(root: Path, pid: int, text: str) -> str:
    """`Inventory.norm` for a sandbox at `root` whose live session is `pid`. That is
    all `norm` reads off its object, so none of the sandbox is built."""
    bare = Inventory.__new__(Inventory)
    bare.root = root
    bare.sleeper = type("Session", (), {"pid": pid})
    return bare.norm(text)


@pytest.mark.parametrize("shape,given,resolved", NORM_ROOTS, ids=[s for s, _, _ in NORM_ROOTS])
def test_norm_takes_the_sandbox_root_out_before_any_rule_that_could_cut_it_up(
        tmp_path, shape, given, resolved):
    """THE ROOT GOES FIRST (#334). `norm` applied `TREE_ID` to the whole answer
    before it took out the sandbox root, so a root whose own path held a segment
    `TREE_ID` matches - `rv-c302-309-work`, a folder named for a review - was cut up
    (`rv-<TREE>`) and no root was left to take out: the two inventory tests that
    compare one sandbox's answer with another's failed for no reason but the
    folder the suite ran from. The pid rule had the same fault for a root with the
    live session's pid as a segment. One answer, written under each root, must leave
    the same text."""
    target = tmp_path / resolved
    target.mkdir(parents=True)
    root = tmp_path / given
    if root != target:
        root.symlink_to(target)
    real = Path(os.path.realpath(root))
    tree = real / "repos" / "repoA" / ".claude" / "worktrees" / "w-run"
    # `tree_id_for`'s shape: a `cksum`, then the path with what a name cannot hold
    # folded to `-`.
    folded = re.sub(r"-+", "-", re.sub(r"[^A-Za-z0-9._-]", "-", str(tree))).strip("-")
    answer = "\n".join([
        f"ROOT\t{root}/lane-state/repoA-1",
        f"TREE\tc410664495-{folded}\tok\t{root}/repos/repoA/.claude/worktrees/w-run"
        "\tbranch feat/run head 0123456789abcdef0123456789abcdef01234567"
        " observed 2026-10-04T00:00:00Z",
        f"TREE\tc410664495-{folded}\tok\t{real}/repos/repoA/.claude/worktrees/w-run",
        f"HOLDER\tlive\t{NORM_PID}\torphan",
    ])
    want = "\n".join([
        "ROOT\t<ROOT>/lane-state/repoA-1",
        "TREE\t<TREE>\tok\t<ROOT>/repos/repoA/.claude/worktrees/w-run"
        "\tbranch feat/run head <HEX> observed <UTC>",
        "TREE\t<TREE>\tok\t<ROOT>/repos/repoA/.claude/worktrees/w-run",
        "HOLDER\tlive\t<PID>\torphan",
    ])
    got = _norm_of(root, NORM_PID, answer)
    assert got == want, f"{shape}:\n{got}"


def test_the_inventory_source_mirrors_every_lanes_sidecars(inv):
    """THE TABLE IS THE INVENTORY (#161): one row per tree each lane's sidecars
    name, every column from the helper that wrote it - the owner from
    `managed-projection`'s read, the lifecycle from the snapshot, the liveness
    from the listing's own session read, the counts and the stamp from the
    observation, the base and the last commit read of the RECORDED head - and
    nothing of the register's touched."""
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    assert "inventory:Eagle (sqlite) - 5 upserted, 0 removed" in res.stdout, res.stdout
    rows = inv.rows()
    run = rows[f"repoA-1:{inv.run_tree}"]
    dirty = rows[f"repoA-1:{inv.dirty_tree}"]
    a2 = rows[f"repoA-2:{inv.a2_tree}"]
    main = inv._g(inv.repo, "rev-parse", "origin/main")
    assert (run["workstation"], run["owner"], run["branch"], run["lifecycle"]) == \
        ("Eagle", "legacy", "feat/run", "RUNNING")
    assert (run["dirty_count"], run["unpushed_count"], run["writer_live"]) == (0, 0, 0)
    assert run["base"] == main
    assert run["last_commit"] == f"{main} the lane's first commit"
    assert (run["generation"], run["operation"], run["provenance"]) == (1, "op-test-a1", "0")
    assert UTC.fullmatch(run["last_seen_utc"]), run["last_seen_utc"]
    head = inv._g(inv.dirty_tree, "rev-parse", "HEAD")
    assert (dirty["dirty_count"], dirty["unpushed_count"]) == (1, 1)
    assert dirty["last_commit"] == f"{head} work not yet pushed"
    assert dirty["base"] == main
    assert (a2["lifecycle"], a2["generation"], a2["writer_live"], a2["provenance"]) == \
        ("SWAPPING", 2, 1, "2")
    assert (a2["pr_number"], a2["pr_state"]) == (None, None)
    m1 = rows["repoM-1:/nowhere/repoM-1/w"]
    m2 = rows["repoM-2:/nowhere/repoM-2/w"]
    assert (m1["owner"], m1["lifecycle"]) == ("managed ledger-1", "INDETERMINATE")
    assert (m2["owner"], m2["lifecycle"]) == ("unknown", "INDETERMINATE")
    assert m1["last_commit"] == "1" * 40 and m1["base"] is None
    conn = sqlite3.connect(str(inv.e.sqlite))
    sources = [r[0] for r in conn.execute("SELECT source FROM provenance")]
    assert sources == ["inventory:Eagle"], sources
    for table in REGISTER_TABLES_FOR_TESTS:
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    prov = conn.execute("SELECT commit_sha, generation FROM provenance").fetchone()
    assert re.fullmatch(r"[0-9a-f]{64}", prov[0]) and prov[1] == 1


REGISTER_TABLES_FOR_TESTS = ("source_files", "lanes", "log_lines", "register_lines",
                             "lane_aliases", "transcript_pointers")


def test_an_inventory_replay_changes_nothing_and_one_write_moves_one_row(inv):
    """REPLAY (14(d)): a second sync of an unchanged inventory writes not one
    byte - `indexed_utc` included - and one `set-lane-tree` afterwards upserts
    the one row it moved."""
    assert inv.sync().returncode == 0
    before = dump(inv.e.sqlite, with_utc=True)
    time.sleep(1.1)
    again = inv.sync()
    assert again.returncode == 0, again.stderr
    assert "nothing to write" in again.stdout, again.stdout
    assert dump(inv.e.sqlite, with_utc=True) == before
    (inv.run_tree / "new.txt").write_text("a fresh change\n")
    inv.ok("set-lane-tree", "repoA-1", str(inv.run_tree), "--checkout", str(inv.repo))
    third = inv.sync()
    assert "1 upserted, 0 removed" in third.stdout, third.stdout
    assert inv.rows()[f"repoA-1:{inv.run_tree}"]["dirty_count"] == 1


def test_a_tree_the_inventory_no_longer_names_leaves_the_table(inv):
    """ROWS LEAVE WITH THEIR RECORD (#161): a tree removed from the inventory -
    at landing, or by a sweep's disposition - leaves the table in the next
    sync, and nothing else moves."""
    assert inv.sync().returncode == 0
    sidecar = [f for f in (inv.lsr / "repoA-1" / "trees").iterdir()
               if "w-dirty" in f.name]
    assert len(sidecar) == 1
    sidecar[0].unlink()
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    assert "0 upserted, 1 removed" in res.stdout, res.stdout
    assert f"repoA-1:{inv.dirty_tree}" not in inv.rows()
    assert f"repoA-1:{inv.run_tree}" in inv.rows()


def test_a_wiped_inventory_reconciles_row_for_row(inv):
    """WIPED-INDEX RECONCILE (14(d)): the rebuild equals a synced table, row for
    row; and a row changed by hand in the store is found by what it SAYS and
    put right."""
    assert inv.sync().returncode == 0
    synced = dump(inv.e.sqlite)
    inv.e.sqlite.unlink()
    dry = inv.e.index("reconcile", "--source", "inventory", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert not inv.e.sqlite.exists(), "a dry run created the store"
    res = inv.e.index("reconcile", "--source", "inventory")
    assert res.returncode == 0, res.stderr
    assert re.search(r"worktrees\s+0 kept\s+5 upserted", res.stdout), res.stdout
    assert dump(inv.e.sqlite) == synced
    conn = sqlite3.connect(str(inv.e.sqlite))
    conn.execute("UPDATE worktrees SET dirty_count = 0, lifecycle = 'SWAPPED' "
                 "WHERE path = ?", (str(inv.dirty_tree),))
    conn.commit()
    conn.close()
    assert "nothing to write" in inv.sync().stdout
    fixed = inv.e.index("reconcile", "--source", "inventory")
    assert re.search(r"worktrees\s+4 kept\s+1 upserted", fixed.stdout), fixed.stdout
    righted = dump(inv.e.sqlite)
    assert righted["worktrees"] == synced["worktrees"]
    # A FINGERPRINT CHANGED BY HAND, every row right, is put right by the next
    # sync rather than left naming a table that is not there (Copilot round 1
    # on #171).
    conn = sqlite3.connect(str(inv.e.sqlite))
    conn.execute("UPDATE provenance SET commit_sha = ? WHERE source = 'inventory:Eagle'", ("f" * 64,))
    conn.commit()
    conn.close()
    healed = inv.sync()
    assert healed.returncode == 0 and "0 upserted, 0 removed" in healed.stdout, healed.stdout
    assert [r[:2] for r in dump(inv.e.sqlite)["provenance"]] == \
        [r[:2] for r in synced["provenance"]]
    # the same table, so the same fingerprint - and a sync count that went UP
    assert [r[:2] for r in righted["provenance"]] == [r[:2] for r in synced["provenance"]]
    assert righted["provenance"][0][2] == synced["provenance"][0][2] + 1


def test_an_inventorys_provenance_only_moves_forward_per_lane(inv):
    """MONOTONIC PROVENANCE (14(d)), PER LANE: a lane whose lifecycle snapshot
    reads BELOW the generation its rows were written at - one moved aside and
    begun again - is written nothing by `sync`, which says why; the other
    lanes sync; and `reconcile` takes the lane as it now stands."""
    assert inv.sync().returncode == 0
    snap = inv.lsr / "repoA-2" / "lane-state.yaml"
    snap.rename(snap.with_suffix(".aside"))
    inv.ok("set-lane-state", "repoA-2", "RUNNING", "--operation", "op-test-again")
    (inv.run_tree / "moved.txt").write_text("repoA-1 moves on\n")
    inv.ok("set-lane-tree", "repoA-1", str(inv.run_tree), "--checkout", str(inv.repo))
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    assert "lane repoA-2: its rows are kept as they are" in res.stdout, res.stdout
    assert "only moves forward" in res.stdout
    assert "1 upserted, 0 removed" in res.stdout, res.stdout
    rows = inv.rows()
    assert rows[f"repoA-2:{inv.a2_tree}"]["generation"] == 2
    assert rows[f"repoA-2:{inv.a2_tree}"]["lifecycle"] == "SWAPPING"
    assert rows[f"repoA-1:{inv.run_tree}"]["dirty_count"] == 1
    rec = inv.e.index("reconcile", "--source", "inventory")
    assert rec.returncode == 0, rec.stderr
    assert "generation went back from 2 to 1" in rec.stdout, rec.stdout
    rows = inv.rows()
    assert (rows[f"repoA-2:{inv.a2_tree}"]["generation"],
            rows[f"repoA-2:{inv.a2_tree}"]["lifecycle"]) == (1, "RUNNING")


def test_the_inventory_owner_column_is_the_seams_answer(inv):
    """THE SEAM (14(e), ruling 2026-10-04): a valid marker's leftovers index as
    `managed <owner>`, a malformed one's as `unknown` - never `legacy` - and a
    plain row's as `legacy`; and only a legacy lane's lifecycle is pronounced,
    the others' being `INDETERMINATE`, as `lane-reconcile` pronounces nothing
    on them either. The indexer carries no parser of the marker."""
    assert inv.sync().returncode == 0
    owners = {(r["lane"], r["owner"], r["lifecycle"]) for r in inv.rows().values()}
    assert ("repoM-1", "managed ledger-1", "INDETERMINATE") in owners
    assert ("repoM-2", "unknown", "INDETERMINATE") in owners
    assert ("repoA-1", "legacy", "RUNNING") in owners
    assert ("repoA-2", "legacy", "SWAPPING") in owners
    rec = inv.e.edit("lane-reconcile", "repoM-1")
    assert "managed-owned" in rec.stdout
    source = INDEXER.read_text(encoding="utf-8")
    for vocabulary in ("mode=managed", "managed-owner", "bound-lane"):
        assert vocabulary not in source


def _wt(inv: Inventory, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return inv.e.run("bash", LANES, "--worktrees", *args, env=env)


def test_lanes_worktrees_shows_one_running_tree_and_one_dirty_one(inv):
    """`lanes --worktrees <lane>` (#161): every open worktree of the lane with
    its owner, branch, lifecycle, dirty and unpushed counts, when it was last
    seen and whether the writer is live - and a footer that sends a person to
    the act that reads the disk."""
    res = _wt(inv, "repoA-1")
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[0].split()[:6] == ["WORKSTATION", "LANE", "OWNER", "LIFECYCLE", "WRITER", "BRANCH"]
    run = next(l for l in lines if l.endswith(str(inv.run_tree)))
    dirty = next(l for l in lines if l.endswith(str(inv.dirty_tree)))
    assert run.split()[:8] == ["Eagle", "repoA-1", "legacy", "RUNNING", "none", "feat/run", "0", "0"]
    assert dirty.split()[:8] == ["Eagle", "repoA-1", "legacy", "RUNNING", "none", "feat/dirty", "1", "1"]
    assert UTC.search(run)
    assert "2 worktree(s) in 1 lane(s) on 1 workstation(s)" in res.stdout
    assert "lanes-edit.sh lane-reconcile <lane>" in res.stdout
    every = _wt(inv)
    assert every.returncode == 0
    assert "5 worktree(s) in 4 lane(s)" in every.stdout
    live = next(l for l in every.stdout.splitlines() if l.endswith(str(inv.a2_tree)))
    assert live.split()[3:5] == ["SWAPPING", "live"], live
    none = _wt(inv, "repoB-1")
    assert none.returncode == 8 and "no worktree is inventoried for lane repoB-1" in none.stdout
    for bad in (("repoA-1", "--all"), ("repoA-1", "repoA-2"), ("--here",), ("--closed",)):
        refused = _wt(inv, *bad)
        assert refused.returncode == 64, (bad, refused.stderr)


def test_the_index_read_of_the_worktrees_is_the_source_read(inv):
    """`lanes --index --worktrees` ANSWERS WHAT THE SIDECARS ANSWER where the
    table is current, byte for byte, and says so on stderr; a write the index
    has not followed is the index's lag, said by the time it was synced."""
    assert inv.sync().returncode == 0
    for args in ((), ("repoA-1",), ("--all",)):
        src = _wt(inv, *args)
        idx = _wt(inv, *args, "--index")
        assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), args
        assert re.search(r"read: index \(sqlite\) at inventory:Eagle synced " + UTC.pattern,
                         idx.stderr), idx.stderr
        assert "read: " not in src.stderr
        # THE FOOTER NAMES WHERE ITS ACT RUNS (opensoft/openRepoTools#173,
        # Copilot's fourth review of #171): an index read lists other
        # workstations' rows, and `lane-reconcile` reads only the disk and
        # the sidecars of the workstation it runs on.
        assert "lanes-edit.sh lane-reconcile <lane>, run ON THE WORKSTATION its rows name" \
            in idx.stdout, idx.stdout
    (inv.run_tree / "unseen.txt").write_text("the index has not followed this\n")
    inv.ok("set-lane-tree", "repoA-1", str(inv.run_tree), "--checkout", str(inv.repo))
    src = _wt(inv, "repoA-1")
    idx = _wt(inv, "repoA-1", "--index")
    assert src.stdout != idx.stdout


@pytest.mark.parametrize("kind,setup", _fallback_setups(), ids=[k for k, _ in _fallback_setups()])
def test_each_worktrees_index_failure_falls_back_to_the_sidecars(inv, kind, setup):
    """FALLBACK (14(b)) for the table too: missing, unreachable, wiped (no
    inventory source), of an unknown schema, refused, or switched off - each
    says `read: sources (index <why>)` and returns the sidecars' own answer."""
    env = setup(inv.e)
    if kind == "wiped":
        assert inv.sync().returncode == 0
        conn = sqlite3.connect(str(inv.e.sqlite))
        conn.execute("DELETE FROM provenance")
        conn.commit()
        conn.close()
    for args in ((), ("repoA-1",)):
        src = _wt(inv, *args, env=env)
        idx = _wt(inv, *args, "--index", env=env)
        assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), (kind, args)
        assert f"read: sources (index {kind}" in idx.stderr, (kind, idx.stderr)


#: THE INVENTORY'S ACTS AND THE READS THEY MAKE (#161): its two writers, which
#: nudge the indexer, and the reads an act makes of the inventory for itself.
INVENTORY_ACTS = [
    ("set-lane-tree", "repoA-1", "<RUN>", "--checkout", "<REPO>"),
    ("set-lane-state", "repoA-1", "SWAPPING", "--expect", "RUNNING", "--operation", "op-acts"),
    ("lane-trees", "repoA-1"),
    ("lane-state", "repoA-2"),
    ("lane-reconcile", "repoA-1"),
    ("lane-reconcile", "repoA-2"),
    ("lane-reconcile", "repoM-1"),
    ("lane-tree-now", "<DIRTY>"),
]


def _inv_act(inv: Inventory, act: tuple, extra: dict) -> tuple:
    argv = [a.replace("<RUN>", str(inv.run_tree)).replace("<REPO>", str(inv.repo))
             .replace("<DIRTY>", str(inv.dirty_tree)) for a in act]
    res = inv.e.edit(*argv, env=extra)
    # A LANE'S TREES ARE LISTED IN THE ORDER THEIR RECORDS' NAMES SORT, and a
    # record's name begins with a `cksum` of its path - which differs between
    # two sandboxes by construction. So the lines are compared as a set of
    # lines, each of them whole.
    out = "\n".join(sorted(inv.norm(res.stdout).split("\n")))
    return (res.returncode, out, inv.norm(res.stderr))


def test_offline_no_read_the_inventory_acts_are_byte_identical_against_an_unreachable_index(tmp_path):
    """OFFLINE NO-READ (14(b), #161): with an indexer installed and configured
    at a Postgres nobody can reach, the inventory writers and `lane-reconcile`
    answer byte for byte as with no index at all - and the writers' nudges DID
    reach for that store, `sync --source inventory`, after they had answered."""
    control = Inventory(tmp_path / "control")
    indexed = Inventory(tmp_path / "indexed")
    try:
        indexed.e.install_indexer()
        fake = indexed.root / "pgfake"
        fake.mkdir()
        psql_log = indexed.root / "psql.log"
        # THE STORE IT REACHED FOR, from the `PG*` variables alone, as in the
        # acts' offline test above (Question 11; L2-0c).
        (fake / "psql").write_text(
            "#!/bin/sh\n"
            "printf 'postgresql://%s@%s%s/%s\\n' \"$PGUSER\" \"$PGHOST\" \"${PGPORT:+:$PGPORT}\" "
            f"\"$PGDATABASE\" >> {psql_log}\n"
            "echo 'psql: error: connection to server at \"lanes-index.invalid\" failed' >&2\nexit 2\n")
        (fake / "psql").chmod(0o755)
        pw = indexed.e.config / "pgpass"
        pw.write_text("*:*:*:*:never-read\n")
        pw.chmod(0o600)
        indexed.e.write_config(f"url=postgresql://lanes_writer@lanes-index.invalid/qa\npassfile={pw}\n")
        extra = {"PATH": indexed.e.path_with(indexed.e.indexbin, fake), "LANES_INDEX": None}
        for act in INVENTORY_ACTS:
            a = _inv_act(control, act, {})
            b = _inv_act(indexed, act, extra)
            assert a == b, (act, a, b)
        assert _wait_for(psql_log, 15.0), "no inventory nudge ever reached for the configured store"
        assert "lanes_writer" in psql_log.read_text()
    finally:
        control.close()
        indexed.close()


def test_a_poisoned_worktrees_table_changes_no_inventory_acts_answer(tmp_path):
    """POISONED INDEX (14(b), #161): wrong `worktrees` rows - a forged tree, a
    forged lifecycle, forged counts and a forged owner - change no inventory
    act's answer, `lane-reconcile` included; and the poison is REAL: `lanes
    --index --worktrees` reads it."""
    control = Inventory(tmp_path / "control")
    poisoned = Inventory(tmp_path / "poisoned")
    try:
        assert poisoned.sync().returncode == 0
        conn = sqlite3.connect(str(poisoned.e.sqlite))
        conn.execute("UPDATE worktrees SET lifecycle = 'SWAPPED', dirty_count = 99, "
                     "unpushed_count = 99, owner = 'managed evil', writer_live = 1")
        conn.execute("INSERT INTO worktrees (source, record_id, workstation, lane, owner, path, "
                     "branch, lifecycle, digest, provenance, indexed_utc, schema_version) VALUES "
                     "('inventory:Eagle', 'repoA-1:/forged', 'Eagle', 'repoA-1', 'legacy', "
                     "'/forged', 'feat/forged', 'RUNNING', 'x', '0', 'now', 1)")
        conn.commit()
        conn.close()
        for act in INVENTORY_ACTS:
            a = _inv_act(control, act, {})
            b = _inv_act(poisoned, act, {"LANES_INDEX": None})
            assert a == b, (act, a, b)
        seen = _wt(poisoned, "--index", env={"LANES_INDEX": None})
        assert "read: index (sqlite)" in seen.stderr
        assert "/forged" in seen.stdout and "managed evil" in seen.stdout, \
            "the poison never reached the index read: vacuous"
    finally:
        control.close()
        poisoned.close()


def test_an_inventory_write_nudges_and_a_read_never_does(inv):
    """THE NUDGE (#161): `set-lane-tree` and `set-lane-state` start the same
    detached `lanes-index sync` a landed push does, asked for the inventory -
    stdin closed, never waited, the writer not delayed - while the reads an act
    makes of the inventory start none, and `LANES_INDEX=off` stops it."""
    stubdir = inv.root / "stub"
    stubdir.mkdir()
    (stubdir / "lanes-index").write_text(STUB)
    (stubdir / "lanes-index").chmod(0o755)
    mark = inv.root / "stubmark"
    path = inv.e.path_with(stubdir)
    pid_file = Path(str(mark) + ".pid")
    for read in (("lane-trees", "repoA-1"), ("lane-reconcile", "repoA-1"), ("lane-state", "repoA-1"),
                 ("worktrees", "--all")):
        res = inv.e.edit(*read, env={"PATH": path, "LANES_INDEX": None,
                                     "LANES_INDEX_STUB_MARK": str(mark)})
        assert res.returncode == 0, (read, res.stderr)
    assert not _wait_for(pid_file, 1.0), "a read nudged the indexer"
    off = inv.e.edit("set-lane-tree", "repoA-1", str(inv.run_tree), "--checkout", str(inv.repo),
                     env={"PATH": path, "LANES_INDEX": "off", "LANES_INDEX_STUB_MARK": str(mark)})
    assert off.returncode == 0, off.stderr
    assert not _wait_for(pid_file, 1.0), "LANES_INDEX=off still nudged"
    for write in (("set-lane-tree", "repoA-1", str(inv.run_tree), "--checkout", str(inv.repo)),
                  ("set-lane-state", "repoA-1", "SWAPPING", "--operation", "op-nudge")):
        for leftover in stubdir.parent.glob("stubmark.*"):
            leftover.unlink()
        t0 = time.monotonic()
        res = inv.e.edit(*write, env={"PATH": path, "LANES_INDEX": None,
                                      "LANES_INDEX_STUB_MARK": str(mark)}, timeout=25)
        took = time.monotonic() - t0
        assert res.returncode == 0, (write, res.stderr)
        assert _wait_for(pid_file, 10.0), f"{write[0]} never nudged the indexer"
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            assert took < 20, f"{write[0]} waited on its nudge ({took:.1f}s)"
            assert _wait_for(Path(str(mark) + ".argv"), 5.0)
            assert Path(str(mark) + ".argv").read_text().strip() == "sync --source inventory"
            assert _wait_for(Path(str(mark) + ".stdin"), 5.0)
            assert Path(str(mark) + ".stdin").read_text().strip() == "eof"
        finally:
            try:
                os.kill(pid, 15)
            except OSError:
                pass


def test_a_pull_request_is_asked_of_gh_best_effort(inv):
    """`pr` (#161): the newest pull request whose head is the tree's branch,
    asked of `gh` at sync where GitHub may be asked - a fake `gh` here - and
    NULL wherever it is not, or does not answer."""
    inv._g(inv.repo, "remote", "set-url", "origin", "https://github.com/opensoft/repoA.git")
    fake = inv.root / "ghfake"
    fake.mkdir()
    calls = inv.root / "gh.calls"
    (fake / "gh").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {calls}\n"
        "case \"$*\" in *feat/dirty*) echo '[{\"number\":42,\"state\":\"OPEN\"}]' ;; "
        "*feat/run*) echo '[{\"number\":7,\"state\":\"MERGED\"}]' ;; *) echo '[]' ;; esac\n")
    (fake / "gh").chmod(0o755)
    env = {"PATH": inv.e.path_with(fake), "LANES_NO_GITHUB": None}
    res = inv.sync(env=env)
    assert res.returncode == 0, res.stderr
    rows = inv.rows()
    assert (rows[f"repoA-1:{inv.dirty_tree}"]["pr_number"],
            rows[f"repoA-1:{inv.dirty_tree}"]["pr_state"]) == (42, "OPEN")
    assert (rows[f"repoA-1:{inv.run_tree}"]["pr_number"],
            rows[f"repoA-1:{inv.run_tree}"]["pr_state"]) == (7, "MERGED")
    assert rows[f"repoA-2:{inv.a2_tree}"]["pr_number"] is None
    assert "--repo opensoft/repoA --head feat/dirty" in calls.read_text()
    # A MERGED answer is final and is not asked again; an OPEN one is.
    calls.unlink()
    assert inv.sync(env=env).returncode == 0
    asked = calls.read_text()
    assert "feat/dirty" in asked and "feat/run" not in asked, asked


def test_status_names_the_inventory_and_a_mark_names_its_source(inv, monkeypatch):
    """`status` prints this workstation's inventory beside the register; and a
    register sync holding the lock when an inventory nudge arrives syncs the
    INVENTORY before it lets go - the mark names its source."""
    st = inv.e.index("status")
    assert "source inventory:Eagle" in st.stdout
    assert "--source inventory` builds it" in st.stdout
    assert inv.sync().returncode == 0
    st = inv.e.index("status")
    assert re.search(r"provenance:  inventory@[0-9a-f]{12} \(sync 1,", st.stdout), st.stdout
    assert "rows:        5 worktree(s)" in st.stdout
    _as_estate(monkeypatch, inv.e)
    mod = load_indexer()
    runs = []
    monkeypatch.setattr(mod, "run_index", lambda *a: runs.append(("register",) + a) or 0)
    monkeypatch.setattr(mod, "run_inventory", lambda *a: runs.append(("inventory",) + a) or 0)
    real_release = mod.SyncLock.release
    released = []

    def release_after_an_inventory_mark(self):
        if not released and self.handle is not None:
            self.mark_rerun("inventory")
        released.append(1)
        real_release(self)

    monkeypatch.setattr(mod.SyncLock, "release", release_after_an_inventory_mark)
    assert mod.cmd_sync(None) == 0
    assert [r[0] for r in runs] == ["register", "inventory"], runs
    lock = mod.SyncLock()
    assert not lock.has_rerun()
    # A FAILED SOURCE DOES NOT DROP A MARK ALREADY TAKEN (Copilot round 1 on
    # #171): the register's round fails, the inventory's mark - taken off the
    # disk in the same look - is still synced, and the exit is the failure.
    runs.clear()
    released.clear()
    lock.mark_rerun("inventory")
    monkeypatch.setattr(mod, "run_index", lambda *a: runs.append(("register",) + a) or 1)
    monkeypatch.setattr(mod.SyncLock, "release", real_release)
    assert mod.cmd_sync(None) == 1
    assert [r[0] for r in runs] == ["register", "inventory"], runs
    assert not lock.has_rerun()


def test_the_inventory_source_is_this_workstations_alone(inv):
    """Another workstation's inventory is on its own disk and is refused; and a
    container with no LANES_WORKSTATION files nothing under its own id
    (Amendment 11, R-A11-14)."""
    other = inv.e.index("sync", "--source", "inventory:Raven")
    assert other.returncode == 2 and "this workstation's inventory is inventory:Eagle" in other.stderr
    assert not inv.e.sqlite.exists()
    nameless = inv.e.index("sync", "--source", "inventory",
                           env={"LANES_WORKSTATION": None, "LANES_IN_CONTAINER": "1"})
    assert nameless.returncode == 2, (nameless.stdout, nameless.stderr)
    assert "LANES_WORKSTATION" in nameless.stderr
    assert not inv.e.sqlite.exists()
    reg = inv.e.index("export", "--out", inv.root, "--source", "inventory")
    assert reg.returncode == 2
    both = inv.e.index("export", "--out", inv.root, "--worktrees", "--source", "inventory")
    assert both.returncode == 64


def test_a_source_is_refused_before_the_lock_is_asked_for(estate):
    """REFUSED WITH THE LOCK HELD TOO (opensoft/openRepoTools#173, Copilot's
    fourth review of #171): a sync that finds the lock held leaves a mark for
    its source and exits 0, and the holder then syncs THIS workstation's
    source for it. So another workstation's inventory, an inventory in a
    container with no name, and another register are refused before the lock
    is asked for - exit 2, and no mark."""
    import fcntl
    state = estate.state / "openRepoTools"
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "lanes-index.lock", "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        other = estate.index("sync", "--source", "inventory:Raven")
        nameless = estate.index("sync", "--source", "inventory",
                                env={"LANES_WORKSTATION": None, "LANES_IN_CONTAINER": "1"})
        register = estate.index("sync", "--source", "register:someone/else")
        assert not list(state.glob("lanes-index.rerun*")), "a refused source left a mark"
        own = estate.index("sync", "--source", "inventory")
    assert other.returncode == 2, (other.stdout, other.stderr)
    assert ("this workstation's inventory is inventory:Eagle, not the inventory `--source` names"
            in other.stderr)
    assert nameless.returncode == 2 and "LANES_WORKSTATION" in nameless.stderr, nameless.stderr
    assert register.returncode == 2, (register.stdout, register.stderr)
    assert "not the source `--source` names" in register.stderr
    # NOT VACUOUS: this workstation's own source, the lock still held, marks
    assert own.returncode == 0 and "another sync holds" in own.stdout, own.stdout
    assert [p.name for p in state.glob("lanes-index.rerun*")] == ["lanes-index.rerun-inventory"]


def test_a_damaged_table_under_valid_provenance_is_unusable_not_a_traceback(estate):
    """`rows()` SPEAKS `StoreUnusable` (opensoft/openRepoTools#173, Copilot's
    fourth review of #171): with the inventory's provenance valid and its
    `worktrees` table gone, `status` says `rows: unread` rather than printing a
    traceback, and `export --worktrees` leaves by the unusable path - `why`,
    exit 3 - so the read flag says why it read the sources."""
    assert estate.index("sync").returncode == 0
    conn = sqlite3.connect(str(estate.sqlite))
    conn.execute("INSERT INTO provenance (source, commit_sha, generation, indexed_utc, "
                 "schema_version) VALUES ('inventory:Eagle', ?, 1, '2026-10-13T00:00:00Z', 1)",
                 ("a" * 64,))
    conn.execute("DROP TABLE worktrees")
    conn.commit()
    conn.close()
    st = estate.index("status")
    assert "Traceback" not in st.stderr, st.stderr
    assert st.returncode == 1, (st.stdout, st.stderr)
    assert re.search(r"rows: +unread - wiped: .*no such table: worktrees", st.stdout), st.stdout
    out = estate.root / "exp"
    out.mkdir()
    exp = estate.index("export", "--out", out, "--worktrees")
    assert "Traceback" not in exp.stderr, exp.stderr
    assert exp.returncode == 3, (exp.returncode, exp.stderr)
    assert (out / "why").read_text().startswith("wiped: ")
    assert "no such table: worktrees" in (out / "why").read_text()
    listed = estate.run("bash", LANES, "--worktrees", "--index")
    assert "read: sources (index wiped: " in listed.stderr, listed.stderr


def test_a_lane_bound_elsewhere_has_no_liveness_pronounced_here(inv):
    """AMENDMENT 18(b) FOR `writer_live`: a lane whose last STARTED/RESUMED bound
    it on another host cannot be pronounced not-live from here - its session
    records are that host's - so the field is NULL, `unknown` in the listing,
    and never the `0` that reads as *nobody is writing there*."""
    log = inv.e.wip / "lanes" / "log" / "repoA-1.md"
    log.write_text(log.read_text(encoding="utf-8") +
                   f"RESUMED — lane repoA-1, session {UUID_A1B}@Raven, 2026-10-05T00:00:00Z, "
                   f"lane:repoA-1 → host raven; container none; window rsess:1 @9; os macos\n",
                   encoding="utf-8")
    inv.e._git("add", "-A")
    inv.e._git("commit", "-q", "-m", "repoA-1 is bound on Raven now")
    inv.e._git("push", "-q", "origin", "main")
    assert inv.sync().returncode == 0
    rows = inv.rows()
    assert rows[f"repoA-1:{inv.run_tree}"]["writer_live"] is None
    assert rows[f"repoA-2:{inv.a2_tree}"]["writer_live"] == 1
    listed = _wt(inv, "repoA-1")
    run = next(l for l in listed.stdout.splitlines() if l.endswith(str(inv.run_tree)))
    assert run.split()[4] == "unknown", run
    # AND LOCALITY WINS OVER A LOCAL LIVE RECORD (Copilot round 1 on #171):
    # repoA-2's session is still running HERE, under an id its row carries,
    # and its latest binding is now on Raven - which is where its writer is
    # pronounced on, not here.
    log = inv.e.wip / "lanes" / "log" / "repoA-2.md"
    log.write_text(log.read_text(encoding="utf-8") +
                   f"RESUMED — lane repoA-2, session {UUID_A2}@Raven, 2026-10-05T00:00:00Z, "
                   f"lane:repoA-2 → host raven; container none; window rsess:2 @9; os macos\n",
                   encoding="utf-8")
    inv.e._git("add", "-A")
    inv.e._git("commit", "-q", "-m", "repoA-2 is bound on Raven too")
    inv.e._git("push", "-q", "origin", "main")
    assert inv.sync().returncode == 0
    assert inv.rows()[f"repoA-2:{inv.a2_tree}"]["writer_live"] is None


def test_an_inventory_that_cannot_be_read_keeps_its_rows(inv):
    """A READ THAT DID NOT HAPPEN IS NOT AN EMPTY INVENTORY (Amendment 7(d);
    Copilot round 2 on #171): a lane whose `trees` directory is there and
    cannot be listed is `UNREAD` - named in the listing, and its rows KEPT by a
    sync rather than removed as trees it no longer has."""
    assert inv.sync().returncode == 0
    trees = inv.lsr / "repoA-1" / "trees"
    trees.chmod(0)
    try:
        if os.access(trees, os.R_OK):
            pytest.skip("this account reads a mode-000 directory (root): nothing to prove here")
        res = inv.sync()
        assert res.returncode == 0, res.stderr
        assert "lane repoA-1: its rows are kept as they are" in res.stdout, res.stdout
        assert "0 removed" in res.stdout or "nothing to write" in res.stdout, res.stdout
        assert f"repoA-1:{inv.dirty_tree}" in inv.rows()
        listed = _wt(inv)
        assert "inventory NOT READ" in listed.stdout, listed.stdout
        assert "could not be read: that is NOT a lane with no worktrees" in listed.stdout
        # AND THE INDEX SAYS THE ROWS ARE HELD (opensoft/openRepoTools#173): the
        # two it kept are listed beside the NOT READ line the sidecars give,
        # which says they are an earlier sync's - not rows freshly read.
        idx = _wt(inv, "repoA-1", "--index")
        assert idx.returncode == 0 and "read: index (sqlite)" in idx.stderr, idx.stderr
        assert str(inv.run_tree) in idx.stdout and str(inv.dirty_tree) in idx.stdout, idx.stdout
        assert re.search(r"inventory NOT READ: its trees directory \S+ is there and could not be "
                         r"listed - the 2 row\(s\) listed for it are kept from the last sync that "
                         r"read it", idx.stdout), idx.stdout
    finally:
        trees.chmod(0o755)
    # READ AGAIN, THE MARK LEAVES: the index read is the source read once more.
    healed = inv.sync()
    assert healed.returncode == 0 and "0 upserted, 1 removed" in healed.stdout, healed.stdout
    src, idx = _wt(inv, "repoA-1"), _wt(inv, "repoA-1", "--index")
    assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), idx.stdout
    assert "NOT READ" not in idx.stdout


def test_a_tree_with_no_path_is_a_tree_and_not_an_unread_marker(inv):
    """A TREE'S PATH CAN BE EMPTY (the review of #219 at ab853b1): a
    current-schema sidecar with a `tree:` and no `path:` is a `TREE` line
    whose path is empty, and a marker read from the empty path alone exported
    it as `UNREAD` and counted its lane as not read. The marker is a row with
    no path AND the branch `unreadable inventory (...)`, which no git ref can
    be; it has a key of its own, so holding the lane never writes it over such
    a tree; and two trees of one lane with one path are two rows, as they are
    two lines of the source read.

    SINCE #115 (PR #252) A CURRENT-SCHEMA SIDECAR WITH NO `path:` IS NOT WHOLE:
    `lanes-edit.sh worktrees` reads no field of it and lists its row under the
    branch `malformed sidecar`, keeping the path it records and naming it by its
    file where it records none. So the source no longer gives a tree an empty
    path, and this test's branches are never read. The row is still a tree and
    never the marker: counted, held over, and exported as its `TREE` line.

    AND SINCE #302 A RECORD THAT NAMES NO ABSOLUTE PATH HOLDS ITS LANE
    (tests/test_pathless_tree_record_302.py): its row is keyed by its id, which
    is not the tree's key, so the helper prints the lane `UNREAD` beside it, and
    a lane held over such a record is no lane to prove a row's key in. This test
    files none any more (it filed `c1-nopath-x`, whose lane read as not read
    from the first sync). What is left of it is a record that is not whole but
    KEEPS a path: `c2-samepath-y` lacks only its `upstream:` and records the
    path of this lane's whole tree, so it keeps its key and holds nothing. It is
    two rows with one path, a tree each - counted, held over, and exported as
    `TREE` lines - and never the marker. The marker's key rule is pinned for a
    row with no path by the forged line in the test two below."""
    trees = inv.lsr / "repoM-1" / "trees"
    tid = "c2-samepath-y"
    (trees / f"{tid}.yaml").write_text("\n".join([
        "schema: 1", "lane: repoM-1", f"tree: {tid}", "path: /nowhere/repoM-1/w",
        "checkout: unknown", "branch: feat/" + tid[-1], "head: " + "3" * 40, "dirty: 0",
        "unpushed: 0", "writer: none", "generation: 0", "operation: none",
        "observed: 2026-10-04T00:00:00Z", ""]))
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    src, idx = _wt(inv, "repoM-1"), _wt(inv, "repoM-1", "--index")
    assert "read: index (sqlite)" in idx.stderr, idx.stderr
    assert src.stdout.count("malformed sidecar") == 1, src.stdout
    assert src.stdout.count("/nowhere/repoM-1/w") == 2, src.stdout
    assert "NOT READ" not in src.stdout, src.stdout
    assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), idx.stdout
    assert "NOT READ" not in idx.stdout
    st = inv.e.index("status")
    assert "rows:        6 worktree(s)\n" in st.stdout, st.stdout
    # HELD OVER, BOTH STAY, the two with one path.
    trees.chmod(0)
    try:
        if os.access(trees, os.R_OK):
            pytest.skip("this account reads a mode-000 directory (root): nothing to prove here")
        assert inv.sync().returncode == 0
        idx = _wt(inv, "repoM-1", "--index")
        assert idx.stdout.count("/nowhere/repoM-1/w") == 2, idx.stdout
        assert "the 2 row(s) listed for it are kept from the last sync" in idx.stdout, idx.stdout
    finally:
        trees.chmod(0o755)
    healed = inv.sync()
    assert healed.returncode == 0 and "0 upserted, 1 removed" in healed.stdout, healed.stdout
    src, idx = _wt(inv, "repoM-1"), _wt(inv, "repoM-1", "--index")
    assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), idx.stdout


def test_a_tree_whose_branch_reads_like_a_marker_is_a_tree(inv):
    """THE MARKER IS ITS KEY (the delta check of #219 at 5bf29d9): a hand-made
    sidecar with no `path:` and a branch that begins `unreadable inventory (`
    is a tree no git ref names, and still a tree - exported as its `TREE`
    line and counted as a worktree - because a marker is the row keyed
    `unread_key(<lane>)`, which no tree's key can be.

    SINCE #115 (PR #252) a sidecar with no `path:` is not whole and its branch
    is never read, so the forged branch is carried by a WHOLE record: a tree
    with a path whose branch alone reads like the marker's."""
    tid = "c3-forged-branch"
    (inv.lsr / "repoM-1" / "trees" / f"{tid}.yaml").write_text("\n".join([
        "schema: 1", "lane: repoM-1", f"tree: {tid}", "path: /nowhere/repoM-1/forged",
        "checkout: unknown",
        "branch: unreadable inventory (forged by hand)", "head: " + "4" * 40,
        "upstream: none", "dirty: 0", "unpushed: 0", "writer: none", "generation: 0",
        "operation: none", "observed: 2026-10-04T00:00:00Z", ""]))
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    src, idx = _wt(inv, "repoM-1"), _wt(inv, "repoM-1", "--index")
    assert "read: index (sqlite)" in idx.stderr, idx.stderr
    assert "unreadable inventory (forged by hand)" in src.stdout, src.stdout
    assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), idx.stdout
    assert "NOT READ" not in idx.stdout
    st = inv.e.index("status")
    assert "rows:        6 worktree(s)\n" in st.stdout, st.stdout


#: The field separator of `lanes-edit.sh worktrees`' lines.
US = "\x1f"


def test_an_older_helpers_tree_with_no_path_and_a_markers_branch_is_a_tree(inv):
    """THE MARKER IS ITS KEY, FOR THE RIGHT REASON (#252's delta review 2, under
    #173's unread marker). A helper older than #252 printed a current-schema
    sidecar with no `path:` as a `TREE` line with an EMPTY path, and its branch
    is the record's own word, so it can read exactly like a marker's. #219 at
    5bf29d9 took a marker to be such a row - no path and a branch beginning
    `unreadable inventory (` - and the delta check made the key the only rule.
    Since #252 the helper here prints no such line, so nothing fed the reader
    one and that rule would pass again. A wrapped `LANES_EDIT` stands in for the
    older helper and prints one: it is a tree - exported as its own `TREE`
    line, counted as a worktree, and kept as one of its lane's rows when the
    lane is held - and never the lane's marker."""
    forged = US.join([
        "TREE", "Eagle", "repoM-1", "unknown", "", "unreadable inventory (forged by an older helper)",
        "", "INDETERMINATE", "", "", "0", "2026-10-04T00:00:00Z", "8" * 40, "0", "0", "0"])
    extra = inv.root / "older-helper-adds"
    extra.write_text(forged + "\n")
    wrapper = inv.root / "lanes-edit-older"
    real = shlex.quote(str(LANES_EDIT))
    # Its `worktrees` READ adds the line, sorted in as the helper sorts; an
    # `--index` read and every other subcommand are the helper's own.
    wrapper.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        case " $* " in *" --index "*) exec bash {real} "$@" ;; esac
        [ "${{1-}}" = worktrees ] || exec bash {real} "$@"
        out="$(bash {real} "$@")"; rc=$?
        case "$rc" in 0|8) : ;; *) exit "$rc" ;; esac
        {{ [ -z "$out" ] || printf '%s\\n' "$out"; cat {shlex.quote(str(extra))}; }} | LC_ALL=C sort
        """))
    wrapper.chmod(0o755)
    older = {"LANES_EDIT": str(wrapper)}
    res = inv.sync(env=older)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert inv.rows()["repoM-1:"]["branch"] == "unreadable inventory (forged by an older helper)"
    src, idx = _wt(inv, env=older), _wt(inv, "--index", env=older)
    assert "read: index (sqlite)" in idx.stderr, idx.stderr
    assert "unreadable inventory (forged by an older helper)" in src.stdout, src.stdout
    assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), idx.stdout
    assert "NOT READ" not in idx.stdout
    st = inv.e.index("status")
    assert "rows:        6 worktree(s)\n" in st.stdout, st.stdout
    # HELD OVER, IT IS ONE OF THE LANE'S KEPT ROWS: the older helper no longer
    # names it, and the lane's `trees` directory cannot be listed.
    extra.write_text("")
    trees = inv.lsr / "repoM-1" / "trees"
    trees.chmod(0)
    try:
        if os.access(trees, os.R_OK):
            pytest.skip("this account reads a mode-000 directory (root): nothing to prove here")
        held = inv.sync(env=older)
        assert held.returncode == 0, (held.stdout, held.stderr)
        assert "lane repoM-1: its rows are kept as they are" in held.stdout, held.stdout
        assert "repoM-1:" in inv.rows(), sorted(inv.rows())
        idx = _wt(inv, "repoM-1", "--index", env=older)
        assert "the 2 row(s) listed for it are kept from the last sync" in idx.stdout, idx.stdout
    finally:
        trees.chmod(0o755)


def test_an_inventory_sync_asks_for_the_workstation_once(estate):
    """ONE `workstation` READ A SYNC (the review of #219 at ab853b1): the
    refusal before the lock asks `lanes-edit.sh workstation`, and a sync that
    then takes the lock asked a second time for the same answer. It is the
    process's own and is asked once."""
    calls = estate.root / "helper-calls"
    wrapper = estate.root / "lanes-edit-counting"
    wrapper.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$1\" >> {calls}\n"
                       f"exec bash {LANES_EDIT} \"$@\"\n")
    wrapper.chmod(0o755)
    res = estate.index("sync", "--source", "inventory", env={"LANES_EDIT": str(wrapper)})
    assert res.returncode == 0, (res.stdout, res.stderr)
    asked = calls.read_text().splitlines()
    assert "worktrees" in asked, asked  # not vacuous: the sync took the lock and read
    assert asked.count("workstation") == 1, asked


def test_a_first_sync_that_cannot_read_a_lane_says_not_read_in_the_index(inv):
    """A FIRST SYNC IS NOT AN EMPTY ANSWER (opensoft/openRepoTools#173): a lane
    whose `trees` directory is there and cannot be listed at the FIRST sync has
    no rows to keep, and the sync committed usable provenance with nothing for
    it - so `lanes --index --worktrees <lane>` answered "no worktree is
    inventoried" where the sidecars say NOT READ. The lane's marker row is
    exported as the source's own `UNREAD` line, so the two reads are the same
    bytes; and a replay of the same read writes nothing."""
    trees = inv.lsr / "repoA-1" / "trees"
    trees.chmod(0)
    try:
        if os.access(trees, os.R_OK):
            pytest.skip("this account reads a mode-000 directory (root): nothing to prove here")
        res = inv.sync()
        assert res.returncode == 0, res.stderr
        for args in (("repoA-1",), ()):
            src = _wt(inv, *args)
            idx = _wt(inv, *args, "--index")
            assert "read: index (sqlite)" in idx.stderr, (args, idx.stderr)
            assert "no worktree is inventoried" not in idx.stdout, (args, idx.stdout)
            assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), (args, idx.stdout)
            assert "inventory NOT READ" in idx.stdout, (args, idx.stdout)
        st = inv.e.index("status")
        assert "rows:        3 worktree(s), and 1 lane(s) whose inventory could not be read " \
            "at the last sync" in st.stdout, st.stdout
        again = inv.sync()
        assert again.returncode == 0 and "nothing to write" in again.stdout, again.stdout
    finally:
        trees.chmod(0o755)


def test_a_lane_that_went_back_with_no_trees_is_held_too(inv):
    """THE FENCE FOR A LANE WHOSE ROWS WOULD ALL LEAVE (Copilot round 2 on
    #171): its snapshot moved aside and begun again, and no tree recorded since
    - a `sync` asks `lane-state` for its generation, finds it went back, and
    keeps its rows; `reconcile` takes the lane as it now stands."""
    assert inv.sync().returncode == 0
    snap = inv.lsr / "repoA-2" / "lane-state.yaml"
    snap.rename(snap.with_suffix(".aside"))
    for sidecar in (inv.lsr / "repoA-2" / "trees").iterdir():
        sidecar.unlink()
    inv.ok("set-lane-state", "repoA-2", "RUNNING", "--operation", "op-test-empty")
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    assert "lane repoA-2: its rows are kept as they are" in res.stdout, res.stdout
    assert f"repoA-2:{inv.a2_tree}" in inv.rows()
    rec = inv.e.index("reconcile", "--source", "inventory")
    assert rec.returncode == 0, rec.stderr
    assert "generation went back from 2 to 1" in rec.stdout, rec.stdout
    assert f"repoA-2:{inv.a2_tree}" not in inv.rows()


@contextlib.contextmanager
def _unreadable(e: Estate, *revs: str):
    """THE PUBLISHED OBJECTS `revs` NAME, UNREADABLE FOR THE BLOCK: each one's
    loose object in the workspace clone is moved aside, so a `git show` or a
    `git ls-tree` that needs it fails - as on a clone whose object is damaged,
    or a partial clone that cannot fetch it - while every other object reads;
    and it is put back on the way out. The clone wrote these objects itself,
    so they are loose and in no pack."""
    moved = []
    try:
        for rev in revs:
            sha = e._git("rev-parse", rev).strip()
            obj = e.wip / ".git" / "objects" / sha[:2] / sha[2:]
            assert obj.is_file(), f"{rev} ({sha}) is not a loose object of the clone"
            aside = obj.with_name(obj.name + ".aside")
            obj.rename(aside)
            moved.append((obj, aside))
        yield
    finally:
        for obj, aside in reversed(moved):
            aside.rename(obj)


def _git_shim(inv: Inventory, match: str, first: int,
              last: int | None = None) -> tuple[dict, Path]:
    """A `git` FOR ONE CALL'S ENVIRONMENT THAT FAILS SOME CALLS AND ONLY THOSE:
    each call whose arguments contain `match` is counted and logged, the
    `first`th to the `last`th of them (every later one where `last` is None)
    exit 128 as git does on an object it could not read, and every call -
    those among them - is otherwise the real git. A failure `_unreadable`
    cannot make: one that comes and goes between two reads of the same object.
    Returns the environment to run with and the log of the counted calls."""
    real = shutil.which("git", path=inv.e.env["PATH"])
    assert real, "no git on PATH"
    shim = inv.root / "git-shim"
    shim.mkdir(exist_ok=True)
    (shim / "git").write_text(textwrap.dedent("""\
        #!/bin/sh
        case " $* " in
          *"$SHIM_MATCH"*)
            n=0
            [ -f "$SHIM_LOG" ] && n=$(wc -l < "$SHIM_LOG" | tr -d ' ')
            n=$((n + 1))
            printf '%s %s\\n' "$n" "$*" >> "$SHIM_LOG"
            if [ "$n" -ge "$SHIM_FIRST" ] && [ "$n" -le "$SHIM_LAST" ]; then
              echo "fatal: the test's git shim fails call $n" >&2
              exit 128
            fi ;;
        esac
        exec @REAL@ "$@"
        """).replace("@REAL@", shlex.quote(real)))
    (shim / "git").chmod(0o755)
    log = inv.root / "git-shim.log"
    if log.exists():
        log.unlink()
    return {"PATH": inv.e.path_with(shim), "SHIM_MATCH": match, "SHIM_LOG": str(log),
            "SHIM_FIRST": str(first), "SHIM_LAST": str(last or 999999)}, log


def _shim_calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def _sidecar(lsr: Path, lane: str, head: str) -> Path:
    """A whole current-schema record of one tree of `lane`, at
    `/nowhere/<lane>/w`, under the control root `lsr` - the shape the
    fixture's repoM records take."""
    trees = lsr / lane / "trees"
    trees.mkdir(parents=True, exist_ok=True)
    path = trees / f"c0-{lane}.yaml"
    path.write_text("\n".join([
        "schema: 1", f"lane: {lane}", f"tree: c0-{lane}", f"path: /nowhere/{lane}/w",
        "checkout: unknown", f"branch: feat/{lane}", f"head: {head}", "upstream: none",
        "dirty: 0", "unpushed: 0", "writer: none", "generation: 0", "operation: none",
        "observed: 2026-10-04T00:00:00Z", ""]))
    return path


#: THE READS A LANE LISTING RESTS ON (opensoft/openRepoTools#173 item c1), each
#: made to fail, beside the lanes of the seed it is the ONE source of: repoZ-1's
#: row is in the archive alone, repoC-1's in the register alone, and repoB-1 is
#: a log with no row. The last case fails all three, which left the listing
#: EMPTY - and the helper saying "none".
PARTIAL_LISTINGS = [
    ("archive", ("origin/main:lanes/archive/LANES-retired.md",), ("repoZ-1",),
     ("the archive lanes/archive/LANES-retired.md could not be read",)),
    ("register", ("origin/main:lanes/LANES.md",), ("repoC-1",),
     ("the register lanes/LANES.md could not be read",)),
    ("log-listing", ("origin/main:lanes/log",), ("repoB-1",),
     ("the object logs under origin/main:lanes/log/ could not be listed",)),
    ("all-three", ("origin/main:lanes/archive/LANES-retired.md", "origin/main:lanes/LANES.md",
                   "origin/main:lanes/log"), ("repoZ-1", "repoC-1", "repoB-1"),
     ("the register lanes/LANES.md could not be read",
      "the archive lanes/archive/LANES-retired.md could not be read",
      "the object logs under origin/main:lanes/log/ could not be listed")),
]
HEADS = {"repoZ-1": "5" * 40, "repoC-1": "6" * 40, "repoB-1": "7" * 40}


@pytest.mark.parametrize("kind,revs,only,whys", PARTIAL_LISTINGS,
                         ids=[case[0] for case in PARTIAL_LISTINGS])
def test_a_lane_listing_that_is_not_whole_removes_no_row(inv, kind, revs, only, whys):
    """A PARTIAL LANE LISTING IS NO ANSWER (opensoft/openRepoTools#173 item c1,
    Copilot's fourth review of #171). The inventory is read through the lane
    listing, whose lanes are the names the register's rows, the archive's rows
    and the object logs give. Where one of those reads failed the listing said
    so on stderr - the log listing not even that - and listed what the others
    gave, and the sync took it for whole: a lane with a tree and its only row
    in an archive that could not be read was a lane with no trees, and its rows
    were removed. With all three unread the listing was empty, the helper said
    "none", and the sync removed every row.

    The read now says so in ONE `PARTIAL` line, `lanes --worktrees` prints it
    as the lane listing NOT WHOLE, and a sync or a reconcile over it writes
    NOTHING - not a lane it did list either - and says why, so the index stays
    the last whole read. A lane asked for by name is read by its name, which no
    listing gives, and is not partial. The next sync over a whole listing
    writes what moved meanwhile."""
    for lane in only:
        _sidecar(inv.lsr, lane, HEADS[lane])
    assert inv.sync().returncode == 0
    for lane in only:
        assert f"{lane}:/nowhere/{lane}/w" in inv.rows(), lane  # not vacuous
    before = dump(inv.e.sqlite, with_utc=True)
    # A LANE THE LISTING DOES NAME MOVES MEANWHILE.
    moved = inv.lsr / "repoM-1" / "trees" / "c0-repoM-1.yaml"
    moved.write_text(moved.read_text().replace("dirty: 0", "dirty: 4"))
    with _unreadable(inv.e, *revs):
        res = inv.sync()
        rows = inv.rows()
        for lane in only:
            assert f"{lane}:/nowhere/{lane}/w" in rows, (lane, res.stdout, res.stderr)
        assert dump(inv.e.sqlite, with_utc=True) == before, res.stdout
        assert res.returncode == 1, (res.stdout, res.stderr)
        assert "the lane listing `lanes-edit.sh worktrees --all` reads the inventory " \
            f"through was not whole - {'; '.join(whys)} - so a lane it could not name " \
            "would read as a lane with no worktrees" in res.stderr, res.stderr
        assert "- nothing written" in res.stderr, res.stderr
        assert "was not whole" in inv.e.index("status").stdout
        rec = inv.e.index("reconcile", "--source", "inventory")
        assert rec.returncode == 1 and "was not whole" in rec.stderr, (rec.stdout, rec.stderr)
        assert dump(inv.e.sqlite, with_utc=True) == before, rec.stdout
        # A DRY RUN IS REFUSED THE SAME WAY, rather than show as removals the
        # rows of the lanes the read could not name (N4 of the review of #289).
        dry = inv.e.index("reconcile", "--source", "inventory", "--dry-run")
        assert dry.returncode == 1, (dry.stdout, dry.stderr)
        assert f"was not whole - {'; '.join(whys)} - " in dry.stderr, dry.stderr
        assert "removed" not in dry.stdout, dry.stdout
        listed = _wt(inv)
        assert listed.returncode == 0, listed.stderr
        said = [line for line in listed.stdout.splitlines() if "lane listing NOT WHOLE: " in line]
        assert len(said) == 1 and said[0].split()[:3] == ["Eagle", "(every", "lane)"], \
            listed.stdout
        assert said[0].split("lane listing NOT WHOLE: ", 1)[1] == "; ".join(whys), said[0]
        assert "the lane listing above is NOT WHOLE: a lane it could not name is missing " \
            "from it, and that is NOT a lane with no worktrees." in listed.stdout, listed.stdout
        for lane in only:
            assert f" {lane} " not in listed.stdout, listed.stdout
        named = _wt(inv, "repoA-1")
        assert named.returncode == 0, (named.stdout, named.stderr)
        assert "2 worktree(s) in 1 lane(s)" in named.stdout, named.stdout
        assert "NOT WHOLE" not in named.stdout, named.stdout
    healed = inv.sync()
    assert healed.returncode == 0, healed.stderr
    assert "1 upserted, 0 removed" in healed.stdout, healed.stdout
    assert inv.rows()["repoM-1:/nowhere/repoM-1/w"]["dirty_count"] == 4
    src, idx = _wt(inv), _wt(inv, "--index")
    assert (idx.returncode, idx.stdout) == (src.returncode, src.stdout), idx.stdout
    assert "NOT WHOLE" not in src.stdout


def _a_lane_found_through_its_log(inv: Inventory) -> tuple[dict, str]:
    """repoB-1 RESUMED in a checkout of its own, whose `dir` only its log
    records, with one tree under `<parent of that dir>/.lane-state` - synced
    with no override naming a control root, so the tree is found through the
    log's `dir` alone. Returns that environment and the tree's row key."""
    away = inv.root / "elsewhere"
    (away / "repoB").mkdir(parents=True)
    log = inv.e.wip / "lanes" / "log" / "repoB-1.md"
    log.write_text(log.read_text(encoding="utf-8") +
                   f"RESUMED — lane repoB-1, session {UUID_B1}@Eagle, 2026-10-05T00:00:00Z, "
                   f"lane:repoB-1 → dir {away / 'repoB'}; profile team-02a\n", encoding="utf-8")
    inv.e._git("add", "-A")
    inv.e._git("commit", "-q", "-m", "repoB-1 resumed in a checkout of its own")
    inv.e._git("push", "-q", "origin", "main")
    _sidecar(away / ".lane-state", "repoB-1", HEADS["repoB-1"])
    by_dir = {"LANES_LANE_STATE_ROOT": None}
    assert inv.sync(env=by_dir).returncode == 0
    key = "repoB-1:/nowhere/repoB-1/w"
    assert key in inv.rows(), sorted(inv.rows())  # found through its log's `dir` alone
    return by_dir, key


def test_a_lane_whose_log_could_not_be_read_keeps_its_rows(inv):
    """A LOG THE LISTING COULD NOT READ IS NOT A LANE WITH NO TREES
    (opensoft/openRepoTools#173 item c1). Where no override names a control
    root, a lane's trees are under `<parent of its dir>/.lane-state/<lane>`, and
    `dir` is its log's. A published log git could not read gave the listing no
    `dir`, the root fell through to `$PROJECTS_ROOT/.lane-state/<lane>`, where
    no tree is, and the sync removed the lane's rows. That log is a read the
    listing rests on like the other three: the read is `PARTIAL`, naming it,
    and nothing is written."""
    by_dir, key = _a_lane_found_through_its_log(inv)
    with _unreadable(inv.e, "origin/main:lanes/log/repoB-1.md"):
        res = inv.sync(env=by_dir)
        assert key in inv.rows(), (res.stdout, res.stderr)
        assert res.returncode == 1, (res.stdout, res.stderr)
        assert "was not whole - these object logs could not be read: lanes/log/repoB-1.md - " \
            "so a lane it could not name" in res.stderr, res.stderr
    healed = inv.sync(env=by_dir)
    assert healed.returncode == 0 and "nothing to write" in healed.stdout, healed.stdout


def test_a_listing_whose_log_warnings_could_not_be_kept_is_not_whole(inv):
    """WHETHER A LOG FAILED IS A READ TOO (opensoft/openRepoTools#173 item c1).
    The listing learns which published logs git could not read from the
    warnings their read leaves in a temporary file. Where no temporary file can
    be made those warnings go to stderr and nowhere else, so whether any log
    failed is NOT KNOWN - the listing says so and classes no row DORMANT on it -
    and the inventory's read says so too, in its `PARTIAL` line, rather than
    answer as though every log had been read."""
    res = inv.e.edit("worktrees", "--all", env={"TMPDIR": str(inv.root / "not-there")})
    assert res.returncode == 0, res.stderr
    partial = [line.split(US) for line in res.stdout.splitlines()
               if line.startswith("PARTIAL" + US)]
    assert partial == [["PARTIAL", "Eagle", "whether every object log could be read is not "
                        "known, because the warnings of their read could not be kept"]], \
        res.stdout
    assert res.stdout.count("TREE" + US) == 5, res.stdout


@pytest.mark.parametrize("mode", [0o000, 0o400], ids=["mode-000", "mode-400"])
def test_an_unlistable_log_directory_with_no_origin_is_a_partial_listing(inv, mode):
    """THE SAME READ WITH NO `origin` (opensoft/openRepoTools#173 item c1): under
    `LANES_NO_GIT=1`, or in a checkout with no `origin/<branch>`, the lanes with
    a log are named by listing this checkout's log directory - and one that is
    there and cannot be listed named none of them. NOR CAN ONE THAT CANNOT BE
    SEARCHED (N1 of the review of #289): `ls` lists an `r--` directory, and
    then not one of its files could be opened."""
    no_git = {"LANES_NO_GIT": "1"}
    _sidecar(inv.lsr, "repoB-1", HEADS["repoB-1"])
    assert inv.sync(env=no_git).returncode == 0
    key = "repoB-1:/nowhere/repoB-1/w"
    assert key in inv.rows(), sorted(inv.rows())
    logdir = inv.e.wip / "lanes" / "log"
    logdir.chmod(mode)
    try:
        if os.access(logdir, os.R_OK) and os.access(logdir, os.X_OK):
            pytest.skip(f"this account lists and searches a mode-{mode:03o} directory (root): "
                        f"nothing to prove here")
        res = inv.sync(env=no_git)
        assert key in inv.rows(), (res.stdout, res.stderr)
        assert res.returncode == 1, (res.stdout, res.stderr)
        assert "the log directory " in res.stderr, res.stderr
        assert "lanes/log is there and could not be listed" in res.stderr, res.stderr
    finally:
        logdir.chmod(0o755)
    healed = inv.sync(env=no_git)
    assert healed.returncode == 0 and "nothing to write" in healed.stdout, healed.stdout


#: The calls the listing's reads make, as the shim sees them (`" $* "`).
SHOW_ARCHIVE = "show origin/main:lanes/archive/LANES-retired.md "
SHOW_REGISTER = "show origin/main:lanes/LANES.md "
LIST_LOGS = "ls-tree --name-only origin/main -- lanes/log/ "
SHOW_LOG_B1 = "show origin/main:lanes/log/repoB-1.md "


def test_the_listing_names_lanes_from_the_archive_it_checked(inv):
    """THE ARCHIVE THE LISTING READS IS THE ONE IT CHECKED (the review of #289,
    SHOULD-1(b), its probe P2). The read asked whether the archive could be
    read and the listing then read it again, four times, for its rows: an
    archive that read for the check and failed after it left out every lane
    whose only row it holds, from a listing taken as whole, and the sync
    removed their rows. The check's read is now the listing's: a failure after
    it is never read at all."""
    _sidecar(inv.lsr, "repoZ-1", HEADS["repoZ-1"])
    assert inv.sync().returncode == 0
    key = "repoZ-1:/nowhere/repoZ-1/w"
    assert key in inv.rows(), sorted(inv.rows())
    env, log = _git_shim(inv, SHOW_ARCHIVE, first=2)
    res = inv.sync(env=env)
    calls = _shim_calls(log)
    assert calls and calls[0].startswith("1 "), calls  # the shim saw the read: not vacuous
    assert key in inv.rows(), (res.stdout, res.stderr, calls)
    assert res.returncode == 0 and "nothing to write" in res.stdout, (res.stdout, res.stderr)


@pytest.mark.parametrize("last", [2, None], ids=["the-next-read", "every-later-read"])
def test_a_log_list_that_fails_after_the_check_removes_no_row(inv, last):
    """THE LIST OF THE LOGS, TOO (the review of #289, SHOULD-1, its probe P11).
    It was listed for the check, again for the listing's names and again for
    the events, out of which every lane's `dir` comes - and where no override
    names a control root, a lane's trees are found under its `dir`. A later
    list that failed was a listing with no lane named by a log alone, or with
    no `dir` for any lane - the read even said "none" - and the sync removed
    the rows. The names now come from the list the check made, and the
    events' own list, where it fails, says so: the read is `PARTIAL` and
    nothing is written."""
    by_dir, key = _a_lane_found_through_its_log(inv)
    before = dump(inv.e.sqlite, with_utc=True)
    env, shim_log = _git_shim(inv, LIST_LOGS, first=2, last=last)
    res = inv.sync(env={**by_dir, **env})
    calls = _shim_calls(shim_log)
    assert len(calls) >= 2 and calls[0].startswith("1 "), calls  # a later list failed
    assert key in inv.rows(), (res.stdout, res.stderr, calls)
    assert dump(inv.e.sqlite, with_utc=True) == before, res.stdout
    assert res.returncode == 1, (res.stdout, res.stderr, calls)
    assert "was not whole - the object logs under origin/main:lanes/log/ could not be " \
        "listed - so a lane it could not name" in res.stderr, res.stderr
    healed = inv.sync(env=by_dir)
    assert healed.returncode == 0 and "nothing to write" in healed.stdout, healed.stdout


def test_a_lanes_log_that_fails_after_the_listing_removes_no_row(inv):
    """A LANE'S `dir` IS READ ONCE, BY THE LISTING (review r2 of #289,
    SHOULD-A, its probe C1). Where no override names a control root, a lane's
    trees are under the root its log's `dir` places, and the listing reads
    that `dir` out of the events. The list of the lane's trees and its
    lifecycle snapshot then worked the root out again, each reading the lane's
    log a second time, and a `git show` that failed there was thrown away: the
    root fell to `$PROJECTS_ROOT/.lane-state`, where nothing is, the lane read
    as one with no trees, and the sync removed its rows. Both now take the
    listing's `dir`, so the read that could fail is not made. The lane has a
    snapshot here because, with none, a snapshot asked under the wrong root
    answers what the right one would."""
    by_dir, key = _a_lane_found_through_its_log(inv)
    put = inv.e.edit("set-lane-state", "repoB-1", "RUNNING", "--operation", "op-test-b1",
                     env=by_dir)
    assert put.returncode == 0, put.stderr
    assert inv.sync(env=by_dir).returncode == 0
    assert inv.rows()[key]["lifecycle"] == "RUNNING", inv.rows()[key]  # read through `dir` too
    before = dump(inv.e.sqlite, with_utc=True)
    shim, log = _git_shim(inv, SHOW_LOG_B1, first=2, last=2)
    res = inv.sync(env={**by_dir, **shim})
    calls = _shim_calls(log)
    assert calls and calls[0].startswith("1 "), calls  # the listing's own read: not vacuous
    assert len(calls) == 1, calls  # and the lane's `dir` is not read again (NIT-B, #290)
    assert key in inv.rows(), (res.stdout, res.stderr, calls)
    assert dump(inv.e.sqlite, with_utc=True) == before, (res.stdout, res.stderr, calls)
    assert "kept as they are" not in res.stdout, (res.stdout, calls)  # and no lane held over it
    if res.returncode == 1:  # refused over the read that failed, saying why
        assert "was not whole - " in res.stderr, res.stderr
    else:
        assert res.returncode == 0 and "nothing to write" in res.stdout, (res.stdout, res.stderr)


def test_the_listing_names_the_lane_whose_log_sorts_last(inv):
    """THE LAST NAME IN THE LIST OF THE LOGS IS A LANE TOO (review r2 of #289,
    NIT-2, its mutant mNoSentinel). The list the check made is handed to the
    listing with its last newline kept, because `while read` drops a last line
    that has none - and a lane whose log sorts last, with no row in the
    register or the archive, would go unnamed from a listing taken as whole.
    The seed's last log, repoM-2's, has a row; repoY-1 has a log alone."""
    uid = "99999999-0001-4000-8000-000000009001"
    inv.e.commit_paths({"lanes/log/repoY-1.md":
                        f"STARTED — lane repoY-1, session {uid}@Eagle, 2026-10-04T00:00:00Z, "
                        f"lane:repoY-1 → home opensoft/repoY; dir /work/repoY\n"},
                       "repoY-1 has a log alone, and it sorts last")
    names = inv.e._git("ls-tree", "--name-only", "origin/main", "--", "lanes/log/").split()
    assert names[-1] == "lanes/log/repoY-1.md", names  # the LAST name: not vacuous
    _sidecar(inv.lsr, "repoY-1", "8" * 40)
    res = inv.sync()
    assert res.returncode == 0, res.stderr
    assert "repoY-1:/nowhere/repoY-1/w" in inv.rows(), (res.stdout, sorted(inv.rows()))


def test_the_register_is_asked_before_the_listing(inv):
    """THE REGISTER IS ASKED BEFORE THE LISTING READS IT (the review of #289,
    SHOULD-2, its probe P3). A register read that succeeds is cached, and the
    listing reads the cache; asked after the listing, the check would make a
    read of its own - and a register that failed for the listing and read for
    the check was a listing taken as whole without every lane whose only row
    is the register's. Here the FIRST read fails and every later one reads:
    that first read is the check's, so the read is `PARTIAL` - conservatively,
    as the listing's own read would have been whole - and nothing is
    written."""
    _sidecar(inv.lsr, "repoC-1", HEADS["repoC-1"])
    assert inv.sync().returncode == 0
    key = "repoC-1:/nowhere/repoC-1/w"
    assert key in inv.rows(), sorted(inv.rows())
    before = dump(inv.e.sqlite, with_utc=True)
    env, log = _git_shim(inv, SHOW_REGISTER, first=1, last=1)
    res = inv.sync(env=env)
    calls = _shim_calls(log)
    assert len(calls) >= 2, calls  # the first read failed and a later one read
    assert key in inv.rows(), (res.stdout, res.stderr, calls)
    assert dump(inv.e.sqlite, with_utc=True) == before, res.stdout
    assert res.returncode == 1, (res.stdout, res.stderr, calls)
    assert "was not whole - the register lanes/LANES.md could not be read - so a lane it " \
        "could not name" in res.stderr, res.stderr


def test_the_index_read_says_its_last_sync_failed(inv):
    """A SYNC THAT WROTE NOTHING IS SAID BY THE INDEX READ TOO (N2 of the
    review of #289). A sync that refuses a listing that is not whole leaves the
    table and its `synced` time as they were, and `lanes --index --worktrees`
    said only that time: a table no later sync could write read as a current
    one. The read's line now carries this workstation's last error beside its
    source, as `status` does and under the name `status` gives it - a refused
    `reconcile` records one too, and a `--dry-run` none (lane 3's ruling, B4 of
    opensoft/openRepoTools-code#89 comment 6947619546, in place of review r2's
    NIT-1) - until a sync succeeds again."""
    _sidecar(inv.lsr, "repoZ-1", HEADS["repoZ-1"])
    assert inv.sync().returncode == 0
    with _unreadable(inv.e, "origin/main:lanes/archive/LANES-retired.md"):
        assert inv.sync().returncode == 1
    idx = _wt(inv, "--all", "--index")
    assert idx.returncode == 0, idx.stderr
    assert re.search(r"read: index \(sqlite\) at inventory:Eagle synced " + UTC.pattern +
                     r" \(last error: " + UTC.pattern + r" unread: the lane listing "
                     r"`lanes-edit\.sh worktrees --all` reads the inventory through was not "
                     r"whole - the archive lanes/archive/LANES-retired\.md could not be read - ",
                     idx.stderr), idx.stderr
    assert inv.sync().returncode == 0
    again = _wt(inv, "--all", "--index")
    assert re.search(r"read: index \(sqlite\) at inventory:Eagle synced " + UTC.pattern + r"\n",
                     again.stderr), again.stderr
    assert "(last error: " not in again.stderr, again.stderr


def test_the_round_cap_hands_back_a_mark_it_took(estate, monkeypatch):
    """THE CAP LOSES NO MARK (Copilot round 2 on #171): a holder that stops at
    its eighth round with a source still due - its mark taken off the disk and
    not yet synced - marks it again for the next sync."""
    _as_estate(monkeypatch, estate)
    mod = load_indexer()
    lock = mod.SyncLock()
    os.makedirs(mod.state_dir(), exist_ok=True)
    runs = []

    def busy(kind):
        def run(*a):
            runs.append(kind)
            lock.mark_rerun(kind)  # every round, a write lands behind it
            return 0
        return run

    monkeypatch.setattr(mod, "run_index", busy("register"))
    monkeypatch.setattr(mod, "run_inventory", busy("inventory"))
    lock.mark_rerun("inventory")
    assert mod.cmd_sync(None) == 0
    assert len(runs) == 8, runs
    assert runs[-1] == "inventory", runs
    assert os.path.exists(lock.rerun_path("register")), \
        "the register's mark was taken at the cap and never handed back"
    assert os.path.exists(lock.rerun_path("inventory"))


# ======================================================= the bootstrap's arguments
#
# T109's follow-up, on Codex's exact-head review of P10 (opensoft/openRepoTools#165
# 6889426463): `bootstrap` refused a connection string only in its four flags' values,
# after its usage, so a positional argument or an unknown option that carried one
# ended 64 with the whole argument echoed on stderr. Its usage texts now echo no
# argument's value: an unknown argument is named in `ready`'s form, as `login`'s is
# (lane 3's ruling, #165 6894208108), so a bare secret that no rule can tell from a
# word is not echoed either.


@pytest.mark.parametrize("where", ["positional", "unknown-option", "bare-positional",
                                   "bare-unknown-option", "control"])
def test_the_bootstrap_refuses_a_secret_in_any_argument_and_never_echoes_it(estate, where):
    """NO ARGUMENT ECHOES A SECRET (operations.md section 2.4's refusals; T109):
    an argument that carries a connection string or a password is refused with 2
    wherever it stands, before the usage is read, as `login`'s are; and a bare
    secret, positional or as an unknown option's value, is usage (64), named in
    `ready`'s form, which quotes an unknown argument only where all of it is
    letters and '-' after one or two '-', so not at all. The value reaches
    neither stdout nor stderr, and no `psql` is run. Every other flag is in
    order: `[control]`, with no extra argument, does run `psql` (the fake's exit
    1 is 69), so in the other ids it is the extra argument, refused or usage,
    that keeps `psql` from running (lane 3's NIT 1 on PR 89 at 4a8b7b8b)."""
    secret = f"t109-FAKE-{where}-not-a-secret"
    argument, code, words = {
        "positional": (f"postgresql://lanes_register_admin:{secret}@db.invalid:5432/register",
                       2, "carries a connection string or a password"),
        "unknown-option": (f"--dsn=host=db.invalid user=lanes_register_admin password={secret}",
                           2, "carries a connection string or a password"),
        "bare-positional": (secret, 64,
                            "bootstrap: unknown argument that is not one of its flags"),
        "bare-unknown-option": (f"--dsn={secret}", 64,
                                "bootstrap: unknown argument that is not one of its flags"),
        "control": (None, 69, "psql exited 1"),
    }[where]
    fake = estate.root / "pgfake"
    fake.mkdir()
    ran = estate.root / "psql-ran.txt"
    (fake / "psql").write_text(f"#!/bin/sh\necho ran >> {shlex.quote(str(ran))}\nexit 1\n")
    (fake / "psql").chmod(0o755)
    res = estate.index("bootstrap", "--admin-service", "t109admin", "--label", "t109-label",
                       "--repository", "opensoft/t109-workspace", "--lane", "t109-operator",
                       "--no-passwords", *([] if argument is None else [argument]),
                       env={"PATH": estate.path_with(fake)})
    said = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}".replace(secret, "<the secret>")
    assert res.returncode == code, f"[{where}] exit {res.returncode}, not {code}:\n{said}"
    assert secret not in res.stdout and secret not in res.stderr, (
        f"[{where}] the secret was echoed:\n{said}")
    assert words in res.stderr, said
    if where == "control":
        assert ran.exists(), f"[control] psql was not run:\n{said}"
    else:
        assert not ran.exists(), f"[{where}] psql was run:\n{said}"


# ================================================= the argument-naming form, ready's
#
# Lane 3's ruling (opensoft/openRepoTools#165 6894208108) on lane 1's two forms
# (6894177366): `bootstrap` and `login` name an unknown argument as `ready` does,
# quoted only where all of it matches `--?[A-Za-z][A-Za-z-]{0,30}`, and otherwise as
# "unknown argument that is not one of its flags". One row for each example line of
# lane 1's post, for each command. `login` has no `s3cret` row: a word that does not
# start with '-' is its action or its engineer, never an unknown argument.

#: (id, the argument, what the usage line shows in its place)
UNKNOWN_ARGUMENTS = [
    ("dash-secret", "-s3cret", "that is not one of its flags"),
    ("flag-word", "--frob", "'--frob'"),
    ("flag-value", "--pw=s3cret", "that is not one of its flags"),
    ("positional", "s3cret", "that is not one of its flags"),
    ("dash-letters", "-abcdef", "'-abcdef'"),
]

#: Each command with every other argument in order, so that only the unknown one is
#: usage.
UNKNOWN_ARGUMENT_COMMANDS = {
    "bootstrap": ("bootstrap", "--admin-service", "t109admin", "--label", "t109-label",
                  "--repository", "opensoft/t109-workspace", "--lane", "t109-operator",
                  "--no-passwords"),
    "login": ("login", "rotate", "--dump-job", "--admin-service", "t110admin"),
}


@pytest.mark.parametrize("command, argument, shown", [
    pytest.param(command, argument, shown, id=f"{command}-{case}")
    for command in UNKNOWN_ARGUMENT_COMMANDS
    for case, argument, shown in UNKNOWN_ARGUMENTS
    if not (command == "login" and case == "positional")])
def test_bootstrap_and_login_name_an_unknown_argument_as_ready_does(estate, command,
                                                                    argument, shown):
    """READY'S FORM (lane 3's ruling, #165 6894208108): an unknown argument is
    usage (64), quoted only where all of it is letters and '-' after one or two
    '-', and otherwise not shown, so no argument that holds a digit, a symbol or
    '=' reaches stderr. The usage line is all that is printed, and no `psql` is
    run."""
    fake = estate.root / "pgfake"
    fake.mkdir()
    ran = estate.root / "psql-ran.txt"
    (fake / "psql").write_text(f"#!/bin/sh\necho ran >> {shlex.quote(str(ran))}\nexit 1\n")
    (fake / "psql").chmod(0o755)
    res = estate.index(*UNKNOWN_ARGUMENT_COMMANDS[command], argument,
                       env={"PATH": estate.path_with(fake)})
    said = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert res.returncode == 64, f"exit {res.returncode}, not 64:\n{said}"
    assert res.stderr == (f"lanes-index: {command}: unknown argument {shown} - see "
                          f"lanes-index {command} --help\n"), said
    assert res.stdout == "", said
    assert "s3cret" not in res.stderr, f"the argument was echoed:\n{said}"
    assert not ran.exists(), f"psql was run:\n{said}"


# ========================================== an existing indexer that cannot log in
#
# T109's follow-up 2, on Codex's SHOULD at lanes-index:4303 in the same review
# (#165 6889426463), as lane 3 ruled it in lane 1's words (#165 6894116246): an
# existing `lanes_indexer` that cannot log in (`rolcanlogin` false) is refused with 2
# and named, before any write, under `--roles-only` too, and the bootstrap never
# grants LOGIN itself. RE: roles are global to a cluster, so each case takes a
# cluster of its own, with an empty template, from `tests/pgcluster.py` (P01's engine
# plugin), and skips in a tree that does not carry it yet.

#: What a refused bootstrap must leave as it found it: the roles whose names begin
#: `lanes` and whether each can log in, their memberships, the schemas whose names
#: begin `lanes`, the database's ACL, and the count of default privileges.
T109_CATALOG = (
    "SELECT 'role ' || rolname || ' login ' || rolcanlogin::text FROM pg_catalog.pg_roles "
    "WHERE rolname LIKE 'lanes%' "
    "UNION ALL SELECT 'member ' || r.rolname || ' of ' || g.rolname "
    "FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid = m.member "
    "JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
    "WHERE r.rolname LIKE 'lanes%' OR g.rolname LIKE 'lanes%' "
    "UNION ALL SELECT 'schema ' || nspname FROM pg_catalog.pg_namespace "
    "WHERE nspname LIKE 'lanes%' "
    "UNION ALL SELECT 'database ' || coalesce(datacl::text, 'default') "
    "FROM pg_catalog.pg_database WHERE datname = current_database() "
    "UNION ALL SELECT 'default privileges ' || count(*) FROM pg_catalog.pg_default_acl "
    "ORDER BY 1;\n")

#: The full bootstrap's three inputs.
T109_FULL = ("--label", "t109-label", "--repository", "opensoft/t109-workspace",
             "--lane", "t109-operator")


@pytest.fixture
def t109_engine(request, tmp_path):
    """A started cluster of the case's own with an empty template, a database
    `t109_db` made from `template0`, and an estate whose `~/.pg_service.conf`
    names the cluster's socket and superuser as the service `t109admin`. Yields
    `(cluster, bootstrap)`: `bootstrap(*flags)` runs `lanes-index bootstrap
    --admin-service t109admin <flags> --no-passwords`, the cluster's tools first
    on PATH."""
    try:
        import pgcluster
    except ImportError:
        pytest.skip("real PostgreSQL 16: tests/pgcluster.py, P01's engine plugin, is not "
                    "in this tree")
    found = request.getfixturevalue("pg_engine")
    cluster = pgcluster.Cluster(found.bindir, "")
    try:
        cluster.start()
        cluster.psql("CREATE DATABASE t109_db TEMPLATE template0;")
        estate = Estate(tmp_path / "e")
        service = estate.home / ".pg_service.conf"
        service.write_text(f"[t109admin]\nhost={cluster.root}\nport={pgcluster.PORT}\n"
                           f"user={pgcluster.SUPERUSER}\ndbname=t109_db\n", encoding="utf-8")
        service.chmod(0o600)
        path = os.pathsep.join([str(cluster.bindir), estate.env["PATH"]])

        def bootstrap(*flags: str) -> subprocess.CompletedProcess:
            return estate.index("bootstrap", "--admin-service", "t109admin", *flags,
                                "--no-passwords", env={"PATH": path}, timeout=300)

        yield cluster, bootstrap
    finally:
        cluster.destroy()


@pytest.mark.parametrize("flags", [T109_FULL, ("--roles-only",)], ids=["full", "roles-only"])
def test_the_bootstrap_refuses_an_existing_nologin_indexer_with_2_before_any_write(
        t109_engine, flags):
    """AN INDEXER THAT CANNOT LOG IN IS REFUSED (lane 3's ruling, #165
    6894116246, in lane 1's words): where `lanes_indexer` exists NOLOGIN, the
    full bootstrap and `--roles-only` each exit 2, naming `lanes_indexer` and
    that it cannot log in, and print nothing on stdout. The catalog is as it
    was, so nothing was written, and the role is still NOLOGIN: the bootstrap
    never grants LOGIN."""
    cluster, bootstrap = t109_engine
    cluster.psql("CREATE ROLE lanes_indexer NOLOGIN;")
    before = cluster.psql(T109_CATALOG, dbname="t109_db").stdout
    assert "role lanes_indexer login false" in before.splitlines(), before
    res = bootstrap(*flags)
    said = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    assert ("REFUSED: bootstrap: the role lanes_indexer exists and cannot log in (NOLOGIN)"
            in res.stderr), said
    assert res.stdout == "", f"the refused bootstrap printed on stdout:\n{said}"
    after = cluster.psql(T109_CATALOG, dbname="t109_db").stdout
    assert after == before, (f"the refused bootstrap wrote:\nbefore:\n{before}\n"
                             f"after:\n{after}\n{said}")


@pytest.mark.parametrize("flags", [T109_FULL, ("--roles-only",)], ids=["full", "roles-only"])
def test_the_bootstrap_takes_an_existing_indexer_that_can_log_in(t109_engine, flags):
    """THE REFUSAL IS FOR NOLOGIN ALONE: where `lanes_indexer` exists and can
    log in, the full bootstrap and `--roles-only` each exit 0, say `role
    lanes_indexer: unchanged`, and make the other three roles."""
    cluster, bootstrap = t109_engine
    cluster.psql("CREATE ROLE lanes_indexer LOGIN;")
    res = bootstrap(*flags)
    said = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert res.returncode == 0, f"exit {res.returncode}, not 0:\n{said}"
    assert "role lanes_indexer: unchanged" in res.stdout.splitlines(), said
    after = cluster.psql(T109_CATALOG, dbname="t109_db").stdout.splitlines()
    for line in ("role lanes_indexer login true", "role lanes_register_owner login false",
                 "role lanes_register_reader login false",
                 "role lanes_register_writer login false"):
        assert line in after, f"{line!r} is not in the catalog after the run: {after}\n{said}"


# ====================================== the writer's SELECT is on tables alone
#
# T109's follow-up 3, on Codex's exact-head review of P10 at 079a34d8 (BLOCKING
# lanes-index:4360): design.md section 1.4 grants SELECT on the register's
# sequences to READER alone, for pg_dump, and REGISTER-WRITER SELECT on its tables,
# but the scope read let the writer hold SELECT on a sequence too. operations.md
# section 2.4 refuses with 2 a role that holds a privilege outside its scope, named
# and never revoked.

#: Every ACL a refused bootstrap must leave as it found it: the lanes schemas', their
#: relations' and functions', the database's, and the default privileges.
T109_ACLS = (
    "SELECT 'schema ' || nspname || ' ' || coalesce(nspacl::text, '-') "
    "FROM pg_catalog.pg_namespace WHERE nspname LIKE 'lanes%' "
    "UNION ALL SELECT 'relation ' || n.nspname || '.' || c.relname || ' ' "
    "|| coalesce(c.relacl::text, '-') FROM pg_catalog.pg_class c "
    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname LIKE 'lanes%' "
    "UNION ALL SELECT 'function ' || p.oid::regprocedure::text || ' ' "
    "|| coalesce(p.proacl::text, '-') FROM pg_catalog.pg_proc p "
    "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname LIKE 'lanes%' "
    "UNION ALL SELECT 'database ' || coalesce(datacl::text, 'default') "
    "FROM pg_catalog.pg_database WHERE datname = current_database() "
    "UNION ALL SELECT 'default ' || defaclrole::regrole::text || ' ' "
    "|| defaclobjtype::text || ' ' || defaclacl::text FROM pg_catalog.pg_default_acl "
    "ORDER BY 1;\n")


def test_the_bootstrap_refuses_a_writer_that_holds_select_on_a_sequence(t109_engine):
    """A WRITER'S SELECT ON A SEQUENCE IS OUTSIDE ITS SCOPE: after a full
    bootstrap, REGISTER-WRITER is given SELECT on one of the register's
    sequences by hand. The second full bootstrap exits 2 before any write,
    naming the grant, prints nothing on stdout, and leaves every ACL as it
    was. Before this change it passed both audits and exited 0."""
    cluster, bootstrap = t109_engine
    first = bootstrap(*T109_FULL)
    assert first.returncode == 0, f"the first bootstrap exited {first.returncode}: {first.stderr}"
    sequence = cluster.psql(
        "SELECT quote_ident(n.nspname) || '.' || quote_ident(c.relname) "
        "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'lanes_register' AND c.relkind = 'S' ORDER BY 1 LIMIT 1;",
        dbname="t109_db").stdout.strip()
    assert sequence, "the register's schema holds no sequence to grant"
    cluster.psql(f"GRANT SELECT ON SEQUENCE {sequence} TO lanes_register_writer;",
                 dbname="t109_db")
    before = cluster.psql(T109_ACLS, dbname="t109_db").stdout
    res = bootstrap(*T109_FULL)
    said = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    assert f"lanes_register_writer holds SELECT on sequence {sequence}" in res.stderr, said
    assert res.stdout == "", f"the refused bootstrap printed on stdout:\n{said}"
    after = cluster.psql(T109_ACLS, dbname="t109_db").stdout
    assert after == before, (f"the refused bootstrap changed an ACL:\nbefore:\n{before}\n"
                             f"after:\n{after}\n{said}")


# ======================================================= no group keeps a grant option
#
# T109's follow-up 4, on Codex's exact-head review of P10 at 079a34d8 (BLOCKING
# lanes-index:4355): the scope read took each ACL item's privilege and not its
# grant option, so a group could keep a privilege in its scope WITH GRANT OPTION and
# hand it on, which design.md section 1.4's GRANTs never give. Now the writer's and
# the reader's privileges, and the indexer's CONNECT, count as in scope only without
# it, and the fault names it.

#: The two groups, each given every row's privilege again WITH GRANT OPTION.
GROUPS = ("lanes_register_writer", "lanes_register_reader")

#: (id, the GRANT made by hand after a full bootstrap, to whom, the privilege, the
#: object as the fault names it)
GRANT_OPTIONS = [
    ("connect", "GRANT CONNECT ON DATABASE t109_db", (*GROUPS, "lanes_indexer"), "CONNECT",
     "database t109_db"),
    ("usage", "GRANT USAGE ON SCHEMA lanes_register", GROUPS, "USAGE", "schema lanes_register"),
    ("select", "GRANT SELECT ON TABLE lanes_register.schema_version", GROUPS, "SELECT",
     "table lanes_register.schema_version"),
    ("execute", "GRANT EXECUTE ON FUNCTION lanes_register.render_file(text)", GROUPS, "EXECUTE",
     "function lanes_register.render_file(text)"),
]


@pytest.mark.parametrize("grant, grantees, privilege, what", [
    pytest.param(grant, grantees, privilege, what, id=ident)
    for ident, grant, grantees, privilege, what in GRANT_OPTIONS])
def test_the_bootstrap_refuses_a_grant_option_on_a_privilege_in_scope(t109_engine, grant,
                                                                      grantees, privilege, what):
    """A GRANT OPTION IS OUTSIDE THE SCOPE: after a full bootstrap, the
    writer and the reader (and, for CONNECT, the indexer) are each given a
    privilege their scope holds again, WITH GRANT OPTION. The second full
    bootstrap exits 2 before any write, naming each as `holds <privilege> WITH
    GRANT OPTION on <object>`, prints nothing on stdout, and leaves every ACL
    as it was. Before this change it passed both audits and exited 0."""
    cluster, bootstrap = t109_engine
    first = bootstrap(*T109_FULL)
    assert first.returncode == 0, f"the first bootstrap exited {first.returncode}: {first.stderr}"
    cluster.psql(f"{grant} TO {', '.join(grantees)} WITH GRANT OPTION;", dbname="t109_db")
    before = cluster.psql(T109_ACLS, dbname="t109_db").stdout
    res = bootstrap(*T109_FULL)
    said = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert res.returncode == 2, f"exit {res.returncode}, not 2:\n{said}"
    for grantee in grantees:
        assert f"{grantee} holds {privilege} WITH GRANT OPTION on {what}" in res.stderr, said
    assert res.stdout == "", f"the refused bootstrap printed on stdout:\n{said}"
    after = cluster.psql(T109_ACLS, dbname="t109_db").stdout
    assert after == before, (f"the refused bootstrap changed an ACL:\nbefore:\n{before}\n"
                             f"after:\n{after}\n{said}")
