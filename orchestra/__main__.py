from pathlib import Path
import sys
from typing import Annotated

from packaging.requirements import InvalidRequirement
from rich.console import Console
import typer

from .config import read_conf
from .release import VersionPart, make_release
from .runner import run_xtest

cli = typer.Typer()
console = Console()


def highligh_marks(text: str) -> str:
    newline = text.rfind("\n") + 1  # marks are on the last line
    return text[:newline] + "[red][bold]" + text[newline:]


def path_exists(path: Path) -> Path:
    if not path.exists():
        raise typer.BadParameter(f"'{path}' does not exist.")
    return path


@cli.callback()
def main(ctx: typer.Context):
    """
    Release automation and test orchestration tools for Python projects.
    """


@cli.command()
def release(
    ctx: typer.Context,
    bump_version: Annotated[
        VersionPart,
        typer.Option("--bump", "-b", help="Bump the major, minor, or patch version."),
    ] = "minor",  # type: ignore # FIXME: enum default not working
    output: Annotated[
        Path, typer.Option(help="JSON file to write package tags")
    ] = Path("pkgtags.json"),
    only: Annotated[
        list[str],
        typer.Option(help="Only tag the specified package (repeat for multiple)"),
    ] = [],
    config: Annotated[Path, typer.Option("--conf", "-c", callback=path_exists)] = Path(
        "pyproject.toml"
    ),
):
    """Tag releases for all packages."""
    conf = read_conf(f"{config}")
    make_release(conf, bump_version, output, only)


_xtest_doc_ref = (
    "Reference package version (published to PyPI), "
    "specified as a requirements spec: pkg==<ver>; "
    "used as the reference test suite (repeat for multiple specs)"
)

_xtest_doc_dev = (
    "Development package version (branch/tag in a repo) to test. "
    "(repeat for multiple specs)"
)


@cli.command()
def xtest(
    ctx: typer.Context,
    ref: Annotated[list[str], typer.Option("--ref", "-r", help=_xtest_doc_ref)],
    dev: Annotated[list[str], typer.Option("--dev", "-d", help=_xtest_doc_dev)],
    config: Annotated[Path, typer.Option("--conf", "-c", callback=path_exists)] = Path(
        "pyproject.toml"
    ),
):
    """Test development version of a package/repo against a published version

    Running the test suite for a published version with a development version
    will identify API incompatibility.

    """
    conf = read_conf(f"{config}")
    print(f"{ref=}")
    print(f"{dev=}")
    try:
        run_xtest(conf, ref, dev)
    except InvalidRequirement as err:
        console.print(f"Invalid requirement:\n{highligh_marks(str(err))}")
        sys.exit(1)
    except ValueError as err:
        console.print(f"{type(err).__name__}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
