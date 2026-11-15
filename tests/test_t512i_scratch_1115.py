"""T512'S INSTALL IDENTITY, A SCRATCH PROOF (lane 5, round 1115, writer sonnet).

NOT A PERMANENT TEST, and never on T512's branch: T512 changes `lanes-index`
alone, and its cases for the service live in lane 2's T237 module
(`tests/test_sql_register_guard.py`), which this tree does not have and which
this file does not touch. Like rounds 3 to 5's scratch modules, it lives on a
scratch branch beside T512's commits. None of its cases needs PostgreSQL.

Lane 5's choice (a) on lane 1's T124 prototype (#165 6890257498): `install=`
is the launcher's `size mtime_ns inode`, then, where `lanes_index_main.py` is
in the directory of `os.path.realpath(__file__)`, that module's three; rule 4
takes three runs of ASCII digits or six, one space between each, and nothing
else; the client's comparison is as it was.

- `register_serve_install`: no module file, three numbers, equal to
  `__file__`'s; a module beside the launcher's realpath, six, the launcher's
  first, through a symlinked launcher as well; a module whose `stat` fails
  other than by absence, empty;
- rule 4, `_REGISTER_SERVE_INSTALL_RE`, applied with `fullmatch` as the
  client applies it;
- the client, `register_serve_ask`, against a real socket and an owner file:
  an owner file of three numbers read by a client whose install has six is
  another install (the client starts a service), not an unusable file.
"""

import ast
import errno
import importlib.util
import os
import shutil
import socket
import threading
import time
from importlib.machinery import SourceFileLoader

import pytest

INDEXER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lanes-index")
MODULE = "lanes_index_main.py"
TREE_MODULE = os.path.join(os.path.dirname(INDEXER), MODULE)
#: A TREE OF T124'S FORM (lane 1's R2, #165 6892234131, NIT 3): `lanes-index`
#: is a launcher, and the body, the rule and `register_serve_install` are in
#: `lanes_index_main.py` beside it. Then a copy of the launcher runs only with
#: the module beside it, so `_install_in` places the module, the rule's text
#: is read from the module, and the two cases that need a launcher with no
#: module beside it skip: the three-number form exists only before T124.
T124_TREE = os.path.isfile(TREE_MODULE)
RULE_SOURCE = TREE_MODULE if T124_TREE else INDEXER
_loaded = [0]


def _load(path):
    """`lanes-index` at `path`, run as a module whose `__file__` is `path`."""
    _loaded[0] += 1
    name = f"lanes_index_t512i_scratch_{_loaded[0]}"
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _install_in(directory):
    """A copy of this tree's `lanes-index` in `directory`, loaded there: on a
    tree of T124's form, with its module beside it, since the launcher exits
    without one."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(str(directory), "lanes-index")
    shutil.copyfile(INDEXER, path)
    if T124_TREE:
        shutil.copyfile(TREE_MODULE, os.path.join(str(directory), MODULE))
    return path, _load(path)


def _put_module(directory, text="# the launcher's module, as T124 moves the body\n"):
    """The module's file in `directory`, written with `text`: a rewrite in
    place, which a copy already loaded does not read again."""
    path = os.path.join(str(directory), MODULE)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _ensure_module(directory):
    """The module's file in `directory`: the one `_install_in` placed on a
    tree of T124's form, else a stand-in, which no single-file copy reads."""
    path = os.path.join(str(directory), MODULE)
    return path if os.path.isfile(path) else _put_module(directory)


def _skip_on_t124_tree(why):
    if T124_TREE:
        pytest.skip(f"this tree is of T124's form, whose launcher exits without its module: {why}")


def _ident(path):
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns, st.st_ino


# ============================================== register_serve_install

def test_t512i_no_module_file_leaves_the_three_numbers_of_dunder_file(tmp_path):
    """Every tree before T124: no module file, so today's three numbers,
    equal to the size, mtime in ns and inode of `__file__`'s file."""
    _skip_on_t124_tree("no install of it has no module file, so the three-number form is before T124's")
    path, li = _install_in(tmp_path / "bare")
    got = li.register_serve_install()
    assert got == _ident(path)
    assert len(got) == 3 and all(isinstance(part, int) for part in got)


