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
    engine);

and the image cache's own cases, lane 2's T210e (B10 tasks:972's
`PENDING-L2`), each named with `image_cache` so that lane 1's T302 selects
them with `-k 'sql_register_render and image_cache'`, with no engine: see
"the image cache (T302's API)" below;

and the render read's one case with `start`, lane 2's T210f (B10 tasks:1003;
lane 1's T301 cache-forward, #165 6767347563): with `start`,
`register_render_read` returns the images, `{path: bytes}`, and not the rows.
No engine, no image cache: see "the render read's `start`" below.

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
T117). It runs with T203's register fake first on `PATH`, whose log, with no
call that carries a request in it, is the oracle for "no `psql` call"; the
fake answers T106's `psql --version` probe itself since T203b.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
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
    # THE ATTEMPT DIRECTORY EXISTS BEFORE THE FIRST SNAPSHOT, as the seam's
    # does (contract section 3.3: its digest, run nonce and attempt "are
    # known before the first snapshot"); `--tree` names an empty `tree/` in it.
    attempt.mkdir(parents=True, exist_ok=True)
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

def fake_psql_dir(directory: Path, answers: list = None) -> dict:
    """T203's register fake, written to `directory` as `psql`, which a case
    puts first on `PATH`. Since T203b it answers `psql --version` itself,
    `psql (PostgreSQL) 16.4` (`PSQL_VERSION_LINE`), the probe lane 1's T106
    makes once per process on a register path, and logs that probe as its
    own kind (`"kind": "version"`, no `call`). Returns the variables the fake
    reads: its log, and its answers where `answers` teaches any (T203's
    docstring)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "psql").write_text(REGISTER_FAKE_PSQL, encoding="utf-8")
    (directory / "psql").chmod(0o755)
    env = {"FAKE_PSQL_LOG": str(directory / "psql.log")}
    if answers is not None:
        (directory / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
        env["FAKE_PSQL_ANSWERS"] = str(directory / "answers.json")
    return env


def fake_calls(fake: dict) -> list:
    """The fake's log, one object per call that carried a request: the
    entries with no `kind`. A `psql --version` probe (T203b's `"kind":
    "version"`) sends nothing, so it is left out, as T210's own wrapper
    left it out before T203b."""
    log = Path(fake["FAKE_PSQL_LOG"])
    if not log.exists():
        return []
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    return [e for e in entries if e.get("kind") != "version"]


def _sanitized_path() -> str:
    """The caller's PATH without any directory that holds a `lanes-index` or
    a `psql`: an installed indexer, or a real `psql`, is never what a case
    runs."""
    return os.pathsep.join(part for part in os.environ.get("PATH", "").split(os.pathsep)
                           if part and not os.path.exists(os.path.join(part, "lanes-index"))
                           and not os.path.exists(os.path.join(part, "psql")))


def workspace(root: Path, fakebin: Path) -> tuple:
    """A files-mode workspace on a bare origin, at C (SEED), whose
    `workspace.yaml` names that origin as its `repository:` and the checkout
    as its `path:`, as `test_sql_register_import.py`'s `Workspace` names
    them, with a fake `tmux` and `fakebin` first on `PATH`, in the
    environment that `Workspace` sets. Returns (the estate, the environment,
    the register source `sync --source` must name: `register:` and the
    repository as `lanes-index`'s `source_of` normalizes it, its `.git`
    dropped)."""
    estate = Estate(root)
    agents = estate.home / ".agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "workspace.yaml").write_text(
        f"repository: {estate.origin}\npath: {estate.checkout}\n", encoding="utf-8")
    source = "register:" + re.sub(r"\.git$", "", str(estate.origin))
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
    return estate, env, source


def test_sync_source_register_does_nothing_on_primary_and_says_so(tmp_path):
    """`lanes-index sync --source register:<owner/repo>` on a `mode=primary`
    workstation, this workstation's own source, makes no `psql` call, writes
    nothing (the checkout's HEAD, status, index and `origin/main` as they
    were, and nothing in `lanes-index`'s state directory but its sync lock:
    no index store, no status record), exits 0, and its output says it does
    nothing on primary (AT-1's
    FP case; lane 1's T117, "`cmd_sync` with a `register:<owner/repo>`
    source does nothing on primary, and says so"; the delta's "The post-write
    nudge does not re-index the mirror into its own source"). #160's
    run-wide `LANES_INDEX=off` is unset, or it would say nothing of
    primary."""
    fakebin = tmp_path / "fakebin"
    fake = fake_psql_dir(fakebin)
    estate, env, source = workspace(tmp_path / "ws", fakebin)
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
    state_root = Path(env["XDG_STATE_HOME"])
    before, state_before = estate.state(), _files_under(state_root)
    proc = run_index(copy, ["sync", "--source", source], env, cwd=estate.checkout)
    said = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"sync exited {proc.returncode}: {said}"
    assert fake_calls(fake) == [], f"sync made a psql call on primary: {fake_calls(fake)}"
    assert "primary" in said, f"sync's output does not say it does nothing on primary: {said!r}"
    assert estate.state() == before, "sync wrote to the checkout"
    state_after = _files_under(state_root)
    written = sorted(p for p, digest in state_after.items() if state_before.get(p) != digest)
    assert all(SYNC_LOCK_FILES.match(p) for p in written), (
        f"sync wrote under {state_root} on primary, beyond its lock: {written}")


#: What a sync may leave in `lanes-index`'s state directory,
#: `$XDG_STATE_HOME/openRepoTools/`, when it does nothing: its one-at-a-time
#: lock and the lock's rerun marks (`SyncLock`, 14(d) and #161). An index
#: store (`lanes-index.sqlite`) or a status record is a write.
SYNC_LOCK_FILES = re.compile(r"^openRepoTools/lanes-index\.(lock|rerun(-[a-z]+)?)$")


def _files_under(root: Path) -> dict:
    """Every file under `root`, {relative path: sha256}."""
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ============================================================ the image cache (T302's API)
#
# THE IMAGE CACHE'S OWN TEST (lane 2's T210e; B10 tasks:972's `PENDING-L2`;
# F10-OWED items 26 and 34): lane 1's T302 adds the cache to `lanes-index`,
# under its state directory, `register-images/` (design Y:4963; PC-1), with
# the five functions and two constants of lane 3's ruling (#165 6746004829,
# extended by 6755051914) and lane 1's formats (#165 6755106847, "The
# formats, for lane 2's test"), as its fix round left them (6755799745; lane
# 3's delta check, 6755954683). T302's first run selects these cases with
# `-k 'sql_register_render and image_cache'`. They need no engine: each loads
# `lanes-index` as a module, with `XDG_STATE_HOME` under the case's own
# directory, and calls the API in process. They fail until T302 lands, by the
# assertion `image_cache_module` makes; the last one fails until lane 1's
# follow-up commit too (6755954683, doubts 1 and 2).

#: The API lane 3's ruling fixes: five functions and two constants.
IMAGE_CACHE_API = ("image_cache_get", "image_cache_put", "image_cache_head",
                   "image_cache_record", "image_cache_collect")
IMAGE_CACHE_CONSTANTS = {"IMAGE_CACHE_KEEP": 3, "IMAGE_CACHE_FLOOR_SECONDS": 600}
#: A temp file as lane 1's format names it: `.<name>.tmp-<pid>-<8 hex>`.
IMAGE_CACHE_TEMP = re.compile(r"^\..+\.tmp-[0-9]+-[0-9a-f]{8}$")
#: Older than collection's floor, with room: an hour before now.
IMAGE_CACHE_OLD = 3600


class ImageCache:
    """`lanes-index` loaded as a module whose state directory is `state`
    (`XDG_STATE_HOME`), with the cache's paths."""

    def __init__(self, module, state: Path):
        self.m = module
        self.root = state / "openRepoTools" / "register-images"
        self.objects = self.root / "objects"
        self.seq = self.root / "seq"
        self.head_file = self.root / "head"
        self.lock = self.root / "lock"

    def object(self, digest: str) -> Path:
        return self.objects / digest

    def age(self, path: Path, seconds: int = IMAGE_CACHE_OLD) -> None:
        """Sets `path`'s mtime `seconds` before now, past the floor."""
        then = time.time() - seconds
        os.utime(path, (then, then), follow_symlinks=False)

    def temps(self) -> list:
        """Every temp file of lane 1's form left anywhere in the cache."""
        if not self.root.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob(".*")
                      if IMAGE_CACHE_TEMP.match(p.name))


def image_cache_module(tmp_path: Path, monkeypatch) -> ImageCache:
    """`lanes-index` as a module, under its own name so nothing else in the
    run shares it, with `XDG_STATE_HOME` set to `<tmp_path>/state`, where
    `state_dir()` puts `openRepoTools/register-images/`. Asserts the API is
    there: lane 1's T302, B10 tasks:972 (the case's red until it lands)."""
    from importlib.machinery import SourceFileLoader
    import importlib.util
    loader = SourceFileLoader(f"lanes_index_image_cache_{uuid.uuid4().hex}", str(LANES_INDEX))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    missing = [name for name in (*IMAGE_CACHE_API, *IMAGE_CACHE_CONSTANTS)
               if not hasattr(module, name)]
    assert not missing, (
        f"{LANES_INDEX} has no image cache API, {missing} missing: lane 1's T302 (B10 "
        f"tasks:972; #165 6755106847) has not landed")
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    return ImageCache(module, state)


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_the_image_cache_puts_and_gets_an_object_only_by_its_digest(tmp_path, monkeypatch):
    """`image_cache_put(data)` returns `data`'s sha256 as 64 lowercase hex and
    writes `objects/<digest>` under `$XDG_STATE_HOME/openRepoTools/
    register-images/`, the file 0600 and each directory 0700, by a temp file
    and a rename that leaves no temp file; a `bytearray` is taken as bytes,
    and anything else raises `TypeError` before the cache is touched, the
    one error that escapes. `image_cache_get(digest)` returns the bytes only
    when they hash to `digest`: a missing object, a digest that is not 64
    lowercase hex, a name outside `objects/`, an object whose bytes changed
    and a symlink at the object's name are each a miss (None), and `put`
    replaces the bad object and leaves a link's target alone. A second `put`
    of an object already whole rewrites nothing and sets its mtime to now,
    so the floor keeps it (lane 1's readings 1 and 2; fix round NIT-3 and
    NIT-4)."""
    cache = image_cache_module(tmp_path, monkeypatch)
    m = cache.m
    with pytest.raises(TypeError):
        m.image_cache_put("lanes/LANES.md as text, not bytes")
    assert not (tmp_path / "state").exists(), "put touched the cache before its TypeError"

    data = f"# LANES.md {EM} the image cache's own test\n".encode("utf-8")
    digest = m.image_cache_put(data)
    assert digest == _digest(data) and re.fullmatch(r"[0-9a-f]{64}", digest), digest
    assert cache.object(digest).read_bytes() == data
    assert _mode(cache.object(digest)) == 0o600, oct(_mode(cache.object(digest)))
    for directory in (tmp_path / "state" / "openRepoTools", cache.root, cache.objects):
        assert _mode(directory) == 0o700, f"{directory} is {oct(_mode(directory))}, not 0700"
    assert m.image_cache_get(digest) == data
    assert m.image_cache_put(bytearray(data)) == digest
    assert cache.temps() == [], f"a temp file was left: {cache.temps()}"

    # MISSES: an object that is not there, and digests out of form.
    other = _digest(b"never put\n")
    assert m.image_cache_get(other) is None
    for bad in (digest.upper(), digest[:63], digest + "0", "", "../head", None, 7):
        assert m.image_cache_get(bad) is None, f"get({bad!r}) was not a miss"

    # A WHOLE OBJECT IS NOT WRITTEN AGAIN; ITS MTIME COMES TO NOW.
    inode = os.lstat(cache.object(digest)).st_ino
    cache.age(cache.object(digest))
    assert m.image_cache_put(data) == digest
    assert os.lstat(cache.object(digest)).st_ino == inode, "a whole object was rewritten"
    assert time.time() - os.lstat(cache.object(digest)).st_mtime < 60, (
        "put of a whole object left its old mtime, so the floor would not keep it")

    # AN OBJECT WHOSE BYTES CHANGED IS A MISS, AND PUT REPLACES IT.
    cache.object(digest).write_bytes(b"torn")
    assert m.image_cache_get(digest) is None, "get returned bytes that do not hash to the name"
    assert m.image_cache_put(data) == digest
    assert m.image_cache_get(digest) == data and cache.object(digest).read_bytes() == data

    # A SYMLINK AT THE OBJECT'S NAME IS A MISS, AND PUT REPLACES IT (NIT-4).
    outside = tmp_path / "outside"
    outside.write_bytes(data)
    cache.object(digest).unlink()
    cache.object(digest).symlink_to(outside)
    assert m.image_cache_get(digest) is None, "get followed a symlink at an object's name"
    assert m.image_cache_put(data) == digest
    assert not cache.object(digest).is_symlink() and cache.object(digest).read_bytes() == data
    assert outside.read_bytes() == data, "put changed a link's target"
    assert cache.temps() == [], f"a temp file was left: {cache.temps()}"


def test_the_image_cache_records_manifests_and_a_head_that_moves_only_forward(tmp_path,
                                                                               monkeypatch):
    """`image_cache_record(n, manifest)` writes `seq/<n>`, one `<path>` TAB
    `<digest>` line per path, each LF-ended, sorted by path bytewise, an
    empty manifest an empty file, 0600; a second record of one `n` merges
    into the first, a path in both taking the second's digest. `head` is
    `<n>` and an LF, read with or without the LF and never with a leading
    zero, and moves only forward; a missing `head`, or one with no seq, is
    written as the larger of `n` and the highest seq `seq/` lists (NIT-2).
    `image_cache_head()` answers (seq, manifest), or None. A record whose `n`
    is not a whole number from 0 to 2**63 - 1, or whose manifest is not a
    dict of paths with no control character to digests, is skipped, and no
    call raises (lane 1's readings 6 and 7)."""
    cache = image_cache_module(tmp_path, monkeypatch)
    m = cache.m
    assert m.image_cache_head() is None
    accented = "lanes/log/repo" + chr(0x00E9) + "-1.md"
    d1, d2, d3 = (_digest(f"image {k}\n".encode("ascii")) for k in (1, 2, 3))
    m.image_cache_record(5, {"lanes/log/repoA-1.md": d2, accented: d3, "lanes/LANES.md": d1})
    expected = [("lanes/LANES.md", d1), ("lanes/log/repoA-1.md", d2), (accented, d3)]
    assert (cache.seq / "5").read_bytes() == "".join(
        f"{p}\t{d}\n" for p, d in expected).encode("utf-8"), "the manifest's form or order"
    assert cache.head_file.read_bytes() == b"5\n"
    assert _mode(cache.seq / "5") == 0o600 and _mode(cache.head_file) == 0o600
    assert _mode(cache.seq) == 0o700
    assert m.image_cache_head() == (5, dict(expected))

    # THE HEAD NEVER MOVES BACK.
    m.image_cache_record(3, {"lanes/LANES.md": d2})
    assert (cache.seq / "3").read_bytes() == f"lanes/LANES.md\t{d2}\n".encode("ascii")
    assert cache.head_file.read_bytes() == b"5\n", "a lower record moved the head back"

    # A SECOND RECORD OF ONE SEQ MERGES, ITS OWN DIGEST WINNING.
    m.image_cache_record(5, {"lanes/LANES.md": d3, "lanes/aliases.tsv": d1})
    assert m.image_cache_head() == (5, {"lanes/LANES.md": d3, "lanes/aliases.tsv": d1,
                                        "lanes/log/repoA-1.md": d2, accented: d3})

    # AN EMPTY MANIFEST IS AN EMPTY FILE; THE HEAD READS WITH OR WITHOUT ITS LF.
    m.image_cache_record(7, {})
    assert (cache.seq / "7").read_bytes() == b"" and cache.head_file.read_bytes() == b"7\n"
    assert m.image_cache_head() == (7, {})
    cache.head_file.write_bytes(b"7")
    assert m.image_cache_head() == (7, {}), "a head with no LF is not read"
    for bad in (b"07\n", b"7\n\n", b" 7\n", b"seven\n", b""):
        cache.head_file.write_bytes(bad)
        assert m.image_cache_head() is None, f"a head of {bad!r} was read"

    # A HEAD WITH NO SEQ, OR NONE, IS WRITTEN AS THE LARGER OF n AND seq/'s HIGHEST.
    cache.head_file.write_bytes(b"seven\n")
    m.image_cache_record(4, {"lanes/LANES.md": d1})
    assert cache.head_file.read_bytes() == b"7\n", "a junk head was not repaired to 7"
    cache.head_file.unlink()
    m.image_cache_record(2, {"lanes/LANES.md": d1})
    assert cache.head_file.read_bytes() == b"7\n", "a missing head moved back to 2"

    # RECORDS OUT OF FORM ARE SKIPPED, AND RAISE NOTHING.
    before = sorted(p.name for p in cache.seq.iterdir())
    for n, manifest in ((-1, {}), (True, {}), (2 ** 63, {}), ("9", {}), (9.0, {}),
                        (9, {"lanes/LANES.md": d1.upper()}), (9, {"lanes/a\tb.md": d1}),
                        (9, {"lanes/a\nb.md": d1}), (9, {"lanes/a" + chr(0) + ".md": d1}),
                        (9, {"": d1}), (9, [("lanes/LANES.md", d1)]), (9, None)):
        m.image_cache_record(n, manifest)
    assert sorted(p.name for p in cache.seq.iterdir()) == before, (
        "a record out of form wrote a manifest")
    assert cache.head_file.read_bytes() == b"7\n"
    assert m.image_cache_record(2 ** 63 - 1, {}) is None
    assert cache.head_file.read_bytes() == str(2 ** 63 - 1).encode("ascii") + b"\n"
    assert cache.temps() == [], f"a temp file was left: {cache.temps()}"


def test_the_image_cache_collects_all_but_the_last_three_manifests_past_the_floor(
        tmp_path, monkeypatch):
    """Collection keeps the manifests of the `IMAGE_CACHE_KEEP` = 3 highest
    seqs and removes every older one; it removes an object named in none of
    them only when its mtime is over `IMAGE_CACHE_FLOOR_SECONDS` = 600 old,
    so an old object a kept manifest names, and a young one none names, both
    stay. It removes a temp file of the form `.<name>.tmp-<pid>-<8 hex>`
    only past the same floor, and no other name. Where one of the kept
    manifests is out of form, it removes no object (lane 1's readings 3, 4
    and 5). `image_cache_record` collects too, under the same lock."""
    cache = image_cache_module(tmp_path, monkeypatch)
    m = cache.m
    for name, value in IMAGE_CACHE_CONSTANTS.items():
        assert getattr(m, name) == value, f"{name} is {getattr(m, name)!r}, not {value}"
    data = [f"image {k}\n".encode("ascii") for k in range(1, 8)]
    o = [m.image_cache_put(d) for d in data]
    for k in range(1, 6):
        m.image_cache_record(k, {"lanes/LANES.md": o[k - 1]})
    assert sorted(p.name for p in cache.seq.iterdir()) == ["3", "4", "5"], (
        "record kept a manifest older than the last three")

    for k in (0, 1, 2, 3, 6):
        cache.age(cache.object(o[k]))
    temps = {"objects/.x.tmp-41-0123abcd": True, "objects/.y.tmp-42-89abcdef": False,
             ".head.tmp-43-deadbeef": True, "seq/.5.tmp-44-cafef00d": True}
    strays = ("objects/notes.txt", "objects/" + "A" * 64, "objects/.x.tmp-45-XYZ")
    for rel, old in temps.items():
        (cache.root / rel).write_bytes(b"part")
        if old:
            cache.age(cache.root / rel)
    for rel in strays:
        (cache.root / rel).write_bytes(b"stray")
        cache.age(cache.root / rel)

    m.image_cache_collect()
    kept = {k for k in range(7) if cache.object(o[k]).exists()}
    assert kept == {2, 3, 4, 5}, (
        f"objects kept: {sorted(kept)}, not images 3 and 4 (old, named by seqs 3 and 4), 5 "
        f"(named by the head) and 6 (named by none, younger than the floor)")
    assert sorted(p.name for p in cache.seq.iterdir() if not p.name.startswith(".")) == \
        ["3", "4", "5"]
    for rel, old in temps.items():
        assert (cache.root / rel).exists() is not old, (
            f"{rel}: a temp file {'over' if old else 'under'} the floor was "
            f"{'kept' if old else 'removed'}")
    for rel in strays:
        assert (cache.root / rel).exists(), f"collection removed {rel}, not a name it writes"
    assert m.image_cache_head() == (5, {"lanes/LANES.md": o[4]})

    # A KEPT MANIFEST OUT OF FORM: NO OBJECT IS REMOVED.
    cache.age(cache.object(o[5]))
    (cache.seq / "4").write_bytes(b"lanes/LANES.md")
    m.image_cache_collect()
    assert cache.object(o[5]).exists(), (
        "collection removed an object while a kept manifest could not be read")


def test_the_image_cache_skips_a_busy_or_odd_lock_and_never_waits(tmp_path, monkeypatch):
    """Recording and collection take `register-images/lock` with `LOCK_EX |
    LOCK_NB`, tried once: while another holder has it, `image_cache_record`
    writes nothing and `image_cache_collect` removes nothing, and neither
    waits. A `lock` that is not a regular file, a FIFO with no reader here,
    counts as busy, and the call returns at once with nothing changed
    (lane 1's fix round, SHOULD-1). The lock file is 0600."""
    import fcntl
    import threading
    cache = image_cache_module(tmp_path, monkeypatch)
    m = cache.m
    d1, d2 = (m.image_cache_put(f"image {k}\n".encode("ascii")) for k in (1, 2))
    m.image_cache_record(1, {"lanes/LANES.md": d1})
    assert _mode(cache.lock) == 0o600, oct(_mode(cache.lock))
    loose = m.image_cache_put(b"named by no manifest\n")
    cache.age(cache.object(loose))

    held = os.open(str(cache.lock), os.O_WRONLY | os.O_APPEND)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        start = time.monotonic()
        m.image_cache_record(2, {"lanes/LANES.md": d2})
        m.image_cache_collect()
        assert time.monotonic() - start < 5, "a call waited for the held lock"
        assert not (cache.seq / "2").exists(), "record wrote while the lock was held"
        assert cache.head_file.read_bytes() == b"1\n"
        assert cache.object(loose).exists(), "collect removed an object while the lock was held"
    finally:
        os.close(held)

    m.image_cache_collect()
    assert not cache.object(loose).exists(), "collect did nothing once the lock was free"
    m.image_cache_record(2, {"lanes/LANES.md": d2})
    assert cache.head_file.read_bytes() == b"2\n"

    # A FIFO AT THE LOCK'S NAME: BUSY, AT ONCE, WHETHER OR NOT IT BLOCKS ITS OPEN.
    os.replace(str(cache.lock), str(cache.root / "lock.aside"))
    os.mkfifo(str(cache.lock), 0o600)
    loose = m.image_cache_put(b"named by no manifest, again\n")
    cache.age(cache.object(loose))
    worker = threading.Thread(target=lambda: (m.image_cache_record(3, {"lanes/LANES.md": d1}),
                                              m.image_cache_collect()), daemon=True)
    worker.start()
    worker.join(10)
    assert not worker.is_alive(), "record or collect blocked on a FIFO at the lock's name"
    assert not (cache.seq / "3").exists() and cache.head_file.read_bytes() == b"2\n"
    assert cache.object(loose).exists(), "collect ran through a FIFO lock"
    assert stat.S_ISFIFO(os.lstat(cache.lock).st_mode)


def test_the_image_cache_follows_no_symlink_at_its_lock_or_its_head(tmp_path, monkeypatch):
    """Lane 1's follow-up to T302's fix round (lane 3's delta check, #165
    6755954683, doubts 1 and 2): the lock is opened with `O_NOFOLLOW`, so a
    symlink planted at `register-images/lock` is a skip, its target neither
    changed nor created; and `record` treats a symlinked `head` as a missing
    one, so it replaces the link with a regular `head` and leaves the link's
    target alone. Until that commit lands, this case fails by its own
    assertion, where the rest of the image cache's cases pass."""
    cache = image_cache_module(tmp_path, monkeypatch)
    m = cache.m
    d1 = m.image_cache_put(b"image 1\n")
    m.image_cache_record(1, {"lanes/LANES.md": d1})

    # A SYMLINKED HEAD: RECORD REPLACES THE LINK, NOT ITS TARGET.
    target = tmp_path / "elsewhere-head"
    target.write_bytes(b"1\n")
    cache.head_file.unlink()
    cache.head_file.symlink_to(target)
    m.image_cache_record(2, {"lanes/LANES.md": d1})
    assert target.read_bytes() == b"1\n", "record wrote through a symlinked head"
    assert not cache.head_file.is_symlink() and cache.head_file.read_bytes() == b"2\n", (
        "record left a symlinked head in place (lane 3's 6755954683, doubt 2's fix: ELOOP as "
        "FileNotFoundError), so image_cache_head() stays unreadable")

    # A SYMLINKED LOCK, DANGLING: A SKIP, AND ITS TARGET IS NOT CREATED.
    planted = tmp_path / "elsewhere" / "lock-target"
    planted.parent.mkdir()
    os.replace(str(cache.lock), str(cache.root / "lock.aside"))
    cache.lock.symlink_to(planted)
    m.image_cache_record(3, {"lanes/LANES.md": d1})
    assert not planted.exists(), (
        "the lock's open followed a symlink and created its target (lane 3's 6755954683, "
        "doubt 1: O_NOFOLLOW on the lock)")
    assert not (cache.seq / "3").exists(), "record ran under a symlinked lock"


# ======================================== the render read's `start` (T301's cache-forward)
#
# LANE 1'S CACHE-FORWARD COMMIT (T301's `e4d28a505af8`, tag `l1-007-T301-cf1`;
# #165 6767347563; the cache signature lane 3 accepted in 6755051914, B10
# tasks:996-1003). B10 gives T210 "one case with `start`, so that both arms are
# covered", and lane 1's doubt 1 says what it expects: with `start`,
# `register_render_read` returns THE IMAGES, `{path: bytes}`, and not the rows;
# without it, still `(journal, edits, files)`. T210f (line W4b, wave 6) is this
# case. It needs no engine: the read runs in process against a stand-in store
# that answers each SELECT the code sends from an in-memory sqlite database, as
# lane 1's own hand checks do ("sqlite stood in for PostgreSQL"), and fails
# until the cache-forward commit lands, by the assertion `render_read_module`
# makes.
#
# What the case reads from lane 1's code rather than from a contract, since
# section 3.6 fixes only the CLI: `register_render_read(store, k, *, start=None,
# row="render")`, `register_render_queries(k, *, since=None)`,
# `register_cache_state(images)`, `register_images(journal, edits, files, *,
# start=None)`, `RenderRefused`, and the store's one method the read calls,
# `_query_many(queries, snapshot=True, row=...)`, whose answer is a list of
# result sets of rows of text fields (`t`/`f` for a boolean, None for NULL).

#: The paths of the journal below: the render set's files, and `lanes/STORE`,
#: which is journaled and is never an image.
LANES_MD, ALPHA_LOG, BETA_LOG, GAMMA_LOG = ("lanes/LANES.md", "lanes/log/alpha.md",
                                            "lanes/log/beta.md", "lanes/log/gamma.md")
ALIASES_TSV, ARCHIVE_MD = "lanes/aliases.tsv", "lanes/archive/old.md"
#: The files whose row says `final_newline` false: an image with no last LF.
NO_LAST_LF = frozenset({ALIASES_TSV})

#: AT-1's journal in miniature, as `commit_write` leaves it (design section 1.3.1): an
#: import, then writes. An entry is `(kind, edits, no_last_lf)`; an edit is
#: `("create", path)`, `("append", path, text)`, `("replace", path, n, text)`,
#: `("delete", path, n)` or `("remove", path)`. Seq 2 touches `lanes/STORE`;
#: seq 3 replaces a line, seq 4 deletes one, seq 5 removes a file, and
#: `lanes/archive/old.md` is never touched after the import.
RENDER_JOURNAL = [
    ("import", [("create", LANES_MD), ("append", LANES_MD, "# LANES"),
                ("append", LANES_MD, "| alpha | held |"),
                ("create", ALPHA_LOG), ("append", ALPHA_LOG, "alpha 1"),
                ("append", ALPHA_LOG, f"alpha 2 {EM} two"),
                ("create", ALIASES_TSV), ("append", ALIASES_TSV, "old\talpha"),
                ("create", ARCHIVE_MD), ("append", ARCHIVE_MD, "archived")], NO_LAST_LF),
    ("write", [("append", LANES_MD, "| beta | free |")], ()),
    ("write", [("append", ALPHA_LOG, "alpha 3"), ("create", BETA_LOG),
               ("append", BETA_LOG, "beta 1"), ("create", STORE_PATH)], ()),
    ("write", [("replace", ALPHA_LOG, 1, "alpha 1 (edited)")], ()),
    ("write", [("delete", ALPHA_LOG, 2), ("append", ALIASES_TSV, "new\tbeta")], NO_LAST_LF),
    ("write", [("remove", BETA_LOG), ("append", LANES_MD, "| gamma | free |")], ()),
]
#: The same register after a re-import at seq 4 (before a confirmed cutover):
#: the root is replaced, so alpha and beta are gone and the seqs 0 to 3 of the
#: old root are history a cache may still hold.
RENDER_REIMPORT = RENDER_JOURNAL[:4] + [
    ("import", [("create", LANES_MD), ("append", LANES_MD, "# LANES (re-imported)"),
                ("create", GAMMA_LOG), ("append", GAMMA_LOG, "gamma 1"),
                ("create", ALIASES_TSV), ("append", ALIASES_TSV, "old\tgamma")], NO_LAST_LF),
    ("write", [("append", GAMMA_LOG, "gamma 2")], ()),
]


def _render_image_bytes(lines: list, final_newline: bool) -> bytes:
    """One file's bytes as `render_file` builds them (design Y:1297), spelled
    out here so that the case's oracle is not the code's own function."""
    return ("\n".join(lines) + ("\n" if final_newline and lines else "")).encode("utf-8")


class RenderJournal:
    """`entries` replayed by this test's own model, which gives what the
    register would hold: the rows of `journal`, `journal_edits` and
    `journal_files`, and for each seq the render set's images and its state,
    `{path: (lines, final_newline)}`, as the cache's read-back should give."""

    def __init__(self, entries: list):
        self.rows = {"journal": [], "journal_edits": [], "journal_files": []}
        self.images_at, self.state_at = [], []
        state: dict = {}
        for seq, (kind, edits, no_last_lf) in enumerate(entries):
            self.rows["journal"].append((seq, kind))
            if kind == "import":
                state.clear()
            touched = []
            for ordinal, edit in enumerate(edits, 1):
                op, path = edit[0], edit[1]
                if path not in touched:
                    touched.append(path)
                lines = state[path][0] if path in state else None
                row = (None, None, None)
                if op == "create":
                    state[path] = [[], True]
                elif op == "append":
                    row = (len(lines) + 1, None, edit[2])
                    lines.append(edit[2])
                elif op == "replace":
                    row = (edit[2], _digest(lines[edit[2] - 1].encode("utf-8")), edit[3])
                    lines[edit[2] - 1] = edit[3]
                elif op == "delete":
                    row = (edit[2], _digest(lines[edit[2] - 1].encode("utf-8")), None)
                    del lines[edit[2] - 1]
                else:
                    del state[path]
                self.rows["journal_edits"].append((seq, ordinal, op, path, *row, None))
            for path in touched:
                if path not in state:
                    self.rows["journal_files"].append((seq, path, "f", None, None))
                    continue
                if path in no_last_lf:
                    state[path][1] = False
                lines, final_newline = state[path]
                self.rows["journal_files"].append(
                    (seq, path, "t", _digest(_render_image_bytes(lines, final_newline)),
                     "t" if final_newline else "f"))
            self.images_at.append({p: _render_image_bytes(*v) for p, v in state.items()
                                   if RENDER_SET.match(p)})
            self.state_at.append({p: (list(v[0]), v[1]) for p, v in state.items()
                                  if RENDER_SET.match(p)})
        self.last = len(entries) - 1


class RenderRegister:
    """The stand-in store: `register_render_read` calls `store._query_many(
    queries, snapshot=True, row=...)`, and this answers each SELECT it is
    given from an in-memory sqlite database holding `journal`'s rows. It
    records each call in `requests`, as `(queries, snapshot, row)`. With
    `raises` set, a call records itself and raises that, as a dead connection
    does."""

    DDL = (
        "CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER, "
        "writers_from INTEGER, readers_from INTEGER)",
        "CREATE TABLE register_head (id INTEGER PRIMARY KEY, seq INTEGER)",
        "CREATE TABLE journal (seq INTEGER PRIMARY KEY, kind TEXT)",
        "CREATE TABLE journal_edits (seq INTEGER, ord INTEGER, op TEXT, path TEXT, "
        "line_no INTEGER, old_sha256 TEXT, new_text TEXT, to_path TEXT)",
        "CREATE TABLE journal_files (seq INTEGER, path TEXT, present TEXT, sha256 TEXT, "
        "final_newline TEXT)",
    )

    def __init__(self, module, journal: RenderJournal):
        import sqlite3
        self.db = sqlite3.connect(":memory:")
        for statement in self.DDL:
            self.db.execute(statement)
        self.db.execute("INSERT INTO schema_version VALUES (1, ?, 1, 1)",
                        (module.REGISTER_SCHEMA_VERSION,))
        self.db.execute("INSERT INTO register_head VALUES (1, ?)", (journal.last,))
        for table, rows in journal.rows.items():
            self.db.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(rows[0]))})",
                                rows)
        self.requests: list = []
        self.raises = None

    def _query_many(self, queries, snapshot=False, *, row=None, timer=None):
        self.requests.append((list(queries), snapshot, row))
        if self.raises is not None:
            raise self.raises
        return [[[None if value is None else str(value) for value in fetched]
                 for fetched in self.db.execute(query).fetchall()] for query in queries]


