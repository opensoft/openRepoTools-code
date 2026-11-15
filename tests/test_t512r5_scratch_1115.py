"""T512'S ROUND 5, A SCRATCH PROOF (lane 5, round 1115).

NOT A PERMANENT TEST, and never on T512's branch: it lives on
`scratch/t512r3-proof` alone, beside rounds 3 and 4's modules. The
permanent tests belong to lane 2's T237 module, and lane 2 decides who
writes them. Each case below fails at bb19b1ad and passes on
`l5/007-T512-followup-d12`'s round 5 head. None needs PostgreSQL.

From lane 3's Codex delta review of bb19b1ad, #165 6886976981:
- SHOULD 1: no old answer once a comparison has seen a change, by Codex's
  interleaving, held in place by a hook in the comparison itself;
- SHOULD 2: a queued request answered `unavailable slow` at its own timer,
  and dropped from the queue;
- SHOULD 3: a regular file, a symbolic link, a directory and a live socket
  at a drawn temporary name all survive the start;
- SHOULD 4: agreement on Codex's two shapes within a time bound, and two
  sets of one prefix that differ refused;
- NIT 5: the ending word only for the requests of the take that ended it;
- NIT 6: a leftover that cannot be removed is logged, and the start draws
  another name;
- NIT 8: only contention is a held lock; `EINTR` is retried.
"""

import errno
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
    loader = SourceFileLoader("lanes_index_t512r5_scratch", INDEXER)
    spec = importlib.util.spec_from_loader("lanes_index_t512r5_scratch", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


LI = _load()

GEN = "0f0e0d0c-0b0a-4908-8706-050403020100"
LANES = "lanes/LANES.md"
TEXT = f"text 7 {GEN}\nend\n".encode("ascii")
DIGEST = "a" * 64


# ===================================================== the service's requests

def _service(tmp_path, monkeypatch):
    """A service past its start, under configuration stamp "old", holding a
    child; a re-read gives mode=primary at stamp "new"; `kill` does nothing
    and no child is ever started."""
    svc = object.__new__(LI.RegisterService)
    svc.cond = threading.Condition()
    svc.cfg, svc.store, svc.config_stamp, svc.config_epoch = {"register_rtt_ms": 0}, "old store", "old", 0
    svc.paths = {"log": str(tmp_path / "register.log")}
    svc.child, svc.state, svc.epoch, svc.lazy, svc.retry_at = "old child", "ready", 0, False, 5.0
    svc.queue, svc.fetching, svc.stopping = [], False, ""
    svc.last_used = svc.last_request = time.monotonic()
    svc.install = LI.register_serve_install()
    svc.kill = lambda child: None
    svc.reload_due, svc.idle_check_s, svc.wanted = False, 3600, set()
    svc.asks = svc.taken = 0         # rounds 4 and 5's state; unused before them
    svc.change_ends = None
    svc.config_checking = 0
    svc.connect = lambda epoch: None
    monkeypatch.setattr(LI, "register_serve_load",
                        lambda: ({"mode": "primary", "register_rtt_ms": 0}, "new"))
    monkeypatch.setattr(LI, "PostgresStore", lambda cfg, role: "new store")
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


def _ask(svc, got, name):
    thread = threading.Thread(
        target=lambda: got.__setitem__(name, svc.answer([("file", LANES)], time.monotonic())),
        name=name, daemon=True)
    thread.start()
    return thread


def test_t512r5_s1_no_old_answer_once_a_comparison_has_seen_a_change(tmp_path, monkeypatch):
    """SHOULD 1, Codex's sequence: request A's query is running on the old
    child; request B's comparison finds the changed stamp and, before B can
    ask the worker for it, A's query returns. The hook is the comparison
    itself: B's stamp is a value whose `!=` records that it has compared,
    then holds B there until the case lets it go, so no sleep orders the
    two. At bb19b1ad A is given its old-settings answer."""
    svc = _service(tmp_path, monkeypatch)
    compared, publish, running, release = (threading.Event() for _ in range(4))

    class _SeenThenHeld(str):
        def __ne__(self, other):
            differs = str.__ne__(self, other)
            compared.set()
            publish.wait(5)
            return differs

    def stamp(_cfg):
        name = threading.current_thread().name
        return {"conn-A": "old", "conn-B": _SeenThenHeld("new")}.get(name, "new")

    def query(_job, _deadline):
        running.set()
        release.wait(5)
        return TEXT

    monkeypatch.setattr(LI, "register_serve_config_stamp", stamp)
    svc.query = query
    got = {}
    with _worker(svc):
        conn_a = _ask(svc, got, "conn-A")
        assert running.wait(5), "A's query never ran"
        conn_b = _ask(svc, got, "conn-B")
        assert compared.wait(5), "B never compared"
        release.set()
        conn_a.join(5)
        publish.set()
        conn_b.join(5)
    # A's answer is never the old child's text. Its word is `unavailable`,
    # or `unavailable slow` where its timer ends first, since the hook holds
    # B's check far longer than a real comparison takes.
    assert got.get("conn-A") in (b"unavailable\n", b"unavailable slow\n"), got
    assert got.get("conn-B") == b"unavailable\n", got


def test_t512r5_s2_a_queued_request_is_answered_at_its_own_timer_and_dropped(
        tmp_path, monkeypatch):
    """SHOULD 2: request B waits in the queue behind A's long query. It is
    answered `unavailable slow` within the client's wait, and is no longer
    queued; at bb19b1ad it waits 1.3 s and stays queued."""
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "old")
    running, release = threading.Event(), threading.Event()

    def query(_job, _deadline):
        running.set()
        release.wait(5)
        return TEXT

    svc.query = query
    got = {}
    with _worker(svc):
        conn_a = _ask(svc, got, "conn-A")
        assert running.wait(5), "A's query never ran"
        began = time.monotonic()
        got_b = svc.answer([("file", LANES)], began)
        took = time.monotonic() - began
        with svc.cond:
            queued = list(svc.queue)
        release.set()
        conn_a.join(5)
    share = LI.register_serve_wait_ms(svc.cfg) / 1000
    assert got_b == b"unavailable slow\n" and took < share, (got_b, took, share)
    assert queued == [], queued


