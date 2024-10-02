from copy import deepcopy
import re
from typing import Any

from click.exceptions import BadArgumentUsage
from rich.console import Console
import tomlkit

from orchestra import ErrorCodes, format_exc

# fmt: off
_CONF: dict[str, Any] = {
    "packagename_regex": "",    # in file
    "pkgname_re": None,         # in memory, re.Pattern[str], constructed from above
    "repos": {},                # from file
    "dependency_graph": {},     # from file
    "default_branch": "master", # default, only here
    "branches": {},             # from file, if absent, filled in using default_branch
}
# fmt: on

console = Console()


def read_toml(path: str) -> dict:
    with open(path, mode="r", newline="") as toml_file:
        return tomlkit.load(toml_file)


def write_toml(data: dict, path: str):
    with open(path, mode="w", newline="") as toml_file:
        tomlkit.dump(data, toml_file)


def check_pkgnames(CONF: dict[str, Any], key: str) -> str:
    """Check if all package names in a section are valid."""
    msg = f"[b]Unknown package names in 'tool.conductor.{key}': {{}}"
    unk = [pkg for pkg in CONF[key] if not CONF["pkgname_re"].match(pkg)]
    return msg.format(f"{', '.join(unk)}") if len(unk) > 0 else ""


def read_conf(path: str, /, only: list[str] = [], exclude: list[str] = []) -> dict:
    CONF = deepcopy(_CONF)
    config = read_toml(path)
    if "tool" in config and "conductor" in config["tool"]:
        config = config["tool"]["conductor"]
    else:
        console.print(f"[b]Missing section 'tool.conductor' in {path!r}.")
        ErrorCodes.CONFIG_ERR.exit()

    # check mandatory sections
    msg = f"[b]Missing config 'tool.conductor.{{}}' in {path!r}."
    if "packagename_regex" not in config:
        console.print(msg.format("packagename_regex"))
        ErrorCodes.CONFIG_ERR.exit()
    if "repos" not in config:
        console.print(msg.format("repos"))
        ErrorCodes.CONFIG_ERR.exit()
    if "dependency_graph" not in config:
        console.print(msg.format("dependency_graph"))
        ErrorCodes.CONFIG_ERR.exit()

    CONF.update(config)
    try:
        CONF["pkgname_re"] = re.compile(config["packagename_regex"])
    except re.error as err:
        prelude = "Invalid 'packagename_regex'"
        regex = config["packagename_regex"]
        pos = err.pos if err.pos else 0
        annotation = " " * (len(prelude) + 3 + pos) + "[b][cyan]^"
        console.print(format_exc(err, f"{prelude}: {regex!r}\n{annotation}"))
        ErrorCodes.CONFIG_ERR.exit()

    # check package name errors in all relevant sections
    error_count = 0
    for key in [("repos"), ("branches"), ("dependency_graph")]:
        if msg := check_pkgnames(CONF, key):
            console.print(msg)
            error_count += 1
    if error_count > 0:
        ErrorCodes.CONFIG_ERR.exit()

    branches_default = {pkg: CONF["default_branch"] for pkg in CONF["repos"]}
    branches = CONF["branches"] if "branches" in CONF else {}
    CONF["branches"].update({**branches_default, **branches})

    if only and exclude:
        raise BadArgumentUsage("`--only` and `--exclude` are mutually exclusive")
    elif exclude:
        only = [pkg for pkg in config["repos"].keys() if pkg not in exclude]

    if len(only) > 0:
        CONF["repos"] = {pkg: CONF["repos"][pkg] for pkg in only}
        branches = {
            pkg: branch for pkg, branch in CONF["branches"].items() if pkg in only
        }
        CONF["branches"] = branches

    return CONF
