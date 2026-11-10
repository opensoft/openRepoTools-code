# SPDX-License-Identifier: Apache-2.0
"""Feature 007's AT-LRLABEL: `register_label=`, and the cutover's two
refusals (L2-N5; T218; FR-001, FR-059) (opensoft/openRepoTools#165).

The test plan's four names, byte for byte. T218 writes them here, in phase
N, since the cutover's cases check lane 1's T116, `cutover`'s transaction
against a scratch schema (FR-059; R1's M3); T116 selects them with
`sql_register_cutover and (cutover_without_register or cutover_at_files or
a_first_cutovers)`. Its other cases (T272's) are phase G's, in this module
too.

THE KEY needs no engine: a file carrying `register_label=` beside
`register_url=` is not refused as an unknown key, and `lanes-index mode`
reads it and exits 0. THE REFUSAL BEFORE `cutover` CONNECTS is FP: a file
with no `register_label=` exits 2 naming the key and S-2, and the fake
`psql`'s log holds no request. THE REST is RE: a label not the switch's at
`files`, at a first cutover and in the after-loss form, exits 2 with no
commit call; and a first cutover's `lanes/STORE` says `database=` the
label. They skip with T205's banner on a bench with no engine.

THE COMMAND FORMS are operations.md's (act 4's step 7 and section 2.3):
`lanes-index cutover --import <C>` and `lanes-index cutover --import <M>
--after-loss`. The refusals' texts are the test plan's (AT-LRLABEL,
"Oracle"); a case asserts their words that name the key and S-2.

READ, NOT FOUND IN A CONTRACT: "the fake `psql`'s log holds no call" is
read as "no call that carries a request": a `psql --version` probe is not
counted (T203's fake), since it sends nothing to a database.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import (PSQL_SHIM, PSQL_SHIM_CONTROL, PSQL_SHIM_LOG,
                                  REGISTER_FAKE_PSQL, RENDER_GIT_HALF_LINE, flipped_copy,
                                  guard_strip_env)

pytestmark = [WINDOWS_SKIP]

LABEL = "register-lrlabel"
OTHER = "register-lrlabel-other"
SCHEMA = "lanes_register"
URL = "postgresql://lrlabel_login@127.0.0.1:55432/register_db"


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


def _said(proc: subprocess.CompletedProcess) -> str:
    return f"exit {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"


class Host:
    """One host: a `lanes-index` copy beside `lanes-edit.sh`, a workspace
    checkout of a bare origin, and the register's fake `psql` first on
    `PATH`."""

    def __init__(self, root: Path):
        self.root = root
        tool = root / "tool"
        tool.mkdir(parents=True)
        source = REPO / "lanes-index"
        if len(RENDER_GIT_HALF_LINE.findall(source.read_bytes())) == 1:
            self.copy = flipped_copy(source, tool, False)
        else:
            self.copy = tool / "lanes-index"
            shutil.copy2(source, self.copy)
        for name in ("lanes-edit.sh", "repos.tsv"):
            if (REPO / name).exists():
                shutil.copy2(REPO / name, tool / name)
        self.fakebin = root / "fakebin"
        _script(self.fakebin / "psql", REGISTER_FAKE_PSQL)
        self.psql_log = root / "psql.log"
        self.home = root / "home"
        self.origin = root / "origin.git"
        self.seed = root / "seed"
        self.wip = self.home / "projects" / "wip"
        self.wip.parent.mkdir(parents=True)
        (root / "t").mkdir()
        self.passfile = _private(root / "secret" / "pgpass",
                                 "127.0.0.1:55432:register_db:lrlabel_login:not-a-secret\n")
        env = guard_strip_env(os.environ, strip=("T218_",))
        for name in ("XDG_CONFIG_HOME", "LANES_INDEX_CONFIG"):
            env.pop(name, None)
        env.update(HOME=str(self.home), XDG_STATE_HOME=str(root / "state"),
                   XDG_CONFIG_HOME=str(root / "config"), TMPDIR=str(root / "t"),
                   LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", LANES_REPO=str(self.wip),
                   LANES_LANE="t218-operator", FAKE_PSQL_LOG=str(self.psql_log),
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                   GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                   PATH=os.pathsep.join([str(self.fakebin),
                                         os.environ.get("PATH", os.defpath)]))
        self.env = env
        self._git("init", "-q", "--bare", "-b", "main", str(self.origin))
        self._git("init", "-q", "-b", "main", str(self.seed))
        (self.seed / "lanes").mkdir()
        (self.seed / "lanes" / "LANES.md").write_text("# Lanes\n", encoding="utf-8")
        self._git("-C", str(self.seed), "add", "lanes/LANES.md")
        self._git("-C", str(self.seed), "commit", "-q", "-m", "seed")
        self._git("-C", str(self.seed), "push", "-q", str(self.origin), "main")
        self._git("clone", "-q", str(self.origin), str(self.wip))
        (self.home / ".agents").mkdir()
        (self.home / ".agents" / "workspace.yaml").write_text(
            f"repository: {self.origin}\npath: {self.wip}\n", encoding="utf-8")

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], check=True, env=self.env, capture_output=True,
                              text=True, stdin=subprocess.DEVNULL)

    def tip(self) -> str:
        return self._git("-C", str(self.wip), "rev-parse", "refs/remotes/origin/main").stdout.strip()

    def config(self, *, label: str | None = LABEL, url: str = URL, reader: str = URL,
               mode: str = "index") -> Path:
        lines = [f"mode={mode}", f"register_url={url}", f"register_passfile={self.passfile}",
                 f"reader_url={reader}", f"reader_passfile={self.passfile}",
                 f"register_schema={SCHEMA}"]
        if label is not None:
            lines.append(f"register_label={label}")
        return _private(self.root / "conf" / "lanes-index.conf", "\n".join(lines) + "\n")

    def run(self, config: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.copy), *args], capture_output=True,
                              text=True, env=dict(self.env, LANES_INDEX_CONFIG=str(config)),
                              cwd=str(self.wip), timeout=300, stdin=subprocess.DEVNULL)

    def requests(self, log: Path | None = None) -> list:
        log = log or self.psql_log
        if not log.exists():
            return []
        entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
                   if line]
        return [entry for entry in entries if entry.get("kind") != "version"]


# --------------------------------------------------------------------- the key
def test_lanes_index_accepts_the_register_label_key(tmp_path):
    host = Host(tmp_path)
    config = host.config()
    proc = host.run(config, "mode")
    assert proc.returncode == 0, (
        f"lanes-index mode refuses a file carrying register_label=:\n{_said(proc)}")
    assert proc.stdout == "index\n", _said(proc)
    assert host.requests() == [], "lanes-index mode ran psql"


# --------------------------------------------------- the refusal before it connects
def test_cutover_without_register_label_is_refused_2_before_it_connects(tmp_path):
    host = Host(tmp_path)
    config = host.config(label=None)
    proc = host.run(config, "cutover", "--import", host.tip())
    assert proc.returncode == 2, (
        f"cutover with no register_label= is not refused with 2:\n{_said(proc)}")
    assert "register_label=" in proc.stderr and "S-2" in proc.stderr, _said(proc)
    assert host.requests() == [], "cutover connected before it refused"


# ------------------------------------------------------------- the RE half
class RegisterHost(Host):
    """RE: a database of its own, bootstrapped through the admin service with
    `--label LABEL` (T109), the writer and reader logins as fixtures, test 7's
    import at origin's tip, the switch at `files`, and section 3.2's shim in
    front of the real `psql`."""

    def __init__(self, request, root: Path):
        cluster = request.getfixturevalue("stoppable_cluster")
        import pgcluster
        super().__init__(root)
        self.cluster = cluster
        self.dbname = "t218_lrlabel"
        cluster.psql(f"CREATE DATABASE {self.dbname} TEMPLATE template0;")
        _private(self.home / ".pg_service.conf", "\n".join([
            "[t218admin]", f"host={cluster.root}", f"port={pgcluster.PORT}",
            f"user={pgcluster.SUPERUSER}", f"dbname={self.dbname}", ""]))
        self.env["PATH"] = os.pathsep.join([str(self.fakebin), str(cluster.bindir),
                                            os.environ.get("PATH", os.defpath)])
        # The shim, not the fake, is `psql` here.
        _script(self.fakebin / "psql", PSQL_SHIM)
        (self.fakebin / PSQL_SHIM_CONTROL).write_text(
            json.dumps({"psql": str(Path(cluster.bindir) / "psql"), "arms": []}),
            encoding="utf-8")
        self.shim_log = self.fakebin / PSQL_SHIM_LOG
        base = self.config(label=LABEL, url="postgresql://unused@127.0.0.1/unused")
        proc = self.run(base, "bootstrap", "--admin-service", "t218admin", "--label", LABEL,
                        "--repository", "opensoft/t218-workspace", "--lane", "t218-operator",
                        "--no-passwords")
        assert proc.returncode == 0, f"the bootstrap (T109) failed:\n{_said(proc)}"
        for login, group in (("t218_writer", "lanes_register_writer"),
                             ("t218_reader", "lanes_register_reader")):
            cluster.psql(f"CREATE ROLE {login} LOGIN IN ROLE {group};", dbname=self.dbname)
        where = f"{str(cluster.root).replace('/', '%2F')}:{pgcluster.PORT}/{self.dbname}"
        self.writer = f"postgresql://t218_writer@{where}"
        self.reader = f"postgresql://t218_reader@{where}"
        imported = self.run(self.config(label=LABEL, url=self.writer, reader=self.reader),
                            "import", "--at", self.tip())
        assert imported.returncode == 0, f"test 7's import failed:\n{_said(imported)}"
        self.shim_log.write_text("", encoding="utf-8")

    def commits(self) -> list:
        return [entry for entry in self.requests(self.shim_log)
                if "commit_write" in entry.get("sent", "") or "COMMIT" in entry.get("sent", "")]


@pytest.mark.parametrize("form", ["first", "after-loss"])
def test_cutover_at_files_with_a_label_not_the_switchs_is_refused_2_before_it_sends(
        tmp_path, request, form):
    host = RegisterHost(request, tmp_path)
    config = host.config(label=OTHER, url=host.writer, reader=host.reader)
    args = ["cutover", "--import", host.tip()] + (["--after-loss"] if form == "after-loss" else [])
    before = host.cluster.psql(f"SELECT * FROM {SCHEMA}.register_switch", dbname=host.dbname).stdout
    proc = host.run(config, *args)
    assert proc.returncode == 2, (
        f"[{form}] cutover with register_label= not the switch's is not refused:\n{_said(proc)}")
    for word in (f"register_label={OTHER}", LABEL, "S-2"):
        assert word in proc.stderr, f"[{form}] the refusal does not name {word}:\n{_said(proc)}"
    assert host.commits() == [], f"[{form}] the refused cutover sent a commit call"
    after = host.cluster.psql(f"SELECT * FROM {SCHEMA}.register_switch", dbname=host.dbname).stdout
    assert after == before, f"[{form}] the refused cutover changed the switch"


def test_a_first_cutovers_store_names_the_register_label(tmp_path, request):
    host = RegisterHost(request, tmp_path)
    config = host.config(label=LABEL, url=host.writer, reader=host.reader)
    proc = host.run(config, "cutover", "--import", host.tip())
    assert proc.returncode == 0, f"the first cutover failed:\n{_said(proc)}"
    host._git("-C", str(host.wip), "fetch", "-q", "origin")
    store = host._git("-C", str(host.wip), "show", "refs/remotes/origin/main:lanes/STORE").stdout
    assert f"database={LABEL}" in store.splitlines(), f"lanes/STORE does not name {LABEL}: {store}"
