# SPDX-License-Identifier: Apache-2.0
"""Trusted exact-pair contract; no routing or queue side effects."""

from hashlib import sha256
import json

import delivery_v13 as v13
import shadow_scope as git
import v13_shadow as projection


SCOPE = "sql-register-v13-p07-p09"
CONFIG = ".github/ci/delivery-p07-p09.json"
PAIR = ((97, "cab8fcfdee749dbeac5fc916d1c9b642e6d6cc4c"),
        (103, "1d16c0cc5092fd8704a67399acee81ef2436f21a"))
HEADS = tuple(head for _number, head in PAIR)
PREREQUISITE = "7f1141be15ac9c0d20c25c802ba9533c2fec811c"
BODIES = {
    "97": "e843a4481ed057cf0b7e27a598da885e06fa6a33888186b32024b769e35ceaa3",
    "103": "56ee0c204f37ad1b7ac0a07de17b7615d09bc4b4edd1443cd4afc1492264d46a",
}
TRANSITION = {
    "tests/conftest.py": ("5c4e3d182094bd149e9a68f826ae427dc9739b5d",
                          "551ae334dc7515c053ad60b7fa1252cd08ff094f"),
    "tests/pgcluster.py": ("97871b78a222b1b3d7cc05ef1bc4bbbeeaa4419d",
                           "4efc76f6370af46c9c2fe9a807555a3d532d3960"),
}
EMPTY = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def own_source(pr):
    number = pr.get("number")
    return type(number) is int and number in {97, 103} and (number, pr["head"]["sha"]) in PAIR


def regular_blob(root, base, path):
    entry = git.git(root, "ls-tree", "-z", git.sha(base), "--", path)
    if entry == b"":
        return None
    metadata, found = entry[:-1].decode().split("\t", 1)
    mode, kind, blob = metadata.split()
    require(entry.endswith(b"\0") and found == path and mode == "100644" and kind == "blob",
            "Exact-pair policy is not a regular blob")
    return git.git(root, "cat-file", "blob", git.sha(blob))


def configuration(root, base):
    raw = regular_blob(root, base, CONFIG)
    if raw is None:
        return None
    require(len(raw) <= 4096, "Exact-pair policy is oversized")
    config = json.loads(raw, object_pairs_hook=projection.unique_pairs)
    require(isinstance(config, dict)
            and set(config) == {"schema_version", "scope", "enabled", "body_sha256", "profiles"}
            and type(config["schema_version"]) is int and config["schema_version"] == 1
            and config["scope"] == SCOPE and type(config["enabled"]) is bool
            and config["body_sha256"] == BODIES, "Invalid exact-pair policy")
    if not config["enabled"]:
        return None
    profiles = config["profiles"]
    require(isinstance(profiles, dict) and set(profiles) == {"P07", "P09"},
            "Unknown exact-pair profile")
    for name, count in (("P07", 40), ("P09", 165)):
        profile = profiles[name]
        require(set(profile) == {"anchor", "chain_sha256", "commit_count", "branch", "tasks", "files"}
                and type(profile["commit_count"]) is int and profile["commit_count"] == count,
                "Invalid exact-pair profile")
    v13.configuration(root, base)
    return profiles


def inventory(root, anchor, tip, files, markers, *, final):
    raw = git.git(root, "diff", "--raw", "--no-abbrev", "--no-renames", "--no-ext-diff",
                  "--ignore-submodules=none", "-z", anchor, tip, "--").split(b"\0")
    require(len(raw) >= 3 and len(raw) % 2 == 1 and raw[-1] == b"", "Invalid source diff")
    seen = {}
    for metadata, raw_path in zip(raw[:-1:2], raw[1:-1:2]):
        require(metadata.startswith(b":"), "Invalid source path record")
        old, new, _before, after, status = metadata[1:].decode("ascii").split()
        path = raw_path.decode("utf-8")
        require(new == "100644" and path not in seen, "Nonregular or duplicate source path")
        if path in markers:
            require((old, after, status) == ("000000", EMPTY, "A"), "Source marker changed")
        else:
            require(path in files and (old, status) in {("000000", "A"), ("100644", "M")},
                    "Source exceeds reviewed path inventory")
        seen[path] = status
    require(markers <= seen.keys() and bool(seen.keys() - markers), "Source prefix incomplete")
    if final:
        require(seen == {**files, **dict.fromkeys(markers, "A")}, "Final source inventory differs")


