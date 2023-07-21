import re
import sys

import tomlkit

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


def read_toml(path: str) -> dict:
    with open(path, mode="r") as toml_file:
        return tomlkit.load(toml_file)


def write_toml(data: dict, path: str):
    with open(path, mode="w") as toml_file:
        tomlkit.dump(data, toml_file)


def read_conf(path: str) -> dict:
    global CONF
    config = read_toml(path)
    if "tool" in config and "conductor" in config["tool"]:
        config = config["tool"]["conductor"]
    else:
        sys.exit(f"No `tool.conductor` section found in {path!r}.")

    # check mandatory sections
    if "packagename_regex" not in config:
        sys.exit(f"No `tool.conductor.packagename_regex` section found in {path!r}.")
    if "repos" not in config:
        sys.exit(f"No `tool.conductor.repos` section found in {path!r}.")
    if "dependency_graph" not in config:
        sys.exit(f"No `tool.conductor.dependency_graph` section found in {path!r}.")

    CONF.update(config)
    CONF["pkgname_re"] = re.compile(config["packagename_regex"])

    branches_default = {pkg: CONF["default_branch"] for pkg in CONF["dependency_graph"]}
    branches = CONF["branches"] if "branches" in CONF else {}
    CONF["branches"].update({**branches_default, **branches})

    return CONF
