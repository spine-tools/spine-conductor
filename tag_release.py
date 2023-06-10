#!/usr/bin/env python

from argparse import (
    ArgumentParser,
    ArgumentDefaultsHelpFormatter,
    RawDescriptionHelpFormatter,
)
from enum import Enum
import os
import re
import subprocess
import textwrap
import warnings

from git import Repo
from packaging import version
from setuptools_scm import get_version
import tomlkit


EDITOR = os.environ.get("EDITOR", "vim")
commit_hdr = """
# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
"""

dependency_graph = {}  # to be read from config
default_branch = "master"

version_re = re.compile(r"[0-9]+(\.[0-9]+){1,}")
pkgname_re: re.Pattern[str]
empty_re = re.compile(r"\s+")



class Version(Enum):
    major = "major"
    minor = "minor"
    patch = "patch"


class RawArgDefaultFormatter(
    ArgumentDefaultsHelpFormatter, RawDescriptionHelpFormatter
):
    """Combine raw help text formatting with default argument display."""

    pass


def base_version(version: str) -> str:
    """Return the base version of a version string."""
    match = version_re.match(version)
    if match:
        return version[slice(*match.span())]
    else:
        warnings.warn(f"Could not parse version {version}!")
        return ""


def read_toml(path: str) -> dict:
    with open(path, mode="r") as toml_file:
        return tomlkit.load(toml_file)


def write_toml(data: dict, path: str):
    with open(path, mode="w") as toml_file:
        tomlkit.dump(data, toml_file)


def is_circular(pkg: str) -> bool:
    """Check if a package has a circular dependency."""
    visited = set()
    to_visit = [pkg]
    while to_visit:
        pkg = to_visit.pop()
        if pkg in visited:
            return True
        visited.add(pkg)
        to_visit.extend(dependency_graph[pkg])
    return False


def latest_tags(repos: list[Repo]) -> list[str]:
    """Return the latest tag for each repo."""
    tags = [
        sorted(map(version.parse, filter(version_re.match, map(str, repo.tags))))[-1]
        for repo in repos
    ]
    return [str(tag) for tag in tags]


def guess_next_versions(
    repos: list[Repo], bump_version: Version = Version.minor
) -> list[str]:
    """Guess the next version for each repo.

    By default, increment the minor version.

    If `bump_version` is `Version.{major,patch}`, increment the major/patch version.

    """
    project = read_toml(f"{repos[0].working_dir}/pyproject.toml")
    if bump_version == Version.patch:
        version_scheme = "guess-next-dev"
    else:
        version_scheme = project["tool"]["setuptools_scm"]["version_scheme"]
    versions = [
        base_version(get_version(root=repo.working_dir, version_scheme=version_scheme))
        for repo in repos
    ]

    def bump_major(version: str):
        major, *_ = version.split(".")
        return f"{int(major) + 1}.0.0"

    if bump_version == Version.major:
        return [bump_major(ver) for ver in versions]
    return versions


def update_pkg_dependecies(pkg: str, pkgs: dict[str, tuple[Repo, str, str]]):
    """Update the versions of the dependencies for a given package/project"""
    repo, _, next_version = pkgs[pkg]
    project = read_toml(f"{repo.working_dir}/pyproject.toml")
    dependecies: list[str] = []
    for dep in project["project"].get("dependencies", []):
        dep_match = pkgname_re.match(dep)
        if dep_match:
            pkg = dep_match.group()
            next_version = pkgs[pkg][-1]
            dependecies.append(f"{pkg}>={next_version}")
        else:
            dependecies.append(dep)
    if len(dependecies) > 0:
        project["project"]["dependencies"] = dependecies
    write_toml(project, f"{repo.working_dir}/pyproject.toml")


def check_current_branch(repo_paths: dict[str, str], branches: dict[str, str]):
    """Check that the current branch matches the default branch for each repo."""
    for pkg, path in repo_paths.items():
        repo = Repo(path)
        if repo.active_branch.name != branches[pkg]:
            raise RuntimeError(
                f"{pkg}@{path} is on branch {repo.active_branch.name!r}, not {branches[pkg]!r}"
            )


def invoke_editor(repo: Repo, tag: str) -> str:
    """Invoke the user's default editor to edit the commit message.

    Raises:
        RuntimeError: If the user cancels the commit message.

    """
    with open(f"{repo.git_dir}/COMMIT_EDITMSG", mode="w+") as tmp_file:
        msg = "\n".join(
            [
                f"Release {tag}",
                "",
                "",
                textwrap.dedent(commit_hdr.strip()),
                f"# Repository: {repo.working_dir}",
                textwrap.indent(repo.git.status(), "# ", predicate=lambda _: True),
            ]
        )
        # Write the contents of the template file to the temporary file
        tmp_file.write(msg)
        tmp_file.flush()

        # Open the temporary file in the user's default editor
        ret = subprocess.run([*EDITOR.split(), tmp_file.name])
        if ret.returncode != 0:
            raise RuntimeError("cancelled by user")

        # Read the contents of the temporary file after the user has edited it
        with open(tmp_file.name, "r") as edited_file:
            lines = edited_file.readlines()
            return "".join(line for line in lines if not line.startswith("#"))


def tag_releases(repo_paths: dict[str, str], bump_version: Version = Version.minor):
    """Tag releases for all packages."""
    _repos = [Repo(path) for path in repo_paths.values()]
    _tags = latest_tags(_repos)
    _next_versions = guess_next_versions(_repos, bump_version)
    pkgs = {
        pkg: (repo, tag, next_version)
        for pkg, (repo, tag, next_version) in zip(
            repo_paths, zip(_repos, _tags, _next_versions)
        )
    }

    for pkg, (repo, tag, next_version) in pkgs.items():
        if tag == next_version:
            continue
        update_pkg_dependecies(pkg, pkgs)
        # FIXME: version will be incorrect when there are no commits on top of
        # the previous release
        # repo.index.add([item.a_path for item in repo.index.diff(None)])
        repo.index.add(f"{repo.working_dir}/pyproject.toml")
        try:
            msg = invoke_editor(repo, next_version)
            if msg == "" or empty_re.match(msg):
                raise RuntimeError("empty commit message")
        except RuntimeError as err:
            warnings.warn(f"aborting: {err}")
            continue
        else:
            repo.index.commit(msg)
            repo.create_tag(next_version)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Tag releases for all packages.",
        formatter_class=RawArgDefaultFormatter,
    )
    parser.add_argument("config", help="TOML config file")
    parser.add_argument(
        "-b",
        "--bump-version",
        type=Version,
        choices=Version,
        default=Version.minor,
        help="Bump the major, minor, or patch version.",
    )
    parser.add_argument("-o", "--only", nargs="+", help="Only tag these packages.")
    args = parser.parse_args()

    config = read_toml(args.config)
    dependency_graph.update(config["dependency_graph"])
    pkgname_re = re.compile(config["packagename_regex"])

    branches = config.get("branches", {pkg: default_branch for pkg in dependency_graph})
    if args.only:
        config["repos"] = {pkg: config["repos"][pkg] for pkg in args.only}
        branches = {pkg: branches[pkg] for pkg in args.only}
    check_current_branch(config["repos"], branches)
    tag_releases(config["repos"], args.bump_version)