def test_t512r5_nit5_the_ending_word_is_for_the_ending_takes_own_requests(tmp_path, monkeypatch):
    """NIT 5, Codex's sequence: A's change, which does not end the service,
    is taken; before A wakes, B asks, and B's change, which does, is taken.
    The case holds the service's lock across both takes, so A cannot wake
    between them. A's change did not end the service: plain `unavailable`.
    At bb19b1ad the flag is the service's, and A says `restarting`."""
    svc = _service(tmp_path, monkeypatch)
    disk = {"stamp": "s1", "cfg": {"mode": "primary", "register_rtt_ms": 0}}
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: disk["stamp"])
    monkeypatch.setattr(LI, "register_serve_load", lambda: (dict(disk["cfg"]), disk["stamp"]))
    got = {}
    conn_a = _ask(svc, got, "conn-A")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with svc.cond:
            if svc.asks == 1:
                break
        time.sleep(0.005)
    with svc.cond:
        svc.take_change()                       # A's change: still primary
        disk["stamp"], disk["cfg"] = "s2", {"mode": "index"}
        svc.asks += 1                           # B asks, as `answer` counts it
        svc.reload_due = True
        svc.take_change()                       # B's change: it ends the service
    conn_a.join(5)
    assert got.get("conn-A") == b"unavailable\n", got
    assert svc.stopping == "its configuration is now mode=index", svc.stopping


# ===================================================== the start

class _Started:
    calls = []

    def __init__(self, *args):
        _Started.calls.append(args)

    def serve(self):
        return 7


def _start_paths(tmp_path, monkeypatch) -> dict:
    monkeypatch.chdir(tmp_path)
    os.mkdir("run", 0o700)
    paths = {key: os.path.join("run", name) for key, name in LI.REGISTER_SERVE_FILES.items()}
    paths["run"] = "run"
    _Started.calls = []
    monkeypatch.setattr(LI, "RegisterService", _Started)
    return paths


def _start(paths) -> int:
    return LI.register_serve_run({"mode": "primary"}, None, paths, ((), ()))


