# SPDX-License-Identifier: Apache-2.0
"""Stand-ins for feature 007's SQL-register tests (L2-0d): the copies and the
stubs of `lanes-index`, and the `psql`s a test puts first on `PATH`.

Test modules import it from `tests/`, as three modules import
`package_layout.py`. What it holds:

- `flipped_copy(source, dest, value)`: `source`, a `lanes-index`, copied to
  `<dest>/lanes-index` with its one `RENDER_GIT_HALF = …` line rewritten to
  `value`, True or False. It takes the constant in either state, so test 14's
  refusing copy still builds once lane 3's T328 sets it True (T277). There is
  no environment override, which would be a production bypass of Q6(c)'s
  refusal (the test plan's open point 3; PC-5). `dest` is a directory, so a
  test copies `lanes-edit.sh` and what it reads beside the copy, where
  `lanes-index` and `lanes-edit.sh` each look for the other.
- `primary_stub(directory)`: a stub `lanes-index` for the bash tests, at
  `<directory>/lanes-index`, that answers `mode` with `primary` and logs every
  call. The contract's whole stub is T207's `contract_stub`.
- `REGISTER_FAKE_PSQL`: the register's fake `psql` (the test plan's section
  3.2), which extends `test_lanes_index.py`'s `FAKE_PSQL`.
- `PSQL_SHIM`: section 3.2's shim in front of the real `psql`, armed per test
  by a control file beside it.

THE FAKE-`psql` HOST RULE (lane 1's L1v4.5:525; #165 6741670709 item 9): the
fake and the shim are made for configurations whose `register_url=` names a
Unix socket or a loopback host (`localhost`, `127.0.0.0/8`, `::1`), or carries
`sslmode=verify-full` with an `sslrootcert=` naming a root file, never
`system`. Lane 1's T104 refuses any other at load (CLI4.5 §2.5), before any
`psql` runs.

THE ARGV LOG: each stub writes `<directory>/lanes-index.argv`, one line per
call, the call's arguments as one JSON array, so a test can assert that the
stub ran and what it was asked.

THE REGISTER'S FAKE `psql`. A test writes `REGISTER_FAKE_PSQL` to `<dir>/psql`,
makes it executable and puts `<dir>` first on `PATH`. Its environment:

- `FAKE_PSQL_LOG` (required) names its log: one JSON object per call, in call
  order, with `FAKE_PSQL`'s fields, `url`, `passfile`, `pgpassword` and
  `stdin`, and these besides:
  - `call`, the call's number in this log, from 1;
  - `argv`, the whole argument list (P1475): what each path sends is the
    test's to assert, and the fake asserts no `VERBOSITY` for the calls the
    design leaves unnamed (the test plan's open point 29);
  - `connect_timeout`, `options` and `service`: `PGCONNECT_TIMEOUT`,
    `PGOPTIONS` (the path's `options=-c lock_timeout=… -c
    statement_timeout=…`) and `PGSERVICE`, each null where it is unset;
  - `pg`: every variable it received whose name begins `PG`, with its value,
    `PGPASSWORD`'s alone recorded as `*`, for T257's inherited-`PG*` cases
    (lane 3's R-PG-1, #165 6747611042).

  `url` is the connection rebuilt from the `PG*` variables, as lane 1's T103
  hands it on, `postgresql://<PGUSER>@<PGHOST>[:<PGPORT>]/<PGDATABASE>`, with
  no port where `PGPORT` is unset, and empty where none of the four is set.
- An argument that is `-d`, `--dbname` or one that holds a connection URL is
  refused: the call is logged with `refused`, and the fake exits 1. No
  register path puts a connection string in an argument list (Y:3491; CLI4.5
  §2.2 and §6).
- `FAKE_PSQL_ANSWERS` (optional) names a JSON file: a list of answers, each
  taught for the calls it names. The first that names a call answers it:
  - it names calls by `call` (that call alone), `from` (every call from that
    one on) and `match` (a text the call's stdin carries), all that it gives
    holding; an answer with none of the three names every call;
  - it answers with `sleep` (seconds, before anything else: a hang past the
    caller's timer), then `stdout` and `stderr`, then `signal` (a name, such
    as `KILL`, that the fake sends itself: a death by a signal) or `exit`
    (default 0).

  So the 69 refusal is `{"call": 1, "exit": 2}`; the retry's shape is
  `{"match": "commit_write", "exit": 3, "stderr": "ERROR:  40001: could not
  serialize access due to concurrent update\\n"}`; and a code taught for exit
  3 is taught as `ERROR:  <SQLSTATE>: <message>`, an LR005 or an LR007 with its
  `DETAIL:  <token>` line after it (section 3.2, "The line it is taught").
- A call no answer names is answered as `FAKE_PSQL` answers it, as an empty
  schema-1 store would, with `FAKE_PSQL_VERSION_FILE` read as it reads it.

THE SHIM. A test writes `PSQL_SHIM` to `<dir>/psql`, makes it executable,
puts `<dir>` first on `PATH`, ahead of the directory of the real `psql`, and
arms it by writing `<dir>/psql-shim.json`. It runs as `python3 -I`, standard
library only. With no control file it hands every call on unchanged. The
control file:

- `psql` (optional): the real `psql` to hand calls to; otherwise the first
  `psql` on `PATH` that is not the shim.
- `arms`: a list, each arm a mode and the calls it applies to. An arm names
  calls by `call` (call k alone), `from` (every call from call k on) or
  `match` (a text the call's script carries, such as `find_write` for a
  lookup try or `commit_write` for a commit call). With `match`, `call` and
  `from` count only the calls that carry the text, so `{"match":
  "commit_write", "call": 2}` is the second commit call. An arm with none of
  the three applies to every call. One test may arm several modes, each on
  its own calls.

The modes, with the keys each takes:

- `window`, `ms`: sleep before handing the call on;
- `before` and `after`: a `pg_terminate_backend(pg_backend_pid())` statement
  before or after the script's last `COMMIT`, joined with psql's `\\;`, so the
  call stays one request. `after` exits 2 once the call has landed; with
  `fifo`, it first blocks on that FIFO;
- `timer`, `ms` or `fifo`: run the real `psql`, then sleep, or block on the
  FIFO in place of the sleep, then answer as `psql` answered;
- `fail-call` (by `call` or `from`) and `fail-match` (by `match`): exit 2,
  sending nothing;
- `edit-entry`, `field` and `value`: rewrite one field of the commit call's
  entry, the `'…'::jsonb` argument of `commit_write(`, before handing the
  call on. `field` may be a dotted path, such as `act.base`, and must exist;
  without `value` the field is removed;
- `no-reconnect`, `as` (`before` or `after`): the first call the arm names
  is lost as that mode loses it, and every later call exits 2, sending
  nothing, as from a host that cannot reconnect;
- `hold`, `fifo`: block on the FIFO before handing the call on. A test's
  `open(fifo, "w")` returns once the call is held, and closing it lets the
  call go;
- `fork`, `fifo`, optional `exit`: start the call in a session of its own
  (`setsid`), where it blocks on the FIFO before it runs the real `psql`, and
  wait for it, so the caller's timer, which kills the shim, never reaches
  the call. With `"exit": true` the shim exits 2 once the fork is made.

Per call, the failures come first (a lost host, then `fail-call` and
`fail-match`), then `edit-entry`, `before` and `after` rewrite the script,
then `hold`, `window`, `fork`, the real `psql`, `after` and `timer`.

The shim writes, beside itself, `psql-shim.log`, one JSON object per call
when the call starts: `call`, `argv`, `stdin`, `sent` (the script as handed
on), `arms` (the modes applied), and the fake's `url`, `passfile`,
`pgpassword` and `pg`; `psql-shim.ends`, one line per call that ended, with
the codes; and its counters in `psql-shim.state`. A control file it cannot
read, an arm it does not know, or an arm that cannot apply to the call it
names (a `before` on a call with no `COMMIT`, an `edit-entry` field that is
not there) ends the call with exit 1 and `psql-shim: …` on stderr, recorded
in the log as `error`, sending nothing.

STANDARD LIBRARY ONLY, AND NOTHING FROM THE SUITE: no `conftest`, no pytest,
so the module loads the same way under pytest and under a task's
`python3 -I -c` verify, on Python 3.9 and up. Each script it writes is
standard library only too.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: THE CODE ROOT: the parent of this file's `tests/`, and the `lanes-index` in
#: it, which `flipped_copy` copies.
REPO = Path(__file__).resolve().parent.parent
LANES_INDEX = REPO / "lanes-index"

#: Q6(c)'S CONSTANT, AS `lanes-index` SPELLS IT (lane 1's T105): one line,
#: `RENDER_GIT_HALF = False` until lane 3's T328 sets it True.
RENDER_GIT_HALF_LINE = re.compile(rb"^RENDER_GIT_HALF = (True|False)$", re.M)

#: The name of each stub's argv log, beside the stub.
ARGV_LOG = "lanes-index.argv"

#: The shim's own files, beside it.
PSQL_SHIM_CONTROL = "psql-shim.json"
PSQL_SHIM_LOG = "psql-shim.log"
PSQL_SHIM_ENDS = "psql-shim.ends"

#: The shim's ten modes (the test plan's section 3.2).
PSQL_SHIM_MODES = ("window", "before", "after", "timer", "fail-call", "fail-match",
                   "edit-entry", "no-reconnect", "hold", "fork")


def flipped_copy(source, dest, value) -> Path:
    """Copy the `lanes-index` at `source` to `<dest>/lanes-index`, its
    `RENDER_GIT_HALF` line rewritten to `value`, and return the copy's path.

    The copy is the source's bytes but that one line, with the executable bit.
    `dest` is made if it is missing. A source with no such line, or with more
    than one, is refused, so a test never runs a copy it did not flip."""
    if not isinstance(value, bool):
        raise TypeError(f"flipped_copy: value must be True or False, not {value!r}")
    text = Path(source).read_bytes()
    found = RENDER_GIT_HALF_LINE.findall(text)
    if len(found) != 1:
        raise ValueError(f"flipped_copy: {source} holds {len(found)} `RENDER_GIT_HALF = ` "
                         f"lines, not one")
    directory = Path(dest)
    directory.mkdir(parents=True, exist_ok=True)
    copy = directory / "lanes-index"
    copy.write_bytes(RENDER_GIT_HALF_LINE.sub(b"RENDER_GIT_HALF = " + str(value).encode(), text))
    copy.chmod(0o755)
    return copy


#: THE STUB FOR THE BASH TESTS (R2's S8): a Python script a test runs by its
#: path. `mode` alone is answered, `primary`; anything else is not stubbed,
#: and ends 64 with that said, so a test sees what reached it.
_PRIMARY_STUB = r'''#!/usr/bin/env python3
# A STUB lanes-index (feature 007, L2-0d): it answers `mode` with `primary`
# and logs every call, one JSON array of arguments per line. Nothing else is
# stubbed here: the contract's whole stub is contract_stub (T207).
import json, sys

with open(ARGV_LOG_PATH, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1:] == ["mode"]:
    sys.stdout.write("primary\n")
    sys.exit(0)
sys.stderr.write("lanes-index: this stub answers only `mode`: %s\n" % json.dumps(sys.argv[1:]))
sys.exit(64)
'''


def primary_stub(directory) -> Path:
    """Write `<directory>/lanes-index`, the stub that answers `mode` with
    `primary` and logs every call to `<directory>/lanes-index.argv`, and
    return its path. `directory` is made if it is missing."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "lanes-index"
    log = str((directory / ARGV_LOG).resolve())
    stub.write_text(_PRIMARY_STUB.replace("ARGV_LOG_PATH", repr(log)), encoding="utf-8")
    stub.chmod(0o755)
    return stub


