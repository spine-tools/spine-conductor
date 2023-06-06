# Rationale & Design
The current release process has manual steps.  Mostly
- to manage the version information, and
- to ensure the consistency of the dependency requirements with other Spine packages

So I propose the following workflow:
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

# Toy implementation
I implement the above scheme in a set of 3 toy repos, where 2 of them
have circular dependency:
- [scm](https://github.com/suvayu/scm) hosts the package `sa-foo`
- [scm-dep](https://github.com/suvayu/scm-dep) hosts the package `sa-bar`
- [scm-base](https://github.com/suvayu/scm-base) hosts the package `sa-baz`
- `sa-foo` and `sa-bar` have a cyclic dependency

Release is done by running the [`tag_release.py`](./tag_release.py)
script.  And each repo has its own action to build and publish wheels
and tarballs to PyPI.  At the moment they are platform independent
wheels, but when the need arises switching to platform dependent
wheels should be possible.

## workflow that the release script automates
1. update spine dependencies
2. tag release
3. repeat for all spine packages

# dev build
We can use [`requirements.txt`](./requirements.txt) to setup the dev
environment.  If people like to choose the location of the checked out
repo for all packages, they may modify the URLs.  This is necessary
because editable install for dependencies is not yet supported using
`pyproject.toml`.  Meaning, `sa-foo` (this package) depends on
`sa-bar`, and if I want to have editable install for both.  To cover
this case, we choose the above methodolody to setup the dev
environment.

*Note:* We can actually simplify this further by only listing our
packages in the requirements file, and relying on pyproject.toml to
deal with external dependencies.  Something like this:
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
- `release-branch-semver`: forward-looking (I chose this)
- `post-release`: clear and concise

# Q&A
## how to make a release?
invoke the release script with a config file
```shell
./tag_release.py ./path/to/release.toml
```

A typical `release.toml` looks like this:
```toml
[repos]
sa-foo = "."
sa-bar = "../scm-dep"
sa-baz = "../scm-base"

# # default
# [branches]
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
It is hardcoded into the release script using the following
(version agnostic) dictionary:
```python
dependency_graph = {
    "sa-foo": ["sa-bar", "sa-baz"],
    "sa-bar": ["sa-foo", "sa-baz"],
    "sa-baz": [],
}
```

## commit experience
The commit interface is almost identical to command line git usage.
So if you have your `EDITOR` variable setup, it should just work™.  If
not, it defaults to opening the `COMMIT_EDITMSG` file in `vim`.

Just like CLI Git, you can cancel a commit in the usual ways: cancel
the edit, or provide an empty commit message.

## possible bugs
I think the logic to skip a release commit when there are no new
commits is buggy.

## where are the packages on Test PyPI?
- [`sa-foo`](https://test.pypi.org/project/sa-foo/#history)
- [`sa-bar`](https://test.pypi.org/project/sa-bar/#history)
- [`sa-baz`](https://test.pypi.org/project/sa-baz/#history)
