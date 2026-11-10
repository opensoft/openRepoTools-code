# SPDX-License-Identifier: Apache-2.0
"""Feature 007's test 1 (AT-1, L2-N1; opensoft/openRepoTools#165): the mirror
byte-identical to a full render from SQL after a write.

THIS MODULE TODAY holds test 1's phase-N part, lane 2's T210:

  * `test_a_storage_layer_entry_renders_byte_identical_to_a_full_render[<entry>]`
    (N, RE): the storage layer's write entry, called as the projection writer
    will call it, then the pure renderer;
  * `test_the_render_of_one_entry_and_of_a_full_render_is_timed_and_recorded`
    (N, RE; M6): the pure renderer timed, never asserted;
  * `test_sync_source_register_does_nothing_on_primary_and_says_so` (FP, no
    engine).

Test 1's phase-W parts and its files-mode twin are lane 2's T240, and its
phase-G part is later still; each adds its cases here.

THE STORAGE-LAYER ENTRY (design S4; the delta spec's "The managed seam stays
the ledger's"). The managed projection writer arrives with the 001 feature's
T024; this change provides the entry it will call and tests it with a fake
writer. Its storage layer is `lanes-index`, the one database client (D2), and
one attempt of S1's loop is two calls (contract section 1):

  1. `lanes-index register snapshot --write-id new --lane <l> --verb <v>
     --args-sha256 <h> --tree <attempt>/tree --checkout <c>` (section 3.2),
     which mints the write id and builds the scratch tree at `n`;
  2. the verb's edit in the scratch tree, then the attempt directory, as the
     seam writes it (section 3.3's table: `snapshot`, `changes.tsv`,
     `images/`, `tree/`, `msg`, `author`, `files`, `not_after`);
  3. `lanes-index register commit --write-id <w> --generation <g> --lane <l>
     --verb <v> --args-sha256 <h> --workstation <ws> <attempt>` (section 3.3).

The fake writer, `projection_entry`, does exactly that, and abandons on any
end of the snapshot but 0 (section 3.3, "The caller's map"). Its cases are
the managed projection itself, which rewrites a row's state cell to carry a
managed-owner marker (`lanes-edit.sh`'s ported reader at 3c26041), and two
other entries of S1's writes, a log line and a `LANES.md` take, so that the
renderer is checked on a row, a line of `LANES.md` and a log.

THE REGISTER, "against an import": a files-mode repository at commit C,
holding AT-1's fixture register (three lanes, one archived; aliases; a lane
with `HOLD`, `LANDING` and `LANDED` lines; a log with `WORD` lines whose UTC
carries milliseconds), loaded by AT-LR006's route (the test plan at
4610-4615): as `lanes_register_writer`, `commit_write` with an `import` entry
of C's render set, then a `cutover` entry, then `record_marker`, so the
switch is `primary` with the marker `present`. No `lanes-index import` or
`cutover` runs (those are L1-A13's and group C's).

THE PURE RENDERER is lane 3's T301, as lane 1 built it (#165 6754569755):
`lanes-index render --images --at <k> --out <dir>` (contract section 3.6),
which writes the render set's images at seq `k` from the journal alone. The
full render from SQL is `render_file` (lane 1's T107) of every path in
`files`.

REAL ENGINE. The entry's cases ask for `pg` (`tests/pgcluster.py`), one
database cloned from the template that T227 builds by the bootstrap; on T205's
empty template they fail, since the schema is not there, and without
PostgreSQL 16 they skip with T205's banner. They fail until L1-A6 (T107 and
T108), L1-A9 (T111, `register snapshot`), L1-A10 (T112, `register commit`)
and T301 land. `lanes-index` runs as T203's flipped copy, `RENDER_GIT_HALF =
True`, so `mode=primary` loads (open point 3), and connects as two logins of
this module's own, members of the writer and the reader groups, by the
cluster's trust.

`sync --source register` NEEDS NO ENGINE: on primary it makes no `psql`
call, writes nothing and says it does nothing on primary (L1-A15, lane 1's
T117). It runs with T203's register fake first on `PATH`, whose empty log is
the oracle for "no `psql` call".
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import (LANES_INDEX, REGISTER_FAKE_PSQL, RENDER_GIT_HALF_LINE,
                                  flipped_copy)

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

LANES_EDIT = REPO / "lanes-edit.sh"

#: The register's schema, `register_schema=`'s default (contract section 2.5).
SCHEMA = "lanes_register"
WRITER, READER = "lanes_register_writer", "lanes_register_reader"
#: The logins `lanes-index` connects as in this module's real-engine cases.
#: Made once per cluster, members of the writer and the reader groups, with
#: no password.
LOGIN_WRITER, LOGIN_READER = "t210_register_writer", "t210_register_reader"

#: What the fake writer stamps: the workstation (`--workstation`, and each
#: line's `session <uuid>@<ws>`), the author, and the operator lane.
WS = "Eagle"
AUTHOR = "T210 fake writer <t210@example.invalid>"
OPERATOR = "repoA-2"
MARKER_COMMIT = "e" * 40
STORE_UTC = "2026-11-09T10:00:00Z"

#: The register's punctuation, spelled by code point so no raw character
#: enters this file: the em dash, the middle dot of a state cell, the arrow
#: of a `LANDED` line.
EM, DOT, ARROW = chr(0x2014), chr(0x00B7), chr(0x2192)

SID_A1 = "aaaaaaaa-0001-4000-8000-00000000a001"
SID_A2 = "aaaaaaaa-0003-4000-8000-00000000a003"
SID_Z1 = "eeeeeeee-0001-4000-8000-00000000e001"
TIP = "0123456789abcdef0123456789abcdef01234567"

#: The render set (Q18 (A); contract section 3.6): `lanes/LANES.md`,
#: `lanes/aliases.tsv`, each `lanes/log/<lane>.md` but the README, and the
#: archive. `lanes/STORE` is the operator entries' alone, never a write's.
RENDER_SET = re.compile(r"^lanes/(LANES\.md|aliases\.tsv|archive/[^/]+\.md"
                        r"|log/(?!README\.md$)[^/]+\.md)$")
STORE_PATH = "lanes/STORE"
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def _row(lane: str, sid: str, state: str, started: str = "2026-10-01T00:00Z") -> str:
    return (f"| `{lane}` | harness `{sid}` | Eagle / test / brett | {started} | none "
            f"| handoffs/{lane}.md | {state} |")


#: AT-1's fixture register at C ("Fixture"): three lanes, one of them
#: archived; `aliases.tsv` entries; a lane with `HOLD`, `LANDING` and
#: `LANDED` lines; a log with `WORD` lines whose UTC carries milliseconds
#: (Q4(d)(i)). `lanes/repos.tsv` and `lanes/log/README.md` are outside the
#: render set, and `register snapshot --tree` takes them from the checkout.
SEED = {
    "lanes/LANES.md": "\n".join([
        f"# LANES.md {EM} test 1's fixture register",
        "",
        "| lane | session id | workstation / env / user | started (UTC) | objects owned "
        "| handoff path | state |",
        "|---|---|---|---|---|---|---|",
        _row("repoA-1", SID_A1, f"LIVE {DOT} 2026-10-01T01:00:00Z {DOT} working"),
        _row("repoA-2", SID_A2, f"PAUSED {DOT} 2026-10-01T02:00:00Z {DOT} parked"),
        "",
        f"HOLD {EM} lane repoA-1 (Eagle), window w, 2026-10-01T03:00:00Z: opensoft/repoA main "
        f"{TIP} for a frozen window",
        f"LANDING {EM} lane repoA-1, session {SID_A1}@Eagle, 2026-10-01T03:10:00Z, PR #7 into "
        f"opensoft/repoA main",
        f"LANDED {EM} lane repoA-1, session {SID_A1}@Eagle, 2026-10-01T03:15:00Z, PR #7 into "
        f"opensoft/repoA main {ARROW} abc1234",
        ""]),
    "lanes/aliases.tsv": "# old\tnew\tutc\nrepoOld-1\trepoA-2\t2026-09-30T00:00:00Z\n",
    "lanes/archive/LANES-retired.md": "\n".join([
        "# retired rows (Amendment 19(d))", "",
        _row("repoZ-1", SID_Z1, f"RETIRED {DOT} 2026-09-02T00:00:00Z {DOT} retired"),
        ""]),
    "lanes/log/repoA-1.md": "\n".join([
        f"# lane repoA-1 {EM} object log (lane-collision-protocol Amendment 7)",
        f"STARTED {EM} lane repoA-1, session {SID_A1}@Eagle, 2026-10-01T00:00:00Z, "
        f"lane:repoA-1 {ARROW} home opensoft/repoA; dir /work/repoA1",
        ""]),
    "lanes/log/repoA-2.md": "\n".join([
        f"# lane repoA-2 {EM} object log (lane-collision-protocol Amendment 7)",
        f"STARTED {EM} lane repoA-2, session {SID_A2}@Eagle, 2026-10-01T02:00:00Z, "
        f"lane:repoA-2 {ARROW} home opensoft/repoA; dir /work/repoA2",
        f"NOTED {EM} lane repoA-2, session {SID_A2}@Eagle, 2026-10-01T02:10:00.123Z, "
        f"lane:repoA-2 {EM} a stamp with milliseconds",
        f"NOTED {EM} lane repoA-2, session {SID_A2}@Eagle, 2026-10-01T02:11:00.456Z, "
        f"lane:repoA-2 {EM} another",
        ""]),
    "lanes/log/README.md": "# the object logs\n",
    "lanes/repos.tsv": "# alias\towner/repo\nrepoA\topensoft/repoA\n",
}


# ------------------------------------------------------------------ the estate
def git(cwd: Path, *args: str, env: dict | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                          env=env, check=False)
    assert proc.returncode == 0, f"git {' '.join(args)} in {cwd}: {proc.stderr}{proc.stdout}"
    return proc.stdout


def git_env(home: Path) -> dict:
    """A git with no person's configuration in it, and an identity of its own."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_", "PG", "LANES_", "TMUX"))}
    env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="T210 estate", GIT_AUTHOR_EMAIL="t210@example.invalid",
               GIT_COMMITTER_NAME="T210 estate", GIT_COMMITTER_EMAIL="t210@example.invalid",
               LC_ALL="C")
    return env


