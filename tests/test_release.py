from itertools import chain, product
from pathlib import Path

from git import Repo
from packaging.version import Version
import pytest

from orchestra.release import (
    VersionPart,
    bump_version,
    check_current_branch,
    guess_next_versions,
    is_circular,
    latest_tags,
    update_pkg_deps,
    version_parse_no_except,
    remote_name,
)

from .conftest import clone_repo, next_versions


@pytest.mark.parametrize(
    "ver, valid", [("0.1", True), ("1.0.1", True), ("test_tag", False)]
)
def test_version_parse(ver, valid):
    res = version_parse_no_except(ver)
    if valid:
        assert isinstance(res, Version)
    else:
        assert res is None


@pytest.mark.parametrize("name", ["scm", "scm-dep", "scm-base"])
def test_remote_name(name):
    assert remote_name(clone_repo(name)) == name


@pytest.mark.parametrize(
    "pkg, expect", [("sa-foo", True), ("sa-bar", True), ("sa-baz", False)]
)
def test_is_circular(pkg, expect):
    assert is_circular(pkg) == expect


def test_latest_tags():
    names = ("scm", "scm-dep", "scm-base")
    tags = latest_tags([clone_repo(name) for name in names])
    assert tags == ["0.7.2", "0.2.3", "0.3.1"]


@pytest.mark.parametrize(
    "version, part, expect",
    [
        ("0.1.2", VersionPart.major, "1.0.0"),
        ("0.1.2", VersionPart.minor, "0.2.0"),
        ("0.1.2", VersionPart.patch, "0.1.3"),
    ],
)
def test_bump_version(version, part, expect):
    assert bump_version(Version(version), part) == expect


@pytest.mark.parametrize(
    "repo, bump, expect",
    [
        *zip(
            *zip(
                *product(
                    ("scm", "scm-dep", "scm-base"),
                    (VersionPart.major, VersionPart.minor, VersionPart.patch),
                )
            ),
            chain(
                ["1.0.0", "0.8.0", "0.7.3"],  # scm (HEAD): 0.7.2 + commits
                ["1.0.0", "0.2.3", "0.2.3"],  # scm-dep (HEAD): 0.2.3
                ["1.0.0", "0.3.1", "0.3.1"],  # scm-base (HEAD): 0.3.1
            ),
        ),
    ],
    indirect=["repo"],
)
def test_guess_next_version(repo, bump, expect):
    assert guess_next_versions([repo], bump)[0] == expect


@pytest.mark.parametrize(
    "repo, expect",
    [("scm", []), ("scm-dep", ["not-empty"]), ("scm-base", [])],
    indirect=["repo"],
)
def test_update_pkg_deps(repo, expect):
    update_pkg_deps(repo, next_versions)
    changes = repo.index.diff(None)
    if expect:
        assert changes
    else:
        assert changes == []


@pytest.mark.parametrize("name", ["scm", "scm-dep", "scm-base"])
def test_check_current_branch(name):
    path = {name: Path(__file__).parent / name}
    check_current_branch(path, {name: "master"})

    with pytest.raises(RuntimeError, match=f".+{name}.+'master'.+'not-there'"):
        check_current_branch(path, {name: "not-there"})
