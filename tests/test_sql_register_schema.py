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
  * `test_the_bootstrap_renders_register_schema_both_ways_and_refuses_the_rest`,
    new since v3f (R-F10-1): DEC-23's rendering of `register_schema=` by
    `lanes-index bootstrap`, lane 1's T109 with T104's key. Its two rendering
    ids ask for the session cluster at run time and bootstrap empty databases
    of their own; its four refusal ids need no engine.
  * `test_commit_write_derives_step_6s_deletes_so_the_tables_equal_the_imports_derivation`,
    new since v3f (R-F10-34, R-F13-2): T107's step 6 and step 7 at the engine. Its
    four ids from lane 3's ruling (c) (two renames, two strays), and case 6a's two,
    `[6a-replace]` and `[6a-remove]`, where the entry takes away the line that holds
    a lane's hold on an object and sends no hold on it: the tables equal the
    import's derivation, step 7 re-marks `superseded_by` and stamps no `seq` or
    `mode`, and step 5a's `objects:` keys name every lane holding the object.

REAL ENGINE. Every case but the one-number rule and DEC-23's test asks for
`pg`, one database cloned from the session's template, so its fixture closure
holds `pg_engine` (T200's rule). The cases assume the template that T227
builds by `lanes-index bootstrap --no-passwords`; on T205's empty template they
fail, since the schema is not there. Without PostgreSQL 16 they skip with
T205's banner. DEC-23's two rendering ids take `pg_cluster` by
`request.getfixturevalue`, so they skip the same way, but that function's
closure does not hold `pg_engine`; its name holds neither word of the launch
job's filter, so T200's check is unaffected.

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
from types import SimpleNamespace

import pytest

from conftest import REPO, git
from pgcluster import Database
from sql_register_helpers import (LANES_INDEX, REGISTER_FAKE_PSQL, RENDER_GIT_HALF_LINE,
                                  flipped_copy)

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
STORE_LABEL = "t221"                          # the bootstrap case's `--label`; `config()` sets no label
STORE_UTC = "2026-11-09T10:00:00Z"            # fixed, so the file's sha256 is the same every run
# D21 (Y:613-615 at a6497d00); one field per line is a reading until T116 writes it; lane 1, #165 6754714549
STORE_LINES = ("store=primary", f"database={STORE_LABEL}", f"import={COMMIT_C}",
               f"lanes-tree={TREE_C}", f"utc={STORE_UTC}")
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
                        *({"ord": n, "op": "append", "path": "lanes/STORE", "new_text": line}
                          for n, line in enumerate(STORE_LINES, start=2))],
                 files=[{"path": "lanes/STORE", "present": True,
                         "sha256": rendered(STORE_LINES), "final_newline": True}])


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
        writer.stdin = None
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
    number = min(win["writers_from"], win["readers_from"]) - 1    # too old: "upgrade the tools"

    def schema_fails(proc):
        return [line for line in proc.stdout.splitlines() if line.startswith("check 9: FAIL")]

    inside = run_index(flipped(tmp_path), args, env)
    assert not schema_fails(inside), f"the shipped client fails check 9:\n{shown(inside)}"
    outside = run_index(window_copy(tmp_path, number), args, env)
    assert outside.returncode == 2, shown(outside)
    fails = schema_fails(outside)
    # lane 1's [P] line form for T119, #165 6754498682 item 1
    assert fails and any("upgrade the tools" in line and names_both(line, win["version"], number)
                         for line in fails), (
        f"check 9 does not fail, upgrade the tools, naming {win['version']} and {number}:\n"
        f"{shown(outside)}")


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
    "store": [("lanes/STORE", "store=primary", set()), ("lanes/STORE", f"| `Lane-A` | {UUID_U} |", set())],
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


# =================================================================== DEC-23's rendering
#: The scratch name the rendering cases bootstrap: any `register_schema=` but
#: the default (lane 2's reading of "a scratch schema", NOTES question 6).
SCRATCH = "t221_scratch"
ADMIN_SERVICE = "t221_admin"
BOOTSTRAP = ["bootstrap", "--admin-service", ADMIN_SERVICE, "--label", "t221",
             "--repository", "opensoft/t221", "--lane", LANE, "--no-passwords"]

#: `lanes_register` as one whole identifier token: the three roles, whose names
#: begin with it, are other tokens (DEC-23; lane 3, #165 6748109738).
SCHEMA_TOKEN = re.compile(r"(?<![A-Za-z0-9_$])lanes_register(?![A-Za-z0-9_$])")
DIGEST = re.compile(r"\b[0-9a-f]{64}\b")

