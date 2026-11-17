# SPDX-License-Identifier: Apache-2.0
"""Offline next-cohort preparation; never a live batch or activation receipt."""

import copy
import importlib
import json

import pytest

from conftest import REPO
from test_ci_delivery import batch, commit, delivery, git
from test_ci_cutover import cutover
from test_ci_v13_delivery import route_source, v13, v13_batch


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def expansion(delivery):
    return importlib.import_module("v13_expansion")


@pytest.fixture
def policy():
    return json.loads((REPO / ".github/ci/v13-prepared-cohort.json").read_text())


@pytest.fixture
def cohort(tmp_path, expansion, policy):
    root = tmp_path / "cohort"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "CI Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.filemode", "true")
    for path in expansion.projection.P01_FILES:
        write(root, path, "# frozen foundation\n")
    write(root, "tests/test_sql_register_fixture.py", "# existing fixture\n")
    anchor = commit(root, "frozen foundation")
    policy["base"] = policy["prerequisite"] = anchor
    for name, profile in policy["profiles"].items():
        git(root, "checkout", "-q", "--detach", anchor)
        for path in profile["files"]:
            write(root, path, "# " + name + " scoped source\n")
        for task in profile["tasks"]:
            write(root, expansion.projection.MARKERS + task, "")
        head = commit(root, name)
        profile["source"].update(anchor=anchor, head=head, commits=[head])
        profile["owner_consent"] = profile["review"] = None
    git(root, "checkout", "-q", "--detach", anchor)
    write(root, expansion.CONFIG, json.dumps(policy))
    return root, policy


def assert_full(result, expansion):
    for key, value in expansion.FULL.items():
        assert result[key] == value


def test_ci_v13_expansion_real_manifest_is_disabled_and_separate(expansion, policy):
    loaded, digest = expansion.read_policy(REPO)
    assert loaded == policy
    assert len(digest) == 64
    assert loaded["enabled"] is False
    assert loaded["held_prs"] == [106]
    assert loaded["order"] == ["P07", "P09"]
    assert expansion.HISTORY_LIMITS == {"P07": 40, "P09": 165}
    for profile in loaded["profiles"].values():
        assert profile["source"]["head"] is None
        assert profile["source"]["commits"] == []
        assert profile["owner_consent"] is profile["review"] is None
    assert loaded["profiles"]["P07"]["files"]["tests/sql_register_cleanup.py"] == "A"
    assert loaded["profiles"]["P09"]["files"]["tests/conftest.py"] == "M"
    active = expansion.projection.read_policy(REPO, "HEAD")
    assert set(active["profiles"]) == {"P05", "P06"}
    for path in ("delivery_route.py", "delivery_verify.py", "delivery_evidence.py", "delivery_v13.py"):
        text = (REPO / ".github/ci" / path).read_text()
        assert "v13_expansion" not in text
        assert "v13-prepared-cohort" not in text


def test_ci_v13_expansion_real_observations_do_not_bind_owner_heads(expansion, policy):
    result = expansion.inspect(REPO, policy["base"])
    assert result["status"] == "pending-owner-heads"
    assert result["reason"] == "unbound-source"
    assert "previews" not in result
    assert_full(result, expansion)


def test_ci_v13_expansion_missing_heads_stay_pending(cohort, expansion):
    root, policy = cohort
    profile = policy["profiles"]["P07"]
    profile["source"].update(head=None, commits=[])
    write(root, expansion.CONFIG, json.dumps(policy))
    result = expansion.inspect(root, policy["base"])
    assert result["status"] == "pending-owner-heads"
    assert "previews" not in result
    assert_full(result, expansion)