def render_read_module():
    """`lanes-index` as a module, under its own name so nothing else in the run
    shares it. Asserts lane 1's cache-forward commit is there: the case's red
    until `register_render_read`, `register_images` and `register_render_queries`
    take their `start` and `since`, and `register_cache_state` reads images
    back (#165 6755040818, 6767347563)."""
    from importlib.machinery import SourceFileLoader
    import importlib.util
    import inspect
    loader = SourceFileLoader(f"lanes_index_render_read_{uuid.uuid4().hex}", str(LANES_INDEX))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    missing = [name for name in ("register_render_read", "register_render_queries",
                                 "register_images", "register_cache_state", "RenderRefused",
                                 "PsqlFailed", "REGISTER_SCHEMA_VERSION")
               if not hasattr(module, name)]
    assert not missing, (
        f"{LANES_INDEX} has no render read, {missing} missing: lane 1's T301, with its "
        f"cache-forward commit (`e4d28a505af8`, #165 6767347563), has not landed")
    wanting = [f"{name}'s {keyword}" for name, keyword in (
        ("register_render_read", "start"), ("register_images", "start"),
        ("register_render_queries", "since"))
        if keyword not in inspect.signature(getattr(module, name)).parameters]
    assert not wanting, (
        f"{LANES_INDEX} takes no {wanting}: lane 1's T301 cache-forward commit "
        f"(`e4d28a505af8`, #165 6767347563) has not landed")
    return module