def test_t512i_a_module_beside_the_launcher_gives_six_numbers_the_launchers_first(tmp_path):
    path, li = _install_in(tmp_path / "bare")
    module = _ensure_module(tmp_path / "bare")
    got = li.register_serve_install()
    assert got == _ident(path) + _ident(module)
    assert len(got) == 6
    assert got[:3] == _ident(path), "the launcher's three come first"


def test_t512i_the_module_changing_changes_the_install_and_so_does_the_launcher(tmp_path):
    """Why not (b): a rewrite of either file alone shows in the value."""
    path, li = _install_in(tmp_path / "bare")
    module = _ensure_module(tmp_path / "bare")
    before = li.register_serve_install()
    _put_module(tmp_path / "bare", "# the module, rewritten, and longer than it was\n")
    os.utime(module, ns=(1_000_000_000, 1_000_000_000))
    after_module = li.register_serve_install()
    assert after_module[:3] == before[:3] and after_module[3:] != before[3:]
    os.utime(path, ns=(2_000_000_000, 2_000_000_000))
    after_launcher = li.register_serve_install()
    assert after_launcher[:3] != after_module[:3] and after_launcher[3:] == after_module[3:]


def test_t512i_a_symlinked_launcher_finds_the_module_beside_the_real_file(tmp_path):
    """`__file__` is the symlink; `stat` follows it, and the module is looked
    for beside the launcher's `realpath`, as T124's launcher finds it."""
    real, _ = _install_in(tmp_path / "real")
    module = _ensure_module(tmp_path / "real")
    os.makedirs(tmp_path / "link")
    link = str(tmp_path / "link" / "lanes-index")
    os.symlink(real, link)
    li = _load(link)
    assert li.__file__ == link
    got = li.register_serve_install()
    assert len(got) == 6
    assert got == _ident(real) + _ident(module)
    assert got[:3] == _ident(link), "the launcher's first, as `stat` follows the link"


def test_t512i_a_dotdot_after_a_symlink_names_the_real_launcher_not_a_lexical_one(tmp_path):
    """Lane 1's R2, NIT 1: `__file__` is `a/link/../lanes-index`, where
    `link` is a symbolic link to `real/sub`. The OS opens `real/lanes-index`;
    a lexical `abspath` would name `a/lanes-index`, another launcher's file
    (or none). The identity is taken from `realpath(__file__)` once, for the
    launcher and for the module's directory."""
    real, _ = _install_in(tmp_path / "real")
    module = _ensure_module(tmp_path / "real")
    other, _ = _install_in(tmp_path / "a")      # a different launcher, at the lexical name
    os.utime(other, ns=(1_000_000_000, 1_000_000_000))
    os.makedirs(tmp_path / "real" / "sub")
    os.symlink(str(tmp_path / "real" / "sub"), str(tmp_path / "a" / "link"))
    given = os.path.join(str(tmp_path / "a"), "link", "..", "lanes-index")
    assert os.path.samefile(given, real) and not os.path.samefile(given, other)
    li = _load(given)
    assert li.__file__ == given
    assert li.register_serve_install() == _ident(real) + _ident(module)
    assert li.register_serve_install()[:3] != _ident(other)


def test_t512i_a_module_beside_the_link_and_not_beside_the_real_file_is_not_named(tmp_path):
    _skip_on_t124_tree("a launcher with no module beside its real file cannot be loaded")
    real, _ = _install_in(tmp_path / "real")
    os.makedirs(tmp_path / "link")
    link = str(tmp_path / "link" / "lanes-index")
    os.symlink(real, link)
    _put_module(tmp_path / "link")
    li = _load(link)
    assert li.register_serve_install() == _ident(real), "three: realpath's directory has none"