@pytest.mark.parametrize("linked", [False, True])
def test_ci_v13_expansion_preview_preserves_full_and_exposes_foundation(cohort, expansion, linked):
    root, policy = cohort
    if linked:
        for profile in policy["profiles"].values():
            for key in ("review", "owner_consent"):
                profile[key] = {"head": profile["source"]["head"], "comment": 123}
        write(root, expansion.CONFIG, json.dumps(policy))
    before = (git(root, "rev-parse", "HEAD"), git(root, "status", "--porcelain"),
              git(root, "show-ref"))
    result = expansion.inspect(root, policy["base"])
    expected = "preview-ready-for-review" if linked else "preview-pending-owner-reviews"
    assert result["status"] == expected
    assert [row["profile"] for row in result["previews"]] == ["P07", "P09"]
    # P07 cannot transition the foundation; P09 changes it only in the final prefix.
    helpers = {"tests/conftest.py", "tests/pgcluster.py"}
    for helper in helpers:
        original = git(root, "rev-parse", f"{policy['base']}:{helper}")
        assert git(root, "rev-parse", f"{result['previews'][0]['tree']}:{helper}") == original
        changed = git(root, "rev-parse", f"{result['previews'][1]['tree']}:{helper}")
        assert changed == git(root, "rev-parse", f"{policy['profiles']['P09']['source']['head']}:{helper}")
        assert changed != original
    assert set(result["foundation_changes_requiring_activation_review"]) == helpers
    assert_full(result, expansion)
    assert before == (git(root, "rev-parse", "HEAD"), git(root, "status", "--porcelain"),
                      git(root, "show-ref"))


@pytest.mark.parametrize("name,count", [("P09", 4), ("P09", 12), ("P07", 13), ("P07", 16),
                                       ("P07", 40), ("P09", 24), ("P09", 25), ("P09", 165)])
def test_ci_v13_expansion_exact_bounded_fixes_can_be_previewed(cohort, expansion, name, count):
    root, policy = cohort
    (root / expansion.CONFIG).unlink()
    profile = policy["profiles"][name]
    git(root, "checkout", "-q", "--detach", profile["source"]["head"])
    for index in range(count - 1):
        path = "tests/test_sql_register_shape.py" if name == "P07" else "tests/test_sql_register_bounds.py"
        write(root, path, f"# exact fix {index}\n")
        head = commit(root, "declared fix")
        profile["source"]["commits"].append(head)
        profile["source"]["head"] = head
    git(root, "checkout", "-q", "--detach", policy["base"])
    write(root, expansion.CONFIG, json.dumps(policy))
    result = expansion.inspect(root, policy["base"])
    assert result["status"] == "preview-pending-owner-reviews"
    assert_full(result, expansion)


@pytest.mark.parametrize("name,limit", [("P07", 40), ("P09", 165)])
@pytest.mark.parametrize("overflow", [False, True])
def test_ci_v13_expansion_per_profile_history_ceiling(tmp_path, expansion, policy, name, limit, overflow):
    profile = policy["profiles"][name]
    commits = [f"{index + 1:040x}" for index in range(limit + int(overflow))]
    profile["source"].update(head=commits[-1], commits=commits)
    profile["owner_consent"] = profile["review"] = None
    write(tmp_path, expansion.CONFIG, json.dumps(policy))
    if overflow:
        with pytest.raises(ValueError):
            expansion.read_policy(tmp_path)
        result = expansion.inspect(tmp_path, policy["base"])
        assert result["status"] == "refused"
        assert_full(result, expansion)
    else:
        loaded, _digest = expansion.read_policy(tmp_path)
        assert loaded["profiles"][name]["source"]["commits"] == commits


@pytest.mark.parametrize("fault", [None, "unlanded-anchor", "pre-prerequisite", "skipped-source"])
def test_ci_v13_expansion_per_source_landed_anchor(cohort, expansion, fault):
    root, policy = cohort
    (root / expansion.CONFIG).unlink()
    initial = policy["base"]
    write(root, "landed-p03.txt", "# already landed prerequisite\n")
    landed = commit(root, "landed P03")
    policy["base"] = landed
    profile = policy["profiles"]["P09"]
    git(root, "checkout", "-q", "--detach", profile["source"]["head"])
    tree = git(root, "merge-tree", "--write-tree", landed, "HEAD")
    head = git(root, "commit-tree", tree, "-p", landed, "-m", "P09 on landed P03")
    profile["source"].update(anchor=landed, head=head, commits=[head])
    if fault == "unlanded-anchor":
        policy["base"] = initial
    elif fault == "pre-prerequisite":
        policy["prerequisite"] = landed
    elif fault == "skipped-source":
        profile["source"]["anchor"] = initial
    git(root, "checkout", "-q", "--detach", policy["base"])
    write(root, expansion.CONFIG, json.dumps(policy))
    result = expansion.inspect(root, policy["base"])
    assert result["status"] == ("refused" if fault else "preview-pending-owner-reviews")
    assert_full(result, expansion)


