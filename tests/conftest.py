from pathlib import Path
from git import Repo
import pytest
import tomlkit

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
