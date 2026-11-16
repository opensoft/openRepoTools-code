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
    assert loaded["order"] == ["P09", "P07"]
    assert all(profile["source"]["commits"][-1] == profile["source"]["head"]
               for profile in loaded["profiles"].values())
    active = expansion.projection.read_policy(REPO, "HEAD")
    assert set(active["profiles"]) == {"P05", "P06"}
    for path in ("delivery_route.py", "delivery_verify.py", "delivery_evidence.py", "delivery_v13.py"):
        text = (REPO / ".github/ci" / path).read_text()
        assert "v13_expansion" not in text
        assert "v13-prepared-cohort" not in text


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
    assert [row["profile"] for row in result["previews"]] == ["P09", "P07"]
    assert set(result["foundation_changes_requiring_activation_review"]) == {"tests/pgcluster.py"}
    assert_full(result, expansion)
    assert before == (git(root, "rev-parse", "HEAD"), git(root, "status", "--porcelain"),
                      git(root, "show-ref"))


@pytest.mark.parametrize("count", [4, 12])
def test_ci_v13_expansion_exact_bounded_fixes_can_be_previewed(cohort, expansion, count):
    root, policy = cohort
    (root / expansion.CONFIG).unlink()
    profile = policy["profiles"]["P09"]
    git(root, "checkout", "-q", "--detach", profile["source"]["head"])
    for index in range(count - 1):
        write(root, "tests/test_sql_register_bounds.py", f"# exact fix {index}\n")
        head = commit(root, "declared fix")
        profile["source"]["commits"].append(head)
        profile["source"]["head"] = head
    git(root, "checkout", "-q", "--detach", policy["base"])
    write(root, expansion.CONFIG, json.dumps(policy))
    result = expansion.inspect(root, policy["base"])
    assert result["status"] == "preview-pending-owner-reviews"
    assert_full(result, expansion)


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
    "boolean-review-comment", "stale-main", "conflict", "temporary-offscope",
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
    elif fault == "symlink":
        target = root / "tests/test_sql_register_shape.py"
        target.unlink()
        target.symlink_to("test_sql_register_render.py")
    elif fault == "wrong-review-head": profile["review"] = {"head": "a" * 40, "comment": 123}
    elif fault == "boolean-review-comment": profile["review"] = {"head": source["head"], "comment": True}
    elif fault == "overlong-history": source["commits"] = ["a" * 40] * 13
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
    if fault in {"extra-path", "nonempty-marker", "deleted-fixture", "executable", "symlink"}:
        source["head"] = commit(root, "unsafe scoped fix")
        source["commits"].append(source["head"])
    write(root, expansion.CONFIG, json.dumps(policy))
    main = moved if fault == "stale-main" else policy["base"]
    result = expansion.inspect(root, main)
    assert result["status"] == "refused"
    assert result["reason"] == "invalid-preparation-context"
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