def test_t512i_a_module_whose_stat_fails_other_than_by_absence_is_empty(tmp_path):
    """A symbolic link in a loop gives `ELOOP` on `stat`, not `ENOENT`: the
    value is (), and `install=` is written with nothing after it."""
    path, li = _install_in(tmp_path / "bare")
    holder = os.path.join(str(tmp_path / "bare"), MODULE + ".loop")
    os.symlink(MODULE, holder)
    os.replace(holder, os.path.join(str(tmp_path / "bare"), MODULE))   # the module is now a loop
    with pytest.raises(OSError) as raised:
        os.stat(os.path.join(str(tmp_path / "bare"), MODULE))
    assert not isinstance(raised.value, FileNotFoundError)
    assert li.register_serve_install() == ()
    assert b"\ninstall=\n" in li.register_serve_owner_text("2026-11-15T00:00:00Z")


class _FailingOs:
    """The module's `os`, whose `stat` fails for one basename, with `errno`."""

    def __init__(self, real, basename, code):
        self._real, self._basename, self._code = real, basename, code

    def __getattr__(self, name):
        return getattr(self._real, name)

    def stat(self, path, *args, **kwargs):
        if os.path.basename(str(path)) == self._basename:
            raise OSError(self._code, os.strerror(self._code), str(path))
        return self._real.stat(path, *args, **kwargs)


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.ENOTDIR, errno.EIO,
                                  errno.ELOOP, errno.ENAMETOOLONG])
def test_t512i_each_other_failure_to_stat_the_module_is_empty(tmp_path, monkeypatch, code):
    path, li = _install_in(tmp_path / "bare")
    _ensure_module(tmp_path / "bare")
    assert len(li.register_serve_install()) == 6
    monkeypatch.setattr(li, "os", _FailingOs(os, MODULE, code))
    assert li.register_serve_install() == ()


def test_t512i_absence_alone_is_the_three_numbers_not_empty(tmp_path, monkeypatch):
    """`FileNotFoundError` for the module, by `ENOENT` however it arises, is
    no module file: three numbers."""
    path, li = _install_in(tmp_path / "bare")
    monkeypatch.setattr(li, "os", _FailingOs(os, MODULE, errno.ENOENT))
    assert li.register_serve_install() == _ident(path)


def test_t512i_a_launcher_whose_stat_fails_is_empty_module_or_not(tmp_path, monkeypatch):
    path, li = _install_in(tmp_path / "bare")
    _ensure_module(tmp_path / "bare")
    monkeypatch.setattr(li, "os", _FailingOs(os, "lanes-index", errno.EACCES))
    assert li.register_serve_install() == ()


def test_t512i_the_owner_text_names_both_files_and_passes_rule_4(tmp_path):
    path, li = _install_in(tmp_path / "bare")
    if not T124_TREE:       # a tree of T124's form has its module from the start
        bare = li.register_serve_owner_text("2026-11-15T00:00:00Z").decode("utf-8")
        line = [text for text in bare.splitlines() if text.startswith("install=")]
        assert line == ["install=" + " ".join(map(str, _ident(path)))]
        assert li._REGISTER_SERVE_INSTALL_RE.fullmatch(line[0][len("install="):])
    module = _ensure_module(tmp_path / "bare")
    both = li.register_serve_owner_text("2026-11-15T00:00:00Z").decode("utf-8")
    line = [text for text in both.splitlines() if text.startswith("install=")]
    assert line == ["install=" + " ".join(map(str, _ident(path) + _ident(module)))]
    assert li._REGISTER_SERVE_INSTALL_RE.fullmatch(line[0][len("install="):])


# =========================================================== rule 4

LI = _load(INDEXER)
_RE = LI._REGISTER_SERVE_INSTALL_RE
_MTIME = "1763190000123456789"       # 19 digits, as an mtime in nanoseconds has


def _runs(count):
    return " ".join(str(10 ** (index % 3) + index) for index in range(count))


@pytest.mark.parametrize("value", [
    "1 2 3", _runs(3), f"4096 {_MTIME} 1234567", "0 0 0", "00 007 0",
    _runs(6), f"4096 {_MTIME} 1234567 8192 {_MTIME} 7654321", "0 0 0 0 0 0",
    " ".join(["9" * 40] * 6)],
    ids=["three-minimal", "three-runs", "three-real", "three-zeros", "three-leading-zeros",
         "six-runs", "six-real", "six-zeros", "six-long"])
def test_t512i_rule_4_accepts_three_runs_and_six(value):
    assert _RE.fullmatch(value), value


