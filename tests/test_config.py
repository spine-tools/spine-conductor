from pathlib import Path

from click.exceptions import BadArgumentUsage
import pytest

from orchestra.config import read_conf


@pytest.mark.parametrize("pkg", ["sa-bar", "sa-foo"])
def test_read_conf(pkg):
    conf_file = Path(__file__).parent / "scm.toml"

    conf = read_conf(f"{conf_file}", only=[pkg])
    assert list(conf["repos"]) == [pkg]
    assert list(conf["branches"]) == [pkg]

    conf = read_conf(f"{conf_file}", exclude=[pkg])
    assert pkg not in list(conf["repos"])
    assert pkg not in list(conf["branches"])

    with pytest.raises(BadArgumentUsage, match="mutually exclusive"):
        read_conf(f"{conf_file}", only=[pkg], exclude=[pkg])
