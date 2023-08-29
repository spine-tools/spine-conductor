from copy import deepcopy
from itertools import chain, product
from pathlib import Path

from packaging.version import Version
import pytest
import tomlkit

from orchestra import ErrorCodes
from orchestra.config import CONF, read_toml
from orchestra.release import (
    VersionPart,
    bump_version,
    check_current_branch,
    guess_next_versions,
    is_circular,
    latest_tags,
    make_release,
    update_pkg_deps,
    version_parse_no_except,
    remote_name,
)

from .conftest import clone_repo, example_pkgs, next_versions


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


@pytest.mark.parametrize("repo", ["scm"], indirect=True)
def test_alt_pkg_names(repo):
    # setup
    pyproject = f"{repo.working_dir}/pyproject.toml"
    pkgconf = read_toml(pyproject)
    deps = pkgconf["project"]["dependencies"]
    for i, dep in enumerate(deps):
        if "sa-bar" in dep:
            deps[i] = dep.replace("-", "_")
    with open(pyproject, mode="w") as f:
        tomlkit.dump(pkgconf, f)
    assert repo.index.diff(None)
    repo.index.add("pyproject.toml")

    # test
    update_pkg_deps(repo, next_versions)  # no KeyError
    assert repo.index.diff(None) == []  # no changes


# only 'scm' has changes, so only 'scm-dep' deps will be updated
@pytest.mark.parametrize("repo", ["scm-dep"], indirect=True)
def test_preserve_line_endings(repo):
    # setup
    pyproject = Path(f"{repo.working_dir}/pyproject.toml")
    txt = pyproject.read_text().replace("\n", "\r\n")
    with open(pyproject, mode="w", newline="") as tf:
        tf.write(txt)
    assert repo.index.diff(None)  # pyproject.toml rewritten w/ CRLF LE
    repo.index.add("pyproject.toml")

    # test
    update_pkg_deps(repo, next_versions)
    diff, *_ = repo.index.diff(None, create_patch=True)
    txt = diff.diff.decode("utf8")
    # 1 header + 2 x 3 line context + 2 line change (+/-)
    assert len(txt.splitlines()) == 9


@pytest.mark.parametrize("name", ["scm", "scm-dep", "scm-base"])
def test_check_current_branch(name):
    pkgname = example_pkgs[name]
    path = {pkgname: Path(__file__).parent / name}
    check_current_branch(path, {pkgname: "master"})

    with pytest.raises(RuntimeError, match=f".+{pkgname}.+'master'.+'not-there'"):
        check_current_branch(path, {pkgname: "not-there"})

    # alternative keys
    path = {name: Path(__file__).parent / name}
    check_current_branch(path, {name: "master"})

    with pytest.raises(RuntimeError, match=f".+{name}.+'master'.+'not-there'"):
        check_current_branch(path, {name: "not-there"})


@pytest.mark.parametrize("pkgname", ["sa-foo", "sa-bar", "sa-baz"])
def test_make_release_ret_code(pkgname, capsys):
    config = deepcopy(CONF)
    config["branches"].update({pkgname: "not-there"})
    with pytest.raises(SystemExit, match=f"{ErrorCodes.BRANCH_ERR}"):
        make_release(config, VersionPart.minor, Path("whatever.json"))
    outerr = capsys.readouterr()
    tokens = ("RuntimeError", f"{pkgname}", "not-there", "Aborting")
    assert all(token in outerr.out for token in tokens)