#: Each refusal id's configurations: `register_schema=` that is not
#: `[a-z_][a-z0-9_]{0,62}` (upper case, a leading digit, a hyphen, 64
#: characters), one beginning `pg_`, and one equal to the index half's schema,
#: `lanes_index` or the configured `schema=` (lane 3, #165 6748109738).
SCHEMA_REFUSALS = {
    "identifier-rule": ["register_schema=T221_scratch\n", "register_schema=1t221\n",
                        "register_schema=t221-scratch\n", f"register_schema={'t' * 64}\n"],
    "pg-prefix": ["register_schema=pg_t221\n"],
    "index-schema": ["register_schema=lanes_index\n",
                     "schema=t221_index\nregister_schema=t221_index\n"],
}

#: Migration 1's own `CREATE SCHEMA` line (Y's §1.2 block), where
#: `[leftover-refused]`'s copy names the schema once more after it.
CREATE_SCHEMA_LINE = re.compile(r"^CREATE SCHEMA (?:IF NOT EXISTS )?lanes_register\b[^\n]*$", re.M)
LEFTOVER = "ALTER SCHEMA lanes_register OWNER TO lanes_register_owner;   -- t221: a leftover"


def bootstrap_conf(where: Path, text: str) -> Path:
    """A 0600 `lanes-index.conf` holding `text`, outside every work tree."""
    where.mkdir(parents=True, exist_ok=True)
    path = where / "lanes-index.conf"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def fake_admin(tmp_path: Path, conf: Path, tag: str) -> tuple:
    """The bootstrap's environment with the register's fake `psql` first on
    `PATH`, taught to fail every request as a database that cannot be reached
    does, and `conf` as the configuration: so a run that gets past every
    refusal reaches the admin connection and exits 69, and its log shows the
    request; a refused run sends nothing. No engine is needed."""
    base = tmp_path / tag
    base.mkdir()
    fake = base / "fake"
    fake.mkdir()
    (fake / "psql").write_text(REGISTER_FAKE_PSQL, encoding="utf-8")
    (fake / "psql").chmod(0o755)
    answers = base / "answers.json"
    answers.write_text(json.dumps([{"exit": 2, "stderr": (
        f'psql: error: connection to server on socket "{base}/.s.PGSQL.5432" failed: '
        f'No such file or directory\n')}]), encoding="utf-8")
    log = base / "psql.log"
    nowhere = SimpleNamespace(host=base / "no-cluster", port=5432, name="t221_none")
    env = admin_env(base, nowhere)
    env.update(PATH=f"{fake}{os.pathsep}{env.get('PATH', os.defpath)}",
               FAKE_PSQL_LOG=str(log), FAKE_PSQL_ANSWERS=str(answers),
               LANES_INDEX_CONFIG=str(conf))
    return env, log


def requests_of(log: Path) -> list:
    """The fake's entries that carried a request (never a `--version`)."""
    if not log.exists():
        return []
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [e for e in entries if e.get("kind") != "version"]


def reaches_the_admin_connection(copy: Path, tmp_path: Path, tag: str) -> None:
    """THE CONTROL: with `register_schema=` the scratch name, the same run gets
    past every refusal to the admin service, so a 2 in the case is the
    refusal it asserts and not a bootstrap this build lacks."""
    env, log = fake_admin(tmp_path, bootstrap_conf(tmp_path / tag, f"register_schema={SCRATCH}\n"),
                          f"{tag}-run")
    proc = run_index(copy, BOOTSTRAP, env)
    sent = requests_of(log)
    assert proc.returncode == 69 and sent, (
        f"the control, register_schema={SCRATCH} through a database that cannot be reached, "
        f"does not reach the admin connection and end 69 ({len(sent)} request(s) sent):\n"
        f"{shown(proc)}")
    assert all(e["service"] == ADMIN_SERVICE for e in sent), sent


def refused_and_sent_nothing(proc: subprocess.CompletedProcess, log: Path, what: str) -> None:
    sent = requests_of(log)
    assert proc.returncode == 2, f"{what}: not refused with 2:\n{shown(proc)}"
    assert not sent, f"{what}: refused, but {len(sent)} request(s) reached psql: {sent}"
    assert not re.search(r": created\b", proc.stdout), f"{what}: created something:\n{shown(proc)}"


def fresh_database(cluster, tag: str) -> Database:
    """An empty database of the session cluster, from `template0`, owned by
    the fixture's superuser, which the admin service connects as."""
    name = f"t221_{tag}_{uuid.uuid4().hex[:8]}"
    cluster.psql(f"CREATE DATABASE {name} TEMPLATE template0;")
    return Database(cluster, name)


