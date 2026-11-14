"""T512'S ROUND 3, A SCRATCH PROOF (lane 5, round 1114e).

NOT A PERMANENT TEST, and never on T512's branch: it lives on
`scratch/t512r3-proof` alone. The permanent tests belong to lane 2's T237
module, and lane 2 decides who writes them. Each case below that names a
change fails at 88b50886 and passes on `l5/007-T512-followup-d12`'s head;
each case named "control" passes at both, and guards what must not move.
None needs PostgreSQL.

- B2 (socket API 8.4, draft 13; lane 3's ruling, #165 6880543448): the
  re-read configuration published, the held child ended and the
  configuration epoch moved in one step, under the worker's lock; a request
  queued or running under an earlier epoch answered `unavailable`.
- B4 (socket API 13.4 and 13.7, draft 13; 6880543448): named records agree
  among themselves, with no list and no covering set as well.
- OP-18 (b) (6880543448, details settled by lane 5 for draft 14): the
  configuration, the reader password file and the URL's TLS files, each by
  its identity from one `os.stat`.
- OP-19 (b) (the same): an owner file over 4,096 bytes, not ending in `\\n`,
  with a known key twice, or with an `install=` other than three runs of
  digits, is unavailable, and the client starts none; and the value the
  writer writes where it cannot `stat` its own file never passes.
- NIT-h (lane 5's ruling on lane 1's U5 NIT-h, #165 6881937840): a server
  of another uid starts no service, whatever the owner file says of the
  install; a case added after the first red run, and in the second.
- Lane 1's U5 gate on T512 (#165 6881993079 and 6882025131): M1, one
  thread, the worker, re-reads a change and retires the child; S1, only
  the worker closes a child's pipes; S2, a failed connect or worker job
  never wedges the worker, and a service whose worker ended stops; N6, the
  owner file and the stamp read only as regular files; N9, no stamp beside
  a service that holds the lock. The B2 cases that go through `answer`
  run the worker, since the worker now re-reads.
- Lane 3's Codex review of 88b50886 (#165 6882203066): SHOULD 3, each
  covering set on its own; SHOULD 6, near-linear agreement; SHOULD 2, the
  connection slot given back on every path; NIT 11, no file work or thread
  start under the service's lock.
"""

import errno
import fcntl
import hashlib
import importlib.util
import inspect
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from importlib.machinery import SourceFileLoader

import pytest

INDEXER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lanes-index")


def _load():
    loader = SourceFileLoader("lanes_index_t512r3_scratch", INDEXER)
    spec = importlib.util.spec_from_loader("lanes_index_t512r3_scratch", loader)
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


def _answer(*items: bytes) -> bytes:
    return f"text 7 {GEN}\n".encode("ascii") + b"".join(items) + b"end\n"


# ===================================================== B2: one step, one epoch

OLD_CHILD, NEW_CHILD, OLD_STORE, NEW_STORE = "old child", "new child", "old store", "new store"
NEW_CFG = {"mode": "primary", "register_rtt_ms": 0, "new": True}
TEXT = _answer(_file(LANES, b"# LANES\n"))


class _Watched(threading.Condition):
    """The service's lock, noting (store, child) each time it is let go, so
    a case sees whatever another thread taking it could have seen."""

    def __init__(self, svc, seen):
        super().__init__()
        self.svc, self.seen = svc, seen

    def __exit__(self, *args):
        self.seen.append((self.svc.store, self.svc.child))
        return super().__exit__(*args)


def _b2_service(tmp_path, monkeypatch, state="ready"):
    """A service past its start, holding OLD_CHILD on OLD_STORE, whose next
    re-read gives NEW_CFG and NEW_STORE; `kill` records what it is given."""
    svc = object.__new__(LI.RegisterService)
    seen, killed = [], []
    svc.cond = _Watched(svc, seen)
    svc.cfg, svc.store, svc.config_stamp, svc.config_epoch = {"register_rtt_ms": 0}, OLD_STORE, "old", 0
    svc.paths = {"log": str(tmp_path / "register.log")}
    svc.child, svc.state, svc.epoch, svc.lazy, svc.retry_at = OLD_CHILD, state, 0, False, 5.0
    svc.queue, svc.fetching, svc.stopping = [], False, ""
    svc.last_used = svc.last_request = time.monotonic()
    svc.install = LI.register_serve_install()
    svc.kill = killed.append
    svc.reload_due, svc.idle_check_s, svc.wanted = False, 3600, set()
    svc.connect = lambda epoch: None     # no child is ever started
    monkeypatch.setattr(LI, "register_serve_load", lambda: (dict(NEW_CFG), "new"))
    monkeypatch.setattr(LI, "PostgresStore", lambda cfg, role: NEW_STORE)
    return svc, seen, killed


class _worker:
    """The service's worker, run as at its start, for the length of a case;
    a re-read stamp is "new" from then on, as `register_serve_load` gives it."""

    def __init__(self, svc):
        self.svc = svc
        self.thread = threading.Thread(target=svc.work, name="the-worker", daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.thread

    def __exit__(self, *args):
        self.svc.stop("the case is done")
        self.thread.join(5)


def _job(items=((("file", LANES)),)):
    """A job under epoch 0, as the head's `_RegisterServeJob` takes it; the
    base's takes no epoch, so that its cases fail on what it does."""
    extra = [0] if "epoch" in inspect.signature(LI._RegisterServeJob).parameters else []
    return LI._RegisterServeJob(list(items), time.monotonic(), *extra)


def test_t512r3_b2_the_configuration_and_the_childs_end_are_one_step(tmp_path, monkeypatch):
    """8.4: "takes the re-read configuration and ends the held child in one
    step, under the lock its worker takes each request by". No moment where
    the lock is free shows the new configuration with the old child."""
    svc, seen, killed = _b2_service(tmp_path, monkeypatch)
    assert svc.reload() == ""
    assert (NEW_STORE, OLD_CHILD) not in seen, f"the lock was let go between the two: {seen}"
    assert svc.store == NEW_STORE and svc.child is None and killed == [OLD_CHILD], (svc.child, killed)


def test_t512r3_b2_a_request_running_under_an_earlier_epoch_is_answered_unavailable(
        tmp_path, monkeypatch):
    """8.4: "a request queued or running under an earlier epoch is answered
    `unavailable`, whatever the old child returns". The configuration
    changes while the request's query runs, and the query still returns a
    whole text answer."""
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch, state="busy")
    job = _job()

    def query(_job, _deadline):
        assert svc.reload() == ""
        return TEXT

    svc.query = query
    svc.serve_job(job)
    assert job.answer == b"unavailable\n", job.answer


