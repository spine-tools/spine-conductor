import json
from pathlib import Path
import shlex
import subprocess

from git import GitCommandError, Repo
from git.remote import PushInfoList
from rich.console import Console
from rich.prompt import Prompt

from orchestra import ErrorCodes, format_git_cmd_err
from orchestra.release import remote_name

CMD_FMT = "gh workflow run --json --repo {repo} {workflow}"

console = Console()


def git_error_handler(res: PushInfoList, err: ErrorCodes, msg: str):
    try:
        res.raise_if_error()
    except GitCommandError as exc:
        console.print(f"pushing {msg} failed!")
        console.print(format_git_cmd_err(exc))
        err.exit()
    else:
        console.print(f"pushed {msg}")


def push_tags(CONF: dict, pkg: str, repo: Repo, tag: str):
    if len(repo.remotes) > 1:
        console.print(
            *(
                f" [{idx}] [red]{remote.name}[/red]: {remote.url}"
                for idx, remote in enumerate(repo.remotes)
            ),
            sep="\n",
        )
        if response := Prompt.ask("Select remote to push tags"):
            try:
                remote = repo.remotes[int(response)]
            except ValueError:
                console.print(f"invalid selection: {response}, aborting!")
                ErrorCodes.USERINPUT_ERR.exit()
                return  # for pyright
        else:
            console.print("empty response, aborting!")
            ErrorCodes.USERINPUT_ERR.exit()
            return  # for pyright
    else:
        remote = repo.remotes[0]
    ref = CONF["branches"][pkg]
    res = remote.push(refspec=ref)
    git_error_handler(res, ErrorCodes.REMOTE_ERR, f"{ref=} -> {remote.name!r}")

    res = remote.push(tags=True)
    git_error_handler(res, ErrorCodes.DUPTAG_ERR, f"{tag=} -> {remote.name!r}")


def dispatch_workflow(CONF: dict, pkgtags_json: Path, **kwargs):
    """Dispatch workflow to build and publish packages

    Parameters
    ----------
    pkgtags_json : Path
        Path to the JSON file containing the package tags
    """
    if _ := kwargs.pop("shell", None):
        console.print("disallow shell=True, as it suppresses output")

    ghrepo = CONF["workflow"]["repo"]
    workflow = CONF["workflow"]["file"]
    CMD = CMD_FMT.format(repo=ghrepo, workflow=workflow)
    try:
        res = subprocess.run(
            shlex.split(CMD),
            input=pkgtags_json.read_bytes(),
            check=True,
            capture_output=True,
            **kwargs,
        )
    except FileNotFoundError as exc:
        console.print(f"{exc.filename!r} missing, did you install GitHub CLI?")
        return exc
    except subprocess.CalledProcessError as exc:
        console.print("failed to trigger workflow with GitHub CLI:")
        console.print(exc.stderr.decode())
        return exc
    else:
        console.print(res.stdout.decode())
    return res


def publish_tags_whls(CONF: dict, pkgtags: Path):
    """Publish packages to PyPI

    Push Git tags to GitHub and trigger a workflow to build the
    packages and publish to PyPI.

    Parameters
    ----------
    config : dict
        Configuration from release.toml/pyproject.toml

    pkgtags : Path
        Path to the JSON file containing the package tags
    """
    tags = json.loads(pkgtags.read_text())
    for pkg, repo_path in CONF["repos"].items():
        if pkg not in tags:
            continue
        repo = Repo(repo_path)
        push_tags(CONF, pkg, repo, tags[remote_name(repo)])
    return dispatch_workflow(CONF, pkgtags)
