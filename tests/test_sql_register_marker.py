# SPDX-License-Identifier: Apache-2.0
"""Feature 007's test 3, the marker `lanes/STORE` (AT-3; opensoft/openRepoTools#165).

T225 (L2-N7; A8): `wip init`'s two cases, AT-3's three reader cases and lane
5's three marker guesses, all in phase N, all FM, with no database:

- `openRepoTools wip init` refuses under the marker, and wherever any file
  under `lanes/` exists with no marker, with no configuration and with
  `mode=index` (Q14(a); FR-005). They fail until lane 3's T303 lands.
- The readers' marker check, F17 (design Y, "F17: the marker check for
  readers"; Y:3055-3068): on a workstation that is not `mode=primary`, a
  reader checks the ref its read uses for `lanes/STORE`; an act refuses 69
  and the guard 2, both with Amendment 22's text, and the listings and the
  `SessionStart` block read on with the `read: mirror` line. They fail until
  lane 5's T504 to T508 (L5-A5) land.

T242 adds test 3's unit form and AT-F8 to this module.

The estate is T215's and T220's, as T203c's helper test builds it: a bare
origin, the lane's checkout under `$HOME/projects`, `$HOME/.agents/
workspace.yaml` naming it, and the register pushed. The marker is committed
by hand on the origin (lane 4's row 8), with D21's five fields one per line in
D21's order (Y:613-615; lane 1, F10's items 22 and 23).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
import uuid
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import GUARD_WINDOW, guard_session, guard_strip_env

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

EDIT = REPO / "lanes-edit.sh"
LANES = REPO / "lanes"
COMMAND = REPO / "openRepoTools"

#: Amendment 22's text, the refusal of an act and of the guard under the
#: marker (Y:3060-3062; AT-3's oracle).
AMENDMENT_22 = "this estate's register is SQL; configure `mode=primary`"
#: The third line of the `read:` family (Y:3048-3050): `read: mirror at
#: <sha12>, <k> sequences behind or unknown (sql unreachable: <why>)`.
MIRROR_LINE = "read: mirror at "
#: How old the ref is, in the refusal (AT-3: "its text says how old the ref it
#: read is"): a count with a unit, or "ago". The form is not fixed by any
#: contract; this is the loosest reading of it.
AGE = re.compile(r"\b\d+ ?(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hour|hours|"
                 r"d|day|days|w|week|weeks)\b|\bago\b", re.I)

#: D21's five fields, one per line, in D21's order.
STORE_TEXT = ("store=primary\ndatabase=lanes-register-test\n"
              "import=0123456789abcdef0123456789abcdef01234567\n"
              "lanes-tree=89abcdef0123456789abcdef0123456789abcdef\n"
              "utc=2026-10-01T00:00:00Z\n")
#: The marker commit's date, so its age is days, never seconds.
MARKER_DATE = "2026-10-01T00:00:00Z"
DOT = chr(0xB7)
REGISTER_HEADER = ["# LANES.md", "",
                   "| lane | session id | workstation / env / user | started (UTC) | objects "
                   "owned | handoff path | state |",
                   "|---|---|---|---|---|---|---|"]
CONFIGURATIONS = ("none", "index")


def _register(session_id: str) -> str:
    """A register whose one row binds `GUARD_WINDOW` to `session_id`, in
    T215's row form."""
    row = (f"| `{GUARD_WINDOW}` | harness `{session_id}` | Eagle / test / brett "
           f"| 2026-10-01T00:00Z | none | handoffs/{GUARD_WINDOW}.md "
           f"| LIVE {DOT} 2026-10-01T02:00:00Z {DOT} working |")
    return "\n".join(REGISTER_HEADER + [row, ""])


