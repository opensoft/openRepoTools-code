# SPDX-License-Identifier: Apache-2.0
"""The real-engine fixture's switch, `OPENREPOTOOLS_REQUIRE_PG` (#165, L2-0b).

THE TEST PLAN'S SECTION 3.3, ITS FOUR CASES. `tests/pgcluster.py` gives the
tests that need a real PostgreSQL 16 their cluster, and `tests/conftest.py`
registers it from its `pytest_configure`. The switch decides what a missing
engine is:

  * unset or `0`, a SKIP of every real-engine test, whose reason names
    `PG_BIN` and the package `postgresql-16`, loud even under `-q`;
  * `1`, as CI sets it, a REFUSAL of the whole run before any test starts:
    pytest's own `UsageError`, exit 4, even where the run selects no
    real-engine test (the refusal is eager);
  * anything else, a refusal too, as `OPENREPOTOOLS_COMPOSED` refuses a
    value that is neither.

EACH CASE RUNS A CHILD PYTEST, since a refusal ends the session that makes it.
The child is `python -m pytest` on this suite's own `conftest.py`, with no
`OPENREPOTOOLS_*`, `PG*` or `PYTEST_ADDOPTS` of the outer run, and with only
what the case sets. Its real-engine test is a PROBE written into the case's
own temporary directory, which asks for `pg`, one database cloned from the
session's template: the suite holds no such test of its own until the
template's tasks land, and a case must not wait for one.

A REAL-ENGINE TEST IS ONE WHOSE FIXTURE CLOSURE HOLDS `pg_engine`, the
session fixture through which every cluster of `tests/pgcluster.py` finds its
binaries, or skips, or fails. A test asks for `pg`, `pg_cluster`,
`stoppable_cluster` or a cluster built on them, and the closure pytest
computes from their definitions reaches `pg_engine`. So the last case reads
pytest's public `fixturenames`, and a cluster fixture added later is held to
the rule by depending on `pg_engine`, as each one must to find the binaries.

Until `tests/conftest.py` registers the plugin, each case FAILS on its own
assertion: the probe's `pg` is a fixture nobody defines, so the child errors
where it should refuse or skip, and the filter's check cannot see the probe.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from conftest import REPO

#: The variable, as `tests/pgcluster.py` and `tests.yml` spell it.
SWITCH = "OPENREPOTOOLS_REQUIRE_PG"

#: THIS MODULE AND ITS SUITE: the child loads the `conftest.py` beside it.
THIS = Path(__file__).resolve()
SUITE = THIS.parent

#: The fixture every cluster finds its binaries through.
ENGINE_FIXTURE = "pg_engine"

#: THE `guard-launch-mode` JOB'S FILTER, as `tests.yml` runs it:
#: `bash tests/run.sh -k '<filter>'`. The job is the launch contract's own,
#: and a real-engine test it selected would turn it into a database job.
LAUNCH_JOB_FILTER = "guard_launch_mode or repo_hygiene"

#: THE PROBE: one real-engine test, written by this module into a case's
#: temporary directory. Its function's name holds the launch job's first word,
#: so that job's filter selects it, and its module's name holds `PROBE_WORD`,
#: which selects it alone where a case runs it.
PROBE_MODULE = "test_engine_probe.py"
PROBE_TEST = "test_guard_launch_mode_sees_this_real_engine_probe"
PROBE_WORD = "engine_probe"
PROBE_SOURCE = f'''# A real-engine test, written by tests/test_sql_register_fixture.py.


def {PROBE_TEST}(pg):
    assert pg.name
'''

#: A PLUGIN FOR THE CHILD'S COLLECTION, loaded by `-p`: every item the
#: collection keeps, its path, and whether its fixture closure holds
#: `ENGINE_FIXTURE`, one JSON line each, in the file `$ENGINE_REPORT` names.
REPORTER_MODULE = "engine_report"
REPORTER_SOURCE = f'''import json
import os


def pytest_collection_finish(session):
    with open(os.environ["ENGINE_REPORT"], "w", encoding="utf-8") as report:
        for item in session.items:
            names = getattr(item, "fixturenames", ())
            report.write(json.dumps({{"nodeid": item.nodeid, "path": str(item.path),
                                     "engine": {ENGINE_FIXTURE!r} in names}}) + "\\n")
'''


def shown(proc: subprocess.CompletedProcess) -> str:
    return (f"exit {proc.returncode}\n--- stdout ---\n{proc.stdout[-4000:]}"
            f"\n--- stderr ---\n{proc.stderr[-4000:]}")


def write_probe(tmp_path: Path) -> Path:
    directory = tmp_path / "probe"
    directory.mkdir()
    probe = directory / PROBE_MODULE
    probe.write_text(PROBE_SOURCE, encoding="utf-8")
    return probe


def no_engine(tmp_path: Path) -> Path:
    """An empty directory for `PG_BIN`: a named `PG_BIN` is final, so it is a
    missing engine on a host that has one, CI's runners among them."""
    directory = tmp_path / "no-engine"
    directory.mkdir()
    return directory


