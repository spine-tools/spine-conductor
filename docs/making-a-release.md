# How to make a release? (with the `scm*` toy example)
Invoke the release command with a config file
```shell
conduct release -c ./path/to/release.toml
```
or configure it in your project's `pyproject.toml`.  Every config
option is expected to be under the `tool.conductor` section.

A typical `release.toml`/`pyproject.toml` looks like this:
```toml
[tool.conductor]
packagename_regex = "sa-[a-z]+"

[tool.conductor.dependency_graph]
sa-foo = ["sa-bar", "sa-baz"]
sa-bar = ["sa-foo", "sa-baz"]
sa-baz = []

[tool.conductor.repos]
sa-foo = "."
sa-bar = "../scm-dep"
sa-baz = "../scm-base"

# # default
# [tool.conductor.branches]
# sa-foo = "master"
# sa-bar = "master"
# sa-baz = "master"
```

# How to make a release of the Spine repositories?
The terminal command is identical as the toy example, however the
configuration for Spine repositories could be as shown below:
```toml
[tool.conductor]
packagename_regex = "spine(toolbox|(db){0,1}[_-][a-z]+)"  # package name on PyPI

[tool.conductor.dependency_graph]
spinetoolbox = ["spine_items", "spine_engine", "spinedb_api"]
spine_items  = ["spinetoolbox", "spine_engine", "spinedb_api"]
spine_engine = ["spinedb_api"]
spinedb_api  = []

[tool.conductor.repos]
spinetoolbox = "."
spine_items  = "venv/src/spine-items"
spine_engine = "venv/src/spine-engine"
spinedb_api  = "venv/src/spinedb-api"

# # default
# [tool.conductor.branches]
# spinetoolbox = "master"
# spine_items  = "master"
# spine_engine = "master"
# spinedb_api  = "master"
```

# How is the next version picked?
By default, the minor version is bumped, but if you want, you can do a
patch/major release by passing `-b patch` or `-b major` to the release
command.

# How to limit the new release to a subset of packages?
You can limit the new releases to a subset of packages by passing a
list like this: `--only sa-foo --only sa-baz` (you have to repeat the
`--only` option for each package).

# How is circular dependency between packages handled?
It is included in the config under the section `dependency_graph`.  It
is equivalent to the following (version agnostic) dictionary:
```python
dependency_graph = {
    "sa-foo": ["sa-bar", "sa-baz"],
    "sa-bar": ["sa-foo", "sa-baz"],
    "sa-baz": [],
}
```

# What is the user experience of making a release commit?
The commit interface is almost identical to command line git usage.
If your environment sets the `EDITOR` variable, it should just work™.
If not, the `conduct release` command tries to find an editor that
works in the terminal depending on your platform, it falls back to in
`vi` (Linux/Mac OS) or `notepad` (Windows).  Basically after adding
any tracked files that were edited, you will need to provide a commit
message for Git (by editing the `.git/COMMIT_EDITMSG` file).

Just like CLI Git, you can cancel a commit in the usual ways: cancel
the edit by terminating your editor with `Ctrl-c`, or provide an empty
commit message.

# Where can I find the toy example packages?
You can find them on Test PyPI
- [`sa-foo`](https://test.pypi.org/project/sa-foo/#history)
- [`sa-bar`](https://test.pypi.org/project/sa-bar/#history)
- [`sa-baz`](https://test.pypi.org/project/sa-baz/#history)

# Testing the release packages before publishing
The publishing workflow runs the test suite on the built wheels before
publishing to PyPI.  This ensures the published wheels work of all
supported platforms.

# How does it look when packages are published from this workflow?
This is an [example
run](https://github.com/suvayu/scm/actions/runs/5256852022) for the
`scm` toy example package.