@pytest.mark.parametrize("count", [0, 1, 2, 4, 5, 7, 8, 9, 12])
def test_t512i_rule_4_refuses_every_other_count_of_runs(count):
    assert not _RE.fullmatch(_runs(count)), count


@pytest.mark.parametrize("value", [
    "1  2 3", "1 2  3", "1 2 3 4  5 6", "1 2 3  4 5 6", "1  2 3 4 5 6",
    " 1 2 3", " 1 2 3 4 5 6", "1 2 3 ", "1 2 3 4 5 6 ", "  1 2 3", "1 2 3  ",
    "1 2 3\n", "1 2 3 4 5 6\n", "\n1 2 3", "\n1 2 3 4 5 6", "1 2 3\r", "1 2 3\n\n",
    "1\t2 3", "1 2\t3 4 5 6", "1 2 3\t4 5 6", "1\n2\n3", "1,2,3", "1 2 3,4 5 6",
    "1 2 3 4 5 6 7", "1 2 3 4 5", "1 2 3 4",
    "", " ", "1", "1 2", "\n", "install=1 2 3",
    "-1 2 3", "1 -2 3", "1 2 +3", "1.5 2 3", "0x1 2 3", "1 2 3 4 5 x", "a b c", "1 2 c",
    "1 2 3 4 5 6 7 8 9",
    "١ ٢ ٣", "１ ２ ３", "1 2 ３", "1 2 3 ４ ５ ６", "² ³ ¹", "१ २ ३ ४ ५ ६", "1 2 3 ４ 5 6",
    "1 2 3", "1 2 3 ", "1 2 3\x00", "1 2 3",
    ], ids=lambda value: repr(value))
def test_t512i_rule_4_refuses_every_other_form(value):
    assert not _RE.fullmatch(value), repr(value)


def test_t512i_rule_4_is_applied_with_fullmatch_and_a_trailing_newline_is_refused():
    """The regex has no `$`, whose `match` would let one trailing newline
    through; `fullmatch` is how the client applies it."""
    assert not _RE.fullmatch("1 2 3\n") and not _RE.fullmatch("1 2 3 4 5 6\n")
    assert _RE.pattern.count("$") == 0
    source = open(RULE_SOURCE, encoding="utf-8").read()    # the module's text, where there is one
    assert "_REGISTER_SERVE_INSTALL_RE.fullmatch(owner[" in source
    assert "_REGISTER_SERVE_INSTALL_RE.match(" not in source


def test_t512i_the_launchers_module_name_equals_register_serve_module():
    """Lane 1's R2, NIT 2: `REGISTER_SERVE_MODULE` repeats the launcher's own
    literal, and only this case checks that the two stay equal. The launcher's
    `.py` names are the string constants of its text, with no directory in
    them; there is one, it is the module's file, and it is the constant's."""
    if not T124_TREE:
        pytest.skip(f"this tree's lanes-index is not T124's launcher: there is no {MODULE} "
                    f"beside it, so there is no second literal to compare")
    tree = ast.parse(open(INDEXER, encoding="utf-8").read())
    names = {node.value for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and node.value.endswith(".py") and "/" not in node.value and " " not in node.value}
    assert names == {LI.REGISTER_SERVE_MODULE}, names
    assert os.path.isfile(os.path.join(os.path.dirname(INDEXER), LI.REGISTER_SERVE_MODULE))


# ============================================= the client, over a socket

def _client_run(tmp_path, monkeypatch):
    """A `run/` of this uid in `tmp_path` at mode 0700, reached by a RELATIVE
    path from a changed directory, so the socket's path is short whatever
    `tmp_path` is."""
    monkeypatch.chdir(tmp_path)
    os.mkdir("run", 0o700)
    os.chmod("run", 0o700)
    paths = {"run": "run", "sock": "run/register.sock", "owner": "run/register.owner",
             "lock": "run/register.lock", "failed": "run/register.failed",
             "log": "run/register.log"}
    return paths


def _owner_file(li, install):
    lines = ["pid=1", "started=2026-11-15T00:00:00Z", f"install={install}"]
    lines += [f"{key}={value}" for key, value in sorted(li.register_serve_host().items())]
    return ("\n".join(lines) + "\n").encode("utf-8")