def migration_digests(proc: subprocess.CompletedProcess) -> dict:
    """Each `migration <n>: created` line's two digests: `script_sha256`'s, and
    the rendered one the bootstrap prints beside it (lane 1, #165 6748099727)."""
    found = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"^migration ([0-9]+): created\b", line)
        if not m:
            continue
        script = re.search(r"script_sha256\W+([0-9a-f]{64})\b", line)
        digests = DIGEST.findall(line)
        assert script and len(digests) == 2, f"no two digests beside script_sha256: {line!r}"
        other = digests[1] if digests[0] == script.group(1) else digests[0]
        found[int(m.group(1))] = (script.group(1), other)
    assert found, f"the bootstrap created no migration:\n{shown(proc)}"
    return found


#: One schema's objects, its owners and its privileges, as one JSON object:
#: every relation with its columns, defaults, constraints and definition,
#: every function's whole definition (its `SET search_path` among it), the
#: triggers, the types, and the ACLs and default privileges.
DESCRIBE = """
SELECT jsonb_build_object(
  'owner', n.nspowner::regrole::text, 'acl', n.nspacl::text,
  'relations', (SELECT coalesce(jsonb_agg(jsonb_build_array(
      c.relname, c.relkind, c.relowner::regrole::text, c.relacl::text,
      (SELECT coalesce(jsonb_agg(jsonb_build_array(a.attname, format_type(a.atttypid, a.atttypmod),
              a.attnotnull, pg_get_expr(d.adbin, d.adrelid), a.attacl::text) ORDER BY a.attnum), '[]')
         FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped),
      (SELECT coalesce(jsonb_agg(jsonb_build_array(k.conname, pg_get_constraintdef(k.oid))
              ORDER BY k.conname), '[]') FROM pg_constraint k WHERE k.conrelid = c.oid),
      CASE WHEN c.relkind = 'i' THEN pg_get_indexdef(c.oid)
           WHEN c.relkind IN ('v', 'm') THEN pg_get_viewdef(c.oid) END) ORDER BY c.relname), '[]')
    FROM pg_class c WHERE c.relnamespace = n.oid),
  'functions', (SELECT coalesce(jsonb_agg(jsonb_build_array(
      p.proname, pg_get_function_identity_arguments(p.oid), p.proowner::regrole::text,
      p.proacl::text, CASE WHEN p.prokind IN ('f', 'p') THEN pg_get_functiondef(p.oid) END)
      ORDER BY p.proname, pg_get_function_identity_arguments(p.oid)), '[]')
    FROM pg_proc p WHERE p.pronamespace = n.oid),
  'triggers', (SELECT coalesce(jsonb_agg(pg_get_triggerdef(t.oid) ORDER BY t.tgname), '[]')
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
   WHERE c.relnamespace = n.oid AND NOT t.tgisinternal),
  'types', (SELECT coalesce(jsonb_agg(jsonb_build_array(y.typname, y.typtype, y.typacl::text)
      ORDER BY y.typname), '[]') FROM pg_type y WHERE y.typnamespace = n.oid),
  'defaults', (SELECT coalesce(jsonb_agg(jsonb_build_array(d.defaclrole::regrole::text,
      d.defaclobjtype, d.defaclacl::text) ORDER BY d.defaclrole::regrole::text, d.defaclobjtype),
      '[]') FROM pg_default_acl d WHERE d.defaclnamespace = n.oid))
FROM pg_namespace n WHERE n.nspname = '{schema}';
"""


def describe(db, schema: str) -> dict:
    out = sql(db, DESCRIBE.format(schema=schema))
    assert out, f"there is no schema {schema} in {db.name}"
    return json.loads(out)


@pytest.mark.parametrize("case", ["default-unchanged", "scratch-every-site", "leftover-refused",
                                  "identifier-rule", "pg-prefix", "index-schema"])