def child(tmp_path: Path, args: list, switch=None, pg_bin=None,
          extra_env=None) -> subprocess.CompletedProcess:
    """`python -m pytest -q` on `args`, from the case's temporary directory,
    with `switch` and `pg_bin` as the only switch and `PG_BIN` it sees."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("OPENREPOTOOLS_", "PG"))
           and key not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if switch is not None:
        env[SWITCH] = switch
    if pg_bin is not None:
        env["PG_BIN"] = str(pg_bin)
    env.update(extra_env or {})
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
               f"--basetemp={tmp_path / 'child-basetemp'}",
               f"--rootdir={SUITE.parent}", *args]
    return subprocess.run(command, cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, timeout=900,
                          check=False)


def probe_run(tmp_path: Path, probe: Path, *options: str, **kwargs):
    """The probe alone: this module is collected beside it, so the child
    loads this suite's `conftest.py`, and `-k` keeps only the probe."""
    return child(tmp_path, [*options, "-k", PROBE_WORD, str(THIS), str(probe)],
                 **kwargs)


def test_the_engine_switch_turns_a_missing_engine_into_a_failure(tmp_path):
    """`OPENREPOTOOLS_REQUIRE_PG=1` with `PG_BIN` naming an empty directory:
    pytest exits 4 before the probe runs, and says why, naming the switch and
    the `PG_BIN` it could not use (section 3.3; the probe's b1, b8 and b9).
    Exit 4 alone is not enough: a missing file is a usage error too."""
    empty = no_engine(tmp_path)
    proc = probe_run(tmp_path, write_probe(tmp_path), switch="1", pg_bin=empty)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 4, (
        f"{SWITCH}=1 with no engine must refuse the run, exit 4:\n{shown(proc)}")
    assert f"{SWITCH}=1" in output and f"PG_BIN={empty}" in output, (
        f"the refusal names neither the switch nor the PG_BIN it could not "
        f"use:\n{shown(proc)}")
    assert PROBE_TEST not in output, f"the probe ran:\n{shown(proc)}"


def test_without_the_switch_a_missing_engine_skips_naming_pg_bin_and_postgresql_16(
        tmp_path):
    """The switch unset, and at `0`, with `PG_BIN` naming an empty directory:
    the probe SKIPS, the run exits 0, and the skip's reason names `PG_BIN`
    and the package `postgresql-16` (the probe's a1 and b10). The child runs
    `-q` with no `-rs`, as the `tests` job does, and its output names both
    too, since a skip a person cannot read is a skip nobody audits."""
    empty = no_engine(tmp_path)
    probe = write_probe(tmp_path)
    for switch in (None, "0"):
        label = "unset" if switch is None else f"at {switch}"
        junit = tmp_path / f"probe-{label.replace(' ', '-')}.xml"
        proc = probe_run(tmp_path, probe, f"--junitxml={junit}",
                         switch=switch, pg_bin=empty)
        assert proc.returncode == 0, (
            f"with the switch {label}, a missing engine must skip, exit 0:\n"
            f"{shown(proc)}")
        cases = {case.get("name"): case for case in
                 ElementTree.parse(str(junit)).getroot().iter("testcase")}
        assert PROBE_TEST in cases, f"the probe did not run:\n{shown(proc)}"
        skipped = cases[PROBE_TEST].find("skipped")
        assert skipped is not None, (
            f"with the switch {label}, the probe did not skip:\n{shown(proc)}")
        reason = (skipped.get("message") or "") + (skipped.text or "")
        for word in ("PG_BIN", "postgresql-16"):
            assert word in reason, (
                f"with the switch {label}, the skip's reason names no "
                f"{word}: {reason}")
            assert word in proc.stdout, (
                f"with the switch {label}, the -q output names no {word}, so "
                f"the tests job's log would not show why:\n{shown(proc)}")


def test_the_engine_switch_refuses_a_value_that_is_not_0_or_1(tmp_path):
    """A value that is neither `1` nor `0` (nor unset) is pytest's usage
    error, exit 4, naming the variable and the value, before any engine is
    looked for (the probe's b3). `true` and `yes` are what a person might
    write; neither is `1`."""
    probe = write_probe(tmp_path)
    for value in ("2", "yes", "true"):
        proc = probe_run(tmp_path, probe, switch=value)
        output = proc.stdout + proc.stderr
        assert proc.returncode == 4, (
            f"{SWITCH}={value!r} must be refused, exit 4:\n{shown(proc)}")
        assert f"{SWITCH}={value!r}" in output, (
            f"the refusal of {SWITCH}={value!r} does not name it:\n"
            f"{shown(proc)}")
        assert PROBE_TEST not in output, f"the probe ran:\n{shown(proc)}"


