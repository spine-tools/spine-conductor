from enum import Enum
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import warnings

from git import Repo
from packaging import version
from rich.console import Console
from rich.prompt import Prompt
from setuptools_scm import get_version

from .config import CONF, read_toml, write_toml

EDITOR = os.environ.get(
    "EDITOR", "notepad" if sys.platform in ("win32", "cygwin") else "vim"
)
commit_hdr = """
# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
"""

empty_re = re.compile(r"\s+")
comma_space_re = re.compile(r"[,\s]+")

console = Console()


def version_parse_no_except(vers: str) -> version.Version | None:
    """Parse a version string and return it as a string.

    If the version string cannot be parsed, return `None`.

    """
    try:
        return version.parse(vers)
    except version.InvalidVersion:
        return


class VersionPart(Enum):
    major = "major"
    minor = "minor"
    patch = "patch"


def remote_name(repo: Repo | str) -> str:
    if isinstance(repo, str):
        repo = Repo(repo)
    return Path(repo.remote().url).stem


def is_circular(pkg: str) -> bool:
    """Check if a package has a circular dependency."""
    visited = set()
    to_visit = [pkg]
    while to_visit:
        pkg = to_visit.pop()
        if pkg in visited:
            return True
        visited.add(pkg)
        to_visit.extend(CONF["dependency_graph"][pkg])
    return False


def latest_tags(repos: list[Repo]) -> list[str]:
    """Return the latest tag for each repo."""
    tags = [
        sorted(filter(version_parse_no_except, map(str, repo.tags)))[-1]
        for repo in repos
    ]
    return [str(tag) for tag in tags]


def bump_version(version: version.Version, part: VersionPart) -> str:
    """Bump the version by the specified part."""
    if part == VersionPart.major:
        return f"{version.major + 1}.0.0"
    elif part == VersionPart.minor:
        return f"{version.major}.{version.minor + 1}.0"
    else:
        return f"{version.major}.{version.minor}.{version.micro + 1}"


def guess_next_versions(
    repos: list[Repo], bump_version_part: VersionPart = VersionPart.minor
) -> list[str]:
    """Guess the next version for each repo.

    Bump the version part specified by `bump_version_part` (default: minor).

    The repo versioning scheme is read from the `pyproject.toml` file
    in the first repo.  However, if `bump_version_part` is
    `VersionPart.patch`, the version scheme is set to `guess-next-dev`
    to ensure that the version is bumped only if there are new
    commits.  For the other cases, the version part is bumped
    unconditionally.

    """
    project = read_toml(f"{repos[0].working_dir}/pyproject.toml")
    if bump_version_part == VersionPart.patch:
        version_scheme = "guess-next-dev"
    else:
        version_scheme = project["tool"]["setuptools_scm"]["version_scheme"]
    versions = [
        version.parse(get_version(root=repo.working_dir, version_scheme=version_scheme))
        for repo in repos
    ]

    if bump_version_part == VersionPart.major:
        return [bump_version(ver, VersionPart.major) for ver in versions]
    return [version.base_version for version in versions]


def update_pkg_deps(repo: Repo, next_versions: dict[str, str]):
    """Update the versions of the dependencies for a given package/project"""
    pyproject_toml = f"{repo.working_dir}/pyproject.toml"
    project = read_toml(pyproject_toml)
    dependecies: list[str] = []
    for dep in project["project"].get("dependencies", []):
        if dep_match := CONF["pkgname_re"].match(dep):
            pkg_ = dep_match.group()
            next_ver = next_versions[pkg_]
            dependecies.append(f"{pkg_}>={next_ver}")
        else:
            dependecies.append(dep)
    if len(dependecies) > 0:
        project["project"]["dependencies"] = dependecies
    write_toml(project, pyproject_toml)


def check_current_branch(repo_paths: dict[str, str], branches: dict[str, str]):
    """Check that the current branch matches the default branch for each repo."""
    for pkg, path in repo_paths.items():
        repo = Repo(path)
        if repo.active_branch.name != branches[pkg]:
            msg = f"{pkg}@{path} is on branch {repo.active_branch.name!r},"
            msg += f" not {branches[pkg]!r}"
            raise RuntimeError(msg)


def prompt_add(repo: Repo) -> int:
    """Prompt the user to select files to add to the index."""
    status = repo.git.status("-sb").splitlines()
    status_ = "\n".join(
        line
        if line.startswith("##")
        else f"[green]{line[0]}[/green][red]{line[1]}[/red]{line[2:]} ({idx})"
        for idx, line in enumerate(status)
    )
    console.print(f"[bold]Repository: {repo.working_dir}")
    console.print(status_)
    response = Prompt.ask("Select the files to add (comma/space separated list)")
    added = 0
    if response == "":
        return added
    for choice in map(int, comma_space_re.split(response)):
        file_path = status[choice][3:].strip()
        repo.index.add(file_path)
        added += 1
    return added


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


def create_tags(
    repo_paths: dict[str, str], bump_version: VersionPart = VersionPart.minor
) -> dict[str, str]:
    """Tag releases for all packages."""
    _repos = [Repo(path) for path in repo_paths.values()]
    _tags = latest_tags(_repos)
    _next_versions = guess_next_versions(_repos, bump_version)
    next_versions = dict(zip(repo_paths, _next_versions))
    pkgs = dict(zip(repo_paths, zip(_repos, _tags, _next_versions)))

    summary = {}
    for pkg, (repo, tag, next_version) in pkgs.items():
        if tag == next_version:
            continue

        update_pkg_deps(repo, next_versions)
        prompt_add(repo)
        modified = [i.a_path for i in repo.index.diff(None)]
        if "pyproject.toml" in modified:  # must add pyproject.toml
            repo.index.add("pyproject.toml")
        added = len([i for i in repo.index.diff("HEAD")])

        if added > 0:
            try:
                msg = invoke_editor(repo, next_version)
                if msg == "" or empty_re.match(msg):
                    raise RuntimeError("empty commit message")
                repo.index.commit(msg)
            except RuntimeError as err:
                warnings.warn(f"aborting commit: {err}")
                continue

        console.print(f"Creating tag: {next_version}")
        repo.create_tag(next_version)
        summary[remote_name(repo)] = next_version
    return summary


def make_release(
    config: dict, bump_version: VersionPart, output: Path, only: list[str] = []
):
    """Make release tag for all packages, and print a summary."""
    branches = config["branches"]
    if len(only) > 0:
        config["repos"] = {pkg: config["repos"][pkg] for pkg in only}
        branches = {pkg: branches[pkg] for pkg in only}
    try:
        check_current_branch(config["repos"], branches)
    except Exception:
        console.print_exception()

    summary = create_tags(config["repos"], bump_version)
    json_str = json.dumps(summary, indent=4)
    output.write_text(json_str)
    msg = "\n[underline]Package Tags summary[/underline] "
    msg = f"{msg} :floppy_disk: :right_arrow: '{output}':"
    console.print(msg)
    console.print_json(json_str)


if __name__ == "__main__":
    import typer

    from .config import read_conf

    def main(
        config: Path = Path("pyproject.toml"),
        bump_version: VersionPart = VersionPart.minor,
        output: Path = Path("pkgtags.json"),
        only: list[str] = [],
    ):
        conf = read_conf(f"{config}")
        make_release(conf, bump_version, output, only)

    typer.run(main)
