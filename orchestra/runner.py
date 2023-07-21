#!/usr/bin/env python
from collections import defaultdict
import hashlib
from itertools import chain, filterfalse, tee
from packaging.requirements import Requirement
from pathlib import Path
import subprocess
import sys
from typing import Any, Annotated, Iterable, TypeVar
from unittest import defaultTestLoader
from unittest import TestResult
import venv

from git import Repo
from packaging.specifiers import Specifier
from rich.console import Console
from rich.table import Table

from .pkgindex import pkg_find, pkg_download, requirements_from_whl
from .release import remote_name


venv_dir = ".venvs"
wheel_dir = ".wheels"
repo_dir = ".repos"

T = TypeVar("T")

console = Console()


def fmt_results(results: TestResult) -> tuple[Table, int]:
    """Formats the results of a test run

    Parameters:
    -----------
    results: TestResult
        The results of a test run

    Returns:
    --------
    tuple[Table, int]
        A tuple of a text table containing the result summary and the total
        number of failures and errors
    """
    tbl = Table(show_header=False)
    tbl.add_row("Tests Run", f"{results.testsRun}")
    if errors := len(results.errors):
        tbl.add_row("Errors", f"{errors}", style="bold red")
    else:
        tbl.add_row("Errors", f"{errors}")
    if failures := len(results.failures):
        tbl.add_row("Failures", f"{failures}", style="bold red")
    else:
        tbl.add_row("Failures", f"{failures}")
    return tbl, failures + errors


def python_in_venv(name: str) -> tuple[str, str]:
    """Returns the path to a virtual environment and its python"""
    venvpath = f"{venv_dir}/{name}"
    python = f"{venvpath}/bin/{Path(sys.executable).name}"
    return venvpath, python


def opts_to_flags(k: str, v: Any, no_eq: bool = False) -> str:
    """Converts a key-value pair to a command line flag

    It also converts `_` to `-`, and if the value is `True`, it only includes
    the flag; if the value is `False` it converts it to `--no-{flag}`.  If the
    value is a list or tuple, it converts it to a space-separated string.

    Examples:
    ---------
    >>> opts_to_flags(output="json")
    "--output=json"
    >>> opts_to_flags("start_dir"="dir")
    "--start-dir=dir"
    >>> opts_to_flags(s="dir")
    "-s dir"
    >>> opts_to_flags(f=True)
    "-f"
    >>> opts_to_flags(force=True)
    "--force"
    >>> opts_to_flags(f=False)
    "--no-f"
    >>> opts_to_flags(force=False)
    "--no-force"

    """

    match k.replace("_", "-"), v:
        case (str() as _k, v) if v is False:
            return f"--no-{_k}"
        case (str() as _k, v) if v is True and len(_k) > 1:
            return f"--{_k}"
        case (str() as _k, v) if v is True:
            return f"-{_k}"
        case (str() as _k, list() | tuple() as v) if len(_k) > 1:
            return f"--{_k} {' '.join(map(str, v))}"
        case (str() as _k, list() | tuple() as v):
            return f"-{_k} {' '.join(map(str, v))}"
        case (str() as _k, v) if len(_k) > 1:
            return f"--{_k} {v}" if no_eq else f"--{_k}={v}"
        case (str() as _k, v):
            return f"-{_k} {v}"


def fmt_opts(opts: dict[str, Any], no_eq: bool = False) -> list[str]:
    """Converts a dictionary of options to a list of command line flags"""
    flags = chain.from_iterable(
        opts_to_flags(k, v, no_eq=no_eq).split() for k, v in opts.items()
    )
    return list(flags)


def pip_install(name: str = "", python: str = "", requires: Iterable[str] = [], **opts):
    """Installs a package in a virtual environment

    One of `name` or `python` must be specified.  If `name` is specified, it
    will install the packages in the virtual environment with that name.  If
    `python` is specified, it will be used to install the packages in
    the virtual environment that contains that python executable.

    If both are present, the virtual environment specified by `name` takes
    precedence.

    Parameters:
    -----------
    name: str
        The name of the virtual environment
    python: str
        The path to the python executable
    requires: Iterable[str]
        The packages to install
    opts: dict[str, Any]
        Additional options to pass to pip

    """
    if (not name) and (not python):
        raise ValueError("`name` and `python` cannot be unspecified simultaneously")

    if name:
        _, python = python_in_venv(name)

    cmd = f"{python} -m pip install".split()
    cmd += fmt_opts(opts, no_eq=True)
    cmd += requires
    subprocess.run(cmd)


