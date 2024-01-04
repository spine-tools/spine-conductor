import pytest

from orchestra import ErrorCodes


@pytest.mark.parametrize(
    "name,val", [(name, val) for val, name in enumerate(ErrorCodes._member_names_, 1)]
)
def test_errors(name, val, capsys):
    err = getattr(ErrorCodes, name)
    assert err == val

    with pytest.raises(SystemExit, match=f"{val}"):
        err.exit("test message")

    captured = capsys.readouterr()
    assert f"{name}: test message" in captured.err