@pytest.mark.parametrize("fault", [
    "enabled", "unknown-key", "boolean-schema", "unknown-profile", "wrong-order",
    "release-unheld", "float-held-id", "wrong-number", "wrong-branch", "extra-file", "missing-file",
    "wrong-status", "wrong-task", "unbound-lineage", "unbound-review", "wrong-scope",
    "bad-observed-head", "boolean-comment", "duplicate-json", "oversized", "bad-anchor", "missing-anchor",
    "missing-cleanup-helper", "modified-cleanup-helper", "missing-report-hook", "added-report-hook",
])
def test_ci_v13_expansion_manifest_refuses_unsafe_or_ambiguous_input(tmp_path, expansion, policy, fault):
    profile = policy["profiles"]["P07"]
    if fault == "enabled": policy["enabled"] = True
    elif fault == "unknown-key": policy["skip_ci"] = True
    elif fault == "boolean-schema": policy["schema_version"] = True
    elif fault == "unknown-profile": policy["profiles"]["P08"] = copy.deepcopy(profile)
    elif fault == "wrong-order": policy["order"].reverse()
    elif fault == "release-unheld": policy["held_prs"] = []
    elif fault == "float-held-id": policy["held_prs"] = [106.0]
    elif fault == "wrong-number": profile["source"]["number"] = True
    elif fault == "wrong-branch": profile["source"]["branch"] = "main"
    elif fault == "extra-file": profile["files"]["lane-start"] = "M"
    elif fault == "missing-file": profile["files"].pop("tests/test_sql_register_shape.py")
    elif fault == "missing-cleanup-helper": profile["files"].pop("tests/sql_register_cleanup.py")
    elif fault == "modified-cleanup-helper": profile["files"]["tests/sql_register_cleanup.py"] = "M"
    elif fault == "missing-report-hook": policy["profiles"]["P09"]["files"].pop("tests/conftest.py")
    elif fault == "added-report-hook": policy["profiles"]["P09"]["files"]["tests/conftest.py"] = "A"
    elif fault == "wrong-status": profile["files"]["tests/test_sql_register_shape.py"] = "M"
    elif fault == "wrong-task": profile["tasks"].append("T999")
    elif fault == "unbound-lineage": profile["source"].update(head=None, commits=["a" * 40])
    elif fault == "unbound-review": profile["review"] = {"head": "a" * 40, "comment": 1}
    elif fault == "wrong-scope": policy["scope"] = "sql-register-v13"
    elif fault == "bad-observed-head": profile["observed_head"] = "bad"
    elif fault == "boolean-comment": policy["owner_coordination"] = True
    elif fault == "bad-anchor": profile["source"]["anchor"] = "invalid"
    elif fault == "missing-anchor": del profile["source"]["anchor"]
    raw = json.dumps(policy)
    if fault == "duplicate-json": raw = raw.replace('"enabled": false', '"enabled": false, "enabled": false')
    elif fault == "oversized": raw += " " * 65537
    write(tmp_path, expansion.CONFIG, raw)
    result = expansion.inspect(tmp_path, policy["base"])
    assert result["status"] == "refused"
    assert_full(result, expansion)