class _ListeningSocket:
    """A socket listening at `path`, accepting one connection, reading its
    request and closing it, so the client's answer is empty and whole."""

    def __init__(self, path):
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(4)
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        try:
            conn.settimeout(5)
            while True:
                data = conn.recv(65536)
                if not data or data.endswith(b"end\n"):
                    break
        except OSError:
            pass
        finally:
            conn.close()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.close()
        self.thread.join(5)


def _ask(li, paths, monkeypatch, owner_install, client_install):
    """What `register_serve_ask` returns for an owner file naming
    `owner_install`, from a client whose own install is `client_install`."""
    monkeypatch.setattr(li, "register_serve_paths", lambda: paths)
    monkeypatch.setattr(li, "register_serve_install", lambda: client_install)
    with open(paths["owner"], "wb") as handle:
        handle.write(_owner_file(li, owner_install))
    with _ListeningSocket(paths["sock"]):
        return li.register_serve_ask(b"list\nend\n", time.monotonic() + 5)


UNUSABLE = ("unavailable", "its owner file cannot be read, or names no install", False)
THREE = (4096, 1763190000123456789, 1234567)
SIX = THREE + (8192, 1763190000987654321, 7654321)
text = lambda numbers: " ".join(map(str, numbers))   # noqa: E731


def test_t512i_an_owner_file_of_three_read_by_a_client_of_six_is_another_install(tmp_path, monkeypatch):
    """The upgrade: a pre-T124 service's three numbers are well formed, and
    differ as text from the new client's six. So the client STARTS a service
    (the third item True) and reads through the old one; it is not unusable."""
    li = LI
    paths = _client_run(tmp_path, monkeypatch)
    got = _ask(li, paths, monkeypatch, text(THREE), SIX)
    assert got[0] == "answer" and got[2] is True, got


def test_t512i_an_owner_file_of_six_read_by_a_client_of_three_is_another_install(tmp_path, monkeypatch):
    li = LI
    paths = _client_run(tmp_path, monkeypatch)
    got = _ask(li, paths, monkeypatch, text(SIX), THREE)
    assert got[0] == "answer" and got[2] is True, got


def test_t512i_an_owner_file_of_six_read_by_a_client_of_the_same_six_is_this_install(tmp_path, monkeypatch):
    li = LI
    paths = _client_run(tmp_path, monkeypatch)
    got = _ask(li, paths, monkeypatch, text(SIX), SIX)
    assert got[0] == "answer" and got[2] is False, got


def test_t512i_an_owner_file_of_three_read_by_a_client_of_the_same_three_is_this_install(tmp_path, monkeypatch):
    li = LI
    paths = _client_run(tmp_path, monkeypatch)
    got = _ask(li, paths, monkeypatch, text(THREE), THREE)
    assert got[0] == "answer" and got[2] is False, got


def test_t512i_the_same_leading_three_with_another_module_is_another_install(tmp_path, monkeypatch):
    """Six against six that differ in the module's three alone."""
    li = LI
    paths = _client_run(tmp_path, monkeypatch)
    other = THREE + (8192, 1763190000987654322, 7654321)
    got = _ask(li, paths, monkeypatch, text(SIX), other)
    assert got[0] == "answer" and got[2] is True, got


@pytest.mark.parametrize("owner_install", ["", " ", "1 2 3 4", "1 2 3 4 5", f"{text(SIX)} 7",
                                           f"{text(SIX)} ", f" {text(THREE)}", "1  2 3"],
                         ids=["empty", "space", "four", "five", "seven", "trailing", "leading",
                              "double-space"])
@pytest.mark.parametrize("client_install", [THREE, SIX], ids=["client-three", "client-six"])
def test_t512i_an_owner_file_that_is_neither_three_nor_six_is_unusable_and_starts_none(
        tmp_path, monkeypatch, owner_install, client_install):
    """Rule 7's empty value, and every other form rule 4 refuses: unavailable,
    the client reads directly, and `start` is False."""
    li = LI
    paths = _client_run(tmp_path, monkeypatch)
    assert _ask(li, paths, monkeypatch, owner_install, client_install) == UNUSABLE
