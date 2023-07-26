# About `spine-conductor`

It is a collection of release orchestration scripts, and CI workflows
to simplify release of Spine packages.

# Usage

Example session:
1. create the release tags
   ```shell
   $ cd /path/to/repo/Spine-Toolbox
   $ conduct release --bump patch
   Repository: /path/to/repo/Spine-Toolbox
   ## master...origin/master
    M pyproject.toml (1)
   Select the files to add (comma/space separated list): 1
   Creating tag: 0.7.2
   Repository: /path/to/repo/Spine-Toolbox/venv/src/spine-items
   ## master...origin/master
    M pyproject.toml (1)
   Select the files to add (comma/space separated list):
   Creating tag: 0.2.3
   Repository: /path/to/repo/Spine-Toolbox/venv/src/spine-engine
   ## master...origin/master
   Select the files to add (comma/space separated list):
   Creating tag: 0.3.1
   Repository: /path/to/repo/Spine-Toolbox/venv/src/spinedb-api
   ## master...origin/master
   Select the files to add (comma/space separated list):
   Creating tag: 0.2.1
   Package Tags summary 💾 ➡ pkgtags.json:
   {
       "Spine-Toolbox": "0.7.2",
       "spine-items": "0.2.3",
       "spine-engine": "0.3.1"
       "Spine-Database-API": "0.2.1",
   }
   ```
2. push the tags to GitHub
   ```shell
   for repo in . venv/src/spine{-items,-engine,db-api}; do
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
packagename_regex = "spine(toolbox|(db){0,1}_[a-z]+)"  # package name on PyPI

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