def mkvenv(
    name: str = "", metadata: str = "", requires: list[str] = [], **pip_opts
) -> str:
    """Creates a virtual environment

    If `name` is specified, it will create a virtual environment with that
    name.  If `metadata` is specified, it will create a virtual environment
    with a name derived from the md5 hash of the metadata.  If both are
    specified, the virtual environment specified by `name` takes precedence.

    The metadata is stored in a file called `metadata.txt` in the virtual
    environment directory.

    Parameters:
    -----------
    name: str
        The name of the virtual environment
    metadata: str
        Metadata to store in the virtual environment
    requires: list[str]
        The packages to install, specified as requirement specifications
    pip_opts: dict[str, Any]
        Additional options to pass to pip

    Returns
    -------
    name: str
        The name of the virtual environment

    """
    if (not name) and (not metadata):
        raise ValueError("`name` and `metadata` cannot be unspecified simultaneously")

    if metadata and metadata[-1] != "\n":
        metadata += "\n"  # add trailing newline for nicer formatting

    if name == "" and metadata:
        name = hashlib.md5(metadata.encode("utf8")).hexdigest()

    venvpath, python = python_in_venv(name)
    venv.create(venvpath, symlinks=True, with_pip=True, prompt=name)

    if metadata:
        (Path(venvpath) / "metadata.txt").write_text(metadata)

    subprocess.run(f"{python} -m pip install -U pip".split())
    if requires:
        pip_install(python=python, requires=requires, **pip_opts)
    return name


def run_in_venv(
    name: str,
    cmd: str,
    *args: str,
    preface_opt: bool = True,
    no_eq: bool = False,
    **opts,
):
    """Runs a command in a virtual environment

    Parameters:
    -----------
    name: str
        The name of the virtual environment
    cmd: str
        The command to run
    args: str
        The arguments to pass to the command
    preface_opt: bool
        Whether to preface command args with the options
    no_eq: bool
        Whether to use `--opt val` or `--opt=val` for options
    opts: dict[str, Any]
        Additional options to pass to the command

    """
    _, python = python_in_venv(name)
    pycmd = f"{python} -m {cmd}".split()
    if preface_opt:
        pycmd += fmt_opts(opts, no_eq=no_eq)
        pycmd += args
    else:
        pycmd += args
        pycmd += fmt_opts(opts, no_eq=no_eq)
    subprocess.run(pycmd)


def run_unittest(directory: str, venv_name: str = "", in_process: bool = False):
    """Runs the unittests in a directory

    Parameters:
    -----------
    directory: str
        The directory containing the tests
    venv_name: str
        The name of the virtual environment
    in_process: bool
        Whether to run the tests in process or in a virtual environment

    Returns
    -------
    results: TestResult (when in_process=True)
        The results of the tests

    Raises
    ------
    ValueError
        If `in_process` is False and `venv_name` is not specified

    """
    if in_process:
        test_suite = defaultTestLoader.discover(directory)
        results = test_suite.run(TestResult())
        return results
    else:
        if not venv_name:
            raise ValueError("venv must be specified if not running in process")

    run_in_venv(venv_name, "unittest", "discover", preface_opt=False, s=directory)


def spec(req: Requirement) -> tuple[str, str, str]:
    """Extracts the name, operator, and version from a requirement"""
    spec = Specifier(f"{req.specifier}")
    return req.name, spec.operator, spec.version


def resolve_versions(specs: Iterable[Requirement]) -> dict[str, str]:
    """Resolves a list of requirements to a list of unique versions by package

    Parameters:
    -----------
    specs: Iterable[Requirement]
        The requirements to resolve

    Returns
    -------
    versions: dict[str, str]
        The resolved versions; the keys are the package names and the values
        are the versions

    Raises
    ------
    ValueError
        If the requirements resolve to multiple versions

    """
    _res: defaultdict[str, list[str]] = defaultdict(list)
    _specs: defaultdict[str, list[str]] = defaultdict(list)
    for req in specs:
        name, _, ver = spec(req)
        _res[name].append(ver)
        _specs[name].append(f"{req.specifier}")

    res: dict[str, str] = {}
    for name, versions in _res.items():
        _versions = list(set(versions))
        if len(_versions) > 1:
            _versions_str = ",".join(_specs[name])
            raise ValueError(
                f"Requirements resolve to multiple versions: {name}{_versions_str}"
            )
        res[name] = _versions[0]

    return res