def test_no_real_engine_test_is_selected_by_the_launch_jobs_filter(tmp_path):
    """L2-0b's hygiene rule: the `guard-launch-mode` job's `-k` selects no
    real-engine test. The child collects this whole suite as the job does,
    with the job's own filter, which pytest matches against each test's
    function, class, module and parametrize id, case-insensitively, so every
    test any later task adds is held to it. The probe, which the filter
    selects on purpose, shows that the check sees a real-engine test; it
    cannot, until the plugin defines `pg`."""
    workflow = (REPO / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8")
    assert f"bash tests/run.sh -k '{LAUNCH_JOB_FILTER}'" in workflow, (
        f"tests.yml no longer runs `bash tests/run.sh -k "
        f"'{LAUNCH_JOB_FILTER}'`: this case must follow the job's filter")
    probe = write_probe(tmp_path)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / f"{REPORTER_MODULE}.py").write_text(REPORTER_SOURCE,
                                                   encoding="utf-8")
    report = tmp_path / "selected.jsonl"
    path = os.pathsep.join([str(plugins), *filter(None, [os.environ.get(
        "PYTHONPATH")])])
    proc = child(tmp_path, ["--collect-only", "-p", REPORTER_MODULE,
                            "-k", LAUNCH_JOB_FILTER, str(SUITE), str(probe)],
                 switch="0",
                 extra_env={"ENGINE_REPORT": str(report), "PYTHONPATH": path})
    assert proc.returncode == 0 and report.is_file(), shown(proc)
    rows = [json.loads(line) for line in
            report.read_text(encoding="utf-8").splitlines()]
    probes = [row for row in rows if Path(row["path"]).resolve() == probe.resolve()]
    assert probes and all(row["engine"] for row in probes), (
        f"the filter selected the probe, a test that asks for `pg`, and its "
        f"fixture closure holds no `{ENGINE_FIXTURE}`: this check cannot see "
        f"a real-engine test, so it would pass whatever the suite held. "
        f"The probe's rows: {probes}")
    suite = [row for row in rows
             if Path(row["path"]).resolve().is_relative_to(SUITE)]
    assert suite, (f"the launch job's filter selects nothing in {SUITE}:\n"
                   f"{shown(proc)}")
    offenders = sorted(row["nodeid"] for row in suite if row["engine"])
    assert not offenders, (
        f"`-k '{LAUNCH_JOB_FILTER}'`, the guard-launch-mode job's filter, "
        f"selects {len(offenders)} real-engine test(s); rename each so that "
        f"no part of its id holds either word: {offenders}")


# ---------------------------------------------------------------- T229's relay
#: THE DELAYED-LOOPBACK RELAY'S OWN TEST (T229; R-P23), before the cases that
#: use it: `tests/pgcluster.py`'s `delayed_loopback(target_port, delay_s)`.
#: `[each-direction]`, `[clean-close]` and `[no-root]` run on a loopback
#: peer of the standard library, so they need no engine; `[tls-untouched]`
#: checks the bytes on such a peer, then asks for T229's TLS cluster for its
#: `verify-full` connect and query, and skips with T205's banner without one.
RELAY_DELAY = 0.2
RELAY_CASES = ["each-direction", "tls-untouched", "clean-close", "no-root"]


def _peer(handler):
    """A loopback server for one connection: `handler(conn, seen)` in a
    thread. Returns (port, thread, seen)."""
    server = socket.create_server(("127.0.0.1", 0))
    seen: dict = {}

    def run():
        try:
            conn, _ = server.accept()
            with conn:
                handler(conn, seen)
        finally:
            server.close()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return server.getsockname()[1], thread, seen


