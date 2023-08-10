# About `spine-conductor`

It is a collection of release orchestration & automation scripts, and
CI workflows to simplify Spine tool development tasks.

# Usage

Example session:
1. create the release tags
   ```shell
   $ cd /path/to/repo/Spine-Toolbox
   $ conduct release --bump patch -c release.toml  # or include in pyproject.toml
   Repository: /path/to/repo/Spine-Toolbox
   ## master...origin/master
    M pyproject.toml (1)
   Select the files to add (comma/space separated list): 1
   Creating tag: 0.6.19 @ 034fb4b
   Repository: /path/to/repo/spine-items
   ## master...origin/master
    M pyproject.toml (1)
   Select the files to add (comma/space separated list): 1
   Creating tag: 0.20.1 @ 5848e25
   Repository: /path/to/repo/spine-engine
   ## master...origin/master
    M pyproject.toml (1)
   Select the files to add (comma/space separated list): 1
   Creating tag: 0.22.1 @ e312db2
   Repository: /path/to/repo/Spine-Database-API
   ## master...origin/master
   Select the files to add (comma/space separated list):
   Creating tag: 0.29.1 @ d9ed86e

   Package Tags summary  💾 ➡ 'pkgtags.json':
   {
     "Spine-Toolbox": "0.6.19",
     "spine-items": "0.20.1",
     "spine-engine": "0.22.1",
     "Spine-Database-API": "0.29.1"
   }
   ```
2. push the tags to GitHub
   ```shell
   for repo in . /path/to/repo/{Spine-Database-API,spine-{items,engine}}; do
       pushd $repo;
       git push origin master --tags;
       popd
   done
   ```
3. trigger the workflow
   ```shell
   $ cat pkgtags.json | gh workflow run --repo spine-tools/spine-conductor test-n-publish.yml --json
   ```

   You can also trigger the workflow from GitHub.  You will have to
   add the tags manually in that case.

# Configuration

The release tagging script is configured in TOML format as shown below:
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

It can be included in `pyproject.toml`, or kept in a separate config
file.  In the latter case, it needs to be provided with the
`-c`/`--config` option when calling the release tagging script.

## Publishing to PyPI

We use the [Trusted
Publishers](https://docs.pypi.org/trusted-publishers/) feature for
releasing to PyPI.  First we have to add this repo as the source for
releases.  Following which, we can trigger the workflow manually or
using [GitHub CLI](https://cli.github.com/).

The release tagging script writes a file called `pkgtags.json` in the
current directory.  It lists the repos that were tagged, along with
the tags.  This can be fed to GitHub CLI to initiate publishing.
```shell
$ cat pkgtags.json | gh workflow run --repo spine-tools/spine-conductor test-n-publish.yml --json
```

The packages may also be publised by triggering the workflow manually
from GitHub.  In that case, the release tags for the different Spine
repos have to be entered manually.

![Screenshot of the GH UI to do manual dispatch](./gh-workflow-dispatch.png "Manual dispatch menu on GH Actions")
