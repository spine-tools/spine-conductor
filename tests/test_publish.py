from io import StringIO
from pathlib import Path

from git import GitCommandError, Remote
import pytest
from orchestra.config import CONF

from orchestra.publish import dispatch_workflow, push_tags


@pytest.mark.parametrize("dup_repos", ["scm"], indirect=True)
@pytest.mark.parametrize("response", ["0", "bad", "\n", None])
def test_push_tags(dup_repos, response, monkeypatch, capsys):
    _, src, dst = dup_repos
    dst.create_tag("test_tag")
    if response is None:
        Remote.rm(dst, "upstream")  # created in fixture
    else:
        monkeypatch.setattr("sys.stdin", StringIO(response))

    push_tags(dst, "test_tag")
    assert any(t for t in src.tags if t.name == "test_tag")

    captured = capsys.readouterr()
    if response in ("bad", "\n"):
        assert "selecting first" in captured.out
        if response == "bad":
            assert "invalid selection" in captured.out
        if response == "\n":
            assert "empty response" in captured.out


@pytest.mark.skip(reason="push error handling not implemented")
@pytest.mark.parametrize("dup_repos", ["scm"], indirect=True)
def test_push_tags_err(dup_repos, capsys):
    _, src, dst = dup_repos
    Remote.rm(dst, "upstream")  # created in fixture
    dst.create_tag("test_tag")

    Path(src.working_dir).rename(f"{src.working_dir}.bak")

    with pytest.raises(GitCommandError):
        push_tags(dst, "test_tag")
    captured = capsys.readouterr()
    assert "pushing 'test_tag' failed" in captured.out
    Path(f"{src.working_dir}.bak").rename(src.working_dir)


@pytest.mark.parametrize(
    "cmd, fname",
    [("echo {repo} {workflow}", "empty"), ("grep packagename_regex", "scm.toml")],
)
def test_dispatch_workflow(cmd, fname, monkeypatch):
    monkeypatch.setattr("orchestra.publish.CMD_FMT", cmd)
    infile = Path(__file__).parent / fname
    infile.touch()
    res = dispatch_workflow(infile).stdout.decode("utf8")
    if fname == "empty":
        assert all(token in res for token in CONF["workflow"].values())
    else:
        *_, token = cmd.split()
        assert token in res
