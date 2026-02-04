from email.parser import Parser as MetadataParser
from enum import Enum
from pathlib import Path
import re
from typing import Literal

from packaging.requirements import Requirement
from packaging.version import Version
from pypi_simple import PyPISimple, ACCEPT_JSON_ONLY, DistributionPackage
from wheel.wheelfile import WheelFile

from .config import read_toml
from .release import version_parse_no_except

version_specifier = re.compile("[<>]=?|==|~=")


class Key(Enum):
    time = "time"
    day = "day"
    week = "week"
    month = "month"


def by_(key: Key = Key.time):
    """Sort key for `DistributionPackage`

    Parameters
    ----------
    key : Key, optional
        Sort key, by default Key.time

    Returns
    -------
    Callable
        Sort key function
    """
    if key == Key.time:
        return lambda pkg: pkg.upload_time
    elif key == Key.day:
        return lambda pkg: (
            pkg.upload_time.year,
            pkg.upload_time.month,
            pkg.upload_time.day,
        )
    elif key == Key.week:
        return lambda pkg: (
            pkg.upload_time.year,
            pkg.upload_time.month,
            pkg.upload_time.isocalendar().week,
        )
    elif key == Key.month:
        return lambda pkg: (
            pkg.upload_time.year,
            pkg.upload_time.month,
        )


class Rel_t(Enum):
    dev = (True, False)
    pre = (False, True)
    rel = (False, False)

    def __eq__(self, version) -> bool:
        if isinstance(version, Version):
            return self.value == (version.is_devrelease, version.is_prerelease)
        return super().__eq__(version)


def pkgs_meta(
    pkgname: str,
    cutoff: int = 2022,
    pkg_type: Literal["wheel", "source"] = "wheel",
    rel_type: Rel_t = Rel_t.rel,
) -> list[DistributionPackage]:
    """Get metadata of all published packages in a project from PyPI

    Parameters
    ----------
    pkgname : str
        Project name
    cutoff : int, optional
        Cutoff year until which packages are considered, by default 2022
    pkg_type : Literal["wheel", "source"], optional
        Package type, by default "wheel"
    rel_type : Rel_t, optional
        Release type, by default Rel_t.rel (release)

    Returns
    -------
    list[DistributionPackage]
        List of package metadata
    """

    def selection(pkg):
        if version := version_parse_no_except(pkg.version):
            return (
                pkg.package_type == pkg_type
                and pkg.upload_time.year >= cutoff
                and rel_type == version
            )
        return False

    with PyPISimple() as pypi:
        # NOTE: without `accept=...`, pkg.upload_time is not always set
        project = pypi.get_project_page(pkgname, accept=ACCEPT_JSON_ONLY)
        # TODO: cache project
        releases = filter(selection, project.packages)
        return sorted(releases, key=by_(Key.time), reverse=True)


def pkg_find(
    requirement_spec: str,
    cutoff: int = 2022,
    pkg_type: Literal["wheel", "source"] = "wheel",
    rel_type: Rel_t = Rel_t.rel,
) -> DistributionPackage:
    """Find a package that matches the requirement

    Parameters
    ----------
    requirement_spec : str
        Requirement specifier; e.g. mypkg==<V.E.R>
    cutoff : int, optional
        Cutoff year until which packages are considered, by default 2022
    pkg_type : Literal["wheel", "source"], optional
        Package type, by default "wheel"
    rel_type : Rel_t, optional
        Release type, by default Rel_t.rel (release)

    Returns
    -------
    DistributionPackage
        Package metadata
    """
    req = Requirement(requirement_spec)

    def version_match(pkg):
        if version := pkg.version:
            return version in req.specifier
        return False

    pkg, *_ = filter(version_match, pkgs_meta(req.name, cutoff, pkg_type, rel_type))
    return pkg


def pkg_download(pkg: DistributionPackage, outdir: str, force: bool = False) -> Path:
    """Download a package from PyPI

    Parameters
    ----------
    pkg : DistributionPackage
        Package metadata
    outdir : str
        Output directory
    force : bool, optional
        Force download, by default False

    Returns
    -------
    Path
        Path to the downloaded package
    """
    with PyPISimple() as pypi:
        wheel = Path(outdir) / pkg.filename
        if not force and wheel.exists():
            return wheel
        # TODO: tqdm progress bar
        pypi.download_package(pkg, path=wheel)
        return wheel


def requirements_from_whl(path: str | Path) -> list[Requirement]:
    """Get dependency requirements from a wheel file

    Parameters
    ----------
    path : str | Path
        Path to the wheel file

    Returns
    -------
    list[Requirement]
        List of requirements
    """
    with WheelFile(path) as whl:
        with whl.open(f"{whl.dist_info_path}/METADATA") as fp:
            # FIXME: move to packaging.metadata.parse_email, requires: packaging>=23.1
            metadata = MetadataParser().parsestr(fp.read().decode("utf8"))
            res = list(map(Requirement, metadata.get_all("Requires-Dist", [])))
    return res


def requirements_from_pyproject(
    proj_path: str | Path, include_dev: bool = True
) -> list[Requirement]:
    proj_path = Path(proj_path)
    file_path = proj_path / "pyproject.toml"
    proj = read_toml(f"{file_path}")
    deps = proj["project"].get("dependencies", [])

    if include_dev and (dev_req := proj_path / "dev-requirements.txt").exists():
        deps += list(filter(None, dev_req.read_text().split("\n")))

    return list(map(Requirement, deps))
