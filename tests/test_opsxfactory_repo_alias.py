# SPDX-License-Identifier: Apache-2.0
"""The case-only rename changes canonical output, not accepted historical input."""
import os
import re
import shutil
import subprocess

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which('bash') is None or shutil.which('git') is None,
    reason='repository aliases and lane discovery require bash and git')]


@pytest.mark.parametrize('alias', [
    'OpsxFactory', 'opsXfactory', 'OPSXFACTORY',
    'opensoft/OpsxFactory', 'opensoft/opsXfactory', 'OPENSOFT/OPSXFACTORY',
])
def test_old_and_current_names_resolve_to_current_github_spelling(alias):
    script = (REPO / 'lanes-edit.sh').read_text()
    function = re.search(r'(?ms)^alias_lookup\(\) \{.*?^\}', script)
    assert function is not None
    result = subprocess.run(
        ['bash', '-c', function.group() + '\n'
         'LANES_REPOS_TSV=\nLANES_REPOS_TSV_SHIPPED="$1"\nalias_lookup "$2"',
         'alias-test', str(REPO / 'repos.tsv'), alias],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'opensoft/opsXfactory\n'


@pytest.mark.parametrize('folder', ['OpsxFactory', 'opsXfactory'])
@pytest.mark.parametrize('remote', ['OpsxFactory', 'opsXfactory'])
@pytest.mark.parametrize('depth', [0, 1, 2])
@pytest.mark.parametrize('owner', ['opensoft', 'someone-else'])
def test_discovery_keeps_old_paths_but_still_proves_the_origin(
        tmp_path, folder, remote, depth, owner):
    projects = tmp_path / 'projects'
    candidate = projects.joinpath(*(['holder'] * depth), folder)
    candidate.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(candidate)], check=True)
    subprocess.run(['git', '-C', str(candidate), 'remote', 'add', 'origin',
                    f'git@github.com:{owner}/{remote}.git'], check=True)
    script = (REPO / 'lane-start').read_text()
    functions = []
    for name in ('origin_nwo', 'lane_dir_is_home'):
        match = re.search(r'(?ms)^' + name + r'\(\).*?^\}', script)
        assert match is not None
        functions.append(match.group())
    discovery = script.split('# Rung 6 —', 1)[1].split('# THE REFUSAL', 1)[0]
    discovery = discovery[discovery.index('\n') + 1:]
    result = subprocess.run(
        ['bash', '-c', '\n'.join(functions) + '\n' + discovery +
         '\nprintf "%s\\n" "$DIR"'],
        env={**os.environ, 'PROJECTS_ROOT': str(projects), 'DIR': '',
             'ls_home': 'opensoft/opsXfactory', 'LANES_EDIT': shutil.which('false')},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = str(candidate) if owner == 'opensoft' else ''
    assert result.stdout == expected + '\n'
