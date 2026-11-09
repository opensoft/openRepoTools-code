# SPDX-License-Identifier: Apache-2.0
"""The register's schema at the engine (#165, L2-N6): AT-MIR's phase-N cases,
AT-VER, AT-LR010, the one-number rule and `register snapshot`'s own output.

WHAT IT CHECKS, by the test plan's entries and lane 2's task T221:

  * AT-MIR (D16): `mirror_state` starts as one empty row; `record_mirror_state`
    records a divergence and a failed pass, keeps the first divergence, and
    never clears one; a malformed sha is 23514; REGISTER-WRITER alone may
    execute it, and no role may UPDATE or DELETE the table; only a
    `stray-import` or `stray-revert` entry clears the divergence. Its gating
    case, "the row never gates alone", is T271's, in phase G.
  * AT-VER (design §1.5): a client outside the version window is refused,
    LR003 at `commit_write` and 69 from `lanes-index`; a migration against an
    older writer snapshot ends 40001 then LR003, or LR003 at once; a second
    bootstrap adds no migration; a migration out of order is LR003; `ready`'s
    check 9 fails a client outside the window. The out-of-window clients are
    copies of `lanes-index` made by T203's `flipped_copy`, as test 14's are,
    with `REGISTER_SCHEMA_VERSION` rewritten in the copy alone.
  * AT-LR010 (lane 1's v2.5): `line_scopes` and `doc_line_scopes` by the scopes
    table's rules, S3's normalized `archive:` key, `entry_new_keys`, and N2's
    `scope_fault` and `scope_checked`, whose LR010 refuses a write or an import
    a line of which derives a key that is not well formed. The five functions
    are called as `lanes_register_owner`, since section 1.4 grants no role
    EXECUTE on them.
  * `test_every_copy_of_register_schema_version_in_a_release_is_one_number`,
    new since v3f (NOTES question 4): design §1.5's hygiene test. It reads
    files, and needs no engine.
  * `test_register_snapshot_prints_its_keys_in_the_contracts_order_and_refuses_with_its_codes`,
    new since v3f (R-F9-3): lane 1's T111 alone, from CLI4.10 and L1v4.10.

REAL ENGINE. Every case but the one-number rule asks for `pg`, one database
cloned from the session's template, so its fixture closure holds `pg_engine`
(T200's rule). The cases assume the template that T227 builds by `lanes-index
bootstrap --no-passwords`; on T205's empty template they fail, since the schema
is not there. Without PostgreSQL 16 they skip with T205's banner.

A REGISTER ON `primary` with the marker `present` is reached as AT-LR006's
fixture reaches it (the test plan at 4610-4615): by the documented functions as
`lanes_register_writer`, `commit_write` with an `import` entry, then with a
`cutover` entry, then `record_marker`. No case runs `lanes-index cutover`.

THE ROLES. The test's own `psql` connects as the fixture's superuser and takes
each role by `SET ROLE`, so a case needs no login of its own except where
`lanes-index` connects: there two logins, made once per session, join the
writer and the reader groups, and connect by the cluster's trust.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from conftest import REPO, git
from sql_register_helpers import LANES_INDEX, flipped_copy

SCHEMA = "lanes_register"
OWNER, WRITER, READER = "lanes_register_owner", "lanes_register_writer", "lanes_register_reader"

#: The logins `lanes-index` connects as in this module's cases. Made once per
#: cluster, members of the writer and the reader groups, with no password.
LOGIN_WRITER, LOGIN_READER = "t221_register_writer", "t221_register_reader"

#: The tables of design §1.2, compared whole where a case says "nothing written".
TABLES = ("schema_version", "migrations", "register_switch", "register_head", "mirror_state",
          "journal", "journal_edits", "journal_files", "journal_scopes", "files", "doc_lines",
          "lanes", "log_lines", "object_holds", "register_lines")

#: What the cases stamp an entry with.
LANE, WS, AUTHOR = "Lane-T221", "ws-t221", "T221 <t221@example.invalid>"
COMMIT_C, TREE_C, MARKER_COMMIT = "c" * 40, "d" * 40, "e" * 40
ARGS_SHA256 = "a" * 64
NOT_AFTER = "2100-01-01T00:00:00Z"            # well past every case (lane 1's v2.3)
STORE_LINE = "primary"
SHA_A, SHA_B = "1" * 40, "2" * 40

#: The configuration's own values, so `c=` and `n_a=` are not the defaults.
CONNECT_TIMEOUT, ADDRESSES = 3, 2

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ERROR_RE = re.compile(r"ERROR:\s+([0-9A-Z]{5}):\s+(.*)")

#: Unicode's 25 White_Space code points (PropList.txt), U+00A0 among them.
WHITE_SPACE = (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0x85, 0xA0, 0x1680,
               *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000)
EM_DASH = "\u2014"
NBSP = "\u00a0"


# ------------------------------------------------------------------ the SQL side
def sql_text(text: str) -> str:
    """`text` as a SQL expression of ASCII alone: quoted runs, and `chr(n)` for
    every character outside printable ASCII, so no client encoding decides it."""
    parts, run = [], []
    for ch in text:
        if 0x20 <= ord(ch) < 0x7F:
            run.append(ch)
            continue
        if run:
            parts.append("'" + "".join(run).replace("'", "''") + "'")
            run = []
        parts.append(f"chr({ord(ch)})")
    if run or not parts:
        parts.append("'" + "".join(run).replace("'", "''") + "'")
    return "(" + " || ".join(parts) + ")"


def psql(db, script: str, role: str = None, appname: str = "t221") -> subprocess.CompletedProcess:
    """One `psql` as the fixture's superuser, with the commit call's settings
    (`VERBOSITY=verbose`, `SHOW_CONTEXT=never`), so a refusal's first stderr
    line is `ERROR:  <SQLSTATE>: <message>`; as `role` where one is named."""
    head = "\\set VERBOSITY verbose\n\\set SHOW_CONTEXT never\nSET client_encoding = 'UTF8';\n"
    if role:
        head += f"SET ROLE {role};\n"
    return subprocess.run([db.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                          input=head + script, capture_output=True, encoding="utf-8",
                          errors="replace", env=db.env(appname=appname), timeout=120,
                          check=False)


def sql(db, script: str, role: str = None) -> str:
    """`psql`, which must succeed; its stdout, stripped."""
    proc = psql(db, script, role)
    assert proc.returncode == 0, (f"psql{' as ' + role if role else ''} exited "
                                  f"{proc.returncode}: {proc.stderr.strip()}\n{script}")
    return proc.stdout.strip()


def error_of(proc: subprocess.CompletedProcess):
    """(SQLSTATE, message) of the first `ERROR:` line on stderr, or (None, None)."""
    m = ERROR_RE.search(proc.stderr or "")
    return (m.group(1), m.group(2).strip()) if m else (None, None)


def refused(proc: subprocess.CompletedProcess, code: str, what: str) -> str:
    """Assert that `proc` ended with `code`, and give the message."""
    got, message = error_of(proc)
    assert proc.returncode != 0 and got == code, (
        f"{what}: expected {code}, got exit {proc.returncode} and {got}: {proc.stderr.strip()}")
    return message


def state(db) -> dict:
    """Every table of design §1.2, each as one sorted JSON array."""
    lines = sql(db, "\n".join(
        f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '[]') "
        f"FROM {SCHEMA}.{table} t;" for table in TABLES)).splitlines()
    assert len(lines) == len(TABLES), lines
    return {table: json.loads(line) for table, line in zip(TABLES, lines)}


def mirror_row(db) -> dict:
    rows = json.loads(sql(db, f"SELECT coalesce(jsonb_agg(to_jsonb(m)), '[]') "
                              f"FROM {SCHEMA}.mirror_state m;"))
    assert len(rows) == 1, f"mirror_state holds {len(rows)} rows, not one: {rows}"
    return rows[0]


def window(db) -> dict:
    return json.loads(sql(db, f"SELECT to_jsonb(v) FROM {SCHEMA}.schema_version v;"))


def generation(db) -> str:
    return sql(db, f"SELECT generation FROM {SCHEMA}.register_switch;")


def head(db) -> int:
    return int(sql(db, f"SELECT seq FROM {SCHEMA}.register_head;"))


def record_mirror_state(db, ws, sha, error, role=WRITER) -> subprocess.CompletedProcess:
    return psql(db, f"SELECT {SCHEMA}.record_mirror_state({sql_text(ws)}, "
                    f"{'NULL' if sha is None else sql_text(sha)}, "
                    f"{'NULL' if error is None else sql_text(error)});", role)


# ------------------------------------------------------------------ the entries
def rendered(lines) -> str:
    """The sha256 of a file of `lines`, LF-ended, as `render_file` renders it."""
    data = "".join(line + "\n" for line in lines).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def line_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entry(kind: str, verb: str, **parts) -> dict:
    """One `commit_write` entry: the journal object, `not_after`, and `parts`."""
    journal = {"kind": kind, "verb": verb, "lane": LANE, "workstation": WS,
               "author": AUTHOR, "message": f"t221: {kind}"}
    journal.update(parts.pop("journal", {}))
    return {"journal": journal, "not_after": NOT_AFTER, **parts}


def import_entry(files: dict, **rows) -> dict:
    """An import of `files` (path to its lines): each created, then its lines
    appended, and each path's digest as it renders."""
    edits, ord_ = [], 0
    for path in sorted(files):
        ord_ += 1
        edits.append({"ord": ord_, "op": "create", "path": path})
        for text in files[path]:
            ord_ += 1
            edits.append({"ord": ord_, "op": "append", "path": path, "new_text": text})
    return entry("import", "import", journal={"git_commit": COMMIT_C, "git_tree": TREE_C},
                 edits=edits,
                 files=[{"path": p, "present": True, "sha256": rendered(files[p]),
                         "final_newline": True} for p in sorted(files)], **rows)


