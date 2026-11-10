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

import hashlib
import json
import os
import re
import shutil
import socket
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


# =========================================================== the readiness check
#
# T218b: `lanes-index ready [--expect index|primary] [--release <version>]
# [--env <name>]` (operations.md section 2.4; lane 1's T119, which selects
# these with `sql_register_operator_tools and (the_readiness_check_fails or
# the_readiness_check_passes or the_readiness_check_10 or
# the_readiness_check_13)`). Its line form is T119's entry (lane 1's, which
# lane 3 accepted, #165 6754522885): `check <n>: ok` or `check <n>: FAIL:
# <reason>`, one line per check in order, then a last line; exit 0 when every
# check passed, 2 when any failed, 64 for usage. It changes nothing.
#
# THE KINDS (AT-P8): FP for the digest, `psql` and refusing-build faults, and
# for check 13, which reads only the resolver; RE for the ready environment,
# its other faults, and check 10. The ready environment is section 5.6's TLS
# cluster (T229), bootstrapped under the pty through its own admin service
# (T109), with one engineer's two logins made by `lanes-index login add`
# (T110), since check 11 always fails on a Unix socket. Until T229 gives that
# cluster, the RE cases fail by `ReadyEnvironment`'s own assertion on an
# engine bench, and skip with T205's banner on one with no engine.
#
# READ, NOT FOUND IN A CONTRACT: the release's digest list is read as a
# `SHA256SUMS` file in `sha256sum`'s form beside the installed `lanes-index`,
# named by `--release <version>` (the design leaves its form open: "its form
# is the design's"); and check 13's "the fake `psql`'s log is empty" is read
# as "check 13's line does not depend on the fake's answers", since the run's
# other checks still connect.

#: One check's line (T119's line form).
CHECK_LINE = re.compile(r"^check (\d+): (ok|FAIL)\b:?[ \t]*(.*)$", re.M)


def _checks(text: str) -> dict:
    """`ready`'s check lines, by number: (`ok` or `FAIL`, the reason)."""
    return {int(m.group(1)): (m.group(2), m.group(3) or "") for m in CHECK_LINE.finditer(text)}


def _addresses(host: str) -> list:
    """The distinct addresses `host` resolves to, by libpq's own lookup:
    `getaddrinfo` with `SOCK_STREAM`, any family, no flags (check 13)."""
    return sorted({info[4][0] for info in
                   socket.getaddrinfo(host, 5432, 0, socket.SOCK_STREAM)})