class Estate:
    """A bare origin and the lane's checkout at C: SEED (or `files`) committed
    and pushed to `main`. `register snapshot --checkout` reads
    `lanes/repos.tsv` and `lanes/log/README.md` from its `origin/main`."""

    def __init__(self, root: Path, files: dict = None):
        self.root = root
        self.home = root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.env = git_env(self.home)
        self.origin = root / "origin.git"
        self.checkout = root / "checkout"
        git(root, "init", "-q", "--bare", "-b", "main", str(self.origin), env=self.env)
        git(root, "clone", "-q", str(self.origin), str(self.checkout), env=self.env)
        self.files = dict(files if files is not None else SEED)
        for path, text in self.files.items():
            target = self.checkout / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        git(self.checkout, "add", "-A", env=self.env)
        git(self.checkout, "commit", "-q", "-m", "C: the fixture register", env=self.env)
        git(self.checkout, "push", "-q", "origin", "main", env=self.env)
        self.c = git(self.checkout, "rev-parse", "HEAD", env=self.env).strip()
        self.lanes_tree = git(self.checkout, "rev-parse", f"{self.c}:lanes", env=self.env).strip()

    def render_set(self) -> dict:
        """C's render set, {path: bytes}."""
        return {p: t.encode("utf-8") for p, t in self.files.items() if RENDER_SET.match(p)}

    def state(self) -> tuple:
        """What a write through the storage layer never changes in the
        checkout: HEAD, `status --porcelain=v1 -uall`, the index's digest and
        `origin/main`."""
        index = self.checkout / ".git" / "index"
        return (git(self.checkout, "rev-parse", "HEAD", env=self.env),
                git(self.checkout, "status", "--porcelain=v1", "-uall", env=self.env),
                hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else "-",
                git(self.checkout, "rev-parse", "origin/main", env=self.env))


