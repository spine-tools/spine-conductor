import json
from pathlib import Path
import shlex
import subprocess

from git import Repo
from rich.console import Console
from rich.prompt import Prompt

from orchestra.config import CONF
from orchestra.release import remote_name

CMD_FMT = "gh workflow run --json --repo {repo} {workflow}"

console = Console()


def push_tags(repo: Repo, tag: str):
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
                console.print(f"invalid selection: {response}, selecting first")
                remote = repo.remotes[0]
        else:
            console.print("empty response, selecting first")
            remote = repo.remotes[0]
    else:
        remote = repo.remotes[0]
    res = remote.push(tag)
    # FIXME: not sure if this is the best way to check for errors
    if len(res) == 0:
        console.print(f"pushing {tag!r} failed")
        res.raise_if_error()
    errs = [err for err in res if err.flags & err.ERROR]
    if len(errs) > 0:
        console.print(f"pushing {tag!r} failed partially")
        for err in errs:
            console.print(err.summary)


def dispatch_workflow(pkgtags_json: Path, **kwargs):
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
    except subprocess.CalledProcessError as exc:
        return exc
    except FileNotFoundError as exc:
        return exc
    return res


def publish_tags_whls(config: dict, pkgtags: Path):
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
    for _, repo_path in config["repos"].items():
        repo = Repo(repo_path)
        push_tags(repo, tags[remote_name(repo)])
    res = dispatch_workflow(pkgtags)
    if isinstance(res, subprocess.CalledProcessError):
        console.print(res.stderr.decode())
        return
    elif isinstance(res, FileNotFoundError):
        console.print(f"{res.filename!r} missing, did you install GitHub CLI?")
        return
    console.print(res.stdout.decode())
