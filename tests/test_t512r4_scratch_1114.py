"""T512'S ROUND 4, A SCRATCH PROOF (lane 5, round 1114e).

NOT A PERMANENT TEST, and never on T512's branch: it lives on
`scratch/t512r3-proof` alone, beside round 3's module. The permanent tests
belong to lane 2's T237 module, and lane 2 decides who writes them. Each
case below that names a change fails at f21ca4a7 and passes on
`l5/007-T512-followup-d12`'s head; each case named "control" passes at
both, and guards what must not move. None needs PostgreSQL.

- N5 (lane 1's U5 gate, #165 6881993079): a temporary socket left by a
  start killed between its bind and its rename is removed under the lock,
  so a later start that draws its name binds.
- N8 (the same): each distinct request line is planned once.
- NIT-A (lane 1, #165 6883749855): a `take_change` that finds no
  difference wakes the waiting request; a request that sees a change while
  the worker is busy is answered within the client's wait.
- The waiting request's word (lane 5's review of round 3, NIT 2):
  `unavailable restarting` only where the worker has found that the change
  ends the service.
- NIT-B (lane 5's review, NIT 4; lane 1): `serve`'s lock attempt is
  retried over about 100 ms.
"""

import fcntl
import importlib.util
import os
import socket
import stat
import threading
import time
from importlib.machinery import SourceFileLoader

import pytest

INDEXER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lanes-index")