def test_the_bootstrap_renders_register_schema_both_ways_and_refuses_the_rest(
        request, tmp_path, case):
    """DEC-23 (lane 3, #165 6748109738; R-F10-1): `lanes-index bootstrap`
    through the admin service, as T109 builds it.

      * `[default-unchanged]`: with `register_schema=` unset, on an empty
        database, the rendered script is T107's migration byte for byte: the
        digest printed beside `script_sha256` equals it, and so does the
        `migrations` row's;
      * `[scratch-every-site]`: with a scratch name, that schema holds every
        relation, function, trigger and type a default bootstrap makes, with
        the same owners and privileges, each definition the default's with
        the whole token `lanes_register` replaced and nothing else changed;
        the three roles keep their names; and no `lanes_register` schema is
        made;
      * `[leftover-refused]`: a copy whose migration names `lanes_register`
        once more, at a site DEC-23 does not render, is refused with 2 and
        sends nothing (lane 2's reading, NOTES question 33);
      * `[identifier-rule]`, `[pg-prefix]` and `[index-schema]`: each
        configuration of `SCHEMA_REFUSALS` is refused with 2, sending nothing.

    The last four need no engine: the register's fake `psql` stands in for
    the database, and a control run shows the same bootstrap reaching it.
    The first two ask for the session cluster at run time, so without
    PostgreSQL 16 they skip with T205's banner."""
    if case in SCHEMA_REFUSALS:
        reaches_the_admin_connection(LANES_INDEX, tmp_path, "control")
        for n, text in enumerate(SCHEMA_REFUSALS[case], start=1):
            env, log = fake_admin(tmp_path, bootstrap_conf(tmp_path / f"conf-{n}", text), f"run-{n}")
            refused_and_sent_nothing(run_index(LANES_INDEX, BOOTSTRAP, env), log,
                                     f"{text.strip()!r}")
        return
    if case == "leftover-refused":
        reaches_the_admin_connection(LANES_INDEX, tmp_path, "control")
        found = RENDER_GIT_HALF_LINE.search(LANES_INDEX.read_bytes())
        assert found, f"{LANES_INDEX} holds no RENDER_GIT_HALF line for T203's flipped_copy"
        copy = flipped_copy(LANES_INDEX, tmp_path / "leftover", found.group(1) == b"True")
        text = copy.read_text(encoding="utf-8")
        sites = CREATE_SCHEMA_LINE.findall(text)
        assert len(sites) == 1, f"{LANES_INDEX} holds {len(sites)} `CREATE SCHEMA lanes_register` lines"
        copy.write_text(CREATE_SCHEMA_LINE.sub(lambda m: m.group(0) + "\n" + LEFTOVER, text),
                        encoding="utf-8")
        env, log = fake_admin(tmp_path, bootstrap_conf(tmp_path / "conf", f"register_schema={SCRATCH}\n"),
                              "run")
        refused_and_sent_nothing(run_index(copy, BOOTSTRAP, env), log, "the leftover's copy")
        return
    cluster = request.getfixturevalue("pg_cluster")
    made = []
    try:
        default = fresh_database(cluster, "default")
        made.append(default.name)
        (tmp_path / "default").mkdir()
        proc = run_index(LANES_INDEX, BOOTSTRAP, admin_env(tmp_path / "default", default))
        assert proc.returncode == 0, shown(proc)
        template, rendered_digest = migration_digests(proc)[1]
        if case == "default-unchanged":
            assert rendered_digest == template, (
                f"on {SCHEMA} the rendered script's digest {rendered_digest} is not "
                f"script_sha256 {template}:\n{shown(proc)}")
            assert sql(default, f"SELECT script_sha256 FROM {SCHEMA}.migrations "
                                f"WHERE version = 1;") == template
            return
        scratch = fresh_database(cluster, "scratch")
        made.append(scratch.name)
        (tmp_path / "scratch").mkdir()
        env = admin_env(tmp_path / "scratch", scratch)
        env["LANES_INDEX_CONFIG"] = str(bootstrap_conf(tmp_path / "scratch" / "conf",
                                                       f"register_schema={SCRATCH}\n"))
        proc = run_index(LANES_INDEX, BOOTSTRAP, env)
        assert proc.returncode == 0, shown(proc)
        script, rendered_scratch = migration_digests(proc)[1]
        assert script == template and rendered_scratch != template, (
            f"for {SCRATCH} the bootstrap prints {script} and {rendered_scratch}, not the "
            f"template's {template} beside a rendered digest of its own:\n{shown(proc)}")
        assert sql(scratch, f"SELECT to_regnamespace('{SCHEMA}') IS NULL;") == "t", (
            f"a bootstrap for {SCRATCH} made a {SCHEMA} schema")
        assert sql(scratch, f"SELECT count(*) FROM pg_roles WHERE rolname IN "
                            f"('{OWNER}', '{WRITER}', '{READER}');") == "3"
        assert sql(scratch, f"SELECT count(*) FROM pg_roles WHERE rolname LIKE "
                            f"'{SCRATCH.replace('_', chr(92) + '_')}%';") == "0"
        want = json.loads(SCHEMA_TOKEN.sub(SCRATCH, json.dumps(describe(default, SCHEMA))))
        got = describe(scratch, SCRATCH)
        assert want["relations"] and want["functions"] and want["acl"], want
        for part in want:
            assert got[part] == want[part], (
                f"{SCRATCH}'s {part} differ from {SCHEMA}'s with the token replaced:\n"
                f"want {json.dumps(want[part], indent=1)[:3000]}\n"
                f"got  {json.dumps(got[part], indent=1)[:3000]}")
    finally:
        for name in made:
            cluster.drop_database(name)


