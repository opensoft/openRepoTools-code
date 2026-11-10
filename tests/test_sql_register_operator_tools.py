# SPDX-License-Identifier: Apache-2.0
"""Feature 007's AT-P8, the operator tools: the bootstrap, the readiness check
and the flip (L2-N5; T218; FR-001, FR-050, FR-054, FR-055, FR-059)
(opensoft/openRepoTools#165).

The test plan's twelve names, byte for byte (AT-P8, "Tests."). This part,
T218a, holds the flip's three: `lanes-index set-mode index|primary [--config
<path>]` (operations.md section 2.4; lane 1's T120, which selects them with
`sql_register_operator_tools and (set_mode_primary or the_flip_writes_only or
the_flip_refuses)`).

THE ORACLE IS AT-P8'S. Setting `primary` refuses with 2, writing nothing,
unless the switch is `primary`, the marker `present`, and the fetched
`lanes/STORE` names this database. The flip writes only `mode=`, keeps the
file's 0600, and leaves the password file as it was. A configuration the flip
cannot write is refused, with nothing written; a read-only mount is flipped
from the host. Each refusal here is shown against its own control: the same
estate with the one fault taken away flips, so a refusal is the condition's
and never a verb this build lacks.

THE ESTATE (FM: no engine). Every case runs a copy of `lanes-index` with
`RENDER_GIT_HALF` set True (T203's `flipped_copy`), so Q6(c)'s refusal, which
comes first, never answers for the conditions tested here. Beside the copy is
`lanes-edit.sh`, which answers `workspace-root` from `$HOME/.agents/
workspace.yaml`'s `path:`, as `test_lanes_index.py` and T215 name the
workspace (Amendment 9(a)). That checkout is a clone of a bare origin, whose
`main` carries `lanes/STORE` (D21's `key=value` lines) or not, per case. The
register's database is the register's fake `psql` (T203), taught one answer,
the switch's row (`mode`, `marker_state`, `database_label`, `set_seq`) as
TEXT-format COPY with `_query_many`'s separator line after it. The
configuration names both URLs on loopback (the fake's host rule), a 0600
password file, and `register_label=`.

READ FROM LANE 1'S CODE, NOT A CONTRACT (T120 at `fc9794af`): the switch's
read as one `SELECT mode, marker_state, database_label, set_seq` of
`register_switch` (so the fake is taught by matching `register_switch`), and
the separator line `\\x1eLANES-INDEX-NEXT` after each COPY's rows.

THE CASES THAT REST ON LANE 1'S STRICTER READINGS (#165 6768689263), which
wait for lane 3's word:
- `[label-not-the-switchs]` rests on reading 2: "`origin/main` names this
  database" requires `register_label=` and compares it. Its origin names the
  switch's label, which is not `register_label=`'s;
- `[fetch-fails]` rests on reading 3: the fetch must succeed. Its checkout's
  `origin/main`, fetched before, already names this database.
Every other case refuses, or flips, under any of the readings.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import (REGISTER_FAKE_PSQL, RENDER_GIT_HALF_LINE, flipped_copy,
                                  guard_strip_env)

pytestmark = [WINDOWS_SKIP]

#: The label `register_label=` names, and the one the second database's
#: switch names.
LABEL = "register-p8"
OTHER = "register-p8-other"

#: The register's schema, `register_schema=`'s default.
SCHEMA = "lanes_register"

#: The separator `_query_many` reads after each COPY's rows (T106's
#: `REGISTER_MARKER_COPY`, read from lane 1's code).
NEXT = "\x1eLANES-INDEX-NEXT"

#: The URL both logins name: loopback, the fake's host rule.
URL = "postgresql://p8_login@127.0.0.1:55432/register_db"


def _private(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _script(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _store(database: str, store: str = "primary") -> str:
    """`lanes/STORE` in D21's form, one `key=value` per line."""
    return "\n".join([f"store={store}", f"database={database}", "import=1",
                      "lanes-tree=0000000000000000000000000000000000000000",
                      "utc=2026-11-10T00:00:00Z", ""])


