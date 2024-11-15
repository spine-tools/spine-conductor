from enum import Enum
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import textwrap

from git import GitCommandError, Repo
from git.config import GitConfigParser
from packaging import version
from rich.console import Console
from rich.prompt import Prompt
from setuptools_scm import get_version
from tomlkit.items import Array, Trivia

from orchestra import ErrorCodes, format_exc, format_git_cmd_err
from orchestra.config import read_toml, write_toml


def find_editor():
    """Find the editor to use for commit messages."""
    conf = GitConfigParser(Path.home() / ".gitconfig")
    if editor := conf.get("core", "editor", fallback=None):
        return editor

    def which() -> str:
        editors: tuple[str, ...] = ("nano", "vim", "nvim", "emacs")
        if sys.platform in ("win32",):
            editors = (*editors, "notepad++", "notepad")
        else:
            editors = (*editors, "vi")
        for editor in map(shutil.which, editors):
            if editor:
                return str(editor)
        raise RuntimeError("couldn't find an editor")

    return os.environ.get("EDITOR", which())


EDITOR = find_editor()
commit_hdr = """
# Please enter the commit message for your changes. Lines starting
# with '#' will be ignored, and an empty message aborts the commit.
#
"""

empty_re = re.compile(r"\s+")
comma_space_re = re.compile(r"[,\s]+")
git_duptag_re = re.compile(r"tag '[0-9.]+' already exists")

console = Console()


def version_parse_no_except(vers: str) -> version.Version | None:
    """Parse a version string and return it as a string.

    If the version string cannot be parsed, return `None`.

    """
    try:
        return version.parse(vers)
    except version.InvalidVersion:
        return None


class VersionPart(Enum):
    major = "major"
    minor = "minor"
    patch = "patch"


def remote_name(repo: Repo | str) -> str:
    if isinstance(repo, str):
        repo = Repo(repo)
    return Path(repo.remote().url).stem


def is_circular(dependency_graph: dict, pkg: str) -> bool:
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
    project = project["tool"]["setuptools_scm"]
    if bump_version_part == VersionPart.patch:
        version_scheme = "guess-next-dev"
    else:
        version_scheme = project.get("version_scheme", "release-branch-semver")
    versions = [
        version.parse(get_version(root=repo.working_dir, version_scheme=version_scheme))
        for repo in repos
    ]

    if bump_version_part == VersionPart.major:
        return [bump_version(ver, VersionPart.major) for ver in versions]
    return [version.base_version for version in versions]


class redict(dict):
    def __missing__(self, key):
        if "-" in key:
            key = key.replace("-", "_")
        elif "_" in key:
            key = key.replace("_", "-")
        else:
            raise KeyError(key)
        if key in self:
            return self[key]
        # FIXME: how do I point to actual line that called __getitem__?
        raise KeyError(key)


def update_pkg_deps(CONF: dict, repo: Repo, next_versions: dict[str, str]):
    """Update the versions of the dependencies for a given package/project"""
    next_versions = redict(next_versions)
    pyproject_toml = f"{repo.working_dir}/pyproject.toml"
    project = read_toml(pyproject_toml)
    dependencies = project["project"].get("dependencies", Array([], Trivia()))
    for i, dep in enumerate(dependencies):
        if dep_match := CONF["pkgname_re"].match(dep):
            pkg_ = dep_match.group()
            try:
                next_ver = next_versions[pkg_]
            except KeyError:
                if pkg_ not in CONF["repos"]:
                    # packages excluded by only/exclude
                    continue
                else:
                    raise  # unexpected
            else:
                dependencies[i] = f"{pkg_}>={next_ver}"
    write_toml(project, pyproject_toml)


def check_current_branch(repo_paths: dict[str, str], branches: dict[str, str]):
    """Check that the current branch matches the default branch for each repo.

    Note: It's not necessary that the dictionary keys are package
    names, as long as they are consistent between the two arguments.

    Parameters
    ----------
    repo_paths : dict[str, str]
        A mapping from package names to paths to the repos.
    branches : dict[str, str]
        A mapping from package names to the default branch for the
        package.

    Raises
    ------
    RuntimeError
        If the current branch does not match the default branch for any
        repo.

    """
    errors = []
    for pkg, path in repo_paths.items():
        repo = Repo(path)
        if repo.active_branch.name != branches[pkg]:
            errors.append((pkg, path, repo.active_branch.name, branches[pkg]))
    if len(errors) > 0:
        msg = "The following repos are not on the default branch:\n"
        for pkg, path, co_branch, branch in errors:
            msg += f"  {pkg}@{path}: {co_branch!r}* != {branch!r}\n"
        raise RuntimeError(msg)


