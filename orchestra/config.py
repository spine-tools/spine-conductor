import sys

import tomlkit


def read_toml(path: str) -> dict:
    with open(path, mode="r") as toml_file:
        return tomlkit.load(toml_file)


def write_toml(data: dict, path: str):
    with open(path, mode="w") as toml_file:
        tomlkit.dump(data, toml_file)


def read_conf(path: str) -> dict:
    config = read_toml(path)
    if "tool" in config and "conductor" in config["tool"]:
        return config["tool"]["conductor"]
    else:
        sys.exit(f"No `tool.conductor` section found in {path!r}.")