class Estate:
    """One host's configuration, a workspace checkout of a bare origin, the
    flipped `lanes-index` beside `lanes-edit.sh`, and the fake `psql`."""

    def __init__(self, root: Path):
        self.root = root
        tool = root / "tool"
        tool.mkdir(parents=True)
        source = REPO / "lanes-index"
        # A BUILD BEFORE lane 1's T105 has no `RENDER_GIT_HALF`, and so no
        # Q6(c) refusal to set aside: it is copied as it is, and the case
        # meets its own assertions.
        if len(RENDER_GIT_HALF_LINE.findall(source.read_bytes())) == 1:
            self.copy = flipped_copy(source, tool, True)
        else:
            self.copy = tool / "lanes-index"
            shutil.copy2(source, self.copy)
        for name in ("lanes-edit.sh", "repos.tsv"):
            if (REPO / name).exists():
                shutil.copy2(REPO / name, tool / name)
        self.fakebin = root / "fakebin"
        _script(self.fakebin / "psql", REGISTER_FAKE_PSQL)
        self.psql_log = root / "psql.log"
        self.answers = root / "psql-answers.json"
        self.answers.write_text("[]", encoding="utf-8")
        home = self.home = root / "home"
        self.origin = root / "origin.git"
        self.seed = root / "seed"
        self.wip = home / "projects" / "wip"
        self.wip.parent.mkdir(parents=True)
        (root / "t").mkdir()
        self.passfile = _private(root / "secret" / "pgpass",
                                 "127.0.0.1:55432:register_db:p8_login:not-a-secret\n")
        self.passfile_bytes = self.passfile.read_bytes()
        env = guard_strip_env(os.environ, strip=("T218_",))
        for name in ("XDG_CONFIG_HOME", "LANES_INDEX_CONFIG", "LANES_GIT_TIMEOUT"):
            env.pop(name, None)
        env.update(HOME=str(home), XDG_STATE_HOME=str(root / "state"),
                   XDG_CONFIG_HOME=str(root / "config"), TMPDIR=str(root / "t"),
                   LANES_NO_GITHUB="1", LANES_REPO=str(self.wip),
                   FAKE_PSQL_LOG=str(self.psql_log), FAKE_PSQL_ANSWERS=str(self.answers),
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                   GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                   PATH=os.pathsep.join([str(self.fakebin),
                                         os.environ.get("PATH", os.defpath)]))
        self.env = env
        self._git("init", "-q", "--bare", "-b", "main", str(self.origin))
        self._git("init", "-q", "-b", "main", str(self.seed))
        # `lanes-edit.sh workspace-root` finds the workspace by its registry.
        (self.seed / "lanes").mkdir()
        (self.seed / "lanes" / "LANES.md").write_text("# Lanes\n", encoding="utf-8")
        self._git("-C", str(self.seed), "add", "lanes/LANES.md")
        self._git("-C", str(self.seed), "commit", "-q", "-m", "seed")
        self._git("-C", str(self.seed), "push", "-q", str(self.origin), "main")
        self._git("clone", "-q", str(self.origin), str(self.wip))
        (home / ".agents").mkdir()
        (home / ".agents" / "workspace.yaml").write_text(
            f"repository: {self.origin}\npath: {self.wip}\n", encoding="utf-8")

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], check=True, env=self.env, capture_output=True,
                       stdin=subprocess.DEVNULL)

    # ------------------------------------------------------------------ origin
    def marker(self, text: str | None) -> None:
        """Origin's `main` gains `lanes/STORE` holding `text`, or loses it
        where `text` is None. The checkout's `origin/main` stays as last
        fetched."""
        target = self.seed / "lanes" / "STORE"
        if text is None:
            if target.exists():
                self._git("-C", str(self.seed), "rm", "-q", "lanes/STORE")
                self._git("-C", str(self.seed), "commit", "-q", "-m", "no marker")
        else:
            target.parent.mkdir(exist_ok=True)
            target.write_text(text, encoding="utf-8")
            self._git("-C", str(self.seed), "add", "lanes/STORE")
            self._git("-C", str(self.seed), "commit", "-q", "--allow-empty", "-m", "marker")
        self._git("-C", str(self.seed), "push", "-q", str(self.origin), "main")

    def fetch(self) -> None:
        self._git("-C", str(self.wip), "fetch", "-q", "origin")

    def unreachable_origin(self) -> None:
        """The checkout's `origin` names a path with nothing there: its fetch
        fails, and its `origin/main` stays as last fetched."""
        self._git("-C", str(self.wip), "remote", "set-url", "origin",
                  str(self.root / "no-origin.git"))

    # ------------------------------------------------------------------ switch
    def switch(self, mode: str, marker: str, label: str, set_seq: int = 7) -> None:
        """The fake answers the switch's read with one row."""
        row = "\t".join([mode, marker, label, str(set_seq)])
        self.answers.write_text(json.dumps([
            {"match": "register_switch", "stdout": f"{row}\n{NEXT}\n"}]), encoding="utf-8")

    def requests(self) -> list:
        """The fake's calls that carry a request (never a `--version`)."""
        if not self.psql_log.exists():
            return []
        entries = [json.loads(line) for line in
                   self.psql_log.read_text(encoding="utf-8").splitlines() if line]
        return [entry for entry in entries if entry.get("kind") != "version"]

    # ----------------------------------------------------------- configuration
    def config(self, mode: str, *, label: str = LABEL, name: str = "conf") -> Path:
        """A 0600 configuration at `mode`, both URLs on loopback, the password
        file, and `register_label=<label>`."""
        return _private(self.root / name / "lanes-index.conf", "\n".join([
            f"mode={mode}", f"register_url={URL}", f"register_passfile={self.passfile}",
            f"reader_url={URL}", f"reader_passfile={self.passfile}",
            f"register_label={label}", f"register_schema={SCHEMA}", ""]))

    def set_mode(self, mode: str, config: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.copy), "set-mode", mode,
                               "--config", str(config)],
                              capture_output=True, text=True, env=self.env, cwd=str(self.wip),
                              timeout=120, stdin=subprocess.DEVNULL)


