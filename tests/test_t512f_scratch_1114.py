"""T512'S DRAFT-12 FOLLOW-UP, A SCRATCH PROOF (lane 5, round r1114c).

NOT A PERMANENT TEST, and never on T512's branch: it lives on
`scratch/t512f-proof` alone. The permanent tests belong to lane 2's T237
module, and lane 2 decides who writes them. Each case below that names a
change fails at 396003a1 and passes on `l5/007-T512-followup-d12`'s head;
each case named "(control)" passes at both, and guards what must not move.

- B3, one view of each path (socket API 13.4, 13.7's row and 5.3, draft 12):
  `register_serve_parse` refuses an answer whose items disagree as "a
  mismatch", and the client then writes `.direct` alone and reads directly.
- The per-request timer (socket API 6.2, draft 12; Y:4012-4016): `SIGINT`,
  `unavailable slow` at once, and the kill only where the request's marker
  has not come within 100 ms more.
- OP-17 (b) (lane 3's ruling, #165 6879724890, point 1): an owner file the
  client cannot read, or with no `install=`, or no line for the client's
  own pid namespace or boot, is unavailable, and the client starts none.
- SHOULD 4 (point 3): the service counts the answer as it builds it, and
  answers `unavailable` at the first record past 16,777,216 bytes.
- SHOULD 5 (point 4): a connection past the cap is closed with no answer.
"""

import hashlib
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import tracemalloc
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

INDEXER = Path(__file__).resolve().parents[1] / "lanes-index"