REGISTER_FAKE_PSQL = r'''#!/usr/bin/env python3
# The REGISTER's FAKE psql (feature 007, L2-0d; the test plan's section 3.2).
# It extends test_lanes_index.py's FAKE_PSQL: it records what FAKE_PSQL
# records, the URL (rebuilt from the PG* variables), PGPASSFILE, whether
# PGPASSWORD is set, and stdin, and also the call's number, the whole argv,
# PGCONNECT_TIMEOUT, PGOPTIONS, PGSERVICE and every PG* variable it received.
# A test may teach it an answer per call (FAKE_PSQL_ANSWERS); otherwise it
# answers as FAKE_PSQL does. No database exists. It asserts no VERBOSITY.
import fcntl, json, os, signal, sys, time

log = os.environ["FAKE_PSQL_LOG"]
answers = os.environ.get("FAKE_PSQL_ANSWERS", "")
vfile = os.environ.get("FAKE_PSQL_VERSION_FILE", "")
version = open(vfile).read().strip() if vfile else "1"
args = sys.argv[1:]
stdin = sys.stdin.read()
env = os.environ
url = ""
if any(env.get(k) for k in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER")):
    url = "postgresql://%s@%s%s/%s" % (env.get("PGUSER", ""), env.get("PGHOST", ""),
                                      ":" + env["PGPORT"] if env.get("PGPORT") else "",
                                      env.get("PGDATABASE", ""))
record = {"url": url, "passfile": env.get("PGPASSFILE", ""), "pgpassword": "PGPASSWORD" in env,
          "stdin": stdin, "argv": args, "connect_timeout": env.get("PGCONNECT_TIMEOUT"),
          "options": env.get("PGOPTIONS"), "service": env.get("PGSERVICE"),
          "pg": {k: ("*" if k == "PGPASSWORD" else v) for k, v in sorted(env.items())
                 if k.startswith("PG")}}
# NO CONNECTION STRING IN THE ARGUMENTS (Y:3491; CLI4.5 section 2.2 and 6).
refused = [a for a in args if a == "--dbname" or a.startswith("--dbname=") or
           (a.startswith("-d") and not a.startswith("--")) or
           "postgresql://" in a or "postgres://" in a]
if refused:
    record["refused"] = "a connection string or -d in the arguments: %s" % json.dumps(refused)
with open(log, "a+", encoding="utf-8") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    handle.seek(0)
    call = sum(1 for _ in handle) + 1
    record = dict({"call": call}, **record)
    handle.write(json.dumps(record) + "\n")
if refused:
    sys.stderr.write("psql: error: the fake refuses %s\n" % record["refused"])
    sys.exit(1)


def taught():
    if not answers:
        return None
    with open(answers, encoding="utf-8") as handle:
        rules = json.load(handle)
    for rule in rules:
        if "call" in rule and rule["call"] != call:
            continue
        if "from" in rule and call < rule["from"]:
            continue
        if "match" in rule and rule["match"] not in stdin:
            continue
        return rule
    return None


rule = taught()
if rule is not None:
    if rule.get("sleep"):
        time.sleep(float(rule["sleep"]))
    sys.stdout.write(rule.get("stdout", ""))
    sys.stderr.write(rule.get("stderr", ""))
    sys.stdout.flush()
    sys.stderr.flush()
    if rule.get("signal"):
        os.kill(os.getpid(), getattr(signal, "SIG" + rule["signal"]))
        time.sleep(5)
    sys.exit(int(rule.get("exit", 0)))
if vfile and "CREATE TABLE IF NOT EXISTS" in stdin:
    with open(vfile, "w") as handle:
        handle.write("1\n")


def echo(text):
    # `\echo` AS psql's OWN LEXER READS IT (opensoft/openRepoTools#166 item 4;
    # psqlscanslash.l's `xslashquote`), as test_lanes_index.py's FAKE_PSQL
    # reads it: words split on blanks, a quoted run taken whole, and inside
    # the quotes `''`, `\n \t \b \r \f`, octal `\ooo` and hex `\xhh` decoded.
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
    elif line.startswith("\\echo"):
        print(echo(line[len("\\echo"):]))
sys.exit(0)
'''