def _state(path: Path) -> tuple:
    """A configuration's bytes, its mode bits, and its directory's names."""
    return (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
            sorted(p.name for p in path.parent.iterdir()))


def _said(proc: subprocess.CompletedProcess) -> str:
    return f"exit {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"


def _mode_lines(path: Path) -> list:
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.split("=", 1)[0].strip() == "mode"]


# ---------------------------------------------------------------- set-mode primary
#: Each fault, and what the estate is otherwise: the switch at `primary` with
#: the marker `present` naming LABEL, and origin's `lanes/STORE` naming LABEL
#: with `store=primary`, fetched.
REFUSALS = {
    # the switch not yet at `primary`: the bootstrap's switch, before the cutover
    "switch-files": dict(switch=("files", "absent", LABEL)),
    # the marker still being added
    "marker-adding": dict(switch=("primary", "adding", LABEL)),
    # the cutover's marker not on origin
    "no-marker-on-origin": dict(marker=None),
    # origin's marker is another database's
    "marker-names-another": dict(marker=_store(OTHER)),
    # origin's marker says the files store
    "marker-says-files": dict(marker=_store(LABEL, store="files")),
    # reading 2: the switch and origin name another database than register_label=
    "label-not-the-switchs": dict(switch=("primary", "present", OTHER), marker=_store(OTHER)),
    # reading 3: the fetch fails, though origin/main, as last fetched, names LABEL
    "fetch-fails": dict(unreachable=True),
}


@pytest.mark.parametrize("fault", list(REFUSALS))
def test_set_mode_primary_refuses_before_the_marker_is_present_or_names_another_database(
        tmp_path, fault):
    estate = Estate(tmp_path)
    case = REFUSALS[fault]
    estate.switch(*case.get("switch", ("primary", "present", LABEL)))
    estate.marker(case.get("marker", _store(LABEL)))
    estate.fetch()
    if case.get("unreachable"):
        estate.unreachable_origin()
    config = estate.config("index")
    before = _state(config)

    proc = estate.set_mode("primary", config)
    assert proc.returncode == 2, f"[{fault}] set-mode primary is not refused with 2:\n{_said(proc)}"
    assert _state(config) == before, (
        f"[{fault}] the refused flip changed the configuration, its mode or its directory:\n"
        f"{_said(proc)}")
    assert _mode_lines(config) == ["mode=index"]
    assert estate.passfile.read_bytes() == estate.passfile_bytes

    # THE CONTROL: the same estate with the fault taken away flips to primary.
    other = estate.config("index", name="control")
    estate.switch("primary", "present", LABEL)
    if case.get("unreachable"):
        estate._git("-C", str(estate.wip), "remote", "set-url", "origin", str(estate.origin))
    estate.marker(_store(LABEL))
    estate.fetch()
    proc = estate.set_mode("primary", other)
    assert proc.returncode == 0, (
        f"[{fault}] the control, with the fault taken away, does not flip:\n{_said(proc)}")
    assert _mode_lines(other) == ["mode=primary"]