def _git(cwd: Path, env: dict, *argv: str) -> str:
    return subprocess.run(["git", *argv], cwd=str(cwd), check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def _configure(root: Path, env: dict, configuration: str) -> None:
    """No configuration, or `mode=index` (AT-3's two configurations), in
    `$XDG_CONFIG_HOME/openRepoTools/lanes-index.conf`, mode 0600 (CLI section 2.5)."""
    if configuration == "index":
        conf = Path(env["XDG_CONFIG_HOME"]) / "openRepoTools" / "lanes-index.conf"
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text("mode=index\n", encoding="utf-8")
        conf.chmod(0o600)


def _push_marker(root: Path, origin: Path, env: dict) -> str:
    """Commit `lanes/STORE` by hand on origin's `main`, from a clone of its
    own (lane 4's row 8). Returns the marker commit's sha."""
    hand = root / "hand"
    subprocess.run(["git", "clone", "-q", str(origin), str(hand)], check=True, env=env,
                   capture_output=True)
    (hand / "lanes" / "STORE").write_text(STORE_TEXT, encoding="utf-8")
    dated = dict(env, GIT_AUTHOR_DATE=MARKER_DATE, GIT_COMMITTER_DATE=MARKER_DATE)
    _git(hand, dated, "add", "lanes/STORE")
    _git(hand, dated, "commit", "-q", "-m", "cutover: lanes/STORE")
    _git(hand, dated, "push", "-q", "origin", "main")
    return _git(hand, env, "rev-parse", "HEAD")


def _estate(root: Path, session_id: str, configuration: str = "none") -> tuple:
    """T215's and T220's estate, whose register's row names `session_id`.
    Returns (`home`, the checkout, the origin, the base environment)."""
    home = root / "home"
    wip = home / "projects" / "wip"
    origin = root / "origin.git"
    wip.parent.mkdir(parents=True)
    (root / "t").mkdir()
    env = guard_strip_env(os.environ)
    env.update(HOME=str(home), XDG_STATE_HOME=str(root / "state"),
               XDG_CONFIG_HOME=str(root / "config"), TMPDIR=str(root / "t"),
               LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", LANES_NO_FETCH="1",
               LANES_REPO=str(wip),
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True,
                   env=env)
    subprocess.run(["git", "clone", "-q", str(origin), str(wip)], check=True, env=env,
                   capture_output=True)
    (wip / "lanes" / "log").mkdir(parents=True)
    (wip / "lanes" / "LANES.md").write_text(_register(session_id), encoding="utf-8")
    (wip / "lanes" / "log" / "README.md").write_text("logs.\n", encoding="utf-8")
    for argv in (["add", "-A"], ["commit", "-q", "-m", "C"], ["push", "-q", "origin", "main"]):
        _git(wip, env, *argv)
    (home / ".agents").mkdir()
    (home / ".agents" / "workspace.yaml").write_text(
        f"repository: {origin}\npath: {wip}\n", encoding="utf-8")
    _configure(root, env, configuration)
    return home, wip, origin, env


def _run(argv: list, env: dict, cwd: Path, stdin: str = "") -> tuple:
    """One run of the lane tooling. Returns (its exit, stdout, stderr)."""
    proc = subprocess.run(["bash", *map(str, argv)], input=stdin, capture_output=True,
                          text=True, cwd=str(cwd), env=env, timeout=120,
                          start_new_session=True)
    return proc.returncode, proc.stdout, proc.stderr


# --- `wip init` (T303) --------------------------------------------------------

#: The nine template files (`openRepoTools`' `WIP_TEMPLATE_FILES`), served by
#: the fake `gh` from a directory of its own, so these cases need no submodule.
TEMPLATE_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", ".gitattributes",
                  ".gitignore", "handoffs/README.md", "lanes/LANES.md",
                  "lanes/log/README.md", "workspaces/.gitkeep")


def _template_text(rel: str) -> str:
    """A template file's stand-in text: one comment line, so `.gitignore`
    ignores nothing, and `.gitkeep` empty, as upstream's is."""
    return "" if rel.endswith(".gitkeep") else f"# {rel}\n"