class ReadyBench(Estate):
    """The FP half: the estate of T218a, with a configuration at `index`, the
    workstation named, and the installed tools' release digest list."""

    RELEASE = "0.0.0-t218"

    def __init__(self, root: Path):
        super().__init__(root)
        self.env["LANES_WORKSTATION"] = "Eagle"
        self.digests(stale=False)

    def digests(self, *, stale: bool) -> None:
        tool = self.copy.parent
        lines = []
        for name in sorted(p.name for p in tool.iterdir()):
            if name == "SHA256SUMS" or not (tool / name).is_file():
                continue
            digest = hashlib.sha256((tool / name).read_bytes()).hexdigest()
            if stale and name == "lanes-index":
                digest = hashlib.sha256(b"another release").hexdigest()
            lines.append(f"{digest}  {name}\n")
        (tool / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")

    def ready(self, config: Path, *args: str, path: str | None = None,
              copy: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env, LANES_INDEX_CONFIG=str(config))
        if path is not None:
            env["PATH"] = path
        return subprocess.run([sys.executable, str(copy or self.copy), "ready",
                               "--release", self.RELEASE, "--env", "t218", *args],
                              capture_output=True, text=True, env=env, cwd=str(self.wip),
                              timeout=120, stdin=subprocess.DEVNULL)

    def path_without_psql(self) -> str:
        """`PATH` with no `psql` on it: every entry that holds one is left out,
        and `git` is kept by a link of its own."""
        keep = self.root / "nopsql"
        keep.mkdir(exist_ok=True)
        real_git = shutil.which("git", path=self.env["PATH"])
        if real_git and not (keep / "git").exists():
            (keep / "git").symlink_to(real_git)
        entries = [entry for entry in os.environ.get("PATH", os.defpath).split(os.pathsep)
                   if entry and not os.access(os.path.join(entry, "psql"), os.X_OK)]
        return os.pathsep.join([str(keep), *entries])


class ReadyEnvironment:
    """The RE half: AT-P8's ready environment. It needs section 5.6's TLS
    cluster (T229), which `tests/pgcluster.py` does not give yet, so it fails
    by its own assertion until T229 lands; with no engine, the
    `stoppable_cluster` it asks for first skips with T205's banner."""

    def __init__(self, request, root: Path):
        request.getfixturevalue("stoppable_cluster")
        import pgcluster
        tls = getattr(pgcluster, "tls_cluster", None)
        assert tls is not None, (
            "AT-P8's ready environment needs section 5.6's TLS cluster, T229's, since check "
            "11 always fails on a Unix socket; tests/pgcluster.py has no tls_cluster yet")
        self.bench = ReadyBench(root)
        self.cluster = request.getfixturevalue("tls_cluster")
        self.config = self.cluster.ready_configuration(self.bench, label=LABEL)

    def ready(self, *args: str) -> subprocess.CompletedProcess:
        return self.bench.ready(self.config, *args)

    def admin(self, sql: str) -> None:
        """One statement through the admin connection, as the owner."""
        self.cluster.psql(f"SET ROLE lanes_register_owner; {sql}")


#: Each fault: the check it fails, its kind, and what it does to the
#: environment (AT-P8's oracle, "The readiness check").
FAULTS = {
    "stale-digest": (1, "FP"),
    "no-psql": (2, "FP"),
    "refusing-build": (5, "FP"),
    "early-primary": (3, "RE"),
    "grant-outside-scope": (4, "RE"),
    "workstation-unset": (6, "RE"),
    "outage-declared": (7, "RE"),
    "expect-primary-switch-files": (8, "RE"),
    "expect-primary-origin-another": (8, "RE"),
    "version-window": (9, "RE"),
}


def _fp_fault(bench: ReadyBench, fault: str) -> subprocess.CompletedProcess:
    config = bench.config("index")
    if fault == "stale-digest":
        bench.digests(stale=True)
        return bench.ready(config, "--expect", "index")
    if fault == "no-psql":
        return bench.ready(config, "--expect", "index", path=bench.path_without_psql())
    if fault == "refusing-build":
        found = RENDER_GIT_HALF_LINE.findall((REPO / "lanes-index").read_bytes())
        assert len(found) == 1, (
            "[refusing-build] lanes-index has no RENDER_GIT_HALF line: lane 1's T105, test "
            "14's refusing state, has not landed, so there is no refusing build to check")
        refusing = flipped_copy(REPO / "lanes-index", bench.root / "refusing", False)
        return bench.ready(config, "--expect", "index", copy=refusing)
    raise AssertionError(f"no FP fault {fault}")


def _re_fault(env: ReadyEnvironment, fault: str) -> subprocess.CompletedProcess:
    bench = env.bench
    if fault == "early-primary":
        text = env.config.read_text(encoding="utf-8").replace("mode=index", "mode=primary")
        env.config.write_text(text, encoding="utf-8")
        return env.ready("--expect", "index")
    if fault == "grant-outside-scope":
        env.admin("GRANT INSERT ON lanes_register.journal TO lanes_register_reader")
        return env.ready("--expect", "index")
    if fault == "workstation-unset":
        bench.env.pop("LANES_WORKSTATION", None)
        return env.ready("--expect", "index")
    if fault == "outage-declared":
        proc = subprocess.run([sys.executable, str(bench.copy), "outage", "declare",
                               "--until", "2099-01-01T00:00:00Z", "--why", "t218 fault"],
                              capture_output=True, text=True, timeout=120, cwd=str(bench.wip),
                              env=dict(bench.env, LANES_INDEX_CONFIG=str(env.config)),
                              stdin=subprocess.DEVNULL)
        assert proc.returncode == 0, f"outage declare (T121) did not declare:\n{_said(proc)}"
        return env.ready("--expect", "index")
    if fault == "expect-primary-switch-files":
        bench.marker(_store(LABEL))
        return env.ready("--expect", "primary")
    if fault == "expect-primary-origin-another":
        env.admin("UPDATE lanes_register.register_switch SET mode = 'primary', "
                  "marker_state = 'present', import_commit = repeat('a', 40), "
                  "import_tree = repeat('b', 40), import_seq = 0, marker_seq = 1, "
                  "marker_commit = repeat('c', 40) WHERE id = 1")
        bench.marker(_store(OTHER))
        return env.ready("--expect", "primary")
    if fault == "version-window":
        env.admin("UPDATE lanes_register.schema_window SET writers_from = version + 1, "
                  "readers_from = version + 1")
        return env.ready("--expect", "index")
    raise AssertionError(f"no RE fault {fault}")


@pytest.mark.parametrize("fault", list(FAULTS))
def test_the_readiness_check_fails_on_each_fault(tmp_path, request, fault):
    number, kind = FAULTS[fault]
    if kind == "FP":
        proc = _fp_fault(ReadyBench(tmp_path), fault)
    else:
        proc = _re_fault(ReadyEnvironment(request, tmp_path), fault)
    checks = _checks(proc.stdout)
    assert proc.returncode == 2, f"[{fault}] ready does not exit 2:\n{_said(proc)}"
    assert checks.get(number, ("", ""))[0] == "FAIL", (
        f"[{fault}] check {number} is not a FAIL line of its own:\n{_said(proc)}")
    if kind == "RE":
        others = sorted(n for n, (state, _) in checks.items() if state == "FAIL" and n != number)
        assert others == [], f"[{fault}] other checks fail too: {others}\n{_said(proc)}"


def test_the_readiness_check_passes_a_ready_environment(tmp_path, request):
    env = ReadyEnvironment(request, tmp_path)
    proc = env.ready("--expect", "index")
    checks = _checks(proc.stdout)
    assert proc.returncode == 0, f"ready fails a ready environment:\n{_said(proc)}"
    assert sorted(checks) == list(range(1, 14)), f"not one line per check:\n{_said(proc)}"
    assert all(state == "ok" for state, _ in checks.values()), _said(proc)


#: Check 10's cases (AT-P8): the switch, the configuration, and whether it fails.
CHECK_10 = ["equal", "label-only", "url-only", "files"]


@pytest.mark.parametrize("case", CHECK_10)
def test_the_readiness_check_10_compares_register_label_with_the_switch_label(
        tmp_path, request, case):
    env = ReadyEnvironment(request, tmp_path)
    primary = ("UPDATE lanes_register.register_switch SET mode = 'primary', "
               "marker_state = 'present', import_commit = repeat('a', 40), "
               "import_tree = repeat('b', 40), import_seq = 0, marker_seq = 1, "
               "marker_commit = repeat('c', 40) WHERE id = 1")
    if case != "files":
        env.admin(primary)
    text = env.config.read_text(encoding="utf-8")
    if case == "label-only":
        text = text.replace(f"register_label={LABEL}", f"register_label={OTHER}")
    elif case == "url-only":
        second = env.cluster.second_database(label=OTHER)
        second.admin(primary)
        text = text.replace(env.cluster.database_name, second.name)
    elif case == "files":
        text = text.replace(f"register_label={LABEL}", f"register_label={OTHER}")
    env.config.write_text(text, encoding="utf-8")
    proc = env.ready("--expect", "index")
    state, reason = _checks(proc.stdout).get(10, ("", ""))
    if case in ("equal", "files"):
        assert state == "ok", f"[{case}] check 10 is not ok:\n{_said(proc)}"
    else:
        assert state == "FAIL" and proc.returncode == 2, (
            f"[{case}] check 10 does not fail:\n{_said(proc)}")
        x, y = (OTHER, LABEL) if case == "label-only" else (LABEL, OTHER)
        assert f"register_label={x}, but the switch names {y}" in reason, _said(proc)


#: Check 13's cases (AT-P8): `register_addresses=` equal to the count, one
#: below it, and an IP literal with no `register_addresses=`.
CHECK_13 = ["equal", "above", "ip-literal"]


@pytest.mark.parametrize("case", CHECK_13)
def test_the_readiness_check_13_compares_each_hosts_address_count_with_register_addresses(
        tmp_path, case):
    bench = ReadyBench(tmp_path)
    host = "127.0.0.1" if case == "ip-literal" else "localhost"
    found = _addresses(host)
    count = len(found)
    if case == "above" and count < 2:
        pytest.skip(f"not run: this runner resolves localhost to {count} address ({found})")
    url = URL.replace("127.0.0.1", host)
    lines = [f"mode=index", f"register_url={url}", f"register_passfile={bench.passfile}",
             f"reader_url={url}", f"reader_passfile={bench.passfile}",
             f"register_label={LABEL}", f"register_schema={SCHEMA}"]
    n_a = {"equal": count, "above": count - 1, "ip-literal": None}[case]
    if n_a is not None:
        lines.append(f"register_addresses={n_a}")
    config = _private(tmp_path / "conf13" / "lanes-index.conf", "\n".join(lines) + "\n")
    proc = bench.ready(config, "--expect", "index")
    state, reason = _checks(proc.stdout).get(13, ("", ""))
    if case == "above":
        assert state == "FAIL" and proc.returncode == 2, (
            f"[{case}] check 13 does not fail:\n{_said(proc)}")
        for word in [host, str(count), str(n_a), *found]:
            assert word in reason, f"[{case}] check 13's reason does not name {word}:\n{_said(proc)}"
    else:
        assert state == "ok", f"[{case}] check 13 is not ok:\n{_said(proc)}"
        assert str(count) in reason and str(n_a or 1) in reason, (
            f"[{case}] check 13 does not print the count and N_a:\n{_said(proc)}")


# ===================================================================== the bootstrap
#
# T218c: `lanes-index bootstrap --admin-service <service> --label <name>
# --repository <owner/name> --lane <name> [--no-passwords]` (operations.md
# section 2.4; lane 1's T109). The admin connection is a service in the
# test's own `$HOME/.pg_service.conf`, with a 0600 `~/.pgpass` beside it, so
# no connection string is ever an argument, and `lanes-index` hands it to
# `psql` only as `PGSERVICE`. FP for the refusals and the service; RE for the
# runs that create (a `stoppable_cluster` of the test's own, since roles are
# global to a cluster), which skip with T205's banner here.

ADMIN = "t218admin"
BOOTSTRAP_INPUTS = ("--label", LABEL, "--repository", "opensoft/t218-workspace",
                    "--lane", "t218-operator")

#: The objects the bootstrap names on its `created` or `unchanged` lines.
OBJECT_LINE = re.compile(r"^(?P<what>.+?):? (?P<state>created|unchanged)$", re.M)

#: The four variables `lanes-index` drops before it runs `psql` (SVC-2).
DROPPED = ("PGSERVICEFILE", "PGSYSCONFDIR", "PGPASSFILE", "PGPASSWORD")


class Bootstrap(Estate):
    """The estate, with the admin service in `$HOME/.pg_service.conf`."""

    def __init__(self, root: Path, *, host: str = "127.0.0.1", port: int = 55432,
                 user: str = "postgres", dbname: str = "register_db"):
        super().__init__(root)
        self.env["LANES_WORKSTATION"] = "Eagle"
        self.service_file = _private(self.home / ".pg_service.conf", "\n".join([
            f"[{ADMIN}]", f"host={host}", f"port={port}", f"user={user}", f"dbname={dbname}",
            ""]))
        _private(self.home / ".pgpass", f"*:*:*:{user}:not-a-secret\n")
        self.conf = self.config("index")

    def bootstrap(self, *args: str, pty_run: bool = False) -> subprocess.CompletedProcess:
        argv = [sys.executable, str(self.copy), "bootstrap", *args]
        env = dict(self.env, LANES_INDEX_CONFIG=str(self.conf))
        if not pty_run:
            return subprocess.run(argv, capture_output=True, text=True, env=env,
                                  cwd=str(self.wip), timeout=300, stdin=subprocess.DEVNULL)
        import pty
        primary, secondary = pty.openpty()
        try:
            proc = subprocess.Popen(argv, stdout=secondary, stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL, env=env, cwd=str(self.wip))
            os.close(secondary)
            secondary = -1
            out = b""
            while True:
                try:
                    chunk = os.read(primary, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
            err = proc.stderr.read().decode("utf-8", "replace")
            proc.wait(timeout=300)
        finally:
            os.close(primary)
            if secondary >= 0:
                os.close(secondary)
        return subprocess.CompletedProcess(argv, proc.returncode,
                                           out.decode("utf-8", "replace").replace("\r\n", "\n"),
                                           err)


def _creating(entries: list) -> list:
    return [entry for entry in entries
            if re.search(r"\b(CREATE|GRANT|ALTER|INSERT)\b", entry.get("stdin", ""))]


def _bootstrap_cluster(request, root: Path):
    """RE: a cluster of the test's own, a database cloned from `template0`, and
    the admin service naming its socket and its bootstrap superuser."""
    cluster = request.getfixturevalue("stoppable_cluster")
    import pgcluster
    name = "t218_p8"
    cluster.psql(f"CREATE DATABASE {name} TEMPLATE template0;")
    bench = Bootstrap(root, host=str(cluster.root), port=pgcluster.PORT,
                      user=pgcluster.SUPERUSER, dbname=name)
    bench.env["PATH"] = os.pathsep.join([str(cluster.bindir),
                                         os.environ.get("PATH", os.defpath)])
    return cluster, name, bench


def _catalog(cluster, name: str) -> str:
    """Tables, columns, constraints, table GRANTs and routine privileges of the
    register's schema, one sorted dump."""
    sql = ("SELECT 'c', table_name, column_name, data_type FROM information_schema.columns "
           f"WHERE table_schema = '{SCHEMA}' UNION ALL "
           "SELECT 'k', table_name, constraint_name, constraint_type FROM "
           f"information_schema.table_constraints WHERE table_schema = '{SCHEMA}' UNION ALL "
           "SELECT 'g', table_name, grantee, privilege_type FROM "
           f"information_schema.role_table_grants WHERE table_schema = '{SCHEMA}' UNION ALL "
           "SELECT 'r', routine_name, grantee, privilege_type FROM "
           f"information_schema.routine_privileges WHERE routine_schema = '{SCHEMA}' "
           "ORDER BY 1, 2, 3, 4")
    return cluster.psql(sql, dbname=name).stdout


def test_bootstrap_run_twice_leaves_one_schema_and_the_same_grants(tmp_path, request):
    cluster, name, bench = _bootstrap_cluster(request, tmp_path)
    first = bench.bootstrap("--admin-service", ADMIN, *BOOTSTRAP_INPUTS, "--no-passwords")
    assert first.returncode == 0, f"the first bootstrap failed:\n{_said(first)}"
    states = [m.group("state") for m in OBJECT_LINE.finditer(first.stdout)]
    assert states and set(states) == {"created"}, _said(first)
    before = _catalog(cluster, name)
    switch = cluster.psql(f"SELECT mode, marker_state, set_seq, database_label "
                          f"FROM {SCHEMA}.register_switch", dbname=name).stdout
    for word in ("files", "absent", "-1", LABEL):
        assert word in switch, f"after the first run the switch is not files/absent/-1/{LABEL}"
    second = bench.bootstrap("--admin-service", ADMIN, *BOOTSTRAP_INPUTS, "--no-passwords")
    assert second.returncode == 0, f"the second bootstrap failed:\n{_said(second)}"
    again = [m.group("state") for m in OBJECT_LINE.finditer(second.stdout)]
    assert again and set(again) == {"unchanged"}, _said(second)
    assert len(again) == len(states)
    assert _catalog(cluster, name) == before, "the second run changed the catalog"


def test_bootstrap_prints_password_file_lines_and_stores_no_secret(tmp_path, request):
    cluster, name, bench = _bootstrap_cluster(request, tmp_path)
    files_before = {p for p in bench.home.rglob("*")} | {p for p in bench.wip.rglob("*")}
    proc = bench.bootstrap("--admin-service", ADMIN, *BOOTSTRAP_INPUTS, pty_run=True)
    assert proc.returncode == 0, f"the bootstrap under a pty failed:\n{_said(proc)}"
    # One password-file line, the indexer's: host:port:database:user:password.
    lines = [line for line in proc.stdout.splitlines() if re.fullmatch(r"[^:\s]+:\d+:[^:]+:[^:]+:\S+", line)]
    assert len(lines) == 1 and ":lanes_indexer:" in lines[0], _said(proc)
    secret = lines[0].rsplit(":", 1)[1]
    # The lanes-index.conf lines: register_label= the --label, and no secret.
    assert f"register_label={LABEL}" in proc.stdout.splitlines(), _said(proc)
    conf_lines = [line for line in proc.stdout.splitlines()
                  if re.match(r"^[a-z_]+=", line)]
    assert not any(secret in line for line in conf_lines)
    for path in ({p for p in bench.home.rglob("*")} | {p for p in bench.wip.rglob("*")}):
        if path.is_file() and path not in files_before:
            assert secret.encode() not in path.read_bytes(), f"{path} holds the secret"


def test_the_bootstrap_refuses_when_stdout_is_not_a_terminal(tmp_path):
    bench = Bootstrap(tmp_path)
    proc = bench.bootstrap("--admin-service", ADMIN, *BOOTSTRAP_INPUTS)
    assert proc.returncode == 2, f"bootstrap through a pipe is not refused with 2:\n{_said(proc)}"
    assert _creating(bench.requests()) == [], "the refused bootstrap sent a creating statement"


@pytest.mark.parametrize("argument", ["key-value", "uri"])
def test_the_bootstrap_refuses_a_connection_string_argument_with_2(tmp_path, argument):
    bench = Bootstrap(tmp_path)
    value = {"key-value": "host=127.0.0.1 user=postgres dbname=register_db",
             "uri": "postgresql://postgres@127.0.0.1:55432/register_db"}[argument]
    proc = bench.bootstrap("--admin-service", value, *BOOTSTRAP_INPUTS, "--no-passwords")
    assert proc.returncode == 2, (
        f"[{argument}] a connection string in --admin-service is not refused with 2:\n"
        f"{_said(proc)}")
    assert bench.requests() == [], f"[{argument}] the refused bootstrap sent a request"


def test_the_bootstrap_passes_the_admin_service_only_as_pgservice(tmp_path):
    bench = Bootstrap(tmp_path)
    bench.env.update(PGSERVICEFILE=str(tmp_path / "elsewhere.conf"),
                     PGSYSCONFDIR=str(tmp_path / "sysconf"),
                     PGPASSFILE=str(tmp_path / "elsewhere.pgpass"),
                     PGPASSWORD="inherited-not-a-secret")
    proc = bench.bootstrap("--admin-service", ADMIN, *BOOTSTRAP_INPUTS, "--no-passwords")
    entries = bench.requests()
    assert entries, f"the bootstrap sent nothing through psql:\n{_said(proc)}"
    for entry in entries:
        assert "refused" not in entry, f"a connection string or -d in psql's argv: {entry}"
        assert not any(arg.startswith("service=") or "service=" in arg
                       for arg in entry["argv"]), entry["argv"]
        assert entry["service"] == ADMIN, f"PGSERVICE is not the admin service: {entry}"
        dropped = sorted(name for name in DROPPED if name in entry["pg"])
        assert dropped == [], f"psql received the inherited {dropped}"