def _load():
    loader = SourceFileLoader("lanes_index_t512f_scratch", str(INDEXER))
    spec = importlib.util.spec_from_loader("lanes_index_t512f_scratch", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


LI = _load()

GEN = "0f0e0d0c-0b0a-4908-8706-050403020100"
LANES = "lanes/LANES.md"
ALIASES = "lanes/aliases.tsv"


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _file(path: str, body: bytes) -> bytes:
    return f"file {path} {_sha(body)} {len(body)}\n".encode("ascii") + body + b"\n"


def _list(*entries) -> bytes:
    lines = [f"list {len(entries)}\n".encode("ascii")]
    for path, body in sorted(entries, key=lambda e: e[0].encode("ascii")):
        lines.append(f"path {path} {_sha(body)}\n".encode("ascii"))
    return b"".join(lines)


def _set(prefix: str, *members) -> bytes:
    out = [f"set {prefix} {len(members)}\n".encode("ascii")]
    for path, body in sorted(members, key=lambda m: m[0].encode("ascii")):
        out.append(_file(path, body))
    return b"".join(out)


def _answer(*items: bytes) -> bytes:
    return f"text 7 {GEN}\n".encode("ascii") + b"".join(items) + b"end\n"


R, R2, A, X, Y, L, L2 = (b"# LANES\n", b"# LANES, other\n", b"a\tb\n", b"x\n", b"y\n",
                         b"log\n", b"log, other\n")

# ============================================== B3: one view of each path

#: (items, answer) whose items disagree, each "a mismatch" (13.4; 13.7's row).
MISMATCHES = {
    "one path with two digests, a file record and the list": (
        [("file", LANES), ("list", "")],
        _answer(_file(LANES, R), _list((LANES, R2)))),
    "a file record's path that the list lacks": (
        [("file", LANES), ("list", "")],
        _answer(_file(LANES, R), _list((ALIASES, A)))),
    "a set short of the list's paths under its prefix": (
        [("list", ""), ("set", "lanes/archive/")],
        _answer(_list(("lanes/archive/x.md", X), ("lanes/archive/y.md", Y)),
                _set("lanes/archive/", ("lanes/archive/x.md", X)))),
    "a set member that the list lacks": (
        [("list", ""), ("set", "lanes/archive/")],
        _answer(_list(("lanes/archive/x.md", X)),
                _set("lanes/archive/", ("lanes/archive/x.md", X), ("lanes/archive/y.md", Y)))),
    "absent where the list holds the log in another case": (
        [("list", ""), ("file", "lanes/log/a.md")],
        _answer(_list(("lanes/log/A.md", L)), b"absent lanes/log/a.md\n")),
    "absent aliases where the list holds them": (
        [("list", ""), ("file", ALIASES)],
        _answer(_list((ALIASES, A)), b"absent lanes/aliases.tsv\n")),
    "ambiguous where the list holds one match": (
        [("list", ""), ("file", "lanes/log/a.md")],
        _answer(_list(("lanes/log/a.md", L)), b"ambiguous lanes/log/a.md\n")),
    "a file record where the list holds two matches": (
        [("list", ""), ("file", "lanes/log/a.md")],
        _answer(_list(("lanes/log/A.md", L2), ("lanes/log/a.md", L)),
                _file("lanes/log/a.md", L))),
    "absent where the set that covers the name holds it": (
        [("set", "lanes/log/"), ("file", "lanes/log/a.md")],
        _answer(_set("lanes/log/", ("lanes/log/a.md", L)), b"absent lanes/log/a.md\n")),
    "a set member and a file record with two digests": (
        [("set", "lanes/log/"), ("file", "lanes/log/a.md")],
        _answer(_set("lanes/log/", ("lanes/log/a.md", L)), _file("lanes/log/a.md", L2))),
}

#: (items, answer) whose items agree, each taken (control).
AGREEING = {
    "form 3's shape, a log in another case and one absent": (
        [("file", LANES), ("list", ""), ("set", "lanes/archive/"), ("file", ALIASES),
         ("file", "lanes/log/a.md"), ("file", "lanes/log/b.md")],
        _answer(_file(LANES, R),
                _list((LANES, R), (ALIASES, A), ("lanes/archive/x.md", X), ("lanes/log/A.md", L)),
                _set("lanes/archive/", ("lanes/archive/x.md", X)), _file(ALIASES, A),
                _file("lanes/log/A.md", L), b"absent lanes/log/b.md\n")),
    "form 1's --all with a named log": (
        [("file", LANES), ("set", "lanes/log/"), ("file", "lanes/log/c.md")],
        _answer(_file(LANES, R), _set("lanes/log/", ("lanes/log/C.md", L), ("lanes/log/d.md", L2)),
                _file("lanes/log/C.md", L))),
    "form 2, no list and no set": (
        [("file", LANES), ("file", ALIASES), ("file", "lanes/log/a.md")],
        _answer(_file(LANES, R), b"absent lanes/aliases.tsv\n", _file("lanes/log/a.md", L))),
    "ambiguous where the list holds two matches": (
        [("list", ""), ("file", "lanes/log/a.md")],
        _answer(_list(("lanes/log/A.md", L2), ("lanes/log/a.md", L)),
                b"ambiguous lanes/log/a.md\n")),
}


@pytest.mark.parametrize("case", sorted(MISMATCHES))
def test_t512f_b3_an_answer_whose_items_disagree_is_a_mismatch(case):
    items, data = MISMATCHES[case]
    with pytest.raises(LI.RegisterServeMalformed) as raised:
        LI.register_serve_parse(data, items)
    assert str(raised.value) == "a mismatch", str(raised.value)


@pytest.mark.parametrize("case", sorted(AGREEING))
def test_t512f_b3_control_an_answer_whose_items_agree_is_taken(case):
    items, data = AGREEING[case]
    assert LI.register_serve_parse(data, items)["kind"] == "text"


def test_t512f_b3_the_client_discards_a_mismatch_writes_direct_alone_and_reads_directly(
        tmp_path, monkeypatch):
    """Form 1, `--files register,paths`: the service's answer names
    `lanes/LANES.md` with one digest in its file record and another in the
    list. The client takes it as `unavailable`: it writes `.direct` and no
    cache file, and returns (None, True), so its caller reads directly."""
    items, data = MISMATCHES["one path with two digests, a file record and the list"]
    monkeypatch.setattr(LI, "register_serve_ask", lambda _data, _deadline: ("answer", data, False))
    cache = tmp_path / "c"
    cache.mkdir()
    opts = {"form": 1, "members": {"register", "paths"}, "all": False, "keys": set(),
            "cache": str(cache / "fam")}
    assert LI.register_read_request(opts)[0] == items
    got = LI.register_read_ask({}, opts)
    assert got == (None, True), got
    assert sorted(os.listdir(cache)) == ["fam.direct"], os.listdir(cache)


# ============================================== the per-request timer

#: A STAND-IN FOR THE HELD `psql`, reading the service's lines on its stdin:
#: a query line holding `SLOW` runs until `SIGINT` (`answers`), or for 5 s
#: with `SIGINT` ignored (`silent`); each `\warn` line prints the service's
#: marker on stderr with `57014` after a cancelled query, else `00000`; in
#: `late`, that marker comes 80 ms after the `SIGINT`. It logs each line.
FAKE_PSQL = r'''
import os, signal, sys, time
mode, log = sys.argv[1], sys.argv[2]
hit = [False]
def on_int(_sig, _frame):
    hit[0] = True
signal.signal(signal.SIGINT, signal.SIG_IGN if mode == "silent" else on_int)
cancelled = False
while True:
    line = sys.stdin.buffer.readline()
    if not line:
        break
    with open(log, "ab") as handle:
        handle.write(line)
    if line.startswith(b"\\warn"):
        nonce = line.split(b"LANES-SERVE ", 1)[1].split(b"'", 1)[0]
        state = b"57014" if cancelled else b"00000"
        cancelled = False
        if state == b"57014" and mode == "late":
            time.sleep(0.08)
        sys.stderr.buffer.write(b"\x1eLANES-SERVE " + nonce + b" " + state + b"\n")
        sys.stderr.buffer.flush()
    elif b"SLOW" in line:
        hit[0] = False
        end = time.monotonic() + 5
        while not hit[0] and time.monotonic() < end:
            time.sleep(0.002)
        cancelled = hit[0]
'''


def _fake_service(tmp_path, mode: str):
    script = tmp_path / "fake_psql.py"
    script.write_text(FAKE_PSQL, encoding="utf-8")
    log = tmp_path / f"psql-{mode}.log"
    child = subprocess.Popen([sys.executable, "-I", str(script), mode, str(log)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    svc = object.__new__(LI.RegisterService)
    svc.cond = threading.Condition()
    svc.cfg = {}
    svc.paths = {"log": str(tmp_path / "register.log")}
    svc.child, svc.state, svc.epoch, svc.lazy, svc.stopping = child, "busy", 0, False, ""
    # READY FIRST: its `SIGINT` handler is set before any `SIGINT` can come.
    ready = svc.exchange(child, b"\\warn '\\036LANES-SERVE ready' :SQLSTATE\n", "ready",
                         time.monotonic() + 10)
    assert ready[0] == "ok", ready
    return svc, child, log


QUERY = b"SELECT SLOW;\n\\warn '\\036LANES-SERVE q-1' :SQLSTATE\n"


def test_t512f_timer_a_child_whose_marker_comes_after_sigint_is_kept_and_rolled_back(tmp_path):
    """6.2: on expiry `SIGINT`, then the kill only where the marker has not
    come within 100 ms more. The stand-in prints it at once after its
    `SIGINT`, so the service keeps it, rolls the cancelled transaction back,
    and answers `slow`."""
    svc, child, log = _fake_service(tmp_path, "answers")
    try:
        status, _out, _state = svc.run(QUERY, "q-1", time.monotonic() + 0.2)
        alive = child.poll() is None
        kept = svc.child is child
        lines = log.read_bytes().splitlines() if log.exists() else []
    finally:
        LI.RegisterService.kill(child, signal.SIGTERM)
    assert status == "slow", status
    assert alive and kept, f"the child was killed though its marker came: alive {alive}, kept {kept}"
    assert any(line.startswith(b"ROLLBACK") for line in lines), lines


def test_t512f_timer_control_a_child_whose_marker_never_comes_is_killed(tmp_path):
    """6.2 (control): a child that ignores `SIGINT` and prints no marker
    within 100 ms is killed, and the next request starts another."""
    svc, child, _log = _fake_service(tmp_path, "silent")
    try:
        status, _out, _state = svc.run(QUERY, "q-1", time.monotonic() + 0.2)
        time.sleep(0.1)
        dead = child.poll() is not None
    finally:
        LI.RegisterService.kill(child, signal.SIGTERM)
    assert status == "slow" and dead and svc.child is None, (status, dead, svc.child)


def test_t512f_timer_unavailable_slow_is_answered_at_expiry_not_after_the_100_ms(tmp_path):
    """6.2: "On expiry the service sends `SIGINT` to `psql`, which cancels
    the query, and answers `unavailable slow`"; the wait for the marker
    comes after. The stand-in prints its marker 80 ms after its `SIGINT`:
    the request is answered at the expiry, and the wait runs on past it."""
    svc, child, _log = _fake_service(tmp_path, "late")
    told = []
    deadline = time.monotonic() + 0.2
    try:
        svc.run(QUERY, "q-1", deadline, expired=lambda: told.append(time.monotonic()))
        ended = time.monotonic()
    finally:
        LI.RegisterService.kill(child, signal.SIGTERM)
    assert len(told) == 1, told
    assert told[0] - deadline < 0.05, f"answered {told[0] - deadline:.3f} s after the expiry"
    assert ended - told[0] >= 0.06, f"the marker's wait ended {ended - told[0]:.3f} s after"


# ============================================== OP-17 (b): the owner file

ASK = b"read 1\nfile lanes/LANES.md\nend\n"
ANSWERED = _answer(_file(LANES, R))


@pytest.fixture
def socket_at_the_fixed_path(tmp_path, monkeypatch):
    """A socket of the case's own in a 0700 `run/`, reached by a short
    relative path from the case's directory, so that no state path is too
    long for `bind()`: it records each request and answers `ANSWERED`."""
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    run.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    paths = {key: str(run / name) for key, name in LI.REGISTER_SERVE_FILES.items()}
    paths["sock"], paths["run"] = "run/register.sock", str(run)
    monkeypatch.setattr(LI, "register_serve_paths", lambda: dict(paths))
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(paths["sock"])
    server.listen(8)
    server.settimeout(0.1)
    got, stop = [], threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            conn.settimeout(1.0)
            data = b""
            try:
                while b"\nend\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                if data:
                    conn.sendall(ANSWERED)
            except OSError:
                pass
            got.append(data)
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield paths, got
    stop.set()
    thread.join(2)
    server.close()


def _owner_lines() -> list:
    return LI.register_serve_owner_text("2026-11-14T00:00:00Z").decode("utf-8").splitlines()


def _owner(paths: dict, lines: list) -> None:
    LI._register_serve_write(paths["owner"], ("\n".join(lines) + "\n").encode("utf-8"))


def test_t512f_op17_control_a_whole_owner_file_of_this_install_is_asked(socket_at_the_fixed_path):
    paths, got = socket_at_the_fixed_path
    _owner(paths, _owner_lines())
    kind, payload, start = LI.register_serve_ask(ASK, time.monotonic() + 2)
    assert (kind, payload, start) == ("answer", ANSWERED, False), (kind, payload, start)
    assert got == [ASK], got


def _unreadable(paths):
    _owner(paths, _owner_lines())
    os.chmod(paths["owner"], 0)


OWNER_CASES = {
    "absent": lambda paths: None,
    "not UTF-8": lambda paths: LI._register_serve_write(paths["owner"],
                                                        b"pid=1\ninstall=\xff\xfe\n"),
    "unreadable": _unreadable,
    "no install line": lambda paths: _owner(paths, [line for line in _owner_lines()
                                                    if not line.startswith("install=")]),
    "no pidns line": lambda paths: _owner(paths, [line for line in _owner_lines()
                                                  if not line.startswith("pidns=")]),
    "no boot line": lambda paths: _owner(paths, [line for line in _owner_lines()
                                                 if not line.startswith("boot=")]),
}


@pytest.mark.parametrize("case", sorted(OWNER_CASES))
def test_t512f_op17_an_owner_file_the_client_cannot_use_is_unavailable_and_starts_none(
        socket_at_the_fixed_path, case):
    paths, got = socket_at_the_fixed_path
    host = LI.register_serve_host()
    if case == "no pidns line" and "pidns" not in host:
        pytest.skip("this host gives no pid namespace")
    if case == "no boot line" and "boot" not in host:
        pytest.skip("this host gives no boot id")
    if case == "unreadable" and os.getuid() == 0:
        pytest.skip("root reads a mode-0 file")
    OWNER_CASES[case](paths)
    kind, _payload, start = LI.register_serve_ask(ASK, time.monotonic() + 2)
    time.sleep(0.2)
    assert (kind, start) == ("unavailable", False), (kind, start, _payload)
    assert not any(got), f"the client sent its request: {got}"


# ============================================== SHOULD 4: counted as built

def _text_service(tmp_path, images: dict):
    svc = object.__new__(LI.RegisterService)
    svc.cond = threading.Condition()
    svc.paths = {"log": str(tmp_path / "register.log")}
    svc.wanted = set()
    svc.bring = lambda snap, held, needed, replay: ({path: images[path] for path in needed}, [])
    return svc


def _snap(images: dict) -> dict:
    return {"listing": {path: (_sha(body), True) for path, body in images.items()},
            "head": 7, "generation": GEN}


def test_t512f_should4_the_answer_stops_at_the_first_record_past_16_mib(tmp_path, monkeypatch):
    """Four logs of 6 MiB: the third record carries the answer past
    16,777,216 bytes. The service answers `unavailable` there, with the
    fixed phrase, and never builds the fourth record; and it never copies a
    body while it builds, so what it allocates stays far under one body."""
    images = {f"lanes/log/{key}.md": bytes([65 + i]) * (6 << 20) for i, key in enumerate("abcd")}
    svc = _text_service(tmp_path, images)
    built = []
    real = LI._register_serve_record

    def counting(path, digest, data):
        built.append(path)
        return real(path, digest, data)

    monkeypatch.setattr(LI, "_register_serve_record", counting)
    items = [("file", path) for path in sorted(images)]
    tracemalloc.start()
    try:
        got = svc.text(items, _snap(images), {}, [])
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert got == b"unavailable\n", got[:80]
    assert len(built) <= 3, f"records built past the bound: {built}"
    assert peak < (4 << 20), f"{peak} bytes allocated while the answer was built"
    log = (tmp_path / "register.log").read_text(encoding="utf-8")
    assert log.endswith(" an answer over 16 MB: unavailable\n"), log


def _one_log_answer(size: int) -> tuple:
    body = b"z" * size
    images = {"lanes/log/a.md": body}
    return images, _answer(_file("lanes/log/a.md", body))


def test_t512f_should4_control_an_answer_of_exactly_16_mib_is_sent_and_one_byte_more_is_not(
        tmp_path):
    head = len(f"text 7 {GEN}\n") + len("end\n") + 1
    size = LI.REGISTER_SERVE_ANSWER_MAX - head - len(f"file lanes/log/a.md {'0' * 64} 16777000\n")
    images, whole = _one_log_answer(size)
    assert len(whole) == LI.REGISTER_SERVE_ANSWER_MAX
    assert _text_service(tmp_path, images).text([("file", "lanes/log/a.md")], _snap(images), {},
                                                 []) == whole
    images, whole = _one_log_answer(size + 1)
    assert len(whole) == LI.REGISTER_SERVE_ANSWER_MAX + 1
    assert _text_service(tmp_path, images).text([("file", "lanes/log/a.md")], _snap(images), {},
                                                 []) == b"unavailable\n"


def test_t512f_should4_control_a_small_answer_is_byte_for_byte_as_before(tmp_path):
    images = {LANES: R, ALIASES: A, "lanes/archive/x.md": X, "lanes/log/A.md": L,
              "lanes/log/B.md": L2, "lanes/log/b.md": L}
    items = [("file", LANES), ("list", ""), ("set", "lanes/archive/"), ("file", ALIASES),
             ("file", "lanes/log/a.md"), ("file", "lanes/log/b.md"), ("file", "lanes/log/z.md")]
    want = _answer(_file(LANES, R), _list(*images.items()),
                   _set("lanes/archive/", ("lanes/archive/x.md", X)), _file(ALIASES, A),
                   _file("lanes/log/A.md", L), b"ambiguous lanes/log/b.md\n",
                   b"absent lanes/log/z.md\n")
    assert _text_service(tmp_path, images).text(items, _snap(images), {}, []) == want


# ============================================== SHOULD 5: the connection cap

def test_t512f_should5_a_connection_past_the_cap_is_closed_with_no_answer(tmp_path, monkeypatch):
    """The cap's connections are held, each waiting for its request (here
    `w_s` is 5.2 s); one more is closed at once with no answer; and once
    they close, a new one is held again."""
    cap = getattr(LI, "REGISTER_SERVE_CONNECTIONS_MAX", 16)
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    monkeypatch.chdir(tmp_path)
    paths = {key: str(run / name) for key, name in LI.REGISTER_SERVE_FILES.items()}
    paths["sock"], paths["run"] = "run/register.sock", str(run)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(paths["sock"])
    server.listen(64)
    svc = LI.RegisterService({"register_rtt_ms": 5000}, None, paths, server,
                             os.lstat(paths["sock"]).st_ino, ((), ()))
    svc.begin = lambda: None
    svc.end = lambda: None
    result = {}

    def client():
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(paths["sock"])
        return conn

    def held_or(conn, wait: float):
        conn.settimeout(wait)
        try:
            return conn.recv(100)
        except socket.timeout:
            return "held"

    def drive():
        try:
            held = [client() for _ in range(cap)]
            time.sleep(1.0)
            extra = client()
            result["extra"] = held_or(extra, 2.0)
            result["held"] = [held_or(conn, 0.05) for conn in held]
            for conn in held + [extra]:
                conn.close()
            time.sleep(0.6)
            again = client()
            result["again"] = held_or(again, 0.5)
            again.close()
        finally:
            svc.stop("the case is done")

    handlers = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    thread = threading.Thread(target=drive, daemon=True)
    thread.start()
    try:
        svc.serve()
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        thread.join(10)
        server.close()
    assert result.get("held") == ["held"] * cap, result
    assert result.get("extra") == b"", f"the connection past the cap of {cap}: {result}"
    assert result.get("again") == "held", result