PSQL_SHIM = r'''#!/usr/bin/env -S python3 -I
# THE PSQL SHIM (feature 007, L2-0d; the test plan's section 3.2): one
# `python3 -I` script, standard library only, in front of the REAL psql, armed
# per test by psql-shim.json beside it. Its modes: window, before, after,
# timer, fail-call, fail-match, edit-entry, no-reconnect, hold and fork.
# tests/sql_register_helpers.py's docstring is its manual.
import fcntl, json, os, re, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.join(HERE, "psql-shim.json")
LOG = os.path.join(HERE, "psql-shim.log")
ENDS = os.path.join(HERE, "psql-shim.ends")
STATE = os.path.join(HERE, "psql-shim.state")
LOCK = os.path.join(HERE, "psql-shim.lock")
MODES = ("window", "before", "after", "timer", "fail-call", "fail-match", "edit-entry",
         "no-reconnect", "hold", "fork")
KEYS = {"mode", "call", "from", "match", "ms", "fifo", "exit", "field", "value", "as"}
NEEDS = {"window": ("ms",), "hold": ("fifo",), "fork": ("fifo",), "edit-entry": ("field",),
         "no-reconnect": ("as",), "fail-match": ("match",)}
TERMINATE = "SELECT pg_terminate_backend(pg_backend_pid())"
COMMIT = re.compile(r"\bCOMMIT\b[ \t]*;?", re.I)
ENTRY = re.compile(r"'((?:[^']|'')*)'::jsonb")


class ShimError(Exception):
    pass


def arm_key(arm):
    return json.dumps(arm, sort_keys=True)


def check(arms):
    if not isinstance(arms, list):
        raise ShimError("`arms` is not a list")
    for arm in arms:
        if not isinstance(arm, dict) or arm.get("mode") not in MODES:
            raise ShimError("an arm with no mode of %s: %s" % (", ".join(MODES), json.dumps(arm)))
        unknown = sorted(set(arm) - KEYS)
        if unknown:
            raise ShimError("an arm with keys it does not know, %s: %s"
                            % (", ".join(unknown), json.dumps(arm)))
        for key in NEEDS.get(arm["mode"], ()):
            if key not in arm:
                raise ShimError("a `%s` arm needs `%s`: %s" % (arm["mode"], key, json.dumps(arm)))
        if arm["mode"] == "timer" and "ms" not in arm and "fifo" not in arm:
            raise ShimError("a `timer` arm needs `ms` or `fifo`: %s" % json.dumps(arm))
        if arm["mode"] == "no-reconnect" and arm["as"] not in ("before", "after"):
            raise ShimError("a `no-reconnect` arm's `as` is `before` or `after`: %s"
                            % json.dumps(arm))


def names(arm, call, script, state):
    # Whether `arm` names this call. With `match`, `call` and `from` count the
    # calls that carry the text (the count is kept in the state, per arm).
    number = call
    if "match" in arm:
        if arm["match"] not in script:
            return False
        seen = state.setdefault("seen", {})
        number = seen[arm_key(arm)] = seen.get(arm_key(arm), 0) + 1
    if "call" in arm and number != arm["call"]:
        return False
    if "from" in arm and number < arm["from"]:
        return False
    return True


def terminate(script, where):
    found = list(COMMIT.finditer(script))
    if not found:
        raise ShimError("`%s`: the call's script has no COMMIT" % where)
    m = found[-1]
    if where == "before":
        return script[:m.start()] + TERMINATE + " \\; " + script[m.start():]
    statement = script[m.start():m.end()].rstrip(" \t;")
    return script[:m.start()] + statement + " \\; " + TERMINATE + ";" + script[m.end():]


def edit_entry(script, arm):
    at = script.find("commit_write(")
    if at < 0:
        raise ShimError("`edit-entry`: the call carries no commit_write(")
    m = ENTRY.search(script, at)
    if not m:
        raise ShimError("`edit-entry`: no '...'::jsonb entry after commit_write(")
    try:
        entry = json.loads(m.group(1).replace("''", "'"))
        path = arm["field"].split(".")
        node = entry
        for key in path[:-1]:
            node = node[key]
        if path[-1] not in node:
            raise KeyError(path[-1])
    except (ValueError, KeyError, TypeError) as exc:
        raise ShimError("`edit-entry`: the entry has no field %s (%s)" % (arm["field"], exc))
    if "value" in arm:
        node[path[-1]] = arm["value"]
    else:
        del node[path[-1]]
    text = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).replace("'", "''")
    return script[:m.start()] + "'" + text + "'::jsonb" + script[m.end():]


def real_psql(control):
    if control.get("psql"):
        return control["psql"]
    me = os.path.realpath(__file__)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory or ".", "psql")
        if os.path.realpath(candidate) == me:
            continue
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise ShimError("no real psql on PATH behind the shim, and the control file names none")


def block(fifo):
    with open(fifo, "rb") as handle:
        handle.read()


def append(path, record):
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(record) + "\n")


def connection():
    env = os.environ
    url = ""
    if any(env.get(k) for k in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER")):
        url = "postgresql://%s@%s%s/%s" % (env.get("PGUSER", ""), env.get("PGHOST", ""),
                                          ":" + env["PGPORT"] if env.get("PGPORT") else "",
                                          env.get("PGDATABASE", ""))
    return {"url": url, "passfile": env.get("PGPASSFILE", ""), "pgpassword": "PGPASSWORD" in env,
            "pg": {k: ("*" if k == "PGPASSWORD" else v) for k, v in sorted(env.items())
                   if k.startswith("PG")}}


def relay(out, err):
    sys.stdout.buffer.write(out)
    sys.stderr.buffer.write(err)
    sys.stdout.flush()
    sys.stderr.flush()


def text(data):
    return data.decode("utf-8", "surrogateescape")


def main():
    args = sys.argv[1:]
    raw = sys.stdin.buffer.read()
    script = text(raw)
    record = {"argv": args, "stdin": script}
    record.update(connection())
    error = ""
    chosen, lost = [], False
    with open(LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(STATE, encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError:
            state = {}
        call = state["calls"] = state.get("calls", 0) + 1
        record = dict({"call": call}, **record)
        try:
            try:
                with open(CONTROL, encoding="utf-8") as handle:
                    control = json.load(handle)
            except FileNotFoundError:
                control = {}
            except ValueError as exc:
                raise ShimError("the control file is not JSON: %s" % exc)
            arms = control.get("arms", [])
            check(arms)
            chosen = [arm for arm in arms if names(arm, call, script, state)]
            if state.get("lost") and call > state["lost"]:
                lost = True
            for arm in chosen:
                if arm["mode"] == "no-reconnect" and not state.get("lost"):
                    state["lost"] = call
        except ShimError as exc:
            error = str(exc)
        with open(STATE + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(STATE + ".tmp", STATE)
        modes = [arm["mode"] for arm in chosen]
        failing = [arm for arm in chosen if arm["mode"] in ("fail-call", "fail-match")]
        sent = script
        if not error and not lost and not failing:
            try:
                for arm in chosen:
                    if arm["mode"] == "edit-entry":
                        sent = edit_entry(sent, arm)
                for arm in chosen:
                    if arm["mode"] in ("before", "after"):
                        sent = terminate(sent, arm["mode"])
                    elif arm["mode"] == "no-reconnect" and state.get("lost") == call:
                        sent = terminate(sent, arm["as"])
                psql = real_psql(control)
            except ShimError as exc:
                error = str(exc)
        record.update({"sent": sent, "arms": modes})
        if error:
            record["error"] = error
        if lost:
            record["lost"] = True
        append(LOG, record)
    if error:
        sys.stderr.write("psql-shim: %s\n" % error)
        append(ENDS, {"call": call, "exit": 1, "error": error})
        return 1
    if lost or failing:
        why = "no-reconnect" if lost else failing[0]["mode"]
        sys.stderr.write("psql: error: connection to server failed: psql-shim %s (call %d)\n"
                         % (why, call))
        append(ENDS, {"call": call, "exit": 2, "failed": why})
        return 2
    for arm in chosen:
        if arm["mode"] == "hold":
            block(arm["fifo"])
    for arm in chosen:
        if arm["mode"] == "window":
            time.sleep(float(arm["ms"]) / 1000)
    after = [arm for arm in chosen if arm["mode"] == "after" or
             (arm["mode"] == "no-reconnect" and arm["as"] == "after" and state.get("lost") == call)]
    forks = [arm for arm in chosen if arm["mode"] == "fork"]
    data = sent.encode("utf-8", "surrogateescape")
    if forks:
        code, out, err = fork(forks[0], psql, args, data, call)
        if code is None:
            append(ENDS, {"call": call, "exit": 2, "forked": True})
            return 2
    else:
        proc = subprocess.run([psql] + args, input=data, capture_output=True)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    for arm in after:
        if arm.get("fifo"):
            block(arm["fifo"])
    for arm in chosen:
        if arm["mode"] == "timer":
            if arm.get("fifo"):
                block(arm["fifo"])
            else:
                time.sleep(float(arm["ms"]) / 1000)
    relay(out, err)
    exit_code = 2 if after else code
    append(ENDS, {"call": call, "exit": exit_code, "psql": code})
    return exit_code


def fork(arm, psql, args, data, call):
    # The call in a session of its own, blocked on the FIFO before the real
    # psql runs; its answer goes to a file, never to the shim's pipes, which
    # the caller may have stopped reading.
    result = os.path.join(HERE, "psql-shim.fork-%d.json" % call)
    pid = os.fork()
    if pid == 0:
        code = 70
        try:
            os.setsid()
            null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
            os.closerange(3, 1024)
            block(arm["fifo"])
            proc = subprocess.run([psql] + args, input=data, capture_output=True)
            code = proc.returncode
            with open(result + ".tmp", "w", encoding="utf-8") as handle:
                json.dump({"exit": code, "stdout": text(proc.stdout),
                           "stderr": text(proc.stderr)}, handle)
            os.replace(result + ".tmp", result)
            append(ENDS, {"call": call, "exit": code, "fork": os.getpid()})
        finally:
            os._exit(code)
    if arm.get("exit"):
        return None, b"", b""
    os.waitpid(pid, 0)
    with open(result, encoding="utf-8") as handle:
        answer = json.load(handle)
    return (answer["exit"], answer["stdout"].encode("utf-8", "surrogateescape"),
            answer["stderr"].encode("utf-8", "surrogateescape"))


def finish(code):
    # A psql that died by a signal: the shim dies by the same one, so the
    # caller reads a death by a signal, as it would from psql itself.
    if code < 0:
        try:
            signal.signal(-code, signal.SIG_DFL)
        except (OSError, ValueError):
            pass
        os.kill(os.getpid(), -code)
        time.sleep(5)
    sys.exit(code)


finish(main())
'''
