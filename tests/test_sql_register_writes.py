# SPDX-License-Identifier: Apache-2.0
"""Feature 007's test 2 (AT-2; opensoft/openRepoTools#165): a register write
exits 69 when the database is unreachable, with nothing written.

THIS MODULE TODAY holds test 2's storage-layer case alone, phase N (the test
plan's section 1.3; lane 2's T210):
`test_the_storage_layer_entry_exits_69_when_the_database_is_unreachable`.
Test 2's per-verb cases, its refused transactions, its partial failures and
S1's other tests are phase W, lane 2's T241, which adds them here.

THE STORAGE-LAYER ENTRY is the managed projection writer's (design S4), driven
by the fake writer AT-1's part N drives it with,
`test_sql_register_render.py`'s `projection_entry`: one attempt of S1's loop,
`register snapshot --write-id new ... --tree <dir> --checkout <c>` (contract
section 3.2), then, on 0 alone, the attempt directory and `register commit`
(section 3.3), as the verb `managed-projection`.

WHY THE 69 IS THE SNAPSHOT'S. With the database unreachable, the entry's first
call is a read, and a read that cannot reach its database is 69 (contract
section 2.7, "On a read"; section 3.2's exits; AT-2's outcome table, "no
connection at the first snapshot is 69"). `register commit` against an
unreachable database is 3, in doubt, never 69 (section 2.7, CO-5 and CO-6;
lane 1's T112 builds it so), so the entry never reaches it: the writer
abandons on a snapshot's 69 (section 3.3, "The caller's map"). The case fails
until L1-A9 (lane 1's T111, `register snapshot`) lands, and, for the flipped
copy, L1-A4 (T105's constant).

THE FAULT, WITH NO ENGINE (AT-2's "Unreachable"): the configuration's
`register_url=` names a fresh, empty socket directory, and the `psql` first on
`PATH` is T203's register fake, which since T203b answers T106's `psql
--version` itself with 16.4 (logged as its own kind, and left out of
`fake_calls`), and every call that carries a request with `psql`'s own exit 2
and its "connection to server ... failed" text, as the real `psql` answers an
empty socket directory. The fake's log is the oracle for what reached the store:
one call, the snapshot's, with no `commit_write` in it, the configured
password file and no `PGPASSWORD`, and no call after it (no retry that reads
as a write, and no fallback). With no request that reached a database, the
register's rows and the journal are unchanged; on the real engine, the
per-verb cases (T241) read them back by digest.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import WINDOWS_SKIP
from test_sql_register_render import (Estate, fake_calls, fake_psql_dir, flipped, index_env,
                                      primary_config, projection_entry, _sanitized_path)

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

#: Contract section 2.2's argv, exactly.
PSQL_ARGV = ["--no-psqlrc", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-v",
             "VERBOSITY=verbose", "-v", "SHOW_CONTEXT=never"]

#: The writer's login and its password, which must never be printed.
WRITER_LOGIN = "lanes_w_t210"
SECRET = "t210-never-printed-0b5e"


def test_the_storage_layer_entry_exits_69_when_the_database_is_unreachable(tmp_path):
    """The storage-layer entry, called as AT-1's part N calls it, against a
    `register_url=` whose socket directory is fresh and empty: it exits 69,
    and stderr names the store and the error, `psql`'s own first line, which
    names the socket, with no credential and no URL. The fake's log holds one
    call, the snapshot's, sent with section 2.2's argv, as the configured
    login, with the configured password file and no `PGPASSWORD`, and
    carrying no `commit_write`; no call follows it. Nothing is written: no
    scratch tree, no attempt directory beyond it, and the lane checkout's
    HEAD, status, index and `origin/main` as they were (AT-2, "Unreachable
    (RE), the storage-layer entry"; the delta spec's "Unreachable or refused
    is exit 69 with nothing written")."""
    dead = tmp_path / "dead"
    dead.mkdir()
    socket = dead / ".s.PGSQL.5432"
    psql_error = (f'psql: error: connection to server on socket "{socket}" failed: '
                  f"No such file or directory")
    fake = fake_psql_dir(tmp_path / "fakebin", answers=[
        {"exit": 2, "stderr": psql_error + "\n\tIs the server running locally and accepting "
                                           "connections on that socket?\n"}])
    estate = Estate(tmp_path / "estate")
    copy = flipped(tmp_path)
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    passfile = conf_dir / "pgpass"
    passfile.write_text(f"*:*:*:{WRITER_LOGIN}:{SECRET}\n", encoding="utf-8")
    passfile.chmod(0o600)
    host = quote(dead.as_posix(), safe="")
    conf = primary_config(conf_dir / "lanes-index.conf",
                          f"postgresql://{WRITER_LOGIN}@{host}:5432/lanes_t210",
                          f"postgresql://lanes_r_t210@{host}:5432/lanes_t210", passfile)
    env = index_env(tmp_path, conf, estate.home, **fake)
    env["PATH"] = str(tmp_path / "fakebin") + os.pathsep + _sanitized_path()
    before = estate.state()

    done = projection_entry(copy, env, estate.checkout, tmp_path, "managed-projection",
                            "lanes-edit.sh managed-projection: test 2's storage-layer case")
    snap = done["snapshot"]
    said = snap.stdout + snap.stderr
    assert done["code"] == 69, (f"the storage-layer entry exited {done['code']}, not 69: "
                                f"{snap.stderr}")
    assert done["commit"] is None, "the entry went on to `register commit` after a 69"

    # THE ERROR AND THE STORE, WITHOUT CREDENTIALS (contract section 2.6).
    assert psql_error in snap.stderr, f"stderr does not carry psql's error: {snap.stderr!r}"
    assert SECRET not in said, "a password reached the output"
    assert not re.search(r"postgres(ql)?://", said), f"a URL reached the output: {said!r}"

    # WHAT REACHED THE STORE: the snapshot's one call, and nothing after it.
    calls = fake_calls(fake)
    assert len(calls) == 1, f"{len(calls)} psql calls reached the store, not one: {calls}"
    call = calls[0]
    assert call["argv"] == PSQL_ARGV, call["argv"]
    assert call["url"].startswith(f"postgresql://{WRITER_LOGIN}@"), call["url"]
    assert call["passfile"] == str(passfile) and call["pgpassword"] is False, call
    assert "commit_write" not in call["stdin"], "the snapshot's call carried a commit"

    # NOTHING WRITTEN: no scratch tree, and the lane checkout as it was.
    tree = done["attempt"] / "tree"
    assert not tree.exists() or not any(tree.iterdir()), "a scratch tree was built"
    assert not (done["attempt"] / "snapshot").exists()
    assert estate.state() == before, "the lane checkout changed"