# =================================================================== T107's step 6
#: The small mirrors of T107's step-6 cases (lane 3, #165 6755386771, ruling (c)
#: and "Lane 2's cases"; PLACEMENT.md section 1). Every row is literal, in Y
#: section 1.3's entry form, as T223's direct calls are: no case calls T112's
#: or T115's derivation code.
STEP6_UTC = "2026-11-09T10:00:00Z"
STEP6_ROW_A, STEP6_ROW_B, STEP6_ROW_R = "| `Lane-A` | x |", "| `Lane-B` | y |", "| `Lane-R` | x |"
STEP6_LOG_A, STEP6_LOG_B, STEP6_LOG_R = ("lanes/log/Lane-A.md", "lanes/log/Lane-B.md",
                                         "lanes/log/Lane-R.md")
STEP6_WORD_MS = "2026-11-09T10:00:00.123Z"           # a WORD line with milliseconds (lane 3)
STEP6_STRAY_SHA = "5" * 40


def step6_log(verb: str, obj, utc: str = STEP6_UTC) -> tuple:
    """One log line: its text, and its parsed fields (Y's derivation, by hand)."""
    text = f"{verb} {EM_DASH} {obj if obj else 'note'} {EM_DASH} {utc}"
    return text, {"verb": verb, "object": obj, "utc": utc, "utc_ts": utc}


def step6_rows(files: dict, holds_spelled=("CLAIMED", "TAKEOVER")) -> dict:
    """The structured rows of `files` by lane 2's literal derivation of these
    small mirrors (Y:1193-1273, reading 7's corrections): a `lanes` row per
    row line; a `log_lines` row per log line, its lane the file's, NULL
    workstation; each lane's last line per object a hold, `spellings` on
    CLAIMED and TAKEOVER only; no `register_lines`, since no line has a kind;
    no `lane:` objects; NULL `owner`."""
    lanes, logs, holds = [], [], {}
    for path, lines in sorted(files.items()):
        for n, text in enumerate(lines, start=1):
            m = re.fullmatch(r"\| `([^`]+)` \| [a-z] \|", text)
            if path == "lanes/LANES.md" and m:
                lanes.append({"path": path, "line_no": n, "raw": text, "lane_key": m.group(1).lower(),
                              "lane": m.group(1), "archived": False, "owner": None})
            elif path.startswith("lanes/log/"):
                lane = path[len("lanes/log/"):-len(".md")]
                fields = STEP6_FIELDS[text]
                logs.append({"path": path, "line_no": n, "raw": text, "lane": lane,
                             "workstation": None, "unreadable": False, **fields})
                if fields["object"]:
                    holds[(fields["object"], lane.lower())] = {
                        "object": fields["object"], "lane_key": lane.lower(), "lane": lane,
                        "verb": fields["verb"], "utc_ts": fields["utc_ts"], "file": path,
                        "ordinal": n,
                        "spellings": [fields["object"]] if fields["verb"] in holds_spelled else None}
    return {"lanes": lanes, "log_lines": logs, "object_holds": list(holds.values())}


STEP6_CLAIM_O1, _f1 = step6_log("CLAIMED", "o1")
STEP6_CLAIM_O2, _f2 = step6_log("CLAIMED", "o2")
STEP6_OPEN_O3, _f3 = step6_log("OPENED", "o3")
STEP6_TAKE_O1, _f4 = step6_log("TAKEOVER", "o1", "2026-11-09T11:00:00Z")   # Lane-B's, on Lane-A's o1
STEP6_WORD, _fw = step6_log("WORD", None, STEP6_WORD_MS)
STEP6_RENAMED, _fr = step6_log("RENAMED", None, "2026-11-10T12:00:00Z")
STEP6_STRAY, _fs = step6_log("NOTED", None)
STEP6_FIELDS = {STEP6_CLAIM_O1: _f1, STEP6_CLAIM_O2: _f2, STEP6_OPEN_O3: _f3, STEP6_TAKE_O1: _f4,
                STEP6_WORD: _fw, STEP6_RENAMED: _fr, STEP6_STRAY: _fs}