def _log(paths) -> str:
    try:
        with open(paths["log"], encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def test_t512r5_s3_entries_at_a_drawn_name_survive_the_start(tmp_path, monkeypatch):
    """SHOULD 3: the start draws four names, each already taken when it is
    drawn, after the sweep, by an entry it did not make: a regular file, a
    symbolic link, a directory and a live socket; then a free one. All four
    survive, and the start binds the fifth. At bb19b1ad the first bind's
    error path deletes the file, and the start exits 69."""
    paths = _start_paths(tmp_path, monkeypatch)
    with open("target", "wb") as handle:
        handle.write(b"the link's target\n")
    live = []

    def make(name):
        at = os.path.join("run", f"s.{name}")
        if name == "aaaa":
            with open(at, "wb") as handle:
                handle.write(b"a regular file\n")
        elif name == "bbbb":
            os.symlink(os.path.join("..", "target"), at)
        elif name == "cccc":
            os.mkdir(at)
        elif name == "dddd":
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(at)
            sock.listen(1)
            live.append(sock)

    draws, real = iter(["aaaa", "bbbb", "cccc", "dddd", "eeee"]), os.urandom

    def urandom(n):
        if n != 2:
            return real(n)
        name = next(draws)
        make(name)
        return bytes.fromhex(name)

    monkeypatch.setattr(LI.os, "urandom", urandom)
    try:
        got = _start(paths)
        kinds = {name: os.lstat(os.path.join("run", f"s.{name}")).st_mode
                 for name in ("aaaa", "bbbb", "cccc", "dddd")
                 if os.path.lexists(os.path.join("run", f"s.{name}"))}
    finally:
        for sock in live:
            sock.close()
    assert got == 7 and len(_Started.calls) == 1, (got, sorted(os.listdir("run")))
    assert stat.S_ISREG(kinds.get("aaaa", 0)) and stat.S_ISLNK(kinds.get("bbbb", 0)), kinds
    assert stat.S_ISDIR(kinds.get("cccc", 0)) and stat.S_ISSOCK(kinds.get("dddd", 0)), kinds
    with open("target", "rb") as handle:
        assert handle.read() == b"the link's target\n"


def test_t512r5_nit6_a_leftover_that_cannot_be_removed_is_said_and_another_name_drawn(
        tmp_path, monkeypatch):
    """NIT 6: a leftover temporary socket the sweep cannot remove stays, the
    failure is written to `register.log`, and the start that draws its name
    draws another. At bb19b1ad the failure is silent and the start exits 69."""
    paths = _start_paths(tmp_path, monkeypatch)
    left = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    left.bind(os.path.join("run", "s.abcd"))
    left.close()
    real_unlink, real_urandom = os.unlink, os.urandom
    draws = iter(["abcd", "1234"])

    def unlink(path, *args, **kwargs):
        if os.path.basename(path) == "s.abcd":
            raise PermissionError(errno.EPERM, "Operation not permitted", path)
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(LI.os, "unlink", unlink)
    monkeypatch.setattr(LI.os, "urandom",
                        lambda n: bytes.fromhex(next(draws)) if n == 2 else real_urandom(n))
    got = _start(paths)
    log = _log(paths)
    assert got == 7, (got, log)
    assert stat.S_ISSOCK(os.lstat(os.path.join("run", "s.abcd")).st_mode)
    assert "the leftover temporary socket s.abcd could not be removed (EPERM)" in log, log


@pytest.mark.parametrize("fault", ["EINVAL", "EINTR five times"])
def test_t512r5_nit8_only_contention_is_a_held_lock(tmp_path, monkeypatch, fault):
    """NIT 8: an `EINVAL` is a lock that cannot be taken: said, and 69, not
    exit 0 as though a service held it; an `EINTR` is retried at once, and
    five of them still start the service. At bb19b1ad both exit 0 and
    start nothing."""
    paths = _start_paths(tmp_path, monkeypatch)
    real, calls = fcntl.flock, []

    def flock(fd, op):
        calls.append(op)
        if fault == "EINVAL":
            raise OSError(errno.EINVAL, "Invalid argument")
        if len(calls) <= 5:
            raise InterruptedError(errno.EINTR, "Interrupted system call")
        return real(fd, op)

    monkeypatch.setattr(fcntl, "flock", flock)
    got = _start(paths)
    if fault == "EINVAL":
        assert got == LI.EXIT_UNAVAILABLE and _Started.calls == [], (got, calls)
        assert "register.lock could not be locked (EINVAL)" in _log(paths), _log(paths)
    else:
        assert got == 7 and len(_Started.calls) == 1, (got, calls)


# ===================================================== SHOULD 4: agreement's cost

def _timed_agree(records) -> tuple:
    began = time.monotonic()
    agreed = LI.register_serve_agree(records)
    return agreed, time.monotonic() - began


def test_t512r5_s4_agreement_is_near_linear_on_codexs_shapes():
    """SHOULD 4, Codex's two shapes, both valid and far below the bounds:
    1,500 empty sets of one prefix with 1,500 absent names under it; and
    a list of 30,000 paths with 300 empty sets. Each is agreed within a
    bound well above the near-linear check's cost and well below the
    quadratic one's (about 0.33 s and 0.77 s at bb19b1ad on lane 5's host,
    against 0.002 s and 0.024 s at round 5)."""
    shape1 = ([("set", "lanes/", []) for _ in range(1500)]
              + [("absent", f"lanes/n{i:04d}.md") for i in range(1500)])
    listing = [(f"lanes/p/{i:05d}.md", DIGEST) for i in range(30000)]
    shape2 = [("list", "", listing)] + [("set", f"lanes/q{i:03d}/", []) for i in range(300)]
    agreed1, took1 = _timed_agree(shape1)
    agreed2, took2 = _timed_agree(shape2)
    assert agreed1 and took1 < 0.1, took1
    assert agreed2 and took2 < 0.25, took2


def test_t512r5_s4_two_sets_of_one_prefix_that_differ_are_a_mismatch():
    """SHOULD 4, its "reject inconsistent duplicates once": two sets of one
    prefix that name different paths are two views of one transaction that
    disagree. At bb19b1ad, with no list, they pass."""
    member = ("lanes/a.md", DIGEST, b"")
    assert not LI.register_serve_agree([("set", "lanes/", [member]), ("set", "lanes/", [])])
    assert LI.register_serve_agree([("set", "lanes/", [member]), ("set", "lanes/", [member])])
