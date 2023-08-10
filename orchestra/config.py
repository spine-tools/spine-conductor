import re
import sys

from rich.console import Console
import tomlkit

from orchestra import ErrorCodes, format_exc

# fmt: off
CONF = {
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
    with open(path, mode="w") as toml_file:
        tomlkit.dump(data, toml_file)


def check_pkgnames(key: str) -> str:
    """Check if all package names in a section are valid."""
    msg = f"[b]Unknown package names in 'tool.conductor.{key}': {{}}"
    unk = [pkg for pkg in CONF[key] if not CONF["pkgname_re"].match(pkg)]
    return msg.format(f"{', '.join(unk)}") if len(unk) > 0 else ""


def read_conf(path: str) -> dict:
    global CONF
    config = read_toml(path)
    if "tool" in config and "conductor" in config["tool"]:
        config = config["tool"]["conductor"]
    else:
        console.print(f"[b]Missing section 'tool.conductor' in {path!r}.")
        sys.exit(ErrorCodes.CONFIG_ERR)

    # check mandatory sections
    msg = f"[b]Missing config 'tool.conductor.{{}}' in {path!r}."
    if "packagename_regex" not in config:
        console.print(msg.format("packagename_regex"))
        sys.exit(ErrorCodes.CONFIG_ERR)
    if "repos" not in config:
        console.print(msg.format("repos"))
        sys.exit(ErrorCodes.CONFIG_ERR)
    if "dependency_graph" not in config:
        console.print(msg.format("dependency_graph"))
        sys.exit(ErrorCodes.CONFIG_ERR)

    CONF.update(config)
    try:
        CONF["pkgname_re"] = re.compile(config["packagename_regex"])
    except re.error as err:
        prelude = "Invalid 'packagename_regex'"
        regex = config["packagename_regex"]
        pos = err.pos if err.pos else 0
        annotation = " " * (len(prelude) + 3 + pos) + "[b][cyan]^"
        console.print(format_exc(err, f"{prelude}: {regex!r}\n{annotation}"))
        sys.exit(ErrorCodes.CONFIG_ERR)

    # check package name errors in all relevant sections
    error_count = 0
    for key in [("repos"), ("branches"), ("dependency_graph")]:
        if msg := check_pkgnames(key):
            console.print(msg)
            error_count += 1
    if error_count > 0:
        sys.exit(ErrorCodes.CONFIG_ERR)

    branches_default = {pkg: CONF["default_branch"] for pkg in CONF["repos"]}
    branches = CONF["branches"] if "branches" in CONF else {}
    CONF["branches"].update({**branches_default, **branches})

    return CONF