def _wip_fake_gh(root: Path) -> Path:
    """A `gh` that answers `wip init`'s calls as `test_wip_init_command.py`'s
    does, with the repository already created by an administrator, and serves
    the template from `<root>/shape`. A `curl` that refuses."""
    shape = root / "shape" / "templates" / "workspace-root"
    for rel in TEMPLATE_FILES:
        (shape / rel).parent.mkdir(parents=True, exist_ok=True)
        (shape / rel).write_text(_template_text(rel), encoding="utf-8")
    server = root / "github"
    fake = root / "fake-path"
    fake.mkdir()
    (fake / "gh").write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -u
        server={server!s}
        slug_path() {{ printf '%s\\n' "$server/$1.git"; }}
        case "$1 ${{2-}}" in
        "api user") printf '%s\\n' brettheap; exit 0 ;;
        "api --paginate") printf '%s\\n' platform; exit 0 ;;
        esac
        case "$*" in
        "repo view "*) [ -d "$(slug_path "$3")" ] && exit 0; exit 1 ;;
        "repo create "*) exit 1 ;;
        "repo clone "*)
            git clone -q "$(slug_path "$3")" "$4" || exit 1
            git -C "$4" config user.email wip@example.invalid
            git -C "$4" config user.name "wip init tests"
            exit 0 ;;
        "api --method PUT"*) exit 0 ;;
        *"/contents/"*)
            path="${{*}}"; path="${{path##*/contents/}}"; path="${{path%%\\?*}}"
            src="{root / 'shape'!s}/$path"
            [ -f "$src" ] && exec cat -- "$src"
            exit 1 ;;
        esac
        printf 'fake gh: unexpected call: %s\\n' "$*" >&2
        exit 1
        """), encoding="utf-8")
    (fake / "curl").write_text("#!/bin/sh\nprintf 'no test here may reach the network\\n' >&2\n"
                               "exit 1\n", encoding="utf-8")
    for name in ("gh", "curl"):
        (fake / name).chmod(0o755)
    return fake


def _wip_origin(root: Path, files: dict, env: dict) -> Path:
    """`opensoft/brettheap-wip` on the fake server, its `main` carrying
    `files` (path to text), as an administrator or a cutover left it."""
    origin = root / "github" / "opensoft" / "brettheap-wip.git"
    origin.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True,
                   env=env)
    seed = root / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True, env=env,
                   capture_output=True)
    for rel, text in files.items():
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_text(text, encoding="utf-8")
    _git(seed, env, "add", "-A")
    _git(seed, env, "commit", "-q", "-m", "the estate as it stands")
    _git(seed, env, "push", "-q", "origin", "main")
    return origin


def _wip_init(root: Path, files: dict, configuration: str) -> tuple:
    """Runs `openRepoTools wip init` against an origin carrying `files`.
    Returns (exit, output, origin's refs before, origin's refs after, the
    checkouts under `$HOME/projects` with a commit origin's `main` lacks)."""
    root.mkdir(parents=True, exist_ok=True)
    home = root / "home"
    (home / "projects").mkdir(parents=True)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("LANES_", "OPENREPOTOOLS_", "CLAUDE_", "GIT_"))
           and k not in ("AGENT_PROTOCOL_ROOT", "PROJECTS_DIR", "PROJECTS_ROOT", "TMUX",
                         "TMUX_PANE")}
    env.update(HOME=str(home), AGENT_PROTOCOL_ROOT=str(home / ".agents"),
               PROJECTS_DIR=str(home / "projects"), OPENREPOTOOLS_BIN_DIR=str(home / "bin"),
               XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state"),
               GIT_AUTHOR_NAME="wip tests", GIT_COMMITTER_NAME="wip tests",
               GIT_AUTHOR_EMAIL="wip@example.invalid",
               GIT_COMMITTER_EMAIL="wip@example.invalid")
    fake = _wip_fake_gh(root)
    env["PATH"] = f"{fake}{os.pathsep}{env.get('PATH', '/usr/bin:/bin')}"
    origin = _wip_origin(root, files, env)
    _configure(root, env, configuration)
    before = _git(origin, env, "for-each-ref", "--format=%(refname) %(objectname)")
    main = _git(origin, env, "rev-parse", "main")
    proc = subprocess.run(["bash", str(COMMAND), "wip", "init"], capture_output=True,
                          text=True, cwd=str(REPO), env=env, input="", timeout=120,
                          check=False)
    after = _git(origin, env, "for-each-ref", "--format=%(refname) %(objectname)")
    ahead = []
    for checkout in sorted((home / "projects").iterdir()):
        if (checkout / ".git").exists():
            head = _git(checkout, env, "rev-parse", "HEAD")
            status = _git(checkout, env, "status", "--porcelain", "--", ".")
            if head != main or status:
                ahead.append(f"{checkout.name}: HEAD {head[:12]}, status {status!r}")
    return proc.returncode, proc.stdout + proc.stderr, before, after, ahead


def _assert_wip_refused(code: int, out: str, before: str, after: str, ahead: list,
                        path: str, where: str) -> None:
    """T303's refusal: a non-zero exit, the path it found named, nothing
    committed or queued, and origin's refs unchanged."""
    assert code != 0, f"{where}: wip init exited 0 with {path} on origin\n{out[-900:]}"
    assert path in out, f"{where}: the refusal does not name {path}\n{out[-900:]}"
    assert after == before, f"{where}: origin's refs moved\n{before}\n->\n{after}"
    assert not ahead, f"{where}: a commit or a write is queued: {ahead}\n{out[-900:]}"