def cutover_entry() -> dict:
    return entry("cutover", "cutover",
                 edits=[{"ord": 1, "op": "create", "path": "lanes/STORE"},
                        {"ord": 2, "op": "append", "path": "lanes/STORE", "new_text": STORE_LINE}],
                 files=[{"path": "lanes/STORE", "present": True,
                         "sha256": rendered([STORE_LINE]), "final_newline": True}])


def commit_call(db, base: int, body: dict, *, write_id: str = None, client: int = None,
                gen: str = None, role: str = WRITER, appname: str = "t221") -> subprocess.CompletedProcess:
    """The commit call as the writer sends it (section 1.3's step 3; AT-LR006's
    fixture): one SERIALIZABLE transaction around `commit_write`."""
    write_id = write_id or str(uuid.uuid4())
    client = window(db)["version"] if client is None else client
    gen = gen or generation(db)
    literal = json.dumps(body, ensure_ascii=True).replace("'", "''")
    return psql(db, f"BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
                    f"SELECT {SCHEMA}.commit_write({base}, '{write_id}'::uuid, {client}, "
                    f"'{gen}'::uuid, '{literal}'::jsonb);\nCOMMIT;\n", role, appname)


def committed(db, base: int, body: dict, what: str) -> int:
    proc = commit_call(db, base, body)
    assert proc.returncode == 0, f"{what}: commit_write refused it: {proc.stderr.strip()}"
    return int(proc.stdout.strip().splitlines()[-1])


DEFAULT_FILES = {"lanes/LANES.md": ["# Lanes"]}


def bring_to_primary(db, files: dict = None, **rows) -> int:
    """AT-LR006's route (TP:4610-4615): as `lanes_register_writer`, an import,
    then a cutover, then `record_marker`. Returns the head, the cutover's seq."""
    imported = committed(db, head(db), import_entry(files or DEFAULT_FILES, **rows), "the import")
    cut = committed(db, imported, cutover_entry(), "the cutover")
    marker = sql(db, f"SELECT {SCHEMA}.record_marker({window(db)['version']}, {cut}, "
                     f"'{MARKER_COMMIT}', '{WS}');", WRITER)
    assert marker == "present", f"record_marker answered {marker!r}, not present"
    switch = json.loads(sql(db, f"SELECT to_jsonb(s) FROM {SCHEMA}.register_switch s;"))
    assert (switch["mode"], switch["marker_state"]) == ("primary", "present"), switch
    return cut


def scopes(db, call: str) -> set:
    """A set-returning scope function's rows, called as the owner."""
    out = sql(db, f"SELECT coalesce(jsonb_agg(s), '[]') FROM {call} AS s;", OWNER)
    return set(json.loads(out))


# ------------------------------------------------------------------ lanes-index
def ensure_logins(db) -> None:
    """The writer's and the reader's login, once per cluster (roles are
    cluster-wide), members of their groups, with no floor and no password."""
    for login, group in ((LOGIN_WRITER, WRITER), (LOGIN_READER, READER)):
        sql(db, f"DO $l$ BEGIN CREATE ROLE {login} LOGIN IN ROLE {group}; "
                f"EXCEPTION WHEN duplicate_object THEN NULL; END $l$;")