def test_t512r3_b2_a_request_queued_under_an_earlier_epoch_is_answered_unavailable(
        tmp_path, monkeypatch):
    """8.4: a request still queued when the configuration changes is
    answered `unavailable`, at the step."""
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch)
    job = _job()
    svc.queue.append(job)
    assert svc.reload() == ""
    assert job.answer == b"unavailable\n" and svc.queue == [], (job.answer, svc.queue)


def test_t512r3_b2_the_request_that_sees_a_change_is_unavailable_though_a_child_is_ready(
        tmp_path, monkeypatch):
    """8.4: "It answers that request, and every request until the new child
    connects, `unavailable`". Here the new child is ready the moment the
    step ends: the request checked against the earlier epoch is still
    answered `unavailable`, and is never queued."""
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    svc.query = lambda _job, _deadline: TEXT
    real = svc.reload

    def reload_then_ready():
        why = real()
        with svc.cond:
            svc.child, svc.state = NEW_CHILD, "ready"
        return why

    svc.reload = reload_then_ready
    with _worker(svc):
        got = svc.answer([("file", LANES)], time.monotonic())
    assert got == b"unavailable\n", got


def test_t512r3_b2_control_an_answer_under_an_unchanged_configuration_is_given(
        tmp_path, monkeypatch):
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch, state="busy")
    job = _job()
    svc.query = lambda _job, _deadline: TEXT
    svc.serve_job(job)
    assert job.answer == TEXT, job.answer


def test_t512r3_b2_control_a_change_answers_that_request_unavailable_and_retires_the_child(
        tmp_path, monkeypatch):
    """8.4: any other change takes the configuration, ends the held child,
    starts a new one at once (no lazy wait), and answers that request
    `unavailable`."""
    svc, _seen, killed = _b2_service(tmp_path, monkeypatch)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    with _worker(svc):
        got = svc.answer([("file", LANES)], time.monotonic())
    assert got == b"unavailable\n", got
    assert (svc.store, svc.cfg.get("new"), svc.config_stamp) == (NEW_STORE, True, "new")
    assert (svc.child, svc.lazy) == (None, False), (svc.child, svc.lazy)
    assert killed == [OLD_CHILD], killed


def test_t512r3_b2_control_a_mode_other_than_primary_ends_the_service(tmp_path, monkeypatch):
    svc, _seen, killed = _b2_service(tmp_path, monkeypatch)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    monkeypatch.setattr(LI, "register_serve_load", lambda: ({"mode": "index"}, "new"))
    with _worker(svc):
        got = svc.answer([("file", LANES)], time.monotonic())
    assert got == b"unavailable restarting\n" and svc.stopping, (got, svc.stopping)
    assert svc.child == OLD_CHILD and svc.store == OLD_STORE and not killed


# ===================================================== M1: one thread re-reads, the worker

def test_t512r3_m1_one_thread_rereads_a_change_and_the_worker_retires_the_child(
        tmp_path, monkeypatch):
    """Lane 1's U5 gate, #165 6881993079, M1: two connections see one change
    at once; the configuration is re-read once, by the worker, and the old
    child is killed by the worker, never by a connection's thread."""
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch)
    loads, killers, got = [], [], []

    def slow_load():
        loads.append(threading.current_thread().name)
        time.sleep(0.3)
        return dict(NEW_CFG), "new"

    monkeypatch.setattr(LI, "register_serve_load", slow_load)
    monkeypatch.setattr(LI, "register_serve_config_stamp", lambda cfg: "new")
    svc.kill = lambda child: killers.append((child, threading.current_thread().name))
    both = threading.Barrier(2)

    def ask():
        both.wait(5)
        got.append(svc.answer([("file", LANES)], time.monotonic()))

    with _worker(svc):
        askers = [threading.Thread(target=ask, name=f"connection-{i}") for i in range(2)]
        for thread in askers:
            thread.start()
        for thread in askers:
            thread.join(5)
    assert got == [b"unavailable\n"] * 2, got
    assert loads == ["the-worker"], loads
    assert killers == [(OLD_CHILD, "the-worker")], killers


# ===================================================== B4: named records among themselves

FOO, FOO_UP, FOO_ODD = "lanes/log/foo.md", "lanes/log/FOO.md", "lanes/log/Foo.md"
L1, L2 = b"log\n", b"log, other\n"
TWO_LOGS = [("file", FOO), ("file", FOO_UP)]

MISMATCHES = {
    "file for foo, absent for FOO (draft 13's counterexample)": (
        TWO_LOGS, _answer(_file(FOO_ODD, L1), b"absent lanes/log/FOO.md\n")),
    "file for foo and file for FOO, two paths": (
        TWO_LOGS, _answer(_file(FOO_ODD, L1), _file("lanes/log/fOO.md", L2))),
    "file for foo, ambiguous for FOO": (
        TWO_LOGS, _answer(_file(FOO_ODD, L1), b"ambiguous lanes/log/FOO.md\n")),
    "absent for foo, ambiguous for FOO": (
        TWO_LOGS, _answer(b"absent lanes/log/foo.md\n", b"ambiguous lanes/log/FOO.md\n")),
    "one name twice, file then absent": (
        [("file", ALIASES), ("file", ALIASES)],
        _answer(_file(ALIASES, b"a\tb\n"), b"absent lanes/aliases.tsv\n")),
}