def test_wip_init_refuses_under_the_marker(tmp_path):
    """AT-3 (Q14(a); FR-005): with `lanes/STORE` on origin's `main`, `wip init`
    refuses with a non-zero exit, names the marker and commits nothing, the
    same with no configuration and with `mode=index`. Fails until T303."""
    files = {rel: _template_text(rel) for rel in TEMPLATE_FILES
             if not rel.endswith(".gitkeep")}
    files["lanes/log/README.md"] = "logs.\n"
    files["lanes/STORE"] = STORE_TEXT
    codes = {}
    for configuration in CONFIGURATIONS:
        code, out, before, after, ahead = _wip_init(tmp_path / configuration, files,
                                                    configuration)
        _assert_wip_refused(code, out, before, after, ahead, "lanes/STORE", configuration)
        codes[configuration] = code
    assert len(set(codes.values())) == 1, f"the refusal differs by configuration: {codes}"


@pytest.mark.parametrize("found", ["LANES.md", "repos.tsv"])
@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_wip_init_refuses_where_a_lanes_file_exists_with_no_marker(tmp_path, configuration,
                                                                   found):
    """AT-3's third exception: with no marker and one file under `lanes/`,
    `wip init` refuses, names the file and commits nothing. `LANES.md` is
    found with `lanes/log/README.md` missing, the file today's run commits as
    owed (`openRepoTools:5026-5080`); `repos.tsv` is found alone. Fails until
    T303."""
    files = {"README.md": _template_text("README.md"), f"lanes/{found}": f"lanes/{found}\n"}
    code, out, before, after, ahead = _wip_init(tmp_path, files, configuration)
    _assert_wip_refused(code, out, before, after, ahead, f"lanes/{found}",
                        f"{configuration}-{found}")


# --- the readers' marker check, F17 (L5-A5) -----------------------------------

def _who(wip: Path, env: dict) -> tuple:
    return _run([EDIT, "who", "--lane", GUARD_WINDOW], env, wip)


def test_a_readers_refusal_under_the_marker_names_the_refs_age(tmp_path):
    """AT-3 (Q21(a)(A)): an unconfigured reader whose read ref carries the
    marker refuses with 69, Amendment 22's text, and how old that ref is
    (Y:3065: "the refusal says how old it is"). Fails until T504."""
    home, wip, origin, env = _estate(tmp_path, str(uuid.uuid4()))
    _push_marker(tmp_path, origin, env)
    _git(wip, env, "fetch", "-q", "origin", "main")
    _git(wip, env, "merge", "-q", "--ff-only", "origin/main")
    code, out, err = _who(wip, env)
    assert code == 69, f"who exited {code} under the marker\n{out[-600:]}{err[-600:]}"
    assert AMENDMENT_22 in err, f"no Amendment 22 text on stderr\n{err[-900:]}"
    line = next(x for x in err.splitlines() if AMENDMENT_22 in x or "origin/main" in x)
    assert "origin/main" in err and AGE.search(err), \
        f"the refusal names no age for the ref it read ({line!r})\n{err[-900:]}"


def test_a_reader_refuses_when_its_read_ref_carries_the_marker_and_its_tree_does_not(
        tmp_path):
    """AT-3: the check runs on the ref the read uses, never the working tree.
    The checkout's tree lacks `lanes/STORE` and `origin/main` carries it: the
    reader refuses 69. Then a tree that carries it over a ref that does not
    reads on as today. Fails until T504."""
    home, wip, origin, env = _estate(tmp_path / "a", str(uuid.uuid4()))
    _push_marker(tmp_path / "a", origin, env)
    _git(wip, env, "fetch", "-q", "origin", "main")
    assert not (wip / "lanes" / "STORE").exists()
    code, out, err = _who(wip, env)
    assert code == 69 and AMENDMENT_22 in err, \
        f"the ref carries the marker, the tree does not: {code}\n{out[-600:]}{err[-600:]}"

    home, wip, origin, env = _estate(tmp_path / "b", str(uuid.uuid4()))
    (wip / "lanes" / "STORE").write_text(STORE_TEXT, encoding="utf-8")
    _git(wip, env, "add", "lanes/STORE")
    _git(wip, env, "commit", "-q", "-m", "a local marker, never pushed")
    code, out, err = _who(wip, env)
    assert code != 69 and AMENDMENT_22 not in err, \
        f"the tree carries the marker, the ref does not: {code}\n{out[-600:]}{err[-600:]}"