# ---------------------------------------------------------------------- the flip
def test_the_flip_writes_only_mode_and_keeps_0600(tmp_path):
    estate = Estate(tmp_path)
    estate.switch("primary", "present", LABEL)
    estate.marker(_store(LABEL))
    estate.fetch()
    # A comment, a blank line and a key after `mode=` stay where they are.
    config = _private(tmp_path / "conf" / "lanes-index.conf", "\n".join([
        "# this host's register", f"register_url={URL}", "mode=index", "",
        f"register_passfile={estate.passfile}", f"reader_url={URL}",
        f"reader_passfile={estate.passfile}", f"register_label={LABEL}",
        f"register_schema={SCHEMA}", ""]))
    original = config.read_bytes()
    lines = original.decode("utf-8").splitlines(keepends=True)

    # To `primary`: the diff is the mode= line alone.
    proc = estate.set_mode("primary", config)
    assert proc.returncode == 0, f"set-mode primary does not flip:\n{_said(proc)}"
    after = config.read_text(encoding="utf-8").splitlines(keepends=True)
    assert len(after) == len(lines), f"set-mode primary changed the line count: {after}"
    changed = [(old, new) for old, new in zip(lines, after) if old != new]
    assert changed == [("mode=index\n", "mode=primary\n")], (
        f"set-mode primary changed more than the mode= line, or not it: {changed}")
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert estate.passfile.read_bytes() == estate.passfile_bytes
    assert sorted(p.name for p in config.parent.iterdir()) == ["lanes-index.conf"]

    # And back to `index`: the file is byte for byte the one it was.
    proc = estate.set_mode("index", config)
    assert proc.returncode == 0, f"set-mode index does not flip back:\n{_said(proc)}"
    assert config.read_bytes() == original, "set-mode index did not restore the file"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert estate.passfile.read_bytes() == estate.passfile_bytes
    assert sorted(p.name for p in config.parent.iterdir()) == ["lanes-index.conf"]


#: A configuration this account cannot rewrite: its directory, or the file.
UNWRITABLE = {"directory": "directory", "file": "file"}


@pytest.mark.parametrize("what", list(UNWRITABLE))
@pytest.mark.parametrize("mode", ["primary", "index"])
def test_the_flip_refuses_a_configuration_it_cannot_write(tmp_path, what, mode):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("as root every file can be written: the case needs an unprivileged account")
    estate = Estate(tmp_path)
    estate.switch("primary", "present", LABEL)
    estate.marker(_store(LABEL))
    estate.fetch()
    config = estate.config("index" if mode == "primary" else "primary")
    target = config.parent if what == "directory" else config
    saved = stat.S_IMODE(target.stat().st_mode)
    target.chmod(0o500 if what == "directory" else 0o400)
    try:
        before = _state(config)
        proc = estate.set_mode(mode, config)
        assert proc.returncode == 2, (
            f"set-mode {mode} on a {what} it cannot write is not refused with 2:\n{_said(proc)}")
        assert _state(config) == before, f"the refused flip changed the {what}:\n{_said(proc)}"
        assert estate.requests() == [], "the refused flip sent a request to the database"
    finally:
        target.chmod(saved)
    # THE CONTROL: writable again, the same flip is made.
    proc = estate.set_mode(mode, config)
    assert proc.returncode == 0, f"the control, writable, does not flip:\n{_said(proc)}"
    assert _mode_lines(config) == [f"mode={mode}"]