def config(tmp_path: Path, db, mode: str = "primary") -> Path:
    """A 0600 `lanes-index.conf` whose register URLs name the session cluster's
    socket, with `connect_timeout=` and `register_addresses=` of its own."""
    ensure_logins(db)
    path = tmp_path / "lanes-index.conf"
    query = f"?connect_timeout={CONNECT_TIMEOUT}"
    path.write_text(f"mode={mode}\n"
                    f"register_url={db.url(LOGIN_WRITER)}{query}\n"
                    f"reader_url={db.url(LOGIN_READER)}{query}\n"
                    f"register_addresses={ADDRESSES}\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def index_env(tmp_path: Path, conf: Path, **extra) -> dict:
    """The environment `lanes-index` runs in: no inherited `PG*`, no
    `LANES_INDEX` (#160's switch, which `tests/conftest.py` sets), this case's
    configuration and state directory."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG") and k != "LANES_INDEX"}
    env.update(LANES_INDEX_CONFIG=str(conf), XDG_STATE_HOME=str(tmp_path / "state"), **extra)
    return env


def run_index(copy: Path, args, env: dict, cwd: Path = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(copy), *args], capture_output=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120,
                          cwd=str(cwd) if cwd else None, check=False)


def flipped(tmp_path: Path, name: str = "bin") -> Path:
    """T203's flipped copy, `RENDER_GIT_HALF = True`, so `mode=primary` loads."""
    return flipped_copy(LANES_INDEX, tmp_path / name, True)


CONSTANT_LINE = re.compile(r"^REGISTER_SCHEMA_VERSION = [0-9]+$", re.M)


def window_copy(tmp_path: Path, number: int) -> Path:
    """A flipped copy whose `REGISTER_SCHEMA_VERSION` is `number`: AT-VER's
    client outside the window (open point 3), in the copy alone."""
    copy = flipped(tmp_path, f"client-{number}")
    text = copy.read_text(encoding="utf-8")
    assert len(CONSTANT_LINE.findall(text)) == 1, (
        f"{LANES_INDEX} holds no single `REGISTER_SCHEMA_VERSION = <n>` line to rewrite")
    copy.write_text(CONSTANT_LINE.sub(f"REGISTER_SCHEMA_VERSION = {number}", text),
                    encoding="utf-8")
    return copy


def shown(proc: subprocess.CompletedProcess) -> str:
    return (f"exit {proc.returncode}\n--- stdout ---\n{proc.stdout[-3000:]}"
            f"\n--- stderr ---\n{proc.stderr[-3000:]}")


def names_both(text: str, a: int, b: int) -> bool:
    return bool(re.search(rf"\b{a}\b", text)) and bool(re.search(rf"\b{b}\b", text))


# =================================================================== AT-MIR
def test_mirror_state_starts_as_one_empty_row(pg):
    """After the bootstrap, exactly one row, every column but `id` NULL."""
    row = mirror_row(pg)
    assert row.pop("id") == 1, row
    assert row and all(value is None for value in row.values()), (
        f"a bootstrapped mirror_state row has a value set: {row}")


def test_record_mirror_state_records_a_divergence_and_a_failed_pass(pg):
    """`record_mirror_state(ws, <40-hex sha>, NULL)` sets `diverged_sha`,
    `found_utc` and `found_by_ws`; `(ws, NULL, '<error>')` sets `last_error` and
    `last_error_utc`."""
    proc = record_mirror_state(pg, "ws-a", SHA_A, None)
    assert proc.returncode == 0, proc.stderr
    row = mirror_row(pg)
    assert (row["diverged_sha"], row["found_by_ws"]) == (SHA_A, "ws-a"), row
    assert row["found_utc"] is not None, row
    assert row["last_error"] is None and row["last_error_utc"] is None, row
    proc = record_mirror_state(pg, "ws-b", None, "the push was refused")
    assert proc.returncode == 0, proc.stderr
    row = mirror_row(pg)
    assert row["last_error"] == "the push was refused" and row["last_error_utc"] is not None, row


def test_a_failed_pass_record_leaves_the_divergence_as_it_was(pg):
    """A failed pass's record, and a clean pass's after it, leave the
    divergence as it was: only the single-write import and the revert clear
    it (D16)."""
    assert record_mirror_state(pg, "ws-a", SHA_A, None).returncode == 0
    before = mirror_row(pg)
    assert record_mirror_state(pg, "ws-b", None, "render failed").returncode == 0
    after = mirror_row(pg)
    for key in ("diverged_sha", "found_utc", "found_by_ws"):
        assert after[key] == before[key], f"a failed pass's record changed {key}: {after}"
    assert after["last_error"] == "render failed", after
    assert record_mirror_state(pg, "ws-c", None, None).returncode == 0
    clean = mirror_row(pg)
    for key in ("diverged_sha", "found_utc", "found_by_ws"):
        assert clean[key] == before[key], f"a clean pass's record changed {key}: {clean}"
    assert clean["last_error"] is None and clean["last_error_utc"] is None, clean


def test_a_second_divergence_report_keeps_the_first(pg):
    """A second call with another sha leaves the first divergence as it was:
    the function keeps the first one found (section 1.3)."""
    assert record_mirror_state(pg, "ws-a", SHA_A, None).returncode == 0
    first = mirror_row(pg)
    time.sleep(1.1)                               # found_utc is whole seconds
    assert record_mirror_state(pg, "ws-b", SHA_B, None).returncode == 0
    second = mirror_row(pg)
    assert (second["diverged_sha"], second["found_utc"], second["found_by_ws"]) == (
        first["diverged_sha"], first["found_utc"], first["found_by_ws"]), (first, second)


def test_mirror_state_refuses_a_malformed_sha(pg):
    """A sha that is not 40 lower-case hex digits fails with 23514, and the
    row is unchanged."""
    before = mirror_row(pg)
    for bad in ("1" * 39, "1" * 41, "A" * 40, "g" * 40, "", " " + "1" * 39):
        proc = record_mirror_state(pg, "ws-a", bad, None)
        refused(proc, "23514", f"record_mirror_state with the sha {bad!r}")
        assert mirror_row(pg) == before, f"the sha {bad!r} changed the row"


def test_only_register_writer_executes_record_mirror_state_and_none_updates_the_table(pg):
    """READER's call fails with 42501. REGISTER-WRITER's direct `UPDATE` or
    `DELETE` of `mirror_state`, inside `BEGIN READ WRITE`, fails with 42501
    (section 1.4: SELECT on the tables, EXECUTE on the functions). The
    writer's own call, the control, commits."""
    before = mirror_row(pg)
    refused(record_mirror_state(pg, "ws-r", SHA_A, None, role=READER), "42501",
            "READER's call of record_mirror_state")
    for statement in (f"UPDATE {SCHEMA}.mirror_state SET last_error = 'x' WHERE id = 1;",
                      f"DELETE FROM {SCHEMA}.mirror_state WHERE id = 1;"):
        refused(psql(pg, f"BEGIN READ WRITE;\n{statement}\nCOMMIT;\n", WRITER), "42501",
                f"REGISTER-WRITER's {statement.split()[0]}")
    assert mirror_row(pg) == before
    assert record_mirror_state(pg, "ws-w", SHA_A, None).returncode == 0
    assert mirror_row(pg)["diverged_sha"] == SHA_A


@pytest.mark.parametrize("kind", ["import", "revert"])
def test_a_stray_import_or_revert_clears_the_divergence(pg, kind):
    """A `stray-import` entry, and in a second case a `stray-revert` entry,
    through `commit_write`, leaves `diverged_sha` and `found_utc` NULL. The
    revert is an empty journal entry (D16)."""
    n = bring_to_primary(pg)
    assert record_mirror_state(pg, "ws-a", SHA_A, None).returncode == 0
    assert mirror_row(pg)["diverged_sha"] == SHA_A
    if kind == "import":
        lines = DEFAULT_FILES["lanes/LANES.md"] + ["a stray line"]
        body = entry("stray-import", "import --single", journal={"git_commit": SHA_B},
                     edits=[{"ord": 1, "op": "append", "path": "lanes/LANES.md",
                             "new_text": lines[-1]}],
                     files=[{"path": "lanes/LANES.md", "present": True,
                             "sha256": rendered(lines), "final_newline": True}])
    else:
        body = entry("stray-revert", "render --revert", journal={"git_commit": SHA_B})
    assert committed(pg, n, body, f"the stray-{kind} entry") == n + 1
    row = mirror_row(pg)
    assert row["diverged_sha"] is None and row["found_utc"] is None, row
    assert row["found_by_ws"] is None, row


# =================================================================== AT-VER
@pytest.mark.parametrize("case", ["writer-old", "writer-new", "reader-old", "reader-new"])
def test_a_client_outside_the_version_window_is_refused_lr003(pg, tmp_path, case):
    """A writer below `writers_from`, or above `version`, gets LR003 from
    `commit_write`, naming both numbers, with nothing written, and its
    `lanes-index` exits 69 naming both numbers and the remedy. A reader outside
    `readers_from` to `version` exits 69 with nothing on stdout. The copies'
    constant is one below the floor or one above `version` (open point 3)."""
    role, side = case.split("-")
    win = window(pg)
    floor = win["writers_from" if role == "writer" else "readers_from"]
    number = floor - 1 if side == "old" else win["version"] + 1
    remedy = "upgrade the tools" if side == "old" else "run the bootstrap"
    before = state(pg)
    copy = window_copy(tmp_path, number)
    env = index_env(tmp_path, config(tmp_path, pg))
    if role == "writer":
        lines = DEFAULT_FILES["lanes/LANES.md"]
        message = refused(commit_call(pg, head(pg), import_entry({"lanes/LANES.md": lines}),
                                      client=number), "LR003", f"a writer at {number}")
        assert names_both(message, win["version"], number), message
        proc = run_index(copy, ["register", "snapshot", "--write-id", "new", "--lane", LANE,
                                "--verb", "log", "--args-sha256", ARGS_SHA256], env)
    else:
        (tmp_path / "cache").mkdir()
        proc = run_index(copy, ["register", "read", "--prefetch", "--cache",
                                str(tmp_path / "cache" / "register"), "--files", "register"],
                         env)
    assert proc.returncode == 69, f"a {role} at {number}:\n{shown(proc)}"
    assert names_both(proc.stderr, win["version"] if side == "new" else floor, number), shown(proc)
    assert remedy in proc.stderr, f"the refusal names no remedy ({remedy!r}):\n{shown(proc)}"
    assert proc.stdout == "", f"a refused {role} printed:\n{shown(proc)}"
    assert state(pg) == before, f"a {role} outside the window changed the register"


def migration_script(number: int, commit: bool = True) -> str:
    """A migration as section 1.5's step 3 gives it, sent by the admin as the
    bootstrap sends a script: one transaction that touches the head row,
    checks that `version` is one below its own (else LR003), adds a table,
    raises `version` and the floors, and records its `migrations` row."""
    body = (f"BEGIN;\nSET LOCAL ROLE {OWNER};\nSET LOCAL search_path TO {SCHEMA}, pg_catalog;\n"
            f"SET LOCAL lock_timeout = '2000ms';\n"
            f"UPDATE register_head SET seq = seq WHERE id = 1;\n"
            f"DO $m$ BEGIN IF (SELECT version FROM schema_version WHERE id = 1) <> {number - 1} "
            f"THEN RAISE EXCEPTION 'migration {number} needs schema version {number - 1}, not %', "
            f"(SELECT version FROM schema_version WHERE id = 1) USING ERRCODE = 'LR003'; "
            f"END IF; END $m$;\n"
            f"CREATE TABLE t221_migration_{number} (id integer);\n"
            f"UPDATE schema_version SET version = {number}, writers_from = {number}, "
            f"readers_from = {number}, applied_utc = date_trunc('second', clock_timestamp()) "
            f"WHERE id = 1;\n"
            f"INSERT INTO migrations (version, script_sha256, by_lane, by_ws) "
            f"VALUES ({number}, '{'f' * 64}', '{LANE}', '{WS}');\n")
    return body + ("COMMIT;\n" if commit else "")


def wait_for(db, appname: str, condition: str, what: str, ceiling: float = 5.0) -> None:
    """Poll `pg_stat_activity` for `appname`'s backend, in 0.05 s steps under
    `ceiling`, until `condition` holds. No sleep stands in for a barrier."""
    end = time.monotonic() + ceiling
    while time.monotonic() < end:
        if sql(db, f"SELECT count(*) FROM pg_stat_activity a WHERE a.application_name = "
                   f"'{appname}' AND a.datname = current_database() AND ({condition});") != "0":
            return
        time.sleep(0.05)
    pytest.fail(f"{what}: not seen in pg_stat_activity within {ceiling} s")


def session(db, appname: str) -> subprocess.Popen:
    return subprocess.Popen([db.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                            env=db.env(appname=appname))


def a_write(db) -> dict:
    lines = DEFAULT_FILES["lanes/LANES.md"] + ["a written line"]
    return entry("write", "log", journal={"args_sha256": ARGS_SHA256},
                 edits=[{"ord": 1, "op": "append", "path": "lanes/LANES.md",
                         "new_text": lines[-1]}],
                 files=[{"path": "lanes/LANES.md", "present": True, "sha256": rendered(lines),
                         "final_newline": True}])


@pytest.mark.parametrize("case", ["held-40001", "in-turn-lr003"])
def test_a_migration_against_an_older_snapshot_ends_69(pg, tmp_path, case):
    """Held: the migration's transaction holds the head row uncommitted, the
    writer's commit call is seen waiting on it, and the migration commits:
    40001, then the re-read meets the new window, LR003, so 69. In turn: the
    migration commits before the commit call starts; the head's seq is
    unchanged, so there is no LR001, and step 2 raises LR003. Either way the
    shipped client's next snapshot exits 69 naming both numbers."""
    n = bring_to_primary(pg)
    win, gen = window(pg), generation(pg)
    client, number = win["version"], win["version"] + 1
    body = a_write(pg)
    if case == "held-40001":
        migration = session(pg, "t221-migration")
        migration.stdin.write("\\set VERBOSITY verbose\n" + migration_script(number, commit=False))
        migration.stdin.flush()
        wait_for(pg, "t221-migration", "a.state = 'idle in transaction'", "the migration held")
        writer = session(pg, "t221-commit")
        writer.stdin.write("\\set VERBOSITY verbose\n\\set SHOW_CONTEXT never\n"
                           f"SET ROLE {WRITER};\nBEGIN ISOLATION LEVEL SERIALIZABLE;\n"
                           f"SELECT {SCHEMA}.commit_write({n}, '{uuid.uuid4()}'::uuid, {client}, "
                           f"'{gen}'::uuid, '{json.dumps(body).replace(chr(39), chr(39) * 2)}'"
                           f"::jsonb);\nCOMMIT;\n")
        writer.stdin.close()
        wait_for(pg, "t221-commit", "a.wait_event_type = 'Lock' AND cardinality("
                 "pg_blocking_pids(a.pid)) > 0", "the commit call waiting on the head row")
        _, err = migration.communicate("COMMIT;\n", timeout=60)
        assert migration.returncode == 0, f"the migration failed: {err}"
        out, err = writer.communicate(timeout=60)
        code, _ = error_of(subprocess.CompletedProcess([], writer.returncode, out, err))
        assert writer.returncode != 0 and code == "40001", (
            f"the held commit call ended {writer.returncode}, {code}: {err}")
    else:
        assert psql(pg, migration_script(number)).returncode == 0
    assert window(pg)["version"] == number
    message = refused(commit_call(pg, n, body, client=client), "LR003",
                      "the commit call after the migration")
    assert names_both(message, number, client), message
    assert head(pg) == n, "a commit call that met LR003 moved the head"
    proc = run_index(flipped(tmp_path), ["register", "snapshot", "--write-id", "new", "--lane",
                                         LANE, "--verb", "log", "--args-sha256", ARGS_SHA256],
                     index_env(tmp_path, config(tmp_path, pg)))
    assert proc.returncode == 69 and names_both(proc.stderr, number, client), shown(proc)


def admin_env(tmp_path: Path, db) -> dict:
    """The bootstrap's environment: its admin service in `$HOME/.pg_service.conf`,
    naming this case's database, since `lanes-index` drops every inherited
    `PG*` variable before it sets `PGSERVICE` (ops:404), and no configuration
    file, which the bootstrap does not need."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / ".pg_service.conf").write_text(
        f"[t221_admin]\nhost={db.host}\nport={db.port}\ndbname={db.name}\nuser=lanes_test\n",
        encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PG") and k not in ("LANES_INDEX", "LANES_INDEX_CONFIG")}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_STATE_HOME=str(tmp_path / "state"), LANES_WORKSTATION=WS)
    return env


def test_a_second_bootstrap_at_the_same_version_adds_no_migration(pg, tmp_path):
    """`bootstrap` run again at the same version prints `unchanged` and adds no
    `migrations` row. Each `migrations` row carries its script's sha256,
    `by_lane` and `by_ws`."""
    before = json.loads(sql(pg, f"SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY m.version), "
                                f"'[]') FROM {SCHEMA}.migrations m;"))
    assert before, "a bootstrapped register has no migrations row"
    for row in before:
        assert re.fullmatch(r"[0-9a-f]{64}", row["script_sha256"]), row
        assert row["by_lane"] and row["by_ws"], row
    proc = run_index(LANES_INDEX, ["bootstrap", "--admin-service", "t221_admin", "--label",
                                   "t221", "--repository", "opensoft/t221", "--lane", LANE,
                                   "--no-passwords"], admin_env(tmp_path, pg))
    assert proc.returncode == 0, shown(proc)
    assert re.search(rf"^schema {SCHEMA}: unchanged\b", proc.stdout, re.M), shown(proc)
    assert not re.search(r"^migration [0-9]+: created", proc.stdout, re.M), shown(proc)
    after = json.loads(sql(pg, f"SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY m.version), "
                               f"'[]') FROM {SCHEMA}.migrations m;"))
    assert after == before, f"a second bootstrap changed migrations: {before} -> {after}"


def test_a_migration_out_of_order_is_refused_lr003(pg):
    """A migration whose number is not one above `version` fails with LR003
    and changes nothing."""
    before = state(pg)
    number = window(pg)["version"] + 2
    refused(psql(pg, migration_script(number)), "LR003", f"migration {number}")
    assert state(pg) == before, "a migration out of order changed the register"
    assert sql(pg, f"SELECT to_regclass('{SCHEMA}.t221_migration_{number}') IS NULL;") == "t"


def test_ready_fails_a_client_outside_the_version_window(pg, tmp_path):
    """`ready`'s check 9 (operations §2.4; lane 3's ruling 6578020193) fails a
    client outside the window, naming both numbers; the shipped client's
    check 9 does not fail."""
    conf = config(tmp_path, pg, mode="index")
    env = index_env(tmp_path, conf, LANES_WORKSTATION=WS)
    args = ["ready", "--expect", "index", "--release", "0.0.0", "--env", "t221"]
    win = window(pg)
    number = win["version"] + 1

    def schema_fails(proc):
        return [line for line in proc.stdout.splitlines() if "FAIL" in line and re.search(
            r"REGISTER_SCHEMA_VERSION|schema_version|this client is|register schema [0-9]", line)]

    inside = run_index(flipped(tmp_path), args, env)
    assert not schema_fails(inside), f"the shipped client fails check 9:\n{shown(inside)}"
    outside = run_index(window_copy(tmp_path, number), args, env)
    assert outside.returncode == 2, shown(outside)
    fails = schema_fails(outside)
    assert fails and any(names_both(line, win["version"], number) for line in fails), (
        f"check 9 does not fail naming {win['version']} and {number}:\n{shown(outside)}")


# =================================================================== AT-LR010
UUID_U = "0f8fad5b-d9cb-469f-a165-70867728950e"

#: Each `line_scopes` rule: (path, line, the scopes as a set), compared as sets.
LINE_SCOPES = {
    "row": [("lanes/LANES.md", f"| `Lane-A` | {UUID_U} | x |", {"row:lane-a", f"sid:{UUID_U}"}),
            ("lanes/LANES.md", f" | `Lane-A` | {UUID_U} |", set()),
            ("lanes/LANES.md", "| Lane-A | x |", set()),
            ("lanes/LANES.md", "| `` | x |", set())],
    "archive": [("lanes/archive/a.md", "| `foo-3` | x |", {"archive:foo-3"}),
                ("lanes/archive/a.md", "| `alpha` | x |", {"archive:alpha"}),
                ("lanes/archive/a.md", "| `foo-x3` | x |", {"archive:foo-x3"})],
    "archive-normalized": [
        ("lanes/archive/a.md", "| `foo-03` | x |", {"archive:foo-03", "archive:foo-3"}),
        ("lanes/archive/a.md", "| `Foo-3b` | x |", {"archive:foo-3b", "archive:foo-3"}),
        ("lanes/archive/a.md", "| `foo-033` | x |", {"archive:foo-033", "archive:foo-33"}),
        ("lanes/archive/a.md", "| `foo-00` | x |", {"archive:foo-00", "archive:foo-0"})],
    "long-digit-run": [
        ("lanes/archive/a.md", "| `foo-09007199254740993` | x |",
         {"archive:foo-09007199254740993", "archive:foo-9007199254740993"}),
        ("lanes/archive/a.md", "| `foo-0" + "123456789" * 3 + "12` | x |",
         {"archive:foo-0" + "123456789" * 3 + "12", "archive:foo-" + "123456789" * 3 + "12"})],
    "bind": [("lanes/log/Lane-B.md", f"{pad}{verb}{pad2}{EM_DASH} {UUID_U} on ws-b",
              {"bind:lane-b", f"sid:{UUID_U}"})
             for verb, pad, pad2 in (("STARTED", "", " "), ("RESUMED", " ", " "),
                                     ("PAUSED", "\t", "\t "), ("ENDED", "", "  "),
                                     ("RETIRED", " \t", " \t "), ("RENAMED", "", "\t "))],
    "bind-unreadable": [("lanes/log/Lane-B.md", f"PAUSED {EM_DASH} ???", {"bind:lane-b"})],
    "not-lane-kind": [("lanes/log/Lane-B.md", f"CLAIMED {EM_DASH} {UUID_U} o1", set()),
                      ("lanes/log/Lane-B.md", f"HANDOFF-REQUESTED {EM_DASH} {UUID_U}", set())],
    "alias": [("lanes/aliases.tsv", "X\tO\t2026-11-09T10:00:00Z", {"alias:x", "alias:o"})],
    "alias-comment": [("lanes/aliases.tsv", "# X\tO\t2026-11-09T10:00:00Z", set()),
                      ("lanes/aliases.tsv", "  \t O\t2026-11-09T10:00:00Z", {"alias:o"}),
                      ("lanes/aliases.tsv", " \t \t2026-11-09T10:00:00Z", set())],
    "store": [("lanes/STORE", "primary", set()), ("lanes/STORE", f"| `Lane-A` | {UUID_U} |", set())],
}


@pytest.mark.parametrize("case", list(LINE_SCOPES))
def test_line_scopes_derives_each_scope_by_its_rule(pg, case):
    """`line_scopes(path, text)`, one case per rule of the scopes table,
    compared as sets. A long digit run keys with no digit lost and no exponent;
    `RETIRED_ROWS_AWK`'s float key under mawk is lane 4's, and not asserted."""
    for path, text, want in LINE_SCOPES[case]:
        got = scopes(pg, f"{SCHEMA}.line_scopes({sql_text(path)}, {sql_text(text)})")
        assert got == want, f"line_scopes({path!r}, {text!r}) is {got}, not {want}"


#: `doc_line_scopes`' rows: an import of these lines and their structured rows.
DOC_LOG = "lanes/log/Lane-B.md"
DOC_FILES = {
    "lanes/LANES.md": ["# Lanes", "HOLD opensoft/r9 by Lane-D",
                       "LANDING EXPIRED opensoft/r9 #7 for lane Lane-D by Lane-E"],
    DOC_LOG: [f"CLAIMED {EM_DASH} opensoft/r9#12", "?? not a line",
              f"CLAIMED {EM_DASH} lane:Lane-C"],
}


def doc_rows() -> dict:
    log = [{"path": DOC_LOG, "line_no": 1, "raw": DOC_FILES[DOC_LOG][0], "lane": "Lane-B",
            "verb": "CLAIMED", "object": "opensoft/r9#12", "unreadable": False},
           {"path": DOC_LOG, "line_no": 2, "raw": DOC_FILES[DOC_LOG][1], "lane": "Lane-B",
            "verb": None, "object": "opensoft/r9#13", "unreadable": True,
            "unreadable_why": "no verb"},
           {"path": DOC_LOG, "line_no": 3, "raw": DOC_FILES[DOC_LOG][2], "lane": "Lane-B",
            "verb": "CLAIMED", "object": "lane:Lane-C", "unreadable": False}]
    lanes_md = DOC_FILES["lanes/LANES.md"]
    register = [{"path": "lanes/LANES.md", "line_no": 2, "raw": lanes_md[1], "kind": "HOLD",
                 "slot_role": "take", "slot_kind": "hold", "lane": "Lane-D",
                 "repo": "opensoft/r9", "repo_key": "opensoft/r9"},
                {"path": "lanes/LANES.md", "line_no": 3, "raw": lanes_md[2],
                 "kind": "LANDING EXPIRED", "slot_role": "close", "slot_kind": "landing",
                 "lane": "Lane-E", "repo": "opensoft/r9", "repo_key": "opensoft/r9", "pr": 7,
                 "for_lane": "Lane-D"}]
    return {"log_lines": log, "register_lines": register}


DOC_CASES = {"log-line": (DOC_LOG, 1, {"objects:lane-b"}),
             "unreadable": (DOC_LOG, 2, set()),
             "lane-object": (DOC_LOG, 3, set()),
             "slot-line": ("lanes/LANES.md", 2, {"objects:lane-d"}),
             "landing-expired": ("lanes/LANES.md", 3, {"objects:lane-e", "objects:lane-d"})}


@pytest.mark.parametrize("case", list(DOC_CASES))
def test_doc_line_scopes_adds_objects_from_the_structured_rows(pg, case):
    """`doc_line_scopes` adds `objects:` from a line's structured row: a
    readable `log_lines` row on an object that is not `lane:...` gives its lane,
    lower-cased; an unreadable one, or one on `lane:<x>`, gives none; a slot
    line gives its lane, and a `LANDING EXPIRED` also its `for_lane`. The lines
    are stored by an import, at `files`."""
    committed(pg, head(pg), import_entry(DOC_FILES, **doc_rows()), "the import")
    path, line_no, want = DOC_CASES[case]
    line_id = sql(pg, f"SELECT line_id FROM {SCHEMA}.doc_lines WHERE path = {sql_text(path)} "
                      f"AND line_no = {line_no};")
    assert line_id, f"{path} line {line_no} is not stored"
    got = scopes(pg, f"{SCHEMA}.doc_line_scopes({line_id}, {sql_text(path)})")
    assert got == want, f"doc_line_scopes of {path} line {line_no} is {got}, not {want}"


def test_entry_new_keys_reads_the_new_side_and_every_holder(pg):
    """`entry_new_keys(seq)` for a write's seq: each appended or replaced line's
    keys, with its path and `line_no`; each line a rename moved, at its new
    path; and `objects:` with `lower(lane_key)` for every holder of an object
    the write wrote a hold for, at that holder's file and ordinal (N1)."""
    held = f"CLAIMED {EM_DASH} o1"
    n = bring_to_primary(
        pg, {"lanes/LANES.md": ["# Lanes", "| `Lane-A` | x |"],
             "lanes/log/Lane-A.md": [held], "lanes/log/Old.md": [f"STARTED {EM_DASH} s"]},
        log_lines=[{"path": "lanes/log/Lane-A.md", "line_no": 1, "raw": held, "lane": "Lane-A",
                    "verb": "CLAIMED", "object": "o1", "unreadable": False}],
        object_holds=[{"object": "o1", "lane_key": "lane-a", "lane": "Lane-A",
                       "verb": "CLAIMED", "file": "lanes/log/Lane-A.md", "ordinal": 1}])
    opened = f"OPENED {EM_DASH} o1"
    lanes_md = ["# Lanes", "| `Lane-A2` | x |", "| `Lane-B` | y |"]
    body = entry(
        "write", "claim", journal={"args_sha256": ARGS_SHA256},
        edits=[{"ord": 1, "op": "replace", "path": "lanes/LANES.md", "line_no": 2,
                "old_sha256": line_sha("| `Lane-A` | x |"), "new_text": lanes_md[1]},
               {"ord": 2, "op": "append", "path": "lanes/LANES.md", "new_text": lanes_md[2]},
               {"ord": 3, "op": "create", "path": "lanes/log/Lane-B.md"},
               {"ord": 4, "op": "append", "path": "lanes/log/Lane-B.md", "new_text": opened},
               {"ord": 5, "op": "rename", "path": "lanes/log/Old.md",
                "to_path": "lanes/log/Lane-R.md"}],
        files=[{"path": "lanes/LANES.md", "present": True, "sha256": rendered(lanes_md),
                "final_newline": True},
               {"path": "lanes/log/Lane-B.md", "present": True, "sha256": rendered([opened]),
                "final_newline": True},
               {"path": "lanes/log/Lane-R.md", "present": True,
                "sha256": rendered([f"STARTED {EM_DASH} s"]), "final_newline": True},
               {"path": "lanes/log/Old.md", "present": False}],
        log_lines=[{"path": "lanes/log/Lane-B.md", "line_no": 1, "raw": opened, "lane": "Lane-B",
                    "verb": "OPENED", "workstation": WS, "utc": "2026-11-09T10:00:00Z",
                    "utc_ts": "2026-11-09T10:00:00Z", "object": "o1", "unreadable": False}],
        object_holds=[{"object": "o1", "lane_key": "lane-b", "lane": "Lane-B", "verb": "OPENED",
                       "utc_ts": "2026-11-09T10:00:00Z", "file": "lanes/log/Lane-B.md",
                       "ordinal": 1}])
    seq = committed(pg, n, body, "the write")
    rows = json.loads(sql(pg, f"SELECT coalesce(jsonb_agg(jsonb_build_array(k.path, k.line_no, "
                              f"k.scope)), '[]') FROM {SCHEMA}.entry_new_keys({seq}) AS k;", OWNER))
    got = {tuple(row) for row in rows}
    want = {("lanes/LANES.md", 2, "row:lane-a2"), ("lanes/LANES.md", 3, "row:lane-b"),
            ("lanes/log/Lane-R.md", 1, "bind:lane-r"),
            ("lanes/log/Lane-B.md", 1, "objects:lane-b"),
            ("lanes/log/Lane-A.md", 1, "objects:lane-a")}
    assert got == want, f"entry_new_keys({seq}) is {sorted(got)}, not {sorted(want)}"


FAULT_CASES = {f"U+{cp:04X}": (f"row:x{chr(cp)}y", f"row:x[U+{cp:04X}]y") for cp in WHITE_SPACE}
FAULT_CASES.update({"row-no-name": ("row:", "row:"), "row-upper-case": ("row:X", "row:X")})


@pytest.mark.parametrize("case", list(FAULT_CASES))
def test_scope_fault_shows_each_white_space_character(pg, case):
    """`scope_fault` is NULL for a well-formed key, and otherwise the key with
    each white-space character shown as `[U+hhhh]`: each of Unicode's 25
    White_Space code points, U+00A0 among them. `row:`, with no name, and
    `row:X`, in upper case, are returned as they are."""
    key, want = FAULT_CASES[case]
    assert len(WHITE_SPACE) == 25
    got = sql(pg, f"SELECT coalesce({SCHEMA}.scope_fault({sql_text(key)}), '<NULL>');", OWNER)
    assert got == want, f"scope_fault({key!r}) is {got!r}, not {want!r}"
    for good in ("row:xy", "archive:foo-3", "bind:lane-b", "objects:lane-b", "alias:x",
                 f"sid:{UUID_U}"):
        assert sql(pg, f"SELECT {SCHEMA}.scope_fault({sql_text(good)}) IS NULL;", OWNER) == "t", good


def test_scope_checked_raises_lr010_naming_the_path_the_line_and_the_key(pg):
    """`scope_checked(path, line, key)` returns a well-formed key as it is,
    and otherwise raises LR010 with `key: <path> line <n> derives <shown>, which
    is not a scope (...)`."""
    assert sql(pg, f"SELECT {SCHEMA}.scope_checked('lanes/LANES.md', 7, 'row:lane-a');",
               OWNER) == "row:lane-a"
    message = refused(psql(pg, f"SELECT {SCHEMA}.scope_checked('lanes/LANES.md', 7, "
                               f"{sql_text('row:x' + NBSP + 'y')});", OWNER),
                      "LR010", "scope_checked of row:x<U+00A0>y")
    assert message == ("key: lanes/LANES.md line 7 derives row:x[U+00A0]y, which is not a scope "
                       "(a scope's name is lower case, not empty, and holds no white space)"), message


def test_the_journal_scopes_check_takes_a_no_break_space(pg):
    """The CHECK is a backstop only: as the owner, in transactions the test
    rolls back, a `journal_scopes` row `row:x y` fails with 23514 on
    `journal_scopes_scope_check`, but the same key with U+00A0 is stored, since
    `[:space:]` under `COLLATE "C"` is ASCII's alone. Only `scope_checked`
    stops it."""
    seed = (f"BEGIN;\nINSERT INTO {SCHEMA}.journal (seq, write_id, kind, verb, lane, workstation, "
            f"author, message, args_sha256) VALUES (0, '{uuid.uuid4()}', 'write', 'log', "
            f"'{LANE}', '{WS}', '{AUTHOR}', 'seed', '{ARGS_SHA256}');\n")
    proc = psql(pg, seed + f"INSERT INTO {SCHEMA}.journal_scopes (seq, scope) VALUES "
                           f"(0, 'row:x y');\nROLLBACK;\n", OWNER)
    refused(proc, "23514", "a journal_scopes row row:x y")
    assert "journal_scopes_scope_check" in proc.stderr, proc.stderr
    out = sql(pg, seed + f"INSERT INTO {SCHEMA}.journal_scopes (seq, scope) VALUES "
                         f"(0, {sql_text('row:x' + NBSP + 'y')});\n"
                         f"SELECT count(*) FROM {SCHEMA}.journal_scopes WHERE seq = 0;\n"
                         f"ROLLBACK;\n", OWNER)
    assert out == "1", f"the no-break space's row was not stored: {out!r}"
    assert sql(pg, f"SELECT count(*) FROM {SCHEMA}.journal;") == "0"


def test_a_write_that_deletes_a_line_with_a_bad_key_is_refused_lr010(pg):
    """At a write's old side: a stored line that derives such a key, put in
    place by the admin as the owner, since no write or import can store one,
    and a direct call whose entry deletes it: LR010 from step 5a, naming that
    path and line, and nothing written."""
    n = bring_to_primary(pg)
    bad = "| `x y` | x |"
    sql(pg, f"INSERT INTO {SCHEMA}.doc_lines (path, line_no, text, written_seq, written_mode) "
            f"VALUES ('lanes/LANES.md', 2, {sql_text(bad)}, {n - 1}, 'files');", OWNER)
    before = state(pg)
    lines = DEFAULT_FILES["lanes/LANES.md"]
    body = entry("write", "log", journal={"args_sha256": ARGS_SHA256},
                 edits=[{"ord": 1, "op": "delete", "path": "lanes/LANES.md", "line_no": 2,
                         "old_sha256": line_sha(bad)}],
                 files=[{"path": "lanes/LANES.md", "present": True, "sha256": rendered(lines),
                         "final_newline": True}])
    message = refused(commit_call(pg, n, body), "LR010", "a write deleting a bad key's line")
    assert message.startswith("key: lanes/LANES.md line 2 derives row:x[U+0020]y,"), message
    assert state(pg) == before, "a write refused LR010 changed the register"


IMPORT_CASES = {"space": (["| `x y` | x |"], "row:x[U+0020]y", 2),
                "no-break-space": ([f"| `x{NBSP}y` | x |"], "row:x[U+00A0]y", 2),
                "two-lines": (["| `x y` | x |", "| `p q` | x |"], "row:x[U+0020]y", 2)}


def workspace_at(tmp_path: Path, bad_lines) -> tuple:
    """A files-mode workspace repository whose commit C, on a bare origin,
    holds `lanes/LANES.md` with `bad_lines` after its heading."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    files = {"lanes/LANES.md": ["# Lanes", *bad_lines], "lanes/repos.tsv": ["r9\topensoft/r9"],
             "lanes/log/README.md": ["# Logs"], "lanes/aliases.tsv": []}
    for rel, lines in files.items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes("".join(line + "\n" for line in lines).encode("utf-8"))
    git("add", "lanes", cwd=work)
    git("-c", "user.name=T221", "-c", "user.email=t221@example.invalid", "commit", "-q", "-m",
        "C", cwd=work)
    git("remote", "add", "origin", str(origin), cwd=work)
    git("push", "-q", "origin", "main", cwd=work)
    git("fetch", "-q", "origin", cwd=work)
    return work, git("rev-parse", "HEAD", cwd=work).stdout.strip()


@pytest.mark.parametrize("case", list(IMPORT_CASES))
def test_an_import_whose_line_derives_a_bad_key_is_refused_lr010_and_writes_nothing(
        pg, tmp_path, case):
    """At an import: a commit whose `lanes/LANES.md` holds the row-shaped line
    ``| `x y` |``: `lanes-index import --at <C>` exits 2 naming
    `lanes/LANES.md`, that line's number and the key, and the head, the journal
    and every table of §1.2 equal their values before. With two such lines,
    the message names the first in path and line order. The same with U+00A0."""
    bad_lines, shown_key, line_no = IMPORT_CASES[case]
    work, commit = workspace_at(tmp_path, bad_lines)
    env = index_env(tmp_path, config(tmp_path, pg, mode="index"), LANES_REPO=str(work),
                    LANES_WORKSTATION=WS)
    before = state(pg)
    proc = run_index(LANES_INDEX, ["import", "--at", commit], env, cwd=work)
    assert proc.returncode == 2, shown(proc)
    assert "lanes/LANES.md" in proc.stderr and f"line {line_no}" in proc.stderr, shown(proc)
    assert shown_key in proc.stderr, shown(proc)
    if case == "two-lines":
        assert "row:p[U+0020]q" not in proc.stderr and "line 3" not in proc.stderr, shown(proc)
    assert state(pg) == before, "an import refused LR010 changed the register"


# =================================================================== the one number
FORCE_INCLUDE = "[tool.hatch.build.targets.wheel.force-include]"
PAYLOAD_ENTRY = re.compile(r'^"([^"]+)"\s*=\s*"openrepotools/payload/', re.M)
CONSTANT = re.compile(r"^[ \t]*(?:export[ \t]+|readonly[ \t]+|declare[ \t]+-[A-Za-z]+[ \t]+)?"
                      r"REGISTER_SCHEMA_VERSION[ \t]*(?::[ \t]*[A-Za-z_][\w\[\], ]*)?=[ \t]*"
                      r"[\"']?([0-9]+)", re.M)
SCHEMA_ROW = re.compile(r"INSERT INTO schema_version \([^)]*\)\s+VALUES \(([0-9]+),"
                        r"|UPDATE schema_version SET version = ([0-9]+)")
MIGRATION_ROW = re.compile(r"INSERT INTO migrations \([^)]*\)\s+VALUES \(([0-9]+),")


def release_files() -> list:
    """Every file a release ships: the wheel's payload, as `pyproject.toml`'s
    force-include table declares it, and the package's own modules."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert FORCE_INCLUDE in text, f"pyproject.toml has no {FORCE_INCLUDE}"
    table = text.split(FORCE_INCLUDE, 1)[1].split("\n[", 1)[0]
    found = []
    for rel in [*PAYLOAD_ENTRY.findall(table), "src/openrepotools"]:
        path = REPO / rel
        found += sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    return found


def test_every_copy_of_register_schema_version_in_a_release_is_one_number():
    """Design §1.5, "The row and the constant": every program that opens the
    register carries one constant, `REGISTER_SCHEMA_VERSION`, and every copy
    in a release is one number: each assignment in the shipped files, and the
    version the newest migration records in `schema_version` and in
    `migrations`. `lanes-index` carries it (CLI4.10 §2.8). Lane 1's T107
    relies on it. No engine: it reads files."""
    copies = {}
    for path in release_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for value in CONSTANT.findall(text):
            copies.setdefault(int(value), []).append(str(path.relative_to(REPO)))
    index = LANES_INDEX.read_text(encoding="utf-8")
    assert any("lanes-index" in where for found in copies.values() for where in found), (
        f"lanes-index carries no `REGISTER_SCHEMA_VERSION = <n>` (CLI4.10 §2.8, design §1.5); "
        f"the release's copies are {copies or 'none'}")
    assert len(copies) == 1, f"the release's copies of REGISTER_SCHEMA_VERSION differ: {copies}"
    (number,) = copies
    recorded = [int(a or b) for a, b in SCHEMA_ROW.findall(index)]
    assert recorded and max(recorded) == number, (
        f"the migrations record schema_version {recorded}, whose newest is not {number}")
    rows = [int(v) for v in MIGRATION_ROW.findall(index)]
    assert rows and max(rows) == number and sorted(rows) == list(range(1, number + 1)), (
        f"the migrations rows record {rows}, not 1 to {number}")


# =================================================================== T111 alone
SNAPSHOT_KEYS = ("format", "generation", "write_id", "switch", "marker", "n", "clock",
                 "not_after", "schema", "c", "n_a")


@pytest.mark.parametrize("case", ["new-write", "switch-not-primary", "at-without-generation"])
def test_register_snapshot_prints_its_keys_in_the_contracts_order_and_refuses_with_its_codes(
        pg, tmp_path, case):
    """`lanes-index register snapshot`, from T203's flipped copy, with a
    `mode=primary` configuration whose `register_url=` names the session
    cluster's socket (R-F9-3, lane 1's T111):

      * `[new-write]`: on `primary` with the marker `present`, reached by
        AT-LR006's route on a plain clone, `--write-id new --lane --verb
        --args-sha256` exits 0, and stdout is one `key=value` per line,
        LF-ended, in CLI4.10's order (430-446), with no `found=`, `file=` or
        `repos_blob=`; `c=` is `register_url=`'s `connect_timeout=` and `n_a=`
        is `register_addresses=` (CLI4.10:296-297; L1v4.10:255);
      * `[switch-not-primary]`: on the bootstrap's `files` with the marker
        `absent`, check 4 ends the call with 69 (CLI4.10:427), and the case
        asserts the 69 only;
      * `[at-without-generation]`: `--at <k>` without `--generation` ends 64
        (CLI4.10:416; L1v4.10:258), where the act-begin form, no identity
        flag at all, is not refused on the same register."""
    copy = flipped(tmp_path)
    if case != "switch-not-primary":
        n = bring_to_primary(pg)
    env = index_env(tmp_path, config(tmp_path, pg))
    new_write = ["register", "snapshot", "--write-id", "new", "--lane", LANE, "--verb", "log",
                 "--args-sha256", ARGS_SHA256]
    if case == "switch-not-primary":
        proc = run_index(copy, new_write, env)
        assert proc.returncode == 69, shown(proc)
        return
    if case == "at-without-generation":
        control = run_index(copy, ["register", "snapshot"], env)
        assert control.returncode == 0 and control.stdout.startswith("format=1\n"), (
            f"the act-begin form, the control, is refused:\n{shown(control)}")
        proc = run_index(copy, ["register", "snapshot", "--at", str(n)], env)
        assert proc.returncode == 64, shown(proc)
        return
    early = int(float(sql(pg, "SELECT extract(epoch FROM clock_timestamp());")))
    proc = run_index(copy, new_write, env)
    late = int(float(sql(pg, "SELECT extract(epoch FROM clock_timestamp());"))) + 1
    assert proc.returncode == 0, shown(proc)
    assert proc.stdout.endswith("\n") and "\r" not in proc.stdout, repr(proc.stdout)
    lines = proc.stdout[:-1].split("\n")
    pairs = [line.split("=", 1) for line in lines]
    assert all(len(pair) == 2 for pair in pairs), lines
    keys = [key for key, _ in pairs]
    assert tuple(keys) == SNAPSHOT_KEYS, f"the keys are {keys}, not {list(SNAPSHOT_KEYS)}"
    got = dict(pairs)
    assert got["format"] == "1" and got["generation"] == generation(pg), got
    assert UUID_RE.match(got["write_id"]), got
    assert (got["switch"], got["marker"], got["n"]) == ("primary", "present", str(n)), got
    assert re.fullmatch(r"[0-9]+", got["clock"]) and early <= int(got["clock"]) <= late, (
        got, early, late)
    assert re.fullmatch(r"[0-9]+", got["not_after"]) and int(got["not_after"]) >= int(
        got["clock"]) + 2, got
    assert got["schema"] == str(window(pg)["version"]), got
    assert (got["c"], got["n_a"]) == (str(CONNECT_TIMEOUT), str(ADDRESSES)), got
