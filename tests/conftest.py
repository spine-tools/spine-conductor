from pathlib import Path
import shutil
import stat

from git import Repo
import pytest

from orchestra.config import read_conf, read_toml, write_toml

# exclude tests inside example repos from discovery
collect_ignore_glob = ["scm*"]

example_repos = {
    "scm": "https://github.com/suvayu/scm.git",
    "scm-dep": "https://github.com/suvayu/scm-dep.git",
    "scm-base": "https://github.com/suvayu/scm-base.git",
}
example_pkgs = {"scm": "sa-foo", "scm-dep": "sa-bar", "scm-base": "sa-baz"}
# for dependency graph, see tests/scm.toml
next_versions = {
    example_pkgs["scm"]: "0.8.0",  # HEAD: 0.7.2 + commits; depends: scm-dep, scm-base
    example_pkgs["scm-dep"]: "0.2.3",  # HEAD: 0.2.3; depends: scm, scm-base
    example_pkgs["scm-base"]: "0.3.1",  # HEAD: 0.3.1; no scm deps
}


@pytest.fixture(scope="session", autouse=True)
def configure():
    read_conf(f"{Path(__file__).parent / 'scm.toml'}")


def clone_repo(name: str):
    path = Path(__file__).parent / name
    if path.exists():
        return Repo(path)
    return Repo.clone_from(example_repos[name], path)


def rm_ro(_fn, path, exc_info):
    p = Path(path)
    # only handle RO files, dir tree traversal handled by rmtree
    if isinstance(exc_info[1], PermissionError):
        # exc_info <= (exc_t, exc, tb)
        p.chmod(stat.S_IWRITE)
        p.unlink()


@pytest.fixture
def dup_repos(tmp_path, request):
    """Creates a pair of repos with a remote pointing to the other

    The original remote is named 'upstream' in clone2, and 'origin' in
    the clone1.  The repos are cloned into tmp_path, and deleted after
    the test.  The fixture returns a tuple of (name, original, clone1,
    clone2).

        tests/<repo> -> tmp_path/<clone1> -> tmp_path/<clone2>

        tmp_path/<clone1>:
          tests/<repo> (origin)

        tmp_path/<clone2>:
          tmp_path/<clone1> (origin)
          tests/<repo> (upstream)

    Parameters
    ----------
    tmp_path : Path
        pytest fixture
    request : pytest fixture
        pytest request object

    Yields
    ------
    tuple
        (name, original, clone1, clone2)

    """
    name = request.param
    repo = clone_repo(name)

    def _clone(_repo: Repo, path: Path, **kwargs):
        if path.exists():
            return Repo(path)
        else:
            rclone = _repo.clone(f"{path}", **kwargs)
            return rclone

    repo1 = _clone(repo, tmp_path / f"{name}.git", bare=True)
    repo2 = _clone(repo1, tmp_path / f"{name}")
    repo2.create_remote("upstream", repo.working_dir)
    yield name, repo, repo1, repo2
    # FIXME: from Python 3.12 onerror is deprecated in favour or onexc
    shutil.rmtree(repo1.working_dir, onerror=rm_ro)
    shutil.rmtree(repo2.working_dir, onerror=rm_ro)


def edit(fname: str, payload: str, append: bool = True):
    mode = "a" if append else "w"
    with open(fname, mode=mode) as f:
        f.write(payload)


def commit(repo: Repo, fnames: list[str], msg: str):
    repo.index.add(fnames)
    repo.index.commit(msg)


@pytest.fixture
def repo(request):
    repo = clone_repo(request.param)
    yield repo
    repo.head.reset(commit="origin/master", working_tree=True)


def pkg_dash2us(pyproject: str):
    pkgconf = read_toml(pyproject)
    deps = pkgconf["project"]["dependencies"]
    for i, dep in enumerate(deps):
        if "sa-bar" in dep:
            deps[i] = dep.replace("-", "_")
    write_toml(pkgconf, pyproject)