#: Each case: the mirror before, and the mirror after the write.
STEP6_CASES = {
    "rename-live-claim": (
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A], STEP6_LOG_A: [STEP6_CLAIM_O1]},
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_R], STEP6_LOG_R: [STEP6_CLAIM_O1, STEP6_RENAMED]}),
    "rename-millisecond-word-log": (
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A], STEP6_LOG_A: [STEP6_WORD]},
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_R], STEP6_LOG_R: [STEP6_WORD, STEP6_RENAMED]}),
    "stray-deletes-a-row": (
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A, STEP6_ROW_B]},
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_B]}),
    "stray-inserts-before-the-end": (
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A],
         STEP6_LOG_A: [STEP6_CLAIM_O1, STEP6_CLAIM_O2, STEP6_OPEN_O3]},
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A],
         STEP6_LOG_A: [STEP6_CLAIM_O1, STEP6_STRAY, STEP6_CLAIM_O2, STEP6_OPEN_O3]}),
    # Case 6a (R-F13-2; lane 3, #165 6771318480, option (i)): Lane-B's TAKEOVER on o1 is
    # the line that supersedes Lane-A's CLAIMED, and the write takes that line away (a
    # replace by a stray; a remove of its log by a write) and sends NO hold on o1.
    "6a-replace": (
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A, STEP6_ROW_B],
         STEP6_LOG_A: [STEP6_CLAIM_O1], STEP6_LOG_B: [STEP6_TAKE_O1]},
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A, STEP6_ROW_B],
         STEP6_LOG_A: [STEP6_CLAIM_O1], STEP6_LOG_B: [STEP6_STRAY]}),
    "6a-remove": (
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A, STEP6_ROW_B],
         STEP6_LOG_A: [STEP6_CLAIM_O1], STEP6_LOG_B: [STEP6_TAKE_O1]},
        {"lanes/LANES.md": ["# Lanes", STEP6_ROW_A, STEP6_ROW_B],
         STEP6_LOG_A: [STEP6_CLAIM_O1]}),
}


def step6_entry(case: str, before: dict, after: dict) -> dict:
    """The write each case commits. The renames as T112 now builds them (B10
    tasks:428): the row line's `replace`, the log's `rename`, and `log_lines`
    rows only for the lines written, with the holds from every line of the
    renamed log. The strays as `import --single` sends them: a `delete`; and,
    with no insert op, a `replace` of every later line and an `append`
    (6755386771, "No insert op now"). Case 6a's two (lane 3, #165 6771318480):
    a stray's `replace` of Lane-B's TAKEOVER line by a line on no object, with
    the replaced line's own `log_lines` row, and a write's `remove` of Lane-B's
    log; each sends no `object_holds` row, since no line of Lane-B names o1
    after it (T112's `register_commit_entry` sends none for a pair left with
    no line)."""
    rows = step6_rows(after)
    if case == "6a-replace":
        return entry("stray-import", "import --single", journal={"git_commit": STEP6_STRAY_SHA},
                     edits=[{"ord": 1, "op": "replace", "path": STEP6_LOG_B, "line_no": 1,
                             "old_sha256": line_sha(before[STEP6_LOG_B][0]),
                             "new_text": after[STEP6_LOG_B][0]}],
                     files=[{"path": STEP6_LOG_B, "present": True,
                             "sha256": rendered(after[STEP6_LOG_B]), "final_newline": True}],
                     log_lines=[r for r in rows["log_lines"] if r["path"] == STEP6_LOG_B])
    if case == "6a-remove":
        return entry("write", "remove-log", journal={"args_sha256": ARGS_SHA256},
                     edits=[{"ord": 1, "op": "remove", "path": STEP6_LOG_B}],
                     files=[{"path": STEP6_LOG_B, "present": False}])
    if case.startswith("rename-"):
        renamed = {**rows["log_lines"][-1], "workstation": WS}      # primary: Rule 10's CHECK
        lanes = [r for r in rows["lanes"] if r["lane"] == "Lane-R"]
        return entry("write", "rename-lane", journal={"args_sha256": ARGS_SHA256},
                     edits=[{"ord": 1, "op": "replace", "path": "lanes/LANES.md", "line_no": 2,
                             "old_sha256": line_sha(STEP6_ROW_A), "new_text": STEP6_ROW_R},
                            {"ord": 2, "op": "rename", "path": STEP6_LOG_A, "to_path": STEP6_LOG_R},
                            {"ord": 3, "op": "append", "path": STEP6_LOG_R,
                             "new_text": STEP6_RENAMED}],
                     files=[{"path": "lanes/LANES.md", "present": True,
                             "sha256": rendered(after["lanes/LANES.md"]), "final_newline": True},
                            {"path": STEP6_LOG_R, "present": True,
                             "sha256": rendered(after[STEP6_LOG_R]), "final_newline": True},
                            {"path": STEP6_LOG_A, "present": False}],
                     lanes=lanes, log_lines=[renamed],
                     object_holds=[h for h in rows["object_holds"] if h["file"] == STEP6_LOG_R])
    stray = {"journal": {"git_commit": STEP6_STRAY_SHA}}
    if case == "stray-deletes-a-row":
        return entry("stray-import", "import --single", **stray,
                     edits=[{"ord": 1, "op": "delete", "path": "lanes/LANES.md", "line_no": 2,
                             "old_sha256": line_sha(STEP6_ROW_A)}],
                     files=[{"path": "lanes/LANES.md", "present": True,
                             "sha256": rendered(after["lanes/LANES.md"]), "final_newline": True}])
    old, new = before[STEP6_LOG_A], after[STEP6_LOG_A]
    edits = [{"ord": n - 1, "op": "replace", "path": STEP6_LOG_A, "line_no": n,
              "old_sha256": line_sha(old[n - 1]), "new_text": new[n - 1]}
             for n in range(2, len(old) + 1)]
    edits.append({"ord": len(edits) + 1, "op": "append", "path": STEP6_LOG_A, "new_text": new[-1]})
    return entry("stray-import", "import --single", **stray, edits=edits,
                 files=[{"path": STEP6_LOG_A, "present": True, "sha256": rendered(new),
                         "final_newline": True}],
                 log_lines=[r for r in rows["log_lines"] if r["path"] == STEP6_LOG_A
                            and r["line_no"] >= 2],
                 object_holds=[h for h in rows["object_holds"] if h["file"] == STEP6_LOG_A
                               and h["ordinal"] >= 2])


