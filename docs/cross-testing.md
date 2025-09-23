# Cross testing multiple development versions of packages
To do this, simply run something like this:

```shell
conduct xtest --ref spine-items==0.24.1 --ref spine-engine==0.26.1 \
    --dev spinetoolbox==master --dev spinedb_api==data-transition \
	-c myconfig.toml
```

This will do the following:
1. Clone the repos for `spinetoolbox` and `spinedb_api` as per the
   config file into a directory `$PWD/.repos`.
2. Download the wheels for `spine-items` and `spine-engine` from PyPI.
3. Parse the metadata from the wheels and the `pyproject.toml` files
   in the repositories to extract the 1st order 3rd-party
   dependencies.
4. Create a unique (MD5 hashed) virtual environment using the Spine
   package versions (in `$PWD/.venvs`), and
   1. first install the 3rd-party dependencies
   2. install the Spine package wheels, and the development
      branches/tags without dependencies (`--no-deps`).
5. It then runs the test suites of the development versions separately
   using `pytest`; if `pytest` is not available it fallsback to
   `unittest` from the standard library.

## Remarks
The failed tests should point to incompatibilities between the two
development versions of the packages.  Maybe in the future we can also
analyse the failures and highlight the incompatible modules.

Note that after you make changes to the development versions, you can
simply commit to your normal repo (locally), and rerun `xtest`.  It
will fetch the latest commits from the dev branch to the clones inside
`$PWD/.repos`.