AGREEING = {
    "file for foo and for FOO, one path and digest": (
        TWO_LOGS, _answer(_file(FOO_ODD, L1), _file(FOO_ODD, L1))),
    "absent for foo and for FOO": (
        TWO_LOGS, _answer(b"absent lanes/log/foo.md\n", b"absent lanes/log/FOO.md\n")),
    "ambiguous for foo and for FOO": (
        TWO_LOGS, _answer(b"ambiguous lanes/log/foo.md\n", b"ambiguous lanes/log/FOO.md\n")),
    "form 2, names that match no common path": (
        [("file", LANES), ("file", ALIASES), ("file", "lanes/log/a.md"), ("file", "lanes/log/b.md")],
        _answer(_file(LANES, b"r\n"), b"absent lanes/aliases.tsv\n", _file("lanes/log/A.md", L1),
                b"absent lanes/log/b.md\n")),
}


@pytest.mark.parametrize("case", sorted(MISMATCHES))
def test_t512r3_b4_named_records_that_disagree_with_no_list_or_set_are_a_mismatch(case):
    items, data = MISMATCHES[case]
    with pytest.raises(LI.RegisterServeMalformed) as raised:
        LI.register_serve_parse(data, items)
    assert str(raised.value) == "a mismatch", str(raised.value)


@pytest.mark.parametrize("case", sorted(AGREEING))
def test_t512r3_b4_control_named_records_that_agree_are_taken(case):
    items, data = AGREEING[case]
    assert LI.register_serve_parse(data, items)["kind"] == "text"


def test_t512r3_b4_the_client_discards_the_counterexample_and_reads_directly(
        tmp_path, monkeypatch):
    """The client's handling of a mismatch is unchanged: `.direct` alone is
    written, and the caller reads directly. Form 1 sends its keys in
    bytewise order, `FOO` then `foo`, and the answer's records follow it."""
    data = _answer(_file(FOO_ODD, L1), b"absent lanes/log/foo.md\n")
    monkeypatch.setattr(LI, "register_serve_ask", lambda _data, _deadline: ("answer", data, False))
    cache = tmp_path / "c"
    cache.mkdir()
    opts = {"form": 1, "members": set(), "all": False, "keys": {"foo", "FOO"},
            "cache": str(cache / "fam")}
    items = LI.register_read_request(opts)[0]
    assert items == [("file", FOO_UP), ("file", FOO)], items
    got = LI.register_read_ask({}, opts)
    assert got == (None, True), got
    assert sorted(os.listdir(cache)) == ["fam.direct"], os.listdir(cache)


# ===================================================== OP-18 (b): five files, by identity

def _tls_estate(tmp_path, *, key=True):
    """A configuration, its reader password file, and the three TLS files
    its reader URL names by absolute path (the key only where `key`)."""
    files = {}
    for name in ("conf", "pass", "root.crt", "client.crt", "client.key"):
        files[name] = tmp_path / name
        if name != "client.key" or key:
            files[name].write_bytes(f"{name}\n".encode("ascii"))
    url = (f"postgresql://r@db.example/x?sslmode=verify-full&sslrootcert={files['root.crt']}"
           f"&sslcert={files['client.crt']}&sslkey={files['client.key']}")
    cfg = {"path": str(files["conf"]), "reader_passfile": str(files["pass"]), "reader_url": url}
    return cfg, files


def _rewrite_keeping_mtime(path) -> None:
    """The same number of bytes written in place, 50 ms on, past any coarse
    clock's tick, and the mtime set back: only the ctime moves."""
    before = os.stat(path)
    time.sleep(0.05)
    path.write_bytes(path.read_bytes().upper())
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = os.stat(path)
    assert (after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_ino, before.st_size, before.st_mtime_ns)