def test_an_unconfigured_workstations_acts_refuse_and_listings_read_the_mirror(tmp_path):
    """AT-3 (Q21(a)(A)): on an unconfigured workstation under the marker,
    `who` exits 69 with Amendment 22's text, and the listing, `lanes --all`
    (which today exits 0 and lists the lane), reads on, exits 0 and prints the
    `read: mirror` line at origin's tip. Fails until
    T504 and T507."""
    home, wip, origin, env = _estate(tmp_path, str(uuid.uuid4()))
    marker = _push_marker(tmp_path, origin, env)
    _git(wip, env, "fetch", "-q", "origin", "main")
    code, out, err = _who(wip, env)
    assert code == 69 and AMENDMENT_22 in err, f"who: {code}\n{out[-600:]}{err[-600:]}"
    code, out, err = _run([LANES, "--all"], env, wip)
    assert code == 0, f"lanes --all: {code}\n{out[-600:]}{err[-600:]}"
    assert f"{MIRROR_LINE}{marker[:12]}" in err, \
        f"lanes --all printed no `read: mirror at {marker[:12]}` line on stderr\n{err[-900:]}"
    assert GUARD_WINDOW in out, f"lanes --all did not read on\n{out[-900:]}"


def test_the_marker_check_runs_at_the_end_of_log_sync(tmp_path):
    """Lane 5's guess for T506 (A5), its name kept: the checkout has not
    fetched since the cutover, so its ref has no marker; the act's own
    `log_sync` fetch brings it, and F17 at `log_sync`'s end refuses 69 with
    Amendment 22's text. Fails until T506."""
    home, wip, origin, env = _estate(tmp_path, str(uuid.uuid4()))
    _push_marker(tmp_path, origin, env)
    env = dict(env)
    env.pop("LANES_NO_FETCH")
    code, out, err = _who(wip, env)
    assert _git(wip, env, "rev-parse", "origin/main") == _git(origin, env, "rev-parse", "main"), \
        "the act's log_sync did not fetch"
    assert code == 69 and AMENDMENT_22 in err, \
        f"log_sync brought the marker: {code}\n{out[-600:]}{err[-600:]}"


def test_the_session_start_block_reads_on_under_the_marker_with_its_mirror_line(tmp_path):
    """Lane 5's guess for T508 (A5), its name kept: off primary, under the
    marker, the `SessionStart` block reads on, exits 0, and prints the
    `read: mirror` line at origin's tip. Fails until T508."""
    sid = str(uuid.uuid4())
    home, wip, origin, env = _estate(tmp_path, sid)
    marker = _push_marker(tmp_path, origin, env)
    _git(wip, env, "fetch", "-q", "origin", "main")
    hook = '{"session_id":"%s","source":"startup"}' % sid
    code, out, err = _run([EDIT, "session-start"], env, wip, stdin=hook)
    assert code == 0, f"session-start: {code}\n{out[-600:]}{err[-600:]}"
    assert f"{MIRROR_LINE}{marker[:12]}" in out + err, \
        f"no `read: mirror at {marker[:12]}` line\n{out[-600:]}{err[-600:]}"
    assert GUARD_WINDOW in out + err, f"the block did not read on\n{out[-900:]}"


def test_a_mode_index_guard_refuses_2_under_the_marker(tmp_path):
    """Lane 5's guess for T507 (A7), its name kept: on a `mode=index`
    workstation, the guard whose register row names its session refuses 2
    with Amendment 22's text once its read ref carries the marker (F17 in
    `guard_run`; W:4896). Without the marker the same guard passes, 0.
    Fails until T507."""
    sid = str(uuid.uuid4())
    home, wip, origin, env = _estate(tmp_path, sid, configuration="index")
    env = dict(env, LANES_LANE=GUARD_WINDOW)
    with guard_session(home, tmp_path / "bin", wip, session_id=sid) as session:
        def guard():
            return subprocess.run(["bash", str(EDIT), "guard"], input=session.hook_input(),
                                  capture_output=True, text=True, cwd=str(wip),
                                  env=session.env(env), timeout=60, start_new_session=True)
        proc = guard()
        assert proc.returncode == 0, \
            f"the mode=index guard with no marker: {proc.returncode}\n" \
            f"{proc.stdout[-600:]}{proc.stderr[-600:]}"
        _push_marker(tmp_path, origin, env)
        _git(wip, env, "fetch", "-q", "origin", "main")
        proc = guard()
    assert proc.returncode == 2 and AMENDMENT_22 in proc.stderr, \
        f"the mode=index guard under the marker: {proc.returncode}\n" \
        f"{proc.stdout[-600:]}{proc.stderr[-600:]}"
