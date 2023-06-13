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
case, the `setup.py` is simple, so migration should be
straightforward.

# Toy example
The above scheme is implemented in a set of 3 toy repos, where 2 of
them have circular dependency:
- [scm](https://github.com/suvayu/scm) hosts the package `sa-foo`
- [scm-dep](https://github.com/suvayu/scm-dep) hosts the package `sa-bar`
- [scm-base](https://github.com/suvayu/scm-base) hosts the package `sa-baz`
- `sa-foo` and `sa-bar` have a cyclic dependency

Release is done by running the [`tag_release.py`](./tag_release.py)
script.  The main repo (`scm`) has an action to build and publish
wheels and tarballs to PyPI.  At the moment they are platform
independent wheels, but when the need arises switching to platform
dependent wheels should be possible.

## workflow that the release script automates
1. update spine dependencies
2. tag release
3. repeat for all spine packages

# dev build
We can use [`requirements.txt`](./requirements.txt) to setup the dev
environment.  If people like to choose the location of the checked out
repo for all packages, they may modify the URLs.  This is necessary
because editable install for dependencies is not yet supported using
`pyproject.toml`.  Meaning the case when `sa-foo` (the main package)
depends on `sa-bar`, and if I want to have editable install for both.
To cover this case, we choose requirements file methodolody to setup
the dev environment.

*Note:* The requirements file need not list other dependencies as
pyproject.toml includes them.  So this is sufficient:
```
-e ../scm-dep
-e ../scm-base
-e .
```

## version options for dev build
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
## how to make a release?
invoke the release script with a config file
```shell
./tag_release.py -c ./path/to/release.toml
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

## how is the next version picked?
By default, the minor version is bumped, but if you want, you can do a
patch/major release by passing `-b patch` or `-b major` to the release
script.

## how to limit the new release to a subset of packages?
You can limit the new releases to a subset of packages by passing a
list like this: `--only sa-foo sa-baz`

## how is circular dependency between packages handled?
It is included in the config under the section `dependency_graph`.  It
is equivalent to the following (version agnostic) dictionary:
```python
dependency_graph = {
    "sa-foo": ["sa-bar", "sa-baz"],
    "sa-bar": ["sa-foo", "sa-baz"],
    "sa-baz": [],
}
```

## release commit experience
The commit interface is almost identical to command line git usage.
So if you have your `EDITOR` variable setup, it should just work™.  If
not, it defaults to opening the `COMMIT_EDITMSG` file in `vim`.

Just like CLI Git, you can cancel a commit in the usual ways: cancel
the edit, or provide an empty commit message.

## where are the toy packages?
You can find them on Test PyPI
- [`sa-foo`](https://test.pypi.org/project/sa-foo/#history)
- [`sa-bar`](https://test.pypi.org/project/sa-bar/#history)
- [`sa-baz`](https://test.pypi.org/project/sa-baz/#history)

## testing the release packages before publishing
We should also consider running the test suite on the built wheels
before publishing.

## how does it look when packages are published from this workflow?
This is an [example
run](https://github.com/suvayu/scm/actions/runs/5256852022) for the
`scm` package.