@pytest.mark.parametrize("fault", [
    "extra-path", "nonempty-marker", "deleted-fixture", "executable", "symlink",
    "unlisted-commit", "merge-commit", "overlong-history", "wrong-review-head",
    "boolean-review-comment", "stale-main", "conflict", "temporary-offscope", "executable-cleanup-helper",
])
def test_ci_v13_expansion_bound_source_refusals(cohort, expansion, fault):
    root, policy = cohort
    (root / expansion.CONFIG).unlink()
    profile = policy["profiles"]["P07"]
    source = profile["source"]
    git(root, "checkout", "-q", "--detach", source["head"])
    if fault == "extra-path": write(root, "outside.py", "# mixed\n")
    elif fault == "nonempty-marker": write(root, expansion.projection.MARKERS + "T210", "not empty\n")
    elif fault == "deleted-fixture": (root / "tests/fixtures/lanes-edit-v1.1.0/SHA256SUMS").unlink()
    elif fault == "executable": (root / "tests/test_sql_register_shape.py").chmod(0o755)
    elif fault == "executable-cleanup-helper": (root / "tests/sql_register_cleanup.py").chmod(0o755)
    elif fault == "symlink":
        target = root / "tests/test_sql_register_shape.py"
        target.unlink()
        target.symlink_to("test_sql_register_render.py")
    elif fault == "wrong-review-head": profile["review"] = {"head": "a" * 40, "comment": 123}
    elif fault == "boolean-review-comment": profile["review"] = {"head": source["head"], "comment": True}
    elif fault == "overlong-history":
        source["commits"] = [f"{index + 1:040x}" for index in range(expansion.HISTORY_LIMITS["P07"] + 1)]
        source["head"] = source["commits"][-1]
    elif fault in ("stale-main", "conflict"):
        git(root, "checkout", "-q", "--detach", policy["base"])
        write(root, "tests/pgcluster.py", "# conflicting foundation change\n")
        moved = commit(root, "other main")
        if fault == "conflict": policy["base"] = moved
    elif fault == "merge-commit":
        source["head"] = git(root, "commit-tree", git(root, "rev-parse", "HEAD^{tree}"),
                             "-p", source["head"], "-p", policy["base"], "-m", "merge")
        source["commits"].append(source["head"])
    elif fault == "unlisted-commit":
        write(root, "tests/test_sql_register_shape.py", "# undeclared fix\n")
        source["head"] = commit(root, "unlisted fix")
        source["commits"] = [source["head"]]
    elif fault == "temporary-offscope":
        write(root, "outside.py", "# temporary scope escape\n")
        source["commits"].append(commit(root, "off-scope intermediate"))
        (root / "outside.py").unlink()
        source["head"] = commit(root, "restore final scope")
        source["commits"].append(source["head"])
    if fault in {"extra-path", "nonempty-marker", "deleted-fixture", "executable", "symlink", "executable-cleanup-helper"}:
        source["head"] = commit(root, "unsafe scoped fix")
        source["commits"].append(source["head"])
    write(root, expansion.CONFIG, json.dumps(policy))
    main = moved if fault == "stale-main" else policy["base"]
    result = expansion.inspect(root, main)
    assert result["status"] == "refused"
    assert result["reason"] == "invalid-preparation-context"
    assert_full(result, expansion)


@pytest.mark.parametrize("fault", ["missing", "executable", "symlink"])
def test_ci_v13_expansion_report_hook_requires_regular_modified_file(cohort, expansion, fault):
    root, policy = cohort
    (root / expansion.CONFIG).unlink()
    profile = policy["profiles"]["P09"]
    source = profile["source"]
    git(root, "checkout", "-q", "--detach", source["head"])
    target = root / "tests/conftest.py"
    if fault == "executable":
        target.chmod(0o755)
    else:
        target.unlink()
        if fault == "symlink":
            target.symlink_to("pgcluster.py")
    source["head"] = commit(root, "unsafe report hook")
    source["commits"].append(source["head"])
    write(root, expansion.CONFIG, json.dumps(policy))
    result = expansion.inspect(root, policy["base"])
    assert result["status"] == "refused"
    assert_full(result, expansion)


def test_ci_v13_expansion_refusal_never_echoes_private_values(tmp_path, expansion, policy):
    private = "PRIVATE_BRANCH_VALUE_DO_NOT_ECHO"
    policy["profiles"]["P07"]["source"]["branch"] = private
    write(tmp_path, expansion.CONFIG, json.dumps(policy))
    result = expansion.inspect(tmp_path, policy["base"])
    assert result["status"] == "refused"
    assert private not in json.dumps(result)


@pytest.mark.parametrize("name", ["P07", "P09"])
def test_ci_v13_expansion_live_delivery_retains_full_fallback(cutover, v13_batch, name):
    write(v13_batch["root"], ".github/ci/v13-prepared-cohort.json",
          (REPO / ".github/ci/v13-prepared-cohort.json").read_text())
    body = "CI-Shadow: sql-register-v13\nCI-Delivery: sql-register-v13\nCI-Task-Set: " + name
    result = route_source(cutover, v13_batch, body)
    assert result["omit_full"] is False
    assert result["mode"] == "full"