def prompt_add(repo: Repo) -> int:
    """Prompt the user to select files to add to the index."""
    status = repo.git.status("-sb").splitlines()
    console.print(
        f"[bold]Repository: {repo.working_dir}",
        *(
            (
                line
                if line.startswith("##")
                else f" [{idx}][green]{line[0]}[/green][red]{line[1]}[/red]{line[2:]}"
            )
            for idx, line in enumerate(status)
        ),
        sep="\n",
    )
    response = Prompt.ask("Select the files to add (comma/space separated list)")
    added = 0
    if response == "":
        return added
    for choice in map(int, comma_space_re.split(response)):
        # trim 'a/path/to/file' or 'b/path/to/file' used by git
        file_path = status[choice][3:].strip()
        repo.git.add(file_path)
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
                # comment all lines, including empty ones
                textwrap.indent(repo.git.status(), "# ", predicate=lambda _: True),
            ]
        )
        # Write the contents of the template file to the temporary file
        tmp_file.write(msg)
        tmp_file.flush()

        # Open the temporary file in the user's default editor.
        if sys.platform == "win32":
            args = [*EDITOR.split(" "), tmp_file.name]
        else:
            # On *NIX platforms, we an use shlex.split() to support EDITOR command with arguments.
            args = [*shlex.split(EDITOR), tmp_file.name]
        ret = subprocess.run(args)
        if ret.returncode != 0:
            raise RuntimeError("cancelled by user")

        # Read the contents of the temporary file after the user has edited it
        with open(tmp_file.name, "r") as edited_file:
            lines = edited_file.readlines()
            return "".join(line for line in lines if not line.startswith("#"))


def create_tags(
    CONF: dict, bump_version: VersionPart = VersionPart.minor
) -> dict[str, str]:
    """Tag releases for all packages."""
    repo_paths = CONF["repos"]
    _repos = [Repo(path) for path in repo_paths.values()]
    _tags = latest_tags(_repos)
    _next_versions = guess_next_versions(_repos, bump_version)
    next_versions = dict(zip(repo_paths, _next_versions))
    pkgs = dict(zip(repo_paths, zip(_repos, _tags, _next_versions)))

    summary = {}
    for pkg, (repo, tag, next_version) in pkgs.items():
        if tag == next_version:
            continue

        update_pkg_deps(CONF, repo, next_versions)
        prompt_add(repo)
        modified = [i.a_path for i in repo.index.diff(None)]
        if "pyproject.toml" in modified:  # must add pyproject.toml
            repo.git.add("pyproject.toml")
        added = len([i for i in repo.index.diff("HEAD")])

        # NOTE: exit gracefully if python files were modified, as we
        # may not be able to run pre-commit hooks (depends on env setup)
        if py_files := list(filter(lambda p: p.endswith(".py"), modified)):
            msg = f"{repo.working_tree_dir}: python files modified: {py_files}\n"
            msg += "Please commit in the dev environment so that pre-commit hooks can be run."
            console.print(msg)
            ErrorCodes.COMMIT_ERR.exit()

        if added > 0:
            try:
                msg = invoke_editor(repo, next_version)
                if msg == "" or empty_re.match(msg):
                    raise RuntimeError("empty commit message")
            except RuntimeError as err:
                console.print(format_exc(err, "Aborting commit!"))
                ErrorCodes.COMMIT_ERR.exit()
            else:
                repo.index.commit(msg, skip_hooks=True)

        console.print(
            f"Creating tag: {next_version} @ [yellow]{repo.head.commit.hexsha[:7]}"
        )
        try:
            repo.create_tag(next_version)
        except GitCommandError as exc:
            if git_duptag_re.search(exc.stderr):
                if is_circular(CONF["dependency_graph"], pkg):
                    console.print(format_git_cmd_err(exc))
                    ErrorCodes.DUPTAG_ERR.exit()
                else:
                    msg = f"{pkg}@{tag}: skipping duplicate tag, excluded from release"
                    console.print(msg)
                    continue
        else:
            summary[remote_name(repo)] = next_version
    return summary


def make_release(CONF: dict, bump_version: VersionPart, output: Path):
    """Make release tag for all packages, and print a summary."""
    branches = CONF["branches"]
    try:
        check_current_branch(CONF["repos"], branches)
    except RuntimeError as err:
        console.print(format_exc(err, "Aborting!"))
        ErrorCodes.BRANCH_ERR.exit()

    summary = create_tags(CONF, bump_version)
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
        CONF = read_conf(f"{config}")
        make_release(CONF, bump_version, output)

    typer.run(main)
