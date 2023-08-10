# Rationale & Design
The current release process has manual steps.  Mostly
- to manage the version information, and
- to ensure the consistency of the dependency requirements with other Spine packages

Address the above with the following workflow:
1. use [`setuptools_scm`](https://github.com/pypa/setuptools_scm/) to
   manage versions dynamically using git tags
2. use a release tagging script to generate the next version number,
   update the dependency requirements, and create the git tag
3. push the tags to github, and publish the packages to pypi using
   github actions

For the tagging script to work, the build system of all the projects
should be similar.  Since it requires automatic updates, I chose
`pyproject.toml` as the library to r/w toml is quite mature, and both
`setup.py` and `setup.cfg` are now deprecated.  The current spine
packages mostly use `setup.cfg` except Spine Engine.  But even in that
case, the `setup.py` is simple, so migration is straightforward.

# Toy example
The above scheme is implemented in a set of 3 toy repos, where 2 of
them have circular dependency:
- [scm](https://github.com/suvayu/scm) hosts the package `sa-foo`
- [scm-dep](https://github.com/suvayu/scm-dep) hosts the package `sa-bar`
- [scm-base](https://github.com/suvayu/scm-base) hosts the package `sa-baz`
- `sa-foo` and `sa-bar` have a cyclic dependency

Release is done by running [`conduct release`](./orchestra/release.py).
The primary repo (`scm`) has an action to build and publish
wheels and tarballs to TestPyPI.  At the moment they are platform
independent wheels, but when the need arises switching to platform
dependent wheels should be possible (e.g. by using [`cibuildwheel`](https://cibuildwheel.readthedocs.io/en/stable/)).

# Supporting developer build
We can use [`requirements.txt`](./requirements.txt) to setup the dev
environment.  If people like to choose the location of the checked out
repo for all packages, they may modify the URLs.  This is necessary
because editable install for dependencies is not yet supported using
`pyproject.toml`; i.e. the case when `sa-foo` (the primary package)
depends on `sa-bar`, and you want to have editable install for both.
To cover this case, we choose requirements file to setup the dev
environment.

*Note:* The requirements file need not list other dependencies as
pyproject.toml includes them.  So this is sufficient:
```
-e ../scm-dep
-e ../scm-base
-e .
```

## Version options for dev build
The version information is derived from the repo history, the choice
are the following (latest existing tag is **0.3.1**):
```python
>>> from setuptools_scm import get_version
>>> get_version(version_scheme="python-simplified-semver")
'0.3.2.dev1+gbfb07af'
>>> get_version(version_scheme="release-branch-semver")
'0.4.0.dev1+gbfb07af'
>>> get_version(version_scheme="guess-next-dev")
'0.3.2.dev1+gbfb07af'
>>> get_version(version_scheme="no-guess-dev")
'0.3.1.post1.dev1+gbfb07af'
>>> get_version(version_scheme="post-release")
'0.3.1.post1+gbfb07af'
```

Preference:
- `release-branch-semver`: forward-looking (current choice)
- `post-release`: clear and concise

# Q&A
## How to make a release? (with the toy example)
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

## How to make a release of the Spine repositories?
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

## How is the next version picked?
By default, the minor version is bumped, but if you want, you can do a
patch/major release by passing `-b patch` or `-b major` to the release
command.

## How to limit the new release to a subset of packages?
You can limit the new releases to a subset of packages by passing a
list like this: `--only sa-foo --only sa-baz` (you have to repeat the
`--only` option for each package).

## How is circular dependency between packages handled?
It is included in the config under the section `dependency_graph`.  It
is equivalent to the following (version agnostic) dictionary:
```python
dependency_graph = {
    "sa-foo": ["sa-bar", "sa-baz"],
    "sa-bar": ["sa-foo", "sa-baz"],
    "sa-baz": [],
}
```

## What is the user experience of making a release commit?
The commit interface is almost identical to command line git usage.
If your environment sets the `EDITOR` variable, it should just work™.
If not, the `conduct release` command tries to find an editor that
works in the terminal depending on your platform, it falls back to in
`vi` (Linux/Mac OS) or `notepad` (Windows).  Basically after adding
any edited files, you will need to provide a commit message for Git
(by editing the `.git/COMMIT_EDITMSG` file).

Just like CLI Git, you can cancel a commit in the usual ways: cancel
the edit by terminating your editor with `Ctrl-c`, or provide an empty
commit message.

## Where are the toy packages?
You can find them on Test PyPI
- [`sa-foo`](https://test.pypi.org/project/sa-foo/#history)
- [`sa-bar`](https://test.pypi.org/project/sa-bar/#history)
- [`sa-baz`](https://test.pypi.org/project/sa-baz/#history)

## Testing the release packages before publishing (WIP)
The publishing workflow runs the test suite on the built wheels before
publishing to PyPI.

## How does it look when packages are published from this workflow?
This is an [example
run](https://github.com/suvayu/scm/actions/runs/5256852022) for the
`scm` package.
