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
    name = request.param
    repo = clone_repo(name)

    def _clone(_repo: Repo, path: Path):
        if path.exists():
            return Repo(path)
        else:
            rclone = _repo.clone(f"{path}")
            return rclone

    repo1 = _clone(repo, tmp_path / f"{name}1")
    repo2 = _clone(repo1, tmp_path / f"{name}2")
    repo2.create_remote("upstream", repo.working_dir)
    yield repo, repo1, repo2
    shutil.rmtree(repo1.working_dir, onerror=rm_ro)
    shutil.rmtree(repo2.working_dir, onerror=rm_ro)


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
