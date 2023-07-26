import pytest

from orchestra.runner import opts_to_flags


@pytest.mark.parametrize(
    "k, v, res",
    [
        ("output", "json", "--output=json"),
        ("start_dir", "dir", "--start-dir=dir"),
        ("s", "dir", "-s dir"),
        ("args", [1, 2, 3], "--args 1 2 3"),
        ("a", [1, 2, 3], "-a 1 2 3"),
        ("s", "", "-s "),
        ("f", True, "-f"),
        ("force", True, "--force"),
        ("f", False, "--no-f"),
        ("force", False, "--no-force"),
    ],
)
def test_match_pairs(k, v, res):
    assert opts_to_flags(k, v) == res