def _load():
    loader = SourceFileLoader("lanes_index_t512r4_scratch", INDEXER)
    spec = importlib.util.spec_from_loader("lanes_index_t512r4_scratch", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


LI = _load()

GEN = "0f0e0d0c-0b0a-4908-8706-050403020100"
LANES = "lanes/LANES.md"


# ===================================================== the start: N5 and NIT-B

class _Started:
    """`RegisterService` replaced: the start reached the service, which
    answers 7 at once and runs nothing."""

    calls = []

    def __init__(self, *args):
        _Started.calls.append(args)

    def serve(self):
        return 7


def _start_paths(tmp_path, monkeypatch) -> dict:
    """`run/` and its files, by relative paths under the case's own
    directory, so the socket's path is short; and the service replaced."""
    monkeypatch.chdir(tmp_path)
    os.mkdir("run", 0o700)
    paths = {key: os.path.join("run", name) for key, name in LI.REGISTER_SERVE_FILES.items()}
    paths["run"] = "run"
    _Started.calls = []
    monkeypatch.setattr(LI, "RegisterService", _Started)
    return paths


def _draw(monkeypatch, name: str) -> None:
    """The start's two random bytes for its temporary name, fixed."""
    real = os.urandom
    monkeypatch.setattr(LI.os, "urandom", lambda n: bytes.fromhex(name) if n == 2 else real(n))


def _leave_socket(path: str) -> None:
    """A socket at `path` with no listener, as a start killed after its bind
    leaves it."""
    left = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    left.bind(path)
    left.close()


def _start(paths) -> int:
    return LI.register_serve_run({"mode": "primary"}, None, paths, ((), ()))


def test_t512r4_n5_a_start_that_draws_a_leftovers_name_binds(tmp_path, monkeypatch):
    """N5: at f21ca4a7 the bind meets the leftover at its own name, and the
    start exits 69."""
    paths = _start_paths(tmp_path, monkeypatch)
    _leave_socket("run/s.abcd")
    _draw(monkeypatch, "abcd")
    got = _start(paths)
    assert got == 7 and len(_Started.calls) == 1, (got, _Started.calls)
    assert stat.S_ISSOCK(os.lstat(paths["sock"]).st_mode)


def test_t512r4_n5_a_leftover_temporary_socket_is_removed(tmp_path, monkeypatch):
    """N5: a leftover the start does not draw is removed too, so none is
    kept for good."""
    paths = _start_paths(tmp_path, monkeypatch)
    _leave_socket("run/s.9f9f")
    _draw(monkeypatch, "1234")
    assert _start(paths) == 7
    assert not os.path.lexists("run/s.9f9f"), sorted(os.listdir("run"))


def test_t512r4_n5_control_other_names_and_files_not_sockets_are_left(tmp_path, monkeypatch):
    paths = _start_paths(tmp_path, monkeypatch)
    _leave_socket("run/t.abcd")
    _leave_socket("run/s.abcde")
    _leave_socket("run/s.ABCD")
    with open("run/s.beef", "wb") as handle:
        handle.write(b"not a socket\n")
    _draw(monkeypatch, "1234")
    assert _start(paths) == 7
    assert {"t.abcd", "s.abcde", "s.ABCD", "s.beef"} <= set(os.listdir("run")), os.listdir("run")


def test_t512r4_nitb_a_lock_held_for_a_moment_is_waited_for(tmp_path, monkeypatch):
    """NIT-B: the first attempt lands while a failing `serve` holds the lock
    for its stamp; at f21ca4a7 this start exits 0 and starts nothing."""
    paths = _start_paths(tmp_path, monkeypatch)
    real, attempts = fcntl.flock, []

    def flock(fd, op):
        attempts.append(op)
        if len(attempts) == 1:
            raise BlockingIOError(11, "Resource temporarily unavailable")
        return real(fd, op)

    monkeypatch.setattr(fcntl, "flock", flock)
    got = _start(paths)
    assert got == 7 and len(_Started.calls) == 1, (got, attempts)


def test_t512r4_nitb_control_a_lock_held_throughout_exits_0_and_starts_nothing(
        tmp_path, monkeypatch):
    paths = _start_paths(tmp_path, monkeypatch)
    holder = os.open(paths["lock"], os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        got = _start(paths)
    finally:
        os.close(holder)
    assert got == LI.EXIT_OK and _Started.calls == [], (got, _Started.calls)
    assert not os.path.lexists(paths["sock"])


# ===================================================== N8: each distinct line once

def test_t512r4_n8_each_distinct_line_is_planned_once(tmp_path, monkeypatch):
    """N8: five `list` lines check each path's name once, not five times,
    and four lines of one log name scan the listing once; each line is
    still answered, in order."""
    listing = {f"lanes/log/k{i}.md": (f"{i:064x}", 1) for i in range(3)}
    listing[LANES] = ("f" * 64, 1)
    counts = {"name": 0, "scan": 0}
    real_ok, real_ci = LI.register_serve_name_ok, LI.register_log_path_ci

    def name_ok(path):
        counts["name"] += 1
        return real_ok(path)

    def scan(*args, **kwargs):
        counts["scan"] += 1
        return real_ci(*args, **kwargs)

    monkeypatch.setattr(LI, "register_serve_name_ok", name_ok)
    monkeypatch.setattr(LI, "register_log_path_ci", scan)
    svc = object.__new__(LI.RegisterService)
    svc.cond, svc.paths, svc.wanted, svc.images = threading.Condition(), {
        "log": str(tmp_path / "register.log")}, set(), {}
    nobody = "lanes/log/nobody.md"
    items = [("list", ""), ("file", nobody)] * 4 + [("list", "")]
    got = svc.text(items, {"listing": listing, "head": 7, "generation": GEN}, {}, [])
    paths = sorted(listing, key=os.fsencode)
    block = f"list {len(paths)}\n".encode("ascii") + b"".join(
        LI.register_serve_list_line(path, listing[path][0]) for path in paths)
    absent = f"absent {nobody}\n".encode("ascii")
    want = f"text 7 {GEN}\n".encode("ascii") + (block + absent) * 4 + block + b"end\n"
    assert got == want, got[:200]
    assert counts == {"name": len(listing), "scan": 1}, counts


# ===================================================== NIT-A and the word: the waiting request

def _service(tmp_path, state="ready"):
    """A service past its start, under configuration stamp "old", holding a
    child; `kill` does nothing; no child is ever started."""
    svc = object.__new__(LI.RegisterService)
    svc.cond = threading.Condition()
    svc.cfg, svc.store, svc.config_stamp, svc.config_epoch = {"register_rtt_ms": 0}, "old store", "old", 0
    svc.paths = {"log": str(tmp_path / "register.log")}
    svc.child, svc.state, svc.epoch, svc.lazy, svc.retry_at = "old child", state, 0, False, 5.0
    svc.queue, svc.fetching, svc.stopping = [], False, ""
    svc.last_used = svc.last_request = time.monotonic()
    svc.install = LI.register_serve_install()
    svc.kill = lambda child: None
    svc.reload_due, svc.idle_check_s, svc.wanted = False, 3600, set()
    svc.asks = svc.taken = 0        # the head's round 4 state; unused at f21ca4a7
    svc.change_ends = False
    svc.config_checking = 0         # round 5's state (Codex SHOULD 1); unused before it
    svc.connect = lambda epoch: None
    return svc


class _worker:
    def __init__(self, svc):
        self.svc = svc
        self.thread = threading.Thread(target=svc.work, name="the-worker", daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.thread

    def __exit__(self, *args):
        self.svc.stop("the case is done")
        self.thread.join(5)


def _timed_answer(svc) -> tuple:
    began = time.monotonic()
    got = svc.answer([("file", LANES)], began)
    return got, time.monotonic() - began


def test_t512r4_nita_a_change_the_worker_finds_gone_wakes_the_request(tmp_path, monkeypatch):
    """NIT-A: the request sees a change; by the time the worker looks, the
    file has changed back. At f21ca4a7 no epoch moves and nothing wakes the
    request, which waits out its limit, its timer plus 1.1 s."""
    svc = _service(tmp_path)
    looks = iter(["new"])
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: next(looks, "old"))
    loads = []
    monkeypatch.setattr(LI, "register_serve_load", lambda: loads.append(1))
    with _worker(svc):
        got, took = _timed_answer(svc)
    assert got == b"unavailable\n" and took < 0.6, (got, took)
    assert (svc.config_epoch, loads) == (0, []), (svc.config_epoch, loads)


def test_t512r4_nita_a_change_seen_while_the_worker_is_busy_is_answered_within_the_clients_wait(
        tmp_path, monkeypatch):
    """NIT-A: the worker is in a whole-file fetch, up to 11 s, and takes no
    change before it ends. The request is answered `unavailable` within the
    client's wait, 300 ms here; at f21ca4a7 it holds its slot 1.3 s. M1: the
    change is left asked of the worker; the connection re-reads nothing."""
    svc = _service(tmp_path, state="busy")
    svc.fetching = True
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    loads = []
    monkeypatch.setattr(LI, "register_serve_load", lambda: loads.append(1))
    got, took = _timed_answer(svc)
    share = LI.register_serve_wait_ms(svc.cfg) / 1000
    assert got == b"unavailable\n" and took < share, (got, took, share)
    assert (svc.reload_due, svc.config_epoch, loads) == (True, 0, []), (svc.reload_due, loads)


@pytest.mark.parametrize("cause", ["idle for 900 s", "a signal: 15", "its worker ended"])
def test_t512r4_word_a_stop_of_another_cause_during_the_wait_is_plain_unavailable(
        tmp_path, monkeypatch, cause):
    """NIT 2: the service stops during the wait for a cause that is not the
    change. At f21ca4a7 the request is told `unavailable restarting`."""
    svc = _service(tmp_path)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    stopper = threading.Timer(0.05, svc.stop, args=(cause,))
    stopper.start()
    try:
        got, _took = _timed_answer(svc)
    finally:
        stopper.join(5)
    assert got == b"unavailable\n" and svc.stopping == cause, (got, svc.stopping)


def test_t512r4_word_control_a_change_that_ends_the_service_is_restarting(tmp_path, monkeypatch):
    """NIT 2: the worker takes the change within the wait and finds that it
    ends the service: `unavailable restarting`, and the service stops."""
    svc = _service(tmp_path)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    monkeypatch.setattr(LI, "register_serve_load", lambda: ({"mode": "index"}, "new"))
    with _worker(svc):
        got, _took = _timed_answer(svc)
        deadline = time.monotonic() + 2
        while not svc.stopping and time.monotonic() < deadline:
            time.sleep(0.01)
        stopping = svc.stopping
    assert got == b"unavailable restarting\n", got
    assert stopping == "its configuration is now mode=index", stopping