# ------------------------------------------------------------------ the SQL side
def psql(db, script: str, role: str = None) -> subprocess.CompletedProcess:
    """One `psql` as the fixture's superuser, as `role` where one is named,
    with the commit call's settings, so a refusal's first stderr line is
    `ERROR:  <SQLSTATE>: <message>`."""
    head = "\\set VERBOSITY verbose\n\\set SHOW_CONTEXT never\nSET client_encoding = 'UTF8';\n"
    if role:
        head += f"SET ROLE {role};\n"
    return subprocess.run([db.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                          input=head + script, capture_output=True, encoding="utf-8",
                          errors="replace", env=db.env(appname="t210"), timeout=120, check=False)


def sql(db, script: str, role: str = None) -> str:
    proc = psql(db, script, role)
    assert proc.returncode == 0, (f"psql{' as ' + role if role else ''} exited "
                                  f"{proc.returncode}: {proc.stderr.strip()}\n{script}")
    return proc.stdout.strip()


def rows(db, query: str) -> list:
    """`query`'s rows as JSON objects, read in the register's schema."""
    out = sql(db, f"SET search_path TO {SCHEMA};\n"
                  f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t;")
    return json.loads(out.splitlines()[-1])


def head(db) -> int:
    return rows(db, "SELECT seq FROM register_head")[0]["seq"]


def db_clock(db) -> int:
    """The database's clock, floored to whole seconds, as epoch seconds."""
    return rows(db, "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS s")[0]["s"]


def full_render(db) -> dict:
    """The full render from SQL: `render_file` (lane 1's T107) of every path
    in `files`, {path: bytes}."""
    return {r["path"]: base64.b64decode(r["b64"]) for r in rows(
        db, "SELECT path, encode(render_file(path), 'base64') AS b64 FROM files ORDER BY path")}


def _lines(data: bytes) -> list:
    text = data.decode("utf-8")
    assert text.endswith("\n"), "every fixture file ends with a newline"
    return text[:-1].split("\n")


def _entry(kind: str, verb: str, journal: dict = None, **parts) -> dict:
    body = {"kind": kind, "verb": verb, "lane": OPERATOR, "workstation": WS, "author": AUTHOR,
            "message": f"t210: {kind}"}
    body.update(journal or {})
    return {"journal": body, "not_after": "2100-01-01T00:00:00Z", **parts}


def _creates(files: dict) -> tuple:
    """Each of `files` ({path: bytes}) created, then its lines appended, and
    each path's digest as it renders: the edits and the `files` rows."""
    edits, ordinal = [], 0
    for path in sorted(files):
        ordinal += 1
        edits.append({"ord": ordinal, "op": "create", "path": path})
        for text in _lines(files[path]):
            ordinal += 1
            edits.append({"ord": ordinal, "op": "append", "path": path, "new_text": text})
    return edits, [{"path": p, "present": True, "sha256": hashlib.sha256(files[p]).hexdigest(),
                    "final_newline": True} for p in sorted(files)]


def _commit_call(db, base: int, body: dict) -> int:
    """The commit call as the writer sends it, as `lanes_register_writer`
    (section 1.3's step 3; AT-LR006's fixture), and the seq it committed."""
    gen = rows(db, "SELECT generation FROM register_switch")[0]["generation"]
    version = rows(db, "SELECT version FROM schema_version")[0]["version"]
    literal = json.dumps(body, ensure_ascii=True).replace("'", "''")
    out = sql(db, f"BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
                  f"SELECT {SCHEMA}.commit_write({base}, '{uuid.uuid4()}'::uuid, {version}, "
                  f"'{gen}'::uuid, '{literal}'::jsonb);\nCOMMIT;", WRITER)
    return int(out.splitlines()[-1])


def import_to_primary(db, estate: Estate) -> int:
    """AT-LR006's route (TP:4610-4615) over C: an `import` entry of C's render
    set, a `cutover` entry, then `record_marker`, by the documented functions
    as `lanes_register_writer`. Returns the import's seq."""
    edits, files = _creates(estate.render_set())
    imported = _commit_call(db, head(db), _entry(
        "import", "import", {"git_commit": estate.c, "git_tree": estate.lanes_tree},
        edits=edits, files=files))
    store = "".join(f"{line}\n" for line in (
        "store=primary", "database=t210", f"import={estate.c}",
        f"lanes-tree={estate.lanes_tree}", f"utc={STORE_UTC}")).encode("utf-8")
    edits, files = _creates({STORE_PATH: store})
    cut = _commit_call(db, imported, _entry("cutover", "cutover", edits=edits, files=files))
    version = rows(db, "SELECT version FROM schema_version")[0]["version"]
    marker = sql(db, f"SELECT {SCHEMA}.record_marker({version}, {cut}, '{MARKER_COMMIT}', "
                     f"'{WS}');", WRITER)
    assert marker.splitlines()[-1] == "present", f"record_marker answered {marker!r}"
    assert rows(db, "SELECT mode, marker_state FROM register_switch") == \
        [{"mode": "primary", "marker_state": "present"}]
    return imported


# ------------------------------------------------------------------ lanes-index
def require_the_constant() -> None:
    """The flipped copy needs Q6(c)'s constant (lane 1's T105, L1-A4): an
    assertion, so a case without it fails by saying so."""
    assert len(RENDER_GIT_HALF_LINE.findall(LANES_INDEX.read_bytes())) == 1, (
        f"{LANES_INDEX} holds no single `RENDER_GIT_HALF = ...` line, Q6(c)'s build constant "
        f"(L1-A4, lane 1's T105), so no copy can be flipped to load mode=primary")


def flipped(tmp_path: Path, name: str = "bin") -> Path:
    """T203's flipped copy, `RENDER_GIT_HALF = True`, so `mode=primary` loads,
    with `lanes-edit.sh` beside it (the copy rule, CLI4.5 section 6)."""
    require_the_constant()
    copy = flipped_copy(LANES_INDEX, tmp_path / name, True)
    shutil.copy2(str(LANES_EDIT), str(copy.parent / "lanes-edit.sh"))
    return copy


def ensure_logins(db) -> None:
    """The writer's and the reader's login, once per cluster (roles are
    cluster-wide), members of their groups, with no password."""
    for login, group in ((LOGIN_WRITER, WRITER), (LOGIN_READER, READER)):
        sql(db, f"DO $l$ BEGIN CREATE ROLE {login} LOGIN IN ROLE {group}; "
                f"EXCEPTION WHEN duplicate_object THEN NULL; END $l$;")


def primary_config(path: Path, register_url: str, reader_url: str,
                   passfile: Path | None = None) -> Path:
    """A 0600 `lanes-index.conf` with `mode=primary` and the register's two
    URLs (contract section 2.5), outside every work tree."""
    lines = ["mode=primary", f"register_url={register_url}", f"reader_url={reader_url}"]
    if passfile is not None:
        lines += [f"register_passfile={passfile}", f"reader_passfile={passfile}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def index_env(tmp_path: Path, conf: Path, home: Path, **extra) -> dict:
    """The environment `lanes-index` runs in: no inherited `PG*`, `LANES_*`,
    `GIT_*` or `TMUX*` (#160's run-wide `LANES_INDEX=off` among them), this
    case's configuration, state directory and git identity."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PG", "LANES_", "GIT_", "TMUX"))}
    env.update(git_env(home))
    env.update(LANES_INDEX_CONFIG=str(conf), XDG_STATE_HOME=str(tmp_path / "state"), LC_ALL="C")
    env.update(extra)
    return env


def run_index(copy: Path, args, env: dict, cwd: Path = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(copy), *[str(a) for a in args]],
                          capture_output=True, encoding="utf-8", errors="replace", env=env,
                          timeout=120, cwd=str(cwd) if cwd else None, check=False,
                          stdin=subprocess.DEVNULL)


def keys(stdout: str) -> dict:
    """A `key=value` output's keys, each its first value (section 3.2)."""
    found = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key not in found:
            found[key] = value
    return found


def utc_of(epoch: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def epoch_of(utc: str) -> int:
    import calendar
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


# ------------------------------------------------------------------ the fake writer
def _edit_managed_projection(tree: Path, utc: str) -> str:
    """S4's projection: repoA-1's row's state cell carries a managed-owner
    marker, in the form `lanes-edit.sh`'s ported reader parses (3c26041's
    T019): `<STATE> . <utc> . managed-owner mode=... daemon=... generation=...
    bound-lane=<lane>`. Returns the new line."""
    path = tree / "lanes" / "LANES.md"
    text = path.read_text(encoding="utf-8")
    old = _row("repoA-1", SID_A1, f"LIVE {DOT} 2026-10-01T01:00:00Z {DOT} working")
    new = _row("repoA-1", SID_A1, f"LIVE {DOT} {utc} {DOT} managed-owner mode=managed "
                                  f"daemon=t210d generation=7 bound-lane=repoA-1")
    assert text.count(old + "\n") == 1, "the fixture row is in the scratch tree once"
    path.write_text(text.replace(old + "\n", new + "\n"), encoding="utf-8")
    return new


def _edit_log_noted(tree: Path, utc: str) -> str:
    """`log NOTED`'s line, appended to repoA-1's log."""
    line = (f"NOTED {EM} lane repoA-1, session {SID_A1}@{WS}, {utc}, lane:repoA-1 {EM} "
            f"test 1's part N")
    path = tree / "lanes" / "log" / "repoA-1.md"
    path.write_bytes(path.read_bytes() + line.encode("utf-8") + b"\n")
    return line


def _edit_append_hold(tree: Path, utc: str) -> str:
    """`append-line`'s take: a `HOLD` on a repository nobody holds."""
    line = (f"HOLD {EM} lane repoA-2 ({WS}), window w, {utc}: opensoft/repoB main {TIP} "
            f"for a check")
    path = tree / "lanes" / "LANES.md"
    path.write_bytes(path.read_bytes() + line.encode("utf-8") + b"\n")
    return line


#: The entries the fake writer drives: {id: (lane, verb, the edit, the path
#: it touches)}. The managed projection is S4's own verb (design S4: "run
#: through S1's attempt loop as the verb `managed-projection`").
ENTRIES = {
    "managed-projection": ("repoA-1", "managed-projection", _edit_managed_projection,
                           "lanes/LANES.md"),
    "log-noted": ("repoA-1", "log", _edit_log_noted, "lanes/log/repoA-1.md"),
    "append-line-hold": ("repoA-2", "append-line", _edit_append_hold, "lanes/LANES.md"),
}


def _canonical_rows(changes: list, images: dict) -> str:
    """Section 3.2's canonical rows for every path in `changes.tsv`, sorted by
    path bytewise, each LF-ended: `<path>` TAB `1` TAB `<sha256>`, or `0` and
    `-` for a path the write removes."""
    out = []
    for path in sorted({c[1] for c in changes}, key=lambda p: p.encode("utf-8")):
        if path in images:
            out.append(f"{path}\t1\t{hashlib.sha256(images[path]).hexdigest()}\n")
        else:
            out.append(f"{path}\t0\t-\n")
    return "".join(out)


def projection_entry(copy: Path, env: dict, checkout: Path, root: Path, entry: str,
                     message: str) -> dict:
    """The storage layer's write entry, driven by a fake writer as the
    projection writer will call it (design S4; contract sections 3.2 and 3.3):
    `register snapshot --write-id new ... --tree <root>/attempt/tree
    --checkout <checkout>`; on 0 alone, the edit, the attempt directory and
    `register commit`. Returns what each call answered, the entry's code
    (the snapshot's where it did not answer 0, else the commit's), the
    attempt directory, the message and the line the edit wrote."""
    lane, verb, edit, _path = ENTRIES[entry]
    args_sha256 = hashlib.sha256(json.dumps([lane, verb, message]).encode("utf-8")).hexdigest()
    attempt = root / "attempt"
    out = {"snapshot": None, "commit": None, "code": None, "attempt": attempt,
           "message": message, "line": None, "fields": {}, "args_sha256": args_sha256}
    snap = run_index(copy, ["register", "snapshot", "--write-id", "new", "--lane", lane,
                            "--verb", verb, "--args-sha256", args_sha256,
                            "--tree", attempt / "tree", "--checkout", checkout], env)
    out["snapshot"] = snap
    if snap.returncode != 0:
        out["code"] = snap.returncode
        return out
    fields = keys(snap.stdout)
    out["fields"] = fields
    tree = attempt / "tree"
    (attempt / "snapshot").write_text(snap.stdout, encoding="utf-8")
    out["line"] = edit(tree, utc_of(int(fields["clock"])))
    git(tree, "add", "-A", "--", "lanes", env=env)
    changes = []
    for raw in git(tree, "diff", "--cached", "--no-renames", "--raw", "--no-abbrev", "HEAD",
                   env=env).splitlines():
        meta, path = raw.split("\t", 1)
        parts = meta.split()
        changes.append((parts[4], path, parts[2], parts[3]))
    assert changes, "the edit staged a change"
    (attempt / "changes.tsv").write_text(
        "".join(f"{s}\t{p}\t{o}\t{n}\n" for s, p, o, n in changes), encoding="utf-8")
    images = {}
    for status, path, _old, _new in changes:
        if status in ("A", "M"):
            images[path] = (tree / path).read_bytes()
            target = attempt / "images" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(images[path])
    (attempt / "files").write_text(_canonical_rows(changes, images), encoding="utf-8")
    (attempt / "msg").write_text(message, encoding="utf-8")
    (attempt / "author").write_text(AUTHOR + "\n", encoding="utf-8")
    (attempt / "not_after").write_text(fields["not_after"] + "\n", encoding="utf-8")
    commit = run_index(copy, ["register", "commit", "--write-id", fields["write_id"],
                              "--generation", fields["generation"], "--lane", lane,
                              "--verb", verb, "--args-sha256", args_sha256,
                              "--workstation", WS, attempt], env)
    out["commit"] = commit
    out["code"] = commit.returncode
    return out


def render_images(copy: Path, env: dict, k: int, out_dir: Path) -> tuple:
    """The pure renderer, T301: `render --images --at <k> --out <dir>`
    (contract section 3.6). Returns the call and {path: bytes} of every file
    it wrote under `out_dir`."""
    proc = run_index(copy, ["render", "--images", "--at", k, "--out", out_dir], env)
    written = {}
    if out_dir.is_dir():
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                written[path.relative_to(out_dir).as_posix()] = path.read_bytes()
    return proc, written


def _rendered_only(files: dict) -> dict:
    return {p: b for p, b in files.items() if RENDER_SET.match(p)}


class PrimaryRegister:
    """C imported and brought to `primary`, a flipped copy, and the
    configuration that reaches the test's database as this module's logins."""

    def __init__(self, pg, tmp_path: Path):
        self.pg = pg
        self.estate = Estate(tmp_path / "estate")
        self.imported = import_to_primary(pg, self.estate)
        ensure_logins(pg)
        self.copy = flipped(tmp_path)
        (tmp_path / "conf").mkdir()
        conf = primary_config(tmp_path / "conf" / "lanes-index.conf", pg.url(LOGIN_WRITER),
                              pg.url(LOGIN_READER))
        self.env = index_env(tmp_path, conf, self.estate.home)


# ============================================================ part N (real engine)

@pytest.mark.parametrize("entry", list(ENTRIES))
def test_a_storage_layer_entry_renders_byte_identical_to_a_full_render(pg, tmp_path, entry):
    """AT-1's part N: the storage layer's write entry, called as the
    projection writer will call it, commits one entry; then the pure
    renderer's images at that seq equal the full render from SQL, path set
    and bytes, over the four paths, and it writes nothing outside them. The
    journal gains exactly one entry, at the old head plus one, carrying the
    write's message byte for byte and its write id, unique in the journal;
    every row the entry touched reads `primary` as the mode that wrote it
    last; the new line's UTC is the database's, in whole seconds, between the
    clock read before the write and after it. The checkout is unchanged."""
    reg = PrimaryRegister(pg, tmp_path)
    before_head = head(pg)
    before_ids = {r["write_id"] for r in rows(pg, "SELECT write_id FROM journal")}
    checkout_before = reg.estate.state()
    message = f"lanes-edit.sh {ENTRIES[entry][1]}: test 1's part N, {entry}"
    clock_before = db_clock(pg)
    done = projection_entry(reg.copy, reg.env, reg.estate.checkout, tmp_path, entry, message)
    clock_after = db_clock(pg)
    assert done["snapshot"].returncode == 0, (
        f"register snapshot exited {done['snapshot'].returncode}: {done['snapshot'].stderr}")
    assert done["code"] == 0, f"register commit exited {done['code']}: {done['commit'].stderr}"
    seq = before_head + 1
    assert done["commit"].stdout == f"committed {seq}\n", done["commit"].stdout

    # THE JOURNAL: one entry, at the old head plus one, with the message and
    # the write id the snapshot minted, unique in the journal.
    new = rows(pg, f"SELECT seq, write_id, kind, verb, lane, message FROM journal "
                   f"WHERE seq > {before_head} ORDER BY seq")
    lane, verb, _edit, path = ENTRIES[entry]
    assert new == [{"seq": seq, "write_id": done["fields"]["write_id"], "kind": "write",
                    "verb": verb, "lane": lane, "message": message}], new
    assert done["fields"]["write_id"] not in before_ids
    assert rows(pg, f"SELECT count(*) AS n FROM journal "
                    f"WHERE write_id = '{done['fields']['write_id']}'") == [{"n": 1}]

    # THE ROWS: every row the entry wrote reads `primary` as its last writer's.
    touched = rows(pg, f"SELECT 'doc_lines' AS t, written_mode AS m FROM doc_lines "
                       f"WHERE written_seq = {seq} "
                       f"UNION ALL SELECT 'lanes', last_mode FROM lanes WHERE last_seq = {seq} "
                       f"UNION ALL SELECT 'log_lines', mode FROM log_lines WHERE seq = {seq} "
                       f"UNION ALL SELECT 'register_lines', mode FROM register_lines "
                       f"WHERE seq = {seq} "
                       f"UNION ALL SELECT 'object_holds', mode FROM object_holds WHERE seq = {seq}")
    assert touched and {r["m"] for r in touched} == {"primary"}, touched

    # THE UTC: the database's clock in whole seconds (S6, D13).
    utc = utc_of(int(done["fields"]["clock"]))
    assert UTC_RE.match(utc) and utc in done["line"]
    assert clock_before <= epoch_of(utc) <= clock_after, (clock_before, utc, clock_after)

    # THE MIRROR: the pure renderer at seq equals the full render from SQL.
    proc, images = render_images(reg.copy, reg.env, seq, tmp_path / "mirror")
    assert proc.returncode == 0, f"render --images exited {proc.returncode}: {proc.stderr}"
    assert all(RENDER_SET.match(p) or p == STORE_PATH for p in images), (
        f"the renderer wrote outside its four paths: {sorted(images)}")
    full = _rendered_only(full_render(pg))
    assert sorted(_rendered_only(images)) == sorted(full), "the path sets are equal"
    for name in full:
        assert _rendered_only(images)[name] == full[name], f"{name}'s bytes differ"
    assert done["line"].encode("utf-8") + b"\n" in full[path]
    assert images[path] == (done["attempt"] / "images" / path).read_bytes(), (
        "the image the writer sent is the one rendered")
    assert reg.estate.state() == checkout_before, "the lane checkout is unchanged"


def _stats(samples: list) -> dict:
    """Section 5.3's statistics: median and p95 by nearest rank, min-max, n."""
    ordered = sorted(samples)
    rank = lambda p: ordered[max(0, -(-p * len(ordered) // 100) - 1)]  # noqa: E731
    return {"median": rank(50), "p95": rank(95), "min": ordered[0], "max": ordered[-1],
            "n": len(ordered)}


def test_the_render_of_one_entry_and_of_a_full_render_is_timed_and_recorded(pg, tmp_path):
    """M6 (section 5.1): the pure renderer's time, exec to exit, cold once
    and ten warm, for a full render of the fixture register (its images at
    the import's seq) and for one journal entry's image (its images at the
    seq of one entry the storage layer committed on top), each recorded with
    section 5.3's statistics and its n in the job's log and
    `$GITHUB_STEP_SUMMARY` where it is set; never asserted. The correctness
    alongside: every run answers 0; the full render equals C's files byte for
    byte; the one entry's render equals the full render from SQL for the
    same paths, so a measurement that rendered wrongly fails, whatever its
    time."""
    reg = PrimaryRegister(pg, tmp_path)
    done = projection_entry(reg.copy, reg.env, reg.estate.checkout, tmp_path, "log-noted",
                            "lanes-edit.sh log: test 1's measured entry")
    assert done["code"] == 0, (done["snapshot"].stderr, done["commit"] and done["commit"].stderr)
    seq = int(done["commit"].stdout.split()[1])
    path = ENTRIES["log-noted"][3]
    sql_render = _rendered_only(full_render(reg.pg))
    figures = {}
    for label, k in (("full render, the fixture register", reg.imported),
                     ("one entry's image", seq)):
        times = []
        for n in range(11):
            out_dir = tmp_path / "timed" / f"{k}-{n}"
            start = time.monotonic_ns()
            proc, images = render_images(reg.copy, reg.env, k, out_dir)
            times.append((time.monotonic_ns() - start) / 1e6)
            assert proc.returncode == 0, f"render --images --at {k}: {proc.stderr}"
            if k == reg.imported:
                assert _rendered_only(images) == reg.estate.render_set(), (
                    "the full render is C's render set, byte for byte")
            else:
                assert images[path] == sql_render[path], (
                    "the one entry's render equals the full render from SQL")
        figures[label] = (times[0], _stats(times[1:]))
    lines = []
    for label, (cold, warm) in figures.items():
        lines.append(f"| M6 | fixture cluster, Unix socket | `render --images`, {label} | "
                     f"cold {cold:.1f} ms | median {warm['median']:.1f} ms, p95 "
                     f"{warm['p95']:.1f} ms, {warm['min']:.1f}-{warm['max']:.1f} ms, "
                     f"n={warm['n']} |")
    print("\n" + "\n".join(lines))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


# ============================================================ `sync --source register` (FP)

#: T220's `psql --version` wrapper, in its form (`test_sql_register_bounds.py`,
#: lane 2's T220): T106 asks `psql --version` once per process (L1v4.10:152),
#: and T203's register fake does not answer it until T203b, so the wrapper
#: answers it, logged apart, and hands every other call to the fake.
VERSION_WRAPPER = r'''#!/usr/bin/env python3
# T210's `psql --version` wrapper (T220's form): the version T106 asks for,
# logged apart; every other call goes to T203's register fake.
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
if sys.argv[1:] == ["--version"]:
    with open(os.path.join(here, "psql-version.log"), "a", encoding="utf-8") as handle:
        handle.write("--version\n")
    sys.stdout.write("psql (PostgreSQL) 16.4\n")
    sys.exit(0)
fake = os.path.join(here, "register-fake-psql")
os.execv(fake, [fake] + sys.argv[1:])
'''


def fake_psql_dir(directory: Path, answers: list = None) -> dict:
    """T203's register fake behind `VERSION_WRAPPER`, written to `directory`,
    which a case puts first on `PATH`. Returns the variables the fake reads:
    its log, and its answers where `answers` teaches any (T203's docstring)."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in (("register-fake-psql", REGISTER_FAKE_PSQL), ("psql", VERSION_WRAPPER)):
        (directory / name).write_text(text, encoding="utf-8")
        (directory / name).chmod(0o755)
    env = {"FAKE_PSQL_LOG": str(directory / "psql.log")}
    if answers is not None:
        (directory / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
        env["FAKE_PSQL_ANSWERS"] = str(directory / "answers.json")
    return env


def fake_calls(fake: dict) -> list:
    """The fake's log, one object per call that reached it."""
    log = Path(fake["FAKE_PSQL_LOG"])
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _sanitized_path() -> str:
    """The caller's PATH without any directory that holds a `lanes-index` or
    a `psql`: an installed indexer, or a real `psql`, is never what a case
    runs."""
    return os.pathsep.join(part for part in os.environ.get("PATH", "").split(os.pathsep)
                           if part and not os.path.exists(os.path.join(part, "lanes-index"))
                           and not os.path.exists(os.path.join(part, "psql")))


#: The workspace's repository, as its `workspace.yaml` names it, and so the
#: register source `sync --source register:<owner/repo>` must name
#: (`lanes-index`'s `source_of`).
WORKSPACE_REPOSITORY = "opensoft/t210-register"


def workspace(root: Path, fakebin: Path) -> tuple:
    """A files-mode workspace whose `workspace.yaml` names
    `WORKSPACE_REPOSITORY`, on a bare origin, at C (SEED), with a fake `tmux`
    and `fakebin` first on `PATH`, in the environment
    `test_sql_register_import.py`'s `Workspace` sets. Returns (the estate,
    the environment)."""
    estate = Estate(root)
    agents = estate.home / ".agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "workspace.yaml").write_text(
        f"repository: {WORKSPACE_REPOSITORY}\npath: {estate.checkout}\n", encoding="utf-8")
    fakebin.mkdir(parents=True, exist_ok=True)
    (fakebin / "tmux").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (fakebin / "tmux").chmod(0o755)
    for d in ("state", "config", "tmp"):
        (root / d).mkdir(parents=True, exist_ok=True)
    env = dict(estate.env)
    env.update(AGENT_PROTOCOL_ROOT=str(agents), TMPDIR=str(root / "tmp"),
               XDG_STATE_HOME=str(root / "state"), XDG_CONFIG_HOME=str(root / "config"),
               CLAUDE_CONFIG_DIR=str(estate.home / ".claude"), LANES_WORKSTATION=WS,
               LANES_HOST="eagle", LANES_OS="linux", LANES_CONTAINER="none",
               LANES_IN_CONTAINER="0", LANES_NO_GITHUB="1", LANES_REPO=str(estate.checkout),
               PATH=str(fakebin) + os.pathsep + _sanitized_path())
    return estate, env


def test_sync_source_register_does_nothing_on_primary_and_says_so(tmp_path):
    """`lanes-index sync --source register:<owner/repo>` on a `mode=primary`
    workstation, this workstation's own source, makes no `psql` call, writes
    nothing (the checkout's HEAD, status, index and `origin/main` as they
    were), exits 0, and its output says it does nothing on primary (AT-1's
    FP case; lane 1's T117, "`cmd_sync` with a `register:<owner/repo>`
    source does nothing on primary, and says so"; the delta's "The post-write
    nudge does not re-index the mirror into its own source"). #160's
    run-wide `LANES_INDEX=off` is unset, or it would say nothing of
    primary."""
    fakebin = tmp_path / "fakebin"
    fake = fake_psql_dir(fakebin)
    estate, env = workspace(tmp_path / "ws", fakebin)
    copy = flipped(tmp_path)
    sock = tmp_path / "sock"
    sock.mkdir()
    passfile = tmp_path / "conf" / "pgpass"
    passfile.parent.mkdir()
    passfile.write_text("", encoding="utf-8")
    passfile.chmod(0o600)
    host = quote(sock.as_posix(), safe="")
    conf = primary_config(tmp_path / "conf" / "lanes-index.conf",
                          f"postgresql://lanes_w_t210@{host}:5432/lanes_t210",
                          f"postgresql://lanes_r_t210@{host}:5432/lanes_t210", passfile)
    env.update(fake, LANES_INDEX_CONFIG=str(conf))
    env.pop("LANES_INDEX", None)
    before = estate.state()
    proc = run_index(copy, ["sync", "--source", f"register:{WORKSPACE_REPOSITORY}"], env,
                     cwd=estate.checkout)
    said = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"sync exited {proc.returncode}: {said}"
    assert fake_calls(fake) == [], f"sync made a psql call on primary: {fake_calls(fake)}"
    assert "primary" in said, f"sync's output does not say it does nothing on primary: {said!r}"
    assert estate.state() == before, "sync wrote to the checkout"