#: The four structured tables, each row keyed by its line's `(path, line_no)`
#: in place of a line id, without the columns a write stamps: the written seq,
#: the mode and the workstation (lane 2's reading, NOTES question 33).
STRUCTURED = {
    "lanes": f"SELECT to_jsonb(t) - 'row_line_id' - 'last_seq' - 'last_mode' - 'workstation' || "
             f"jsonb_build_object('path', d.path, 'line_no', d.line_no) FROM {SCHEMA}.lanes t "
             f"LEFT JOIN {SCHEMA}.doc_lines d ON d.line_id = t.row_line_id",
    "log_lines": f"SELECT to_jsonb(t) - 'line_id' - 'seq' - 'mode' - 'workstation' || "
                 f"jsonb_build_object('path', d.path, 'line_no', d.line_no) FROM "
                 f"{SCHEMA}.log_lines t LEFT JOIN {SCHEMA}.doc_lines d ON d.line_id = t.line_id",
    "register_lines": f"SELECT to_jsonb(t) - 'line_id' - 'seq' - 'mode' - 'workstation' || "
                      f"jsonb_build_object('path', d.path, 'line_no', d.line_no) FROM "
                      f"{SCHEMA}.register_lines t LEFT JOIN {SCHEMA}.doc_lines d "
                      f"ON d.line_id = t.line_id",
    "object_holds": f"SELECT to_jsonb(t) - 'seq' - 'mode' FROM {SCHEMA}.object_holds t",
}


def structured(db) -> dict:
    out = {}
    for table, query in STRUCTURED.items():
        rows = json.loads(sql(db, f"SELECT coalesce(jsonb_agg(r ORDER BY r::text), '[]') "
                                  f"FROM ({query}) AS q(r);"))
        out[table] = rows
    return out


def step6_holds_of(db, obj: str) -> dict:
    """Every stored `object_holds` row on `obj`, whole, by lane key."""
    rows = json.loads(sql(db, f"SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]') FROM "
                              f"{SCHEMA}.object_holds t WHERE object = {sql_text(obj)};"))
    return {row["lane_key"]: row for row in rows}