def cut(root, base, head):
    profiles = configuration(root, base)
    require(profiles is not None, "Exact-pair delivery is not enabled")
    require(head in HEADS, "Unknown exact-pair source")
    name = "P07" if head == HEADS[0] else "P09"
    profile = profiles[name]
    anchor = git.sha(profile["anchor"])
    markers = {projection.MARKERS + token for token in profile["tasks"]}
    git.git(root, "merge-base", "--is-ancestor", PREREQUISITE, anchor)
    git.git(root, "merge-base", "--is-ancestor", anchor, base)
    paths = sorted(set(profile["files"]) | markers)
    git.git(root, "diff", "--quiet", "--no-ext-diff", "--ignore-submodules=none",
            anchor, base, "--", *paths)
    count = profile["commit_count"]
    raw = git.git(root, "rev-list", "--reverse", "--parents",
                  f"--max-count={count + 1}", f"{anchor}..{head}")
    rows = raw.decode("ascii").splitlines()
    require(len(rows) == count and sha256(raw).hexdigest() == profile["chain_sha256"],
            "Source history differs from the reviewed cut")
    previous = anchor
    for row in rows:
        commit, parent = row.split()
        require(parent == previous, "Exact-pair source chain is not linear")
        inventory(root, anchor, commit, profile["files"], markers, final=commit == head)
        previous = commit
    require(previous == head, "Exact-pair source chain tip differs")
    return profile


def source(root, base, pr, request):
    head, branch = git.side(pr, "head")
    profile = cut(root, base, head)
    number, body = pr["number"], pr.get("body")
    require(type(number) is int and (number, head) in PAIR
            and branch == profile["branch"] and isinstance(body, str)
            and sha256(body.encode()).hexdigest() == BODIES[str(number)]
            and git.side(pr, "base") == (base, "main") and pr["state"] == "open"
            and pr["draft"] is False and pr.get("merged") is False,
            "Exact-pair source metadata differs")
    require(request(git.REPOSITORY, f"pulls/{number}") == pr
            and request(git.REPOSITORY, "git/ref/heads/" + branch)["object"]["sha"] == head
            and request(git.REPOSITORY, "git/ref/heads/main")["object"]["sha"] == base,
            "Exact-pair source moved")
    return number


def foundation(root, rev):
    entries = {}
    data = git.git(root, "ls-tree", "-z", git.sha(rev), "--", *projection.P01_FILES).decode()
    for line in data.split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            mode, kind, sha = meta.split()
            require(mode == "100644" and kind == "blob" and path not in entries,
                    "Foundation entry is not a unique regular blob")
            entries[path] = git.sha(sha)
    require(set(entries) == set(projection.P01_FILES), "Foundation inventory differs")
    return entries


def ordered_trees(root, base, candidate, members):
    """Refuse singleton, reversal, mismatched trees and any other foundation change."""
    require(all(type(row["number"]) is int for row in members)
            and tuple((row["number"], row["head"]) for row in members) == PAIR,
            "Candidate must contain exactly P07 then P09")
    before = foundation(root, base)
    after = dict(before)
    for path, (expected, changed) in TRANSITION.items():
        require(before[path] == expected, "Reviewed foundation base differs")
        after[path] = changed
    previous = base
    trees = []
    for row, blobs in zip(members, (before, after)):
        prefix = git.sha(row["prefix"])
        parents = git.git(root, "show", "-s", "--format=%P", prefix).decode().split()
        require(parents == [previous, row["head"]], "Candidate prefix parents differ")
        tree = git.sha(git.git(root, "rev-parse", prefix + "^{tree}").decode().strip())
        expected = git.sha(git.git(root, "merge-tree", "--write-tree", previous, row["head"]).decode().strip())
        require(tree == expected == row["tree"] and foundation(root, prefix) == blobs,
                "Candidate tree or foundation transition differs")
        trees.append(tree)
        previous = prefix
    require(previous == candidate, "Candidate tip differs")
    return tuple(trees)
