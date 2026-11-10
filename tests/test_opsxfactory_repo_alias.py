"""The case-only rename changes canonical output, not accepted historical input."""
import re
import subprocess

import pytest

from conftest import REPO


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