def test_the_render_read_with_start_returns_the_images_and_a_bad_start_costs_one_full_read():
    """T210's case with `start` (B10 tasks:1003; lane 1, #165 6767347563, doubt
    1: "**Lane 2:** T210's `start` case should expect images"). Both arms of
    `register_render_read`, against a register built by this test's own model
    of `commit_write`:

    WITHOUT `start` it returns `(journal, edits, files)`, the rows from the
    latest import to `k`, which `register_images` builds into the images, in
    one request.

    WITH `start=(c, state)`, `state` being `register_cache_state` of the
    images at `c`, it returns THE IMAGES AT `k`, a `dict` of `bytes` and not
    the rows, equal to the model's for every `c` from 0 to `k`: in ONE request,
    which reads only the entries after `c` (`register_render_queries(k,
    since=c)`), and `start` is left as it was.

    A START IT CANNOT TRUST IS A MISS, NOT AN ERROR: a cached image of an
    untouched path that is wrong (a cache from a reused seq), a cached image
    that an edit does not apply on, a path the cache lacks, a `start` of
    another form and a `c` above `k` each return the right images, by a full
    read as the last request, and a failed proof costs exactly two requests,
    the first read since `c` and the second the full read. An import among
    entries `c+1` to `k` sets `start` aside, so even a wrong cache is no
    miss there, one request. Only the full read's failure ends in
    `RenderRefused`, after the two requests; a dead connection (`PsqlFailed`)
    is raised as it is, after one, and is never tried twice. And
    `register_cache_state` misses (None) on an image that is empty, is not
    UTF-8 or is not bytes, so an estate with an empty file in its render set
    always replays in full."""
    pytest.importorskip("sqlite3")
    import copy
    m = render_read_module()
    journal = RenderJournal(RENDER_JOURNAL)
    register = RenderRegister(m, journal)
    last = journal.last

    def read(k, **kwargs):
        """One call and the requests it made. A `RenderRefused` is no answer, and
        fails the expectation that asked."""
        before = len(register.requests)
        try:
            answer = m.register_render_read(register, k, **kwargs)
        except m.RenderRefused as refusal:
            raise AssertionError(f"read(k={k}) ended in RenderRefused: {refusal}") from None
        return answer, register.requests[before:]

    def kinds(k, sent):
        """The requests as `full` or `since`, for a failure's message."""
        return ["full" if queries == m.register_render_queries(k) else "since"
                for queries, _snapshot, _row in sent]

    def full(k, row="render"):
        return (m.register_render_queries(k), True, row)

    def since(k, c, row="render"):
        return (m.register_render_queries(k, since=c), True, row)

    # THE READ WITHOUT `start` GIVES THE ROWS, IN ONE REQUEST, AND THE ROWS BUILD THE IMAGES.
    for k in range(last + 1):
        rows, sent = read(k)
        assert isinstance(rows, tuple) and len(rows) == 3, (
            f"read(k={k}) without start returned {type(rows).__name__}, not "
            f"(journal, edits, files)")
        assert sent == [full(k)], f"read({k}) sent {kinds(k, sent)}"
        assert rows[0][0] == (0, "import") and rows[0][-1][0] == k, rows[0]
        assert m.register_images(*rows) == journal.images_at[k], f"the images at seq {k}"

    # THE CACHE'S READ-BACK: THE STATE THE MODEL HOLDS, FOR EVERY SEQ.
    for c in range(last + 1):
        assert m.register_cache_state(journal.images_at[c]) == journal.state_at[c], (
            f"register_cache_state of the images at seq {c}")

    # WITH `start`: THE IMAGES AT `k`, FOR EVERY `c` UP TO `k`, IN ONE REQUEST SINCE `c`.
    for c in range(last + 1):
        start = (c, m.register_cache_state(journal.images_at[c]))
        frozen = copy.deepcopy(start)
        for k in range(c, last + 1):
            images, sent = read(k, start=start)
            assert isinstance(images, dict) and not isinstance(images, tuple), (
                f"read(k={k}, start at {c}) returned {type(images).__name__}: with `start` "
                f"it returns the images, {{path: bytes}}, and not the rows")
            assert all(isinstance(p, str) and isinstance(b, bytes) for p, b in images.items())
            assert images == journal.images_at[k], f"the images at seq {k} from a cache at {c}"
            assert sent == [since(k, c)], (
                f"read(k={k}, start at {c}) sent {kinds(k, sent)}, not one request since {c}")
            assert start == frozen, "register_render_read changed `start`"

    # A START IT CANNOT TRUST IS A MISS: THE RIGHT IMAGES, AND A FULL READ LAST.
    k, c = last, 2
    good = dict(journal.images_at[c])
    wrong_untouched = {**good, ARCHIVE_MD: b"another root's archive\n"}
    wrong_edit_base = {**good, ALPHA_LOG: b"not alpha's first line\nalpha 2\nalpha 3\n"}
    lacks_untouched = {p: b for p, b in good.items() if p != ARCHIVE_MD}
    for what, images in (("a wrong image of an untouched path (a cache from a reused seq)",
                          wrong_untouched),
                         ("an image the seq-3 replace does not apply on", wrong_edit_base),
                         ("a cache that lacks an untouched path", lacks_untouched)):
        state = m.register_cache_state(images)
        assert state is not None, f"register_cache_state refused {what}"
        answer, sent = read(k, start=(c, state))
        assert answer == journal.images_at[k], f"the images after {what}"
        assert sent == [since(k, c), full(k)], (
            f"{what}: a failed proof or edit costs exactly two requests, the first since "
            f"seq {c} and the second the full read; sent {kinds(k, sent)}")
    ok_state = m.register_cache_state(good)
    for what, start, at in (("a `c` above `k`", (5, m.register_cache_state(journal.images_at[5])),
                             3),
                            ("a `c` that is not an int", ("2", ok_state), last),
                            ("a `c` that is a bool", (True, ok_state), last),
                            ("a state that is not a dict", (2, "not a state"), last),
                            ("a state of the wrong value form", (2, {LANES_MD: "text"}), last),
                            ("a start of one item", (2,), last),
                            ("a start that is not a pair", [], last)):
        answer, sent = read(at, start=start)
        assert isinstance(answer, dict) and answer == journal.images_at[at], (
            f"the images after {what}")
        assert 1 <= len(sent) <= 2 and sent[-1] == full(at), (
            f"{what}: the last request must be the full read; sent {kinds(at, sent)}")

    # AN IMPORT AMONG ENTRIES `c+1` TO `k` SETS `start` ASIDE: EVEN A WRONG CACHE IS NO MISS.
    again = RenderJournal(RENDER_REIMPORT)
    reimport = RenderRegister(m, again)
    old_root = m.register_cache_state(journal.images_at[2])
    for caches, cached in (("the old root's images", old_root),
                           ("images the seq-3 replace does not apply on, which is never "
                            "applied", m.register_cache_state(wrong_edit_base))):
        for c, k in ((2, 5), (2, 4), (3, 5)):
            before = len(reimport.requests)
            answer = m.register_render_read(reimport, k, start=(c, cached))
            assert answer == again.images_at[k], f"the images at seq {k} past the re-import"
            assert reimport.requests[before:] == [(m.register_render_queries(k, since=c), True,
                                                   "render")], (
                f"a start at {c}, {caches}, was set aside by the re-import at 4, and cost "
                f"one request")
    # A CACHE AT OR AFTER THE IMPORT IS BROUGHT FORWARD AS ANY IS.
    new_root = m.register_cache_state(again.images_at[4])
    before = len(reimport.requests)
    assert m.register_render_read(reimport, 5, start=(4, new_root)) == again.images_at[5]
    assert reimport.requests[before:] == [(m.register_render_queries(5, since=4), True, "render")]

    # ONLY THE FULL READ'S FAILURE ENDS IN `RenderRefused`: k=3 is before the latest import.
    before = len(reimport.requests)
    with pytest.raises(m.RenderRefused):
        m.register_render_read(reimport, 3, start=(2, old_root))
    assert reimport.requests[before:] == [
        (m.register_render_queries(3, since=2), True, "render"),
        (m.register_render_queries(3), True, "render")], (
        "a refused k, with a start, is two requests and then the refusal")

    # A DEAD CONNECTION IS RAISED AS IT IS, AFTER ONE REQUEST, AND NEVER TRIED TWICE.
    register.raises = m.PsqlFailed("unreachable", "the database did not answer")
    before = len(register.requests)
    with pytest.raises(m.PsqlFailed):
        m.register_render_read(register, last, start=(2, ok_state))
    assert register.requests[before:] == [since(last, 2)], "a dead connection was tried twice"
    register.raises = None

    # THE CACHE'S READ-BACK MISSES ON AN IMAGE IT CANNOT READ BACK: THE ESTATE REPLAYS IN FULL.
    images = journal.images_at[last]
    assert m.register_cache_state(images) == journal.state_at[last]
    for what, bad in (("an empty image", {**images, "lanes/log/empty.md": b""}),
                      ("an image that is not UTF-8", {**images, ALPHA_LOG: b"\xff\xfe\n"}),
                      ("an image that is not bytes", {**images, ALPHA_LOG: "alpha\n"}),
                      ("images that are not a dict", list(images.items()))):
        assert m.register_cache_state(bad) is None, f"register_cache_state took {what}"
