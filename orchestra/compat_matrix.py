from collections import Counter
from collections import deque
from itertools import chain
from itertools import dropwhile
from itertools import islice
from itertools import product
from itertools import takewhile
from itertools import tee
import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable
from typing import Iterable
from typing import TypeVar

from pypi_simple import DistributionPackage
from rich.console import Console

from .pkgindex import Key
from .pkgindex import by_
from .pkgindex import pkgs_meta
from .runner import fmt_subprocess_results
from .runner import run_xtest
from .runner import tail_proc_outout

console = Console()


# source: from itertools python docs
def sliding_window(iterable, n):
    "Collect data into overlapping fixed-length chunks or blocks."
    # sliding_window('ABCDEFG', 3) → ABC BCD CDE DEF EFG
    iterator = iter(iterable)
    window = deque(islice(iterator, n - 1), maxlen=n)
    for x in iterator:
        window.append(x)
        yield tuple(window)


T = TypeVar("T")


def fork(predicate: Callable[[T], bool], itr: Iterable[T]) -> tuple[list[T], list[T]]:
    """Split an iterable based on a predicate."""
    seq1, seq2 = tee(itr)
    part1, part2 = takewhile(predicate, seq1), dropwhile(predicate, seq2)
    return list(part1), list(part2)


def pkg_compat_range(
    primary: str, pkg_names: list[str], cutoff: int = 2025
) -> list[list[tuple[DistributionPackage, ...]]]:
    """Generate package versions to test by date proximity."""
    by_date = by_(Key.day)

    def in_range(pkg_newer, pkg, pkg_older):
        return by_date(pkg_newer) >= by_date(pkg) >= by_date(pkg_older)

    all_vers = [pkgs_meta(name, cutoff) for name in pkg_names]
    # NOTE: only 1 package name will match
    (primary_vs, *_), rest_vs = fork(lambda v: v[0].project == primary, all_vers)

    version_tuples = [
        list(
            product(
                [p1],
                *(
                    list(filter(lambda p: in_range(p1, p, p2), _vers))
                    for _vers in rest_vs
                ),
            )
        )
        for p1, p2 in sliding_window(primary_vs, 2)
    ]
    return [i for i in version_tuples if len(i)]


def count_test_outcomes(file_path: str | Path) -> dict[str, int]:
    """Count occurrences of each outcome value across multiple line-delimited JSON files."""
    outcomes = []

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "outcome" not in record:
                continue
            if record.get("when") != "call":
                continue
            if not record.get("nodeid"):
                continue
            outcomes.append(record["outcome"])

    return dict(Counter(outcomes))


def run_test_batches(
    config: dict,
    primary: str,
    dep_pkg_names: list[str],
    *batches: list[tuple[DistributionPackage, ...]],
):
    try:
        proj_path = config["repos"][primary]
    except KeyError:
        raise ValueError(
            f"{primary}: project not defined in repos={list(config['repos'])}"
        )

    specs: list[tuple[str, ...]] = []
    results: list[CompletedProcess] = []
    stats: list[dict[str, int]] = []
    for i, row in enumerate(chain.from_iterable(batches)):
        _vers = [f"{p.project}=={p.version}" for p in row]
        spec = tuple(f"{p.project}=={p.version}" for p in row)
        # only 1 entry in dev=specs[:1] => 1 test result/run
        try:
            log = f"report-{i:02}.jsonl"
            # FIXME: split depends on magic info
            _ret, *_ = run_xtest(config, spec[1:], spec[:1], report_log=log).values()
        except ValueError as err:
            console.print(f"error: {_vers}: {err}")
            continue
        else:
            specs.append(spec)
            results.append(_ret)
            stats.append(count_test_outcomes(log))

        # for user feedback
        console.print(tail_proc_outout(_ret))

    return specs, results, stats


def gen_compat_matrix(config: dict, primary: str, report=False):
    pkg_names: list[str] = list(config["repos"])
    version_tuples = pkg_compat_range(primary, pkg_names, 2025)
    pkg_names.pop(pkg_names.index(primary))
    specs, results, stats = run_test_batches(
        config, primary, pkg_names, *version_tuples[:4]
    )
    tbl, errors = fmt_subprocess_results(specs, results, stats)
    console.print(f"{errors} errors/failures")
    if report:
        console.print(tbl)
    return results


if __name__ == "__main__":
    from typing import Annotated

    import typer

    from .config import read_conf

    def main(
        primary: Annotated[
            str,
            typer.Option("--primary", "-p", help="Name of the primary package"),
        ] = "spinetoolbox",
        config: Annotated[
            Path, typer.Option("--config", "-c", help="TOML config file")
        ] = Path("pyproject.toml"),
    ):
        conf = read_conf(f"{config}")
        gen_compat_matrix(conf, primary, report=True)

    typer.run(main)