def _read_all(sock, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


def _relay_each_direction(relay_of):
    def handler(conn, seen):
        conn.recv(1)
        seen["up"] = time.monotonic()
        seen["sent"] = time.monotonic()
        conn.sendall(b"d")
    port, thread, seen = _peer(handler)
    with relay_of(port, RELAY_DELAY) as relay:
        with socket.create_connection(("127.0.0.1", relay.port), timeout=10) as client:
            sent = time.monotonic()
            client.sendall(b"u")
            assert client.recv(1) == b"d"
            down = time.monotonic()
        thread.join(10)
    assert seen["up"] - sent >= RELAY_DELAY, f"the first byte up came {seen['up'] - sent:.3f} s after it was sent"
    assert down - seen["sent"] >= RELAY_DELAY, f"the first byte down came {down - seen['sent']:.3f} s after it was sent"
    assert seen["up"] - sent < RELAY_DELAY + 5 and down - seen["sent"] < RELAY_DELAY + 5, seen


def _relay_tls_untouched(relay_of, request):
    up, down = os.urandom(200_000), os.urandom(100_000)

    def handler(conn, seen):
        seen["up"] = _read_all(conn, len(up))
        conn.sendall(down)
    port, thread, seen = _peer(handler)
    with relay_of(port, 0.01) as relay:
        with socket.create_connection(("127.0.0.1", relay.port), timeout=30) as client:
            client.sendall(up)
            got = _read_all(client, len(down))
        thread.join(30)
    assert seen.get("up") == up, "the bytes the relay delivered up are not the bytes it was sent"
    assert got == down, "the bytes the relay delivered down are not the bytes it was sent"
    tls = request.getfixturevalue("tls_cluster")
    with relay_of(tls.port, 0.01) as relay:
        env = dict(tls.client_env(), PGPORT=str(relay.port))
        proc = subprocess.run([tls.tool("psql"), "-X", "-A", "-t", "-c",
                               "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"],
                              capture_output=True, text=True, env=env, timeout=60, check=False)
    assert (proc.returncode, proc.stdout.strip()) == (0, "t"), (
        f"a verify-full connect and query through the relay: {shown(proc)}")


def _relay_clean_close(relay_of):
    for first in ("client", "peer"):
        def handler(conn, seen, first=first):
            if first == "peer":
                conn.close()
                return
            seen["eof"] = conn.recv(1)
        port, thread, seen = _peer(handler)
        with relay_of(port, RELAY_DELAY) as relay:
            client = socket.create_connection(("127.0.0.1", relay.port), timeout=10)
            if first == "client":
                client.close()
                thread.join(10)
                assert seen.get("eof") == b"", "the client's close did not reach the peer"
            else:
                assert client.recv(1) == b"", "the peer's close did not reach the client"
                client.close()
            end = time.monotonic() + 5
            while relay.sockets and time.monotonic() < end:
                time.sleep(0.05)
            assert not relay.sockets, f"[{first} first] the relay still holds {len(relay.sockets)} socket(s)"
        assert relay.alive() == [], f"[{first} first] the relay's threads outlive it: {relay.alive()}"


NO_ROOT_CHILD = """
import json, socket, sys, threading
sys.path.insert(0, sys.argv[1])
import pgcluster
server = socket.create_server(("127.0.0.1", 0))
def echo():
    conn, _ = server.accept()
    with conn:
        conn.sendall(conn.recv(16))
threading.Thread(target=echo, daemon=True).start()
with pgcluster.delayed_loopback(server.getsockname()[1], 0.05) as relay:
    with socket.create_connection(("127.0.0.1", relay.port), timeout=10) as client:
        client.sendall(b"no-root")
        said = client.recv(16)
status = open("/proc/self/status").read()
cap = [line.split()[1] for line in status.splitlines() if line.startswith("CapEff:")]
print(json.dumps({"uid": __import__("os").geteuid(), "cap": cap[0] if cap else None, "said": said.decode()}))
"""


def _relay_no_root():
    if os.geteuid() == 0:
        pytest.skip("[no-root] shows the relay needs no capability, and this run is root")
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", NO_ROOT_CHILD, str(SUITE)],
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, shown(proc)
    said = json.loads(proc.stdout.strip().splitlines()[-1])
    assert said["said"] == "no-root", said
    assert said["uid"] == os.getuid(), f"the relay ran as uid {said['uid']}, not the job's {os.getuid()}"
    if said["cap"] is not None:
        assert int(said["cap"], 16) == 0, f"the relay's process holds capabilities {said['cap']}"


@pytest.mark.parametrize("case", RELAY_CASES)
def test_the_delayed_loopback_relay_delays_each_direction_and_passes_tls_through(request, case):
    """T229's relay (R-P23): `[each-direction]`, each direction's first byte
    arrives no sooner than the delay after it was sent, on a monotonic
    clock; `[tls-untouched]`, the bytes it delivers each way equal the bytes
    it was sent, and a `verify-full` connect and a query through it to the
    TLS cluster succeed (R2f-S11); `[clean-close]`, a close on either side
    closes the other, and leaves no thread or socket of the relay's;
    `[no-root]`, a process with no added capability, under the job's own
    uid, starts and uses it."""
    import pgcluster
    relay_of = getattr(pgcluster, "delayed_loopback", None)
    assert relay_of is not None, "tests/pgcluster.py has no delayed_loopback: T229 builds it"
    if case == "each-direction":
        _relay_each_direction(relay_of)
    elif case == "tls-untouched":
        _relay_tls_untouched(relay_of, request)
    elif case == "clean-close":
        _relay_clean_close(relay_of)
    else:
        _relay_no_root()