def clone_from(src_path: str, dst_path: str, branch: str) -> Repo:
    """Clones a git repository

    Parameters:
    -----------
    src_path: str
        The path to the source repository
    dst_path: str
        The path to the destination repository
    branch: str
        The branch to clone

    Returns
    -------
    repo: Repo
        The cloned repository

    """
    path = Path(dst_path) / remote_name(src_path)
    if path.exists():
        repo = Repo(path)
    else:
        repo = Repo.clone_from(src_path, path, multi_options=[f"-b {branch}"])
    return repo


def run_xtest(config: dict, ref: list[str], dev: list[str]):
    """Runs the tests for a package

    Parameters:
    -----------
    config: dict
        The configuration for the package
    ref: list[str]
        The reference requirements
    dev: list[str]
        The development requirements

    Raises
    ------
    ValueError
        If the package spec is incorrect, or unknown packages are included
    """
    ref_pkgs = {Requirement(dep).name: pkg_find(dep) for dep in ref}
    whls = {name: pkg_download(pkg, wheel_dir) for name, pkg in ref_pkgs.items()}
    requirements = set(
        chain(map(Requirement, ref), *map(requirements_from_whl, whls.values()))
    )

    def is_ours(req):
        return config["pkgname_re"].match(req.name)

    _requires = requirements
    while ours := resolve_versions(filter(is_ours, _requires)):
        _whls = {
            name: pkg_download(pkg_find(f"{name}=={ver}"), wheel_dir)
            for name, ver in ours.items()
            if name not in whls
        }
        whls.update(_whls)
        _requires = set(chain(*map(requirements_from_whl, _whls.values())))
        requirements.update(_requires)

    t1, t2 = tee(requirements)
    rest = list(filterfalse(is_ours, t1))
    # NOTE: filter out ours, as they may depend on the dev packages
    ours = resolve_versions(filter(is_ours, t2))
    venv_vers = sorted(f"{pkg}=={ver}" for pkg, ver in ours.items()) + dev
    console.print(f"all versions: {','.join(venv_vers)}")

    dev_pkgs = dict(dep.split("==") for dep in dev if "==" in dep)
    if len(dev) != len(dev_pkgs):
        raise ValueError(f"invalid package spec: {dev=}")
    unk = [pkg for pkg in dev_pkgs if pkg not in ours]
    if unk:
        raise ValueError(f"unknown packages: {str(unk).strip('[]')}")

    repos = {
        name: clone_from(path, repo_dir, config["branches"][name])
        for name, path in config["repos"].items()
    }
    for name, gitref in dev_pkgs.items():
        repos[name].git.checkout(gitref)

    venv_name = mkvenv(metadata="\n".join(venv_vers), requires=list(map(str, rest)))
    console.print("venv: ", venv_name)

    # install dev
    our_deps = chain(
        [repos[name].working_dir for name in dev_pkgs],
        [f"{whl}" for name, whl in whls.items() if name not in dev_pkgs],
    )
    pip_install(venv_name, requires=our_deps, no_deps=True)

    for name in dev_pkgs:
        repo = repos[name]
        # checkout ref tag
        ver = ours[name]
        repo.git.checkout(ver)  # should be a git tag
        # run tests
        work_dir = repo.working_dir
        run_unittest(f"{work_dir}/tests", venv_name=venv_name)

    return


if __name__ == "__main__":
    import typer

    from .config import read_conf

    help_txt = "version of the package, specified as a requirement spec: pkg==<ver>"

    def main(
        ref: Annotated[
            list[str],
            typer.Option("--ref", "-r", help=f"Reference {help_txt}"),
        ],
        dev: Annotated[
            list[str],
            typer.Option("--dev", "-d", help=f"Development {help_txt}"),
        ],
        config: Annotated[
            Path, typer.Option("--config", "-c", help="TOML config file")
        ] = Path("pyproject.toml"),
    ):
        conf = read_conf(f"{config}")
        run_xtest(conf, ref, dev)

    typer.run(main)

    # results = run_tests(directory, in_process=True)
    # tbl, exit_code = fmt_results(results)
    # console.print(tbl)
    # if exit_code > 0:
    #     sys.exit(exit_code)