@pytest.mark.parametrize("case", list(STEP6_CASES))
def test_commit_write_derives_step_6s_deletes_so_the_tables_equal_the_imports_derivation(
        pg, case):
    """T107's step 6 under lane 3's ruling (c) (#165 6755386771): as a
    `replace` or `delete` changes a line, `commit_write` deletes that line's
    structured rows, and a `rename` deletes the old path's holds and moves
    `log_lines` to the new file's lane; the entry carries no deletes.

    Each case clones `tmpl`, brings it to `primary` with the marker `present`
    by AT-LR006's route, with its mirror as the import; a stray first records
    its sha by `record_mirror_state`. Then `commit_write` returns its seq, with
    no 23505, 23503, 23514 (Y:1217-1219) or LR005, and `lanes`, `log_lines`,
    `register_lines` and `object_holds` equal, row for row, what one `import`
    entry of the mirror after the write leaves in a second clone of `tmpl`.
    `[rename-live-claim]` also asserts the claim's hold is the new lane's, and
    `[stray-inserts-before-the-end]` that each hold below the inserted line
    points at its own line.

    CASE 6A (R-F13-2; lane 3, #165 6771318480, option (i); T107's `PENDING-L2`
    marker), `[6a-replace]` and `[6a-remove]`: Lane-B's TAKEOVER on `o1` is the
    line that supersedes Lane-A's CLAIMED on it, and the entry replaces that
    line (a stray's `replace`) or removes its log (a write's `remove`) and
    sends no hold on `o1`. Beside the tables equal to the import's derivation,
    each asserts that step 7 re-marks `superseded_by` on every stored row of
    `o1` as for an object the entry sends, so Lane-A's CLAIMED is live again, and
    stamps no `seq` or `mode` on it; and that the entry's `journal_scopes`
    hold `objects:lane-a` and `objects:lane-b`, every lane holding the object,
    so that the flip is reported (step 5a). They fail until lane 1's commit of
    6a on T107 (`lanes-index` line S), where `commit_write` as T112-fu2 reads
    it re-marks only the objects the entry sends."""
    before, after = STEP6_CASES[case]
    n = bring_to_primary(pg, before, **step6_rows(before))
    body = step6_entry(case, before, after)
    if body["journal"]["kind"] == "stray-import":       # a stray's, which clears a divergence
        assert record_mirror_state(pg, "ws-stray", STEP6_STRAY_SHA, None).returncode == 0
    if case.startswith("6a-"):                          # the control: the claim is superseded
        was = step6_holds_of(pg, "o1")
        assert {k: v["superseded_by"] for k, v in was.items()} == {"lane-a": "lane-b",
                                                                   "lane-b": None}, was
    proc = commit_call(pg, n, body)
    code, message = error_of(proc)
    assert proc.returncode == 0, (
        f"commit_write refused the {case} write with {code} (23505, 23503, 23514 and LR005 "
        f"are the gap's effects, 6755386771): {message}\n{proc.stderr.strip()}")
    assert int(proc.stdout.strip().splitlines()[-1]) == n + 1
    got = structured(pg)
    oracle = Database(pg.cluster, pg.cluster.new_database())
    try:
        committed(oracle, head(oracle), import_entry(after, **step6_rows(after)),
                  "the oracle's import of the mirror after the write")
        want = structured(oracle)
    finally:
        pg.cluster.drop_database(oracle.name)
    for table in STRUCTURED:
        assert got[table] == want[table], (
            f"{case}: {table} is not the import's derivation of the mirror after the write:\n"
            f"got  {json.dumps(got[table], indent=1)[:3000]}\n"
            f"want {json.dumps(want[table], indent=1)[:3000]}")
    holds = {(h["object"], h["lane_key"]): h for h in got["object_holds"]}
    if case == "rename-live-claim":
        assert ("o1", "lane-a") not in holds, holds
        assert (holds[("o1", "lane-r")]["file"], holds[("o1", "lane-r")]["ordinal"]) == (
            STEP6_LOG_R, 1), holds
    if case == "stray-inserts-before-the-end":
        lines = {(r["path"], r["line_no"]): r for r in got["log_lines"]}
        for h in got["object_holds"]:
            line = lines[(h["file"], h["ordinal"])]
            assert (line["object"], line["verb"]) == (h["object"], h["verb"]), (h, line)
        assert sorted(h["ordinal"] for h in got["object_holds"]) == [1, 3, 4], holds
    if case.startswith("6a-"):
        now = step6_holds_of(pg, "o1")
        assert set(now) == {"lane-a"}, (
            f"{case}: step 6 should have deleted Lane-B's hold on o1 with its line, and left "
            f"Lane-A's: {now}")
        assert now["lane-a"]["superseded_by"] is None, (
            f"{case}: Lane-A's CLAIMED on o1 is still superseded by "
            f"{now['lane-a']['superseded_by']!r}, though Lane-B's TAKEOVER is gone: step 7 did "
            f"not re-mark the object, since the entry sends no hold on it (case 6a)")
        assert (now["lane-a"]["seq"], now["lane-a"]["mode"]) == (
            was["lane-a"]["seq"], was["lane-a"]["mode"]), (
            f"{case}: the re-mark stamped Lane-A's row: it was {(was['lane-a']['seq'], was['lane-a']['mode'])}, "
            f"it is {(now['lane-a']['seq'], now['lane-a']['mode'])}; it takes no seq or mode")
        keys = set(json.loads(sql(pg, f"SELECT coalesce(jsonb_agg(scope), '[]') FROM "
                                      f"{SCHEMA}.journal_scopes WHERE seq = {n + 1};")))
        assert {"objects:lane-a", "objects:lane-b"} <= keys, (
            f"{case}: the entry's journal_scopes are {sorted(keys)}; step 5a should add objects: "
            f"for every lane holding o1, objects:lane-a and objects:lane-b, so the flip is reported")
