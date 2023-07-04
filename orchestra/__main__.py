from pathlib import Path

import typer
from typing_extensions import Annotated

from .config import read_conf
from .release import VersionPart, make_release

cli = typer.Typer()


def path_exists(path: Path) -> Path:
    if not path.exists():
        raise typer.BadParameter(f"'{path}' does not exist.")
    return path


@cli.callback()
def main(ctx: typer.Context):
    """
    Release and test orchestration tools for Python projects.
    """


@cli.command()
def release(
    ctx: typer.Context,
    bump_version: Annotated[
        VersionPart, typer.Option(help="Bump the major, minor, or patch version.")
    ] = VersionPart.minor,
    output: Annotated[
        Path, typer.Option(help="JSON file to write package tags")
    ] = Path("pkgtags.json"),
    only: Annotated[
        list[str], typer.Option(help="Only tag the specified packages")
    ] = [],
    config: Annotated[Path, typer.Option(callback=path_exists)] = Path(
        "pyproject.toml"
    ),
):
    """Tag releases for all packages."""
    conf = read_conf(f"{config}")
    make_release(conf, bump_version, output, only)


if __name__ == "__main__":
    cli()