def _replace_by_rename(path, data: bytes) -> None:
    before = os.stat(path)
    temp = path.with_name(path.name + ".new")
    temp.write_bytes(data)
    os.utime(temp, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(temp, path)


@pytest.mark.parametrize("which", ["conf", "pass"])
def test_t512r3_op18_a_file_rewritten_with_its_mtime_kept_is_a_change(tmp_path, which):
    """Rule 4: the identity holds the ctime, which a write moves and no user
    sets back, so `cp -p` or `rsync -t` no longer hides a change; here the
    inode, the size and the mtime are all as they were."""
    cfg, files = _tls_estate(tmp_path)
    before = LI.register_serve_config_stamp(cfg)
    _rewrite_keeping_mtime(files[which])
    assert LI.register_serve_config_stamp(cfg) != before


@pytest.mark.parametrize("which", ["root.crt", "client.crt", "client.key"])
def test_t512r3_op18_a_tls_file_the_url_names_is_watched(tmp_path, which):
    """Rule 1: each of `sslrootcert`, `sslcert` and `sslkey` the reader URL
    names is watched; here one is replaced by `rename`, its mtime kept."""
    cfg, files = _tls_estate(tmp_path)
    before = LI.register_serve_config_stamp(cfg)
    _replace_by_rename(files[which], b"replaced\n")
    assert LI.register_serve_config_stamp(cfg) != before


def test_t512r3_op18_a_missing_tls_file_that_appears_is_a_change(tmp_path):
    """Rule 5: a missing file that appears is a change."""
    cfg, files = _tls_estate(tmp_path, key=False)
    before = LI.register_serve_config_stamp(cfg)
    files["client.key"].write_bytes(b"key\n")
    assert LI.register_serve_config_stamp(cfg) != before


def test_t512r3_op18_a_relative_tls_path_resolves_against_the_working_directory(
        tmp_path, monkeypatch):
    """Rule 3: a relative path, as written, against the working directory
    the child inherits; the same name under another directory is not it."""
    for where in ("a", "b"):
        (tmp_path / where / "certs").mkdir(parents=True)
        (tmp_path / where / "certs" / "root.crt").write_bytes(b"root\n")
    (tmp_path / "conf").write_bytes(b"conf\n")
    cfg = {"path": str(tmp_path / "conf"), "reader_passfile": "",
           "reader_url": "postgresql://r@db.example/x?sslmode=verify-full&sslrootcert=certs/root.crt"}
    monkeypatch.chdir(tmp_path / "a")
    before = LI.register_serve_config_stamp(cfg)
    (tmp_path / "b" / "certs" / "root.crt").write_bytes(b"another root\n")
    assert LI.register_serve_config_stamp(cfg) == before, "a file under another directory moved it"
    (tmp_path / "a" / "certs" / "root.crt").write_bytes(b"a new root\n")
    assert LI.register_serve_config_stamp(cfg) != before


def test_t512r3_op18_the_snapshot_of_one_path(tmp_path):
    """Rule 4: `absent` for `ENOENT` and `ENOTDIR`, `error <errno name>`
    for any other failure, else the five-field identity."""
    (tmp_path / "f").write_bytes(b"f\n")
    st = os.stat(tmp_path / "f")
    assert LI.register_serve_snapshot(str(tmp_path / "none")) == "absent"
    assert LI.register_serve_snapshot(str(tmp_path / "f" / "x")) == "absent"
    assert LI.register_serve_snapshot(str(tmp_path / "f")) == (
        st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    assert LI.register_serve_snapshot("x" * 5000) == f"error {errno.errorcode[errno.ENAMETOOLONG]}"


def test_t512r3_op18_a_request_after_a_tls_file_changes_starts_b2s_step(tmp_path, monkeypatch):
    """Rule 5: the change is a configuration change as section 8.4 handles
    it: the next request has the configuration re-read (`reload`)."""
    cfg, files = _tls_estate(tmp_path)
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch)
    svc.cfg, svc.config_stamp = cfg, LI.register_serve_config_stamp(cfg)
    reloads = []
    svc.reload = lambda: reloads.append(1) or ""
    svc.request = lambda *args: b"queued\n"
    _replace_by_rename(files["root.crt"], b"replaced\n")
    with _worker(svc):
        svc.answer([("file", LANES)], time.monotonic())
    assert reloads == [1], reloads


def test_t512r3_op18_control_an_unchanged_configuration_is_no_change(tmp_path):
    cfg, _files = _tls_estate(tmp_path)
    assert LI.register_serve_config_stamp(cfg) == LI.register_serve_config_stamp(cfg)


def test_t512r3_op18_control_a_configuration_whose_mtime_moves_is_a_change(tmp_path):
    cfg, files = _tls_estate(tmp_path)
    before = LI.register_serve_config_stamp(cfg)
    st = os.stat(files["conf"])
    os.utime(files["conf"], ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert LI.register_serve_config_stamp(cfg) != before


def test_t512r3_op18_control_libpqs_own_files_are_not_watched(tmp_path, monkeypatch):
    """Rule 2 and rule 1's `system`: a root a `PG*` variable names, and a
    file named `system` where `sslrootcert=system`, change nothing."""
    (tmp_path / "conf").write_bytes(b"conf\n")
    (tmp_path / "system").write_bytes(b"not a root\n")
    (tmp_path / "env-root.crt").write_bytes(b"env root\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PGSSLROOTCERT", str(tmp_path / "env-root.crt"))
    cfg = {"path": str(tmp_path / "conf"), "reader_passfile": "",
           "reader_url": "postgresql://r@db.example/x?sslmode=verify-full&sslrootcert=system"}
    before = LI.register_serve_config_stamp(cfg)
    (tmp_path / "system").write_bytes(b"still not a root, longer\n")
    (tmp_path / "env-root.crt").write_bytes(b"another env root\n")
    assert LI.register_serve_config_stamp(cfg) == before


def test_t512r3_op18_control_the_configuration_is_stamped_before_it_is_read(tmp_path, monkeypatch):
    """Rule 6: a change made while `serve` reads the file counts at the next
    request, never as read."""
    cfg, files = _tls_estate(tmp_path)
    monkeypatch.setenv("LANES_INDEX_CONFIG", str(files["conf"]))

    def load_while_it_changes():
        st = os.stat(files["conf"])
        files["conf"].write_bytes(b"changed while read\n")
        os.utime(files["conf"], ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        return dict(cfg)

    monkeypatch.setattr(LI, "load_config", load_while_it_changes)
    loaded, stamp = LI.register_serve_load()
    assert LI.register_serve_config_stamp(loaded) != stamp


# ===================================================== OP-19 (b): values the client can use

ASK = b"read 1\nfile lanes/LANES.md\nend\n"
REPLY = TEXT


@pytest.fixture
def answering_socket(tmp_path, monkeypatch):
    """A socket of the case's own at the fixed path, in a 0700 `run/` reached
    by a short relative path, so no path is too long for `bind()`. It
    records what each connection sends, and answers REPLY to a request."""
    run = tmp_path / "run"
    run.mkdir()
    run.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    paths = {key: str(run / name) for key, name in LI.REGISTER_SERVE_FILES.items()}
    paths["run"], paths["sock"] = str(run), "run/register.sock"
    monkeypatch.setattr(LI, "register_serve_paths", lambda: dict(paths))
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(paths["sock"])
    server.listen(4)
    server.settimeout(0.1)
    sent, done = [], threading.Event()

    def each():
        while not done.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            data = b""
            with conn:
                conn.settimeout(1.0)
                try:
                    while not data.endswith(b"\nend\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    if data:
                        conn.sendall(REPLY)
                except OSError:
                    pass
            sent.append(data)

    thread = threading.Thread(target=each, daemon=True)
    thread.start()
    yield run / "register.owner", sent
    done.set()
    thread.join(2)
    server.close()


def _whole() -> bytes:
    return LI.register_serve_owner_text("2026-11-14T00:00:00Z")


def _swap_install(value: bytes) -> bytes:
    return b"\n".join(b"install=" + value if line.startswith(b"install=") else line
                      for line in _whole().split(b"\n"))


def _padded(total: int) -> bytes:
    whole = _whole()
    return whole + b"#" * (total - len(whole) - 1) + b"\n"


UNUSABLE = {
    "no LF at its end": lambda: _whole()[:-1],
    "pid twice": lambda: _whole() + b"pid=1\n",
    "started twice": lambda: _whole() + b"started=2026-11-14T00:00:00Z\n",
    "install twice, the same value": lambda: _whole() + [
        line for line in _whole().split(b"\n") if line.startswith(b"install=")][0] + b"\n",
    "4,097 bytes": lambda: _padded(4097),
    "install with a fourth field": lambda: _swap_install(b"1 2 3 4"),
    "install with a letter": lambda: _swap_install(b"1 2 3a"),
    "install with a sign": lambda: _swap_install(b"+1 2 3"),
    "install with two spaces": lambda: _swap_install(b"1  2 3"),
    "install with a space after": lambda: _swap_install(b"1 2 3 "),
    "install with a non-ASCII digit": lambda: _swap_install("1 2 ٣".encode("utf-8")),
}


def _ask():
    kind, payload, start = LI.register_serve_ask(ASK, time.monotonic() + 2)
    time.sleep(0.2)
    return kind, payload, start


@pytest.mark.parametrize("case", sorted(UNUSABLE))
def test_t512r3_op19_an_owner_file_whose_values_the_client_cannot_use_is_unavailable(
        answering_socket, case):
    owner, sent = answering_socket
    data = UNUSABLE[case]()
    if case == "4,097 bytes":
        assert len(data) == 4097 and data.endswith(b"\n")
    owner.write_bytes(data)
    kind, payload, start = _ask()
    assert (kind, start) == ("unavailable", False), (kind, start, payload)
    assert not any(sent), f"the client sent its request: {sent}"


def test_t512r3_op19_the_writers_failure_path_never_passes(answering_socket, monkeypatch):
    """Rule 7: where the service cannot `stat` its own `lanes-index` file,
    `register_serve_owner_text` writes the line `install=` with nothing
    after the `=`, which rule 4 never passes: the client reads directly
    and starts none."""
    owner, sent = answering_socket
    mine, real = os.path.abspath(LI.__file__), os.stat

    def failing(path, *args, **kwargs):
        if path == mine:
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return real(path, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(LI.os, "stat", failing)
        text = LI.register_serve_owner_text("2026-11-14T00:00:00Z")
    assert [line for line in text.split(b"\n") if line.startswith(b"install")] == [b"install="]
    owner.write_bytes(text)
    kind, payload, start = _ask()
    assert (kind, start) == ("unavailable", False), (kind, start, payload)
    assert not any(sent), f"the client sent its request: {sent}"
    # The value is "", and rule 4's form needs a digit in each of its runs.
    assert not LI._REGISTER_SERVE_INSTALL_RE.fullmatch("")


USABLE = {
    "the writer's whole file": _whole,
    "4,096 bytes": lambda: _padded(4096),
    "an unknown key twice": lambda: _whole() + b"later=1\nlater=2\n",
    "a line with no =, twice": lambda: _whole() + b"note\nnote\n",
}


@pytest.mark.parametrize("case", sorted(USABLE))
def test_t512r3_op19_control_an_owner_file_of_this_install_is_asked(answering_socket, case):
    owner, sent = answering_socket
    data = USABLE[case]()
    if case == "4,096 bytes":
        assert len(data) == 4096
    owner.write_bytes(data)
    kind, payload, start = _ask()
    assert (kind, payload, start) == ("answer", REPLY, False), (kind, start, payload)
    assert sent == [ASK], sent


def test_t512r3_op19_control_another_install_of_19_digit_fields_starts_one(answering_socket):
    """No digit-count cap: an mtime in nanoseconds has 19 digits. Another
    install's well-formed value still starts a service, and the request is
    still sent, which the old service answers."""
    owner, sent = answering_socket
    owner.write_bytes(_swap_install(b"1 1700000000123456789 2"))
    kind, payload, start = _ask()
    assert (kind, payload, start) == ("answer", REPLY, True), (kind, start, payload)
    assert sent == [ASK], sent


# ===================================================== NIT-h: the uid check wins

def _read_through_another_uid(answering_socket, monkeypatch, tmp_path, owner_bytes: bytes, peer):
    """Form 2's `register read` against a server whose peer credential is
    not this uid's (or cannot be read), behind `owner_bytes`: what it
    returns, the starts it made, and what the server was sent."""
    owner, sent = answering_socket
    owner.write_bytes(owner_bytes)
    monkeypatch.setattr(LI, "register_peercred", peer)
    launches = []
    monkeypatch.setattr(LI, "register_serve_launch", lambda paths: launches.append(paths) or None)
    cache = tmp_path / "cache"
    cache.mkdir()
    got = LI.register_read_ask({}, {"form": 2, "lane": "", "cache": str(cache / "fam")})
    time.sleep(0.2)
    return got, launches, sent, sorted(os.listdir(cache))


def _another_uid(_conn):
    return os.getuid() + 1


def _no_peercred(_conn):
    raise OSError(errno.EINVAL, "no peer credential")


@pytest.mark.parametrize("peer", ["another uid", "a peer credential that cannot be read"])
def test_t512r3_nith_a_server_of_another_uid_behind_another_install_starts_none(
        answering_socket, monkeypatch, tmp_path, peer):
    """Lane 5's ruling on lane 1's U5 NIT-h (#165 6881937840): the uid check
    wins. The owner file names another install, which alone would start a
    service; the server is another uid's, so the client sends nothing,
    starts none, writes `.direct` and reads directly."""
    got, launches, sent, files = _read_through_another_uid(
        answering_socket, monkeypatch, tmp_path, _swap_install(b"1 2 3"),
        _another_uid if peer == "another uid" else _no_peercred)
    assert got == (None, True), got
    assert launches == [], f"the client started a service: {launches}"
    assert not any(sent), f"the client sent its request: {sent}"
    assert files == ["fam.direct"], files


def test_t512r3_nith_control_a_server_of_another_uid_behind_this_install_starts_none(
        answering_socket, monkeypatch, tmp_path):
    got, launches, sent, files = _read_through_another_uid(
        answering_socket, monkeypatch, tmp_path, _whole(), _another_uid)
    assert (got, launches, files) == ((None, True), [], ["fam.direct"]), (got, launches, files)
    assert not any(sent), f"the client sent its request: {sent}"


# ===================================================== S1: only the worker closes the pipes

def _reader_child():
    """A stand-in child on pipes that reads its stdin to the end."""
    return subprocess.Popen([sys.executable, "-I", "-c", "import sys; sys.stdin.buffer.read()"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)


def _close_all(child):
    for pipe in (child.stdin, child.stdout, child.stderr):
        try:
            pipe.close()
        except OSError:
            pass


def _ending_service(child, worker):
    svc = object.__new__(LI.RegisterService)
    svc.cond = threading.Condition()
    svc.child, svc.state, svc.epoch, svc.queue, svc.worker = child, "busy", 0, [], worker
    return svc


def test_t512r3_s1_an_exchange_on_a_closed_pipe_is_the_end_of_the_stream():
    """S1: on Python 3.12 a closed `Popen` pipe's `fileno()` raises
    `ValueError`, which ended the worker; it is the end of the stream."""
    child = _reader_child()
    try:
        child.stdout.close()
        got = LI.RegisterService.exchange(child, b"x\n", "n-1", time.monotonic() + 1)
    finally:
        child.kill()
        child.wait(5)
        _close_all(child)
    assert got == ("eof", b"", ""), got


def test_t512r3_s1_end_kills_the_child_and_leaves_its_pipes_to_a_live_worker():
    """S1: "only the worker closes a child's pipes. Other threads send
    SIGKILL and move the epoch." The service's end, in the main thread,
    while the worker lives."""
    child, release = _reader_child(), threading.Event()
    worker = threading.Thread(target=release.wait, args=(10,), daemon=True)
    worker.start()
    svc = _ending_service(child, worker)
    try:
        svc.end()
        child.wait(5)
        closed = child.stdout.closed or child.stdin.closed
    finally:
        release.set()
        worker.join(5)
        _close_all(child)
    assert child.returncode == -signal.SIGKILL, child.returncode
    assert not closed, "a thread other than the worker closed the child's pipes"
    assert (svc.child, svc.epoch) == (None, 1)


def test_t512r3_s1_control_end_closes_the_pipes_once_the_worker_has_ended():
    child = _reader_child()
    worker = threading.Thread(target=lambda: None, daemon=True)
    worker.start()
    worker.join()
    svc = _ending_service(child, worker)
    try:
        svc.end()
        child.wait(5)
        closed = child.stdout.closed and child.stdin.closed
    finally:
        _close_all(child)
    assert child.returncode is not None and closed, (child.returncode, closed)


# ===================================================== S2: a failure never wedges the worker

def _connecting_service(tmp_path, fail):
    svc = object.__new__(LI.RegisterService)
    svc.cond = threading.Condition()
    svc.paths = {"log": str(tmp_path / "register.log")}
    svc.child, svc.state, svc.epoch, svc.lazy, svc.stopping = None, "connecting", 3, False, ""

    def spawn():
        raise fail

    svc.spawn = spawn
    return svc


def test_t512r3_s2a_a_connect_whose_password_file_cannot_be_made_is_a_failed_connect(tmp_path):
    """S2 (a): `_env`'s `_no_password_file()` raises `StoreUnusable`, not an
    `OSError`; the state must not stay `connecting`."""
    svc = _connecting_service(tmp_path, LI.StoreUnusable("unreachable", "no empty password file"))
    try:
        svc.connect(3)
        raised = None
    except Exception as exc:     # the base lets it out of the connect's thread
        raised = exc
    assert raised is None and (svc.state, svc.lazy) == ("down", True), (raised, svc.state)


def test_t512r3_s2a_control_a_connect_whose_spawn_fails_is_a_failed_connect(tmp_path):
    svc = _connecting_service(tmp_path, OSError(errno.ENOENT, "no psql"))
    svc.connect(3)
    assert (svc.state, svc.lazy) == ("down", True), svc.state


def test_t512r3_s2b_a_worker_job_that_raises_leaves_the_worker_working(tmp_path, monkeypatch):
    """S2 (b): the request is answered `unavailable`, the held child is
    replaced at once with a fixed phrase, and the worker carries on, its
    state never left `busy`."""
    svc, _seen, killed = _b2_service(tmp_path, monkeypatch)
    job = _job()
    svc.queue.append(job)

    def fault(_job):
        raise RuntimeError("a fault in a job")

    svc.serve_job = fault
    with _worker(svc) as worker:
        job.done.wait(2)
        time.sleep(0.2)
        alive, state = worker.is_alive(), svc.state
    assert job.answer == b"unavailable\n", job.answer
    assert alive and state != "busy", (alive, state)
    assert killed == [OLD_CHILD], killed
    log = (tmp_path / "register.log").read_text(encoding="ascii")
    assert "a job of the worker failed: the held child is replaced" in log, log


def _serve_with(tmp_path, monkeypatch, worker):
    """`serve`'s accept loop on a socket of the case's own, its worker given,
    its idle stop at 3 s; returns (its time, register.log)."""
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.chdir(tmp_path)
    paths = {"run": str(run), "sock": "run/register.sock", "log": str(run / "register.log")}
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(paths["sock"])
    server.listen(4)
    svc = LI.RegisterService({}, None, paths, server, os.lstat(paths["sock"]).st_ino, ((), ()))
    svc.idle_stop_s, svc.worker = 3, worker
    svc.begin = lambda: None
    svc.end = lambda: None
    handlers = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    began = time.monotonic()
    try:
        svc.serve()
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        server.close()
    return time.monotonic() - began, (run / "register.log").read_text(encoding="ascii")


def test_t512r3_s2c_a_service_whose_worker_has_ended_stops(tmp_path, monkeypatch):
    """S2 (c): with no worker, nothing is answered; the service stops at
    once, not at its idle stop."""
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    took, log = _serve_with(tmp_path, monkeypatch, dead)
    assert "stopped: its worker ended" in log and took < 2, (took, log)


def test_t512r3_s2c_control_a_service_whose_worker_lives_stops_at_its_idle_stop(
        tmp_path, monkeypatch):
    release = threading.Event()
    live = threading.Thread(target=release.wait, args=(30,), daemon=True)
    live.start()
    try:
        took, log = _serve_with(tmp_path, monkeypatch, live)
    finally:
        release.set()
        live.join(5)
    assert "stopped: idle for 3 s" in log and took >= 2.5, (took, log)


# ===================================================== N6: regular files only

def _returns_in_time(fn, *args) -> tuple:
    out = []
    thread = threading.Thread(target=lambda: out.append(fn(*args)), daemon=True)
    thread.start()
    thread.join(2)
    return not thread.is_alive(), out


def _free_a_blocked_reader(fifo: str) -> None:
    """A reader blocked opening `fifo` is freed by a writer's open."""
    try:
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
    except OSError:
        pass             # no reader is blocked on it


@pytest.mark.parametrize("which", ["owner", "failed"])
def test_t512r3_n6_a_fifo_at_the_owner_file_or_the_stamp_never_blocks_the_read(tmp_path, which):
    """N6 (lane 1's U5 gate, #165 6881993079): a FIFO there is no file the
    client can read; it is passed over at once, never waited on."""
    paths = {"owner": str(tmp_path / "register.owner"), "failed": str(tmp_path / "register.failed")}
    os.mkfifo(paths[which])
    read = LI.register_serve_owner_read if which == "owner" else LI.register_serve_stamp_read
    try:
        returned, out = _returns_in_time(read, paths)
    finally:
        _free_a_blocked_reader(paths[which])
    assert returned and out == [None], (returned, out)


def test_t512r3_n6_control_regular_files_are_read(tmp_path):
    paths = {"owner": str(tmp_path / "register.owner"), "failed": str(tmp_path / "register.failed")}
    (tmp_path / "register.owner").write_bytes(_whole())
    (tmp_path / "register.failed").write_bytes(b"2026-11-14T00:00:00Z no-psql\n")
    owner = LI.register_serve_owner_read(paths)
    stamp = LI.register_serve_stamp_read(paths)
    assert owner is not None and "install" in owner, owner
    assert stamp is not None and stamp[:2] == ("2026-11-14T00:00:00Z", "no-psql"), stamp


# ===================================================== N9: no stamp beside a live service

def _stamp_paths(tmp_path) -> dict:
    return {"lock": str(tmp_path / "register.lock"), "failed": str(tmp_path / "register.failed")}


def test_t512r3_n9_no_stamp_is_written_where_a_service_holds_the_lock(tmp_path):
    """N9 (lane 1's U5 gate, #165 6882025131): a launched `serve` that fails
    its checks while a live service holds `register.lock` leaves no stamp
    beside it (socket API 8.6, draft 13)."""
    paths = _stamp_paths(tmp_path)
    held = os.open(paths["lock"], os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        LI.register_serve_stamp(paths, "no-psql")
    finally:
        os.close(held)
    assert not os.path.lexists(paths["failed"]), (tmp_path / "register.failed").read_bytes()


def test_t512r3_n9_control_a_stamp_is_written_where_no_service_holds_the_lock(tmp_path):
    paths = _stamp_paths(tmp_path)
    LI.register_serve_stamp(paths, "no-psql")
    stamp = LI.register_serve_stamp_read(paths)
    assert stamp is not None and stamp[1] == "no-psql", stamp


# ===================================================== lane 3's Codex review of 88b50886

def _a_set(prefix: str, *members) -> bytes:
    out = [f"set {prefix} {len(members)}\n".encode("ascii")]
    for path, body in sorted(members, key=lambda m: m[0].encode("ascii")):
        out.append(_file(path, body))
    return b"".join(out)


A_LOG = "lanes/log/a.md"

COVERING = {
    "a wider set holds the log, the narrower set lacks it (nested prefixes)": (
        [("set", "lanes/"), ("set", "lanes/log/"), ("file", A_LOG)],
        _answer(_a_set("lanes/", (A_LOG, L1)), _a_set("lanes/log/"), _file(A_LOG, L1))),
    "one prefix twice, the second set lacks the log (duplicate prefixes)": (
        [("set", "lanes/log/"), ("set", "lanes/log/"), ("file", A_LOG)],
        _answer(_a_set("lanes/log/", (A_LOG, L1)), _a_set("lanes/log/"), _file(A_LOG, L1))),
}


@pytest.mark.parametrize("case", sorted(COVERING))
def test_t512r3_cx3_a_named_record_agrees_with_each_covering_set_on_its_own(case):
    """Codex SHOULD 3 (#165 6882203066): one set's paths cannot mask another
    covering set that contradicts the named record."""
    items, data = COVERING[case]
    with pytest.raises(LI.RegisterServeMalformed) as raised:
        LI.register_serve_parse(data, items)
    assert str(raised.value) == "a mismatch", str(raised.value)


def test_t512r3_cx3_control_covering_sets_that_agree_are_taken():
    items = [("set", "lanes/"), ("set", "lanes/log/"), ("file", A_LOG)]
    data = _answer(_a_set("lanes/", (A_LOG, L1)), _a_set("lanes/log/", (A_LOG, L1)),
                   _file(A_LOG, L1))
    assert LI.register_serve_parse(data, items)["kind"] == "text"


def test_t512r3_cx6_agreement_is_near_linear_in_the_answer():
    """Codex SHOULD 6: 5,000 listed logs and 1,000 named ones agree in well
    under half a second; rebuilding and rescanning the union for each named
    record made it quadratic, 5,000,000 folds."""
    digest = "0" * 64
    paths = [f"lanes/log/k{i:05d}.md" for i in range(5000)]
    records = [("list", "", [(path, digest) for path in paths])]
    records += [("absent", f"lanes/log/none{i:05d}.md") for i in range(1000)]
    began = time.monotonic()
    assert LI.register_serve_agree(records)
    took = time.monotonic() - began
    assert took < 0.5, f"{took:.2f} s"


class _CloseFails:
    """A connection whose peer credential cannot be read, and whose close
    raises."""

    def getsockopt(self, *_args):
        raise OSError(errno.EBADF, "no peer credential")

    def close(self):
        raise OSError(errno.EIO, "the close failed")


def test_t512r3_cx2_a_connections_slot_is_given_back_though_its_close_raises(tmp_path):
    """Codex SHOULD 2: the slot is released in a `finally` of its own."""
    svc = object.__new__(LI.RegisterService)
    svc.cond, svc.cfg, svc.live = threading.Condition(), {}, 1
    svc.paths = {"log": str(tmp_path / "register.log")}
    try:
        svc.connection(_CloseFails(), time.monotonic())
    except OSError:
        pass
    assert svc.live == 0, svc.live


def test_t512r3_cx2_a_connection_whose_thread_cannot_start_gives_its_slot_back(
        tmp_path, monkeypatch):
    """Codex SHOULD 2: where `Thread.start` raises, the accepted socket is
    closed with no answer, its slot given back, and the accept loop goes on."""
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.chdir(tmp_path)
    paths = {"run": str(run), "sock": "run/register.sock", "log": str(run / "register.log")}
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(paths["sock"])
    server.listen(4)
    svc = LI.RegisterService({}, None, paths, server, os.lstat(paths["sock"]).st_ino, ((), ()))
    release = threading.Event()
    svc.worker = threading.Thread(target=release.wait, args=(30,), daemon=True)
    svc.worker.start()
    svc.begin = lambda: None
    svc.end = lambda: None
    heard = []

    def client():
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(3)
        try:
            conn.connect(paths["sock"])
            heard.append(conn.recv(100))
        except OSError as exc:
            heard.append(exc)
        finally:
            conn.close()
            time.sleep(0.3)
            svc.stop("the case is done")

    real_start = threading.Thread.start

    def start(thread):
        if getattr(thread, "_target", None) == svc.connection:
            raise RuntimeError("can't start new thread")
        return real_start(thread)

    monkeypatch.setattr(threading.Thread, "start", start)
    asker = threading.Thread(target=client, daemon=True)
    asker.start()
    handlers = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        try:
            svc.serve()
            raised = None
        except Exception as exc:     # the base lets it out of the accept loop
            raised = exc
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        server.close()
        release.set()
        asker.join(5)
    log = (run / "register.log").read_text(encoding="ascii")
    assert raised is None and svc.live == 0, (raised, svc.live)
    assert heard == [b""], heard
    assert "a connection's thread could not start" in log and "stopped: the case is done" in log, log


def _owned_while(svc, calls: list):
    """`register_serve_log` replaced by a record of each phrase, and whether
    the service's lock was held when it was written."""
    return lambda _paths, phrase: calls.append((phrase, svc.cond._is_owned()))


def test_t512r3_cx11_a_failed_connect_logs_outside_the_lock(tmp_path, monkeypatch):
    """Codex NIT 11: the state is set under `cond`, and the log line and the
    stamp's removal are written after it is let go."""
    svc = _connecting_service(tmp_path, OSError(errno.ENOENT, "no psql"))
    calls = []
    monkeypatch.setattr(LI, "register_serve_log", _owned_while(svc, calls))
    svc.connect(3)
    assert calls == [("connect failed", False)], calls


def test_t512r3_cx11_the_connects_thread_is_started_outside_the_lock(tmp_path, monkeypatch):
    svc, _seen, _killed = _b2_service(tmp_path, monkeypatch)
    svc.state, svc.child, svc.retry_at = "down", None, 0.0
    starts = []
    real_start = threading.Thread.start

    def start(thread):
        if getattr(thread, "_target", None) == svc.connect:
            starts.append(svc.cond._is_owned())
        return real_start(thread)

    monkeypatch.setattr(threading.Thread, "start", start)
    with _worker(svc):
        time.sleep(0.3)
    assert starts == [False], starts


def test_t512r3_cx11_control_a_connect_that_succeeds_is_logged_once(tmp_path, monkeypatch):
    svc = _connecting_service(tmp_path, None)
    child = _reader_child()
    svc.spawn = lambda: child
    svc.store = type("S", (), {"addresses": 1, "connect_timeout": 2})()
    svc.exchange = lambda *_args: ("ok", b"", "")
    calls = []
    monkeypatch.setattr(LI, "register_serve_log", lambda _paths, phrase: calls.append(phrase))
    monkeypatch.setattr(LI, "register_serve_unstamp", lambda _paths: calls.append("unstamped"))
    try:
        svc.connect(3)
    finally:
        child.kill()
        child.wait(5)
        _close_all(child)
    assert (svc.state, svc.child is child) == ("ready", True), svc.state
    assert calls == ["unstamped", "connected"], calls
