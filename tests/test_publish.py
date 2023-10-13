from io import StringIO
from pathlib import Path
import sys

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


@pytest.mark.parametrize("cmd", ["echo {repo} {workflow}", "grep packagename_regex"])
def test_dispatch_workflow(cmd, monkeypatch):
    """NOTE: echo to test config substitution, grep to test PIPE"""

    if sys.platform in ("win32",):
        # pytest.skip(reason="FIXME: can't test PIPE on Windows")
        cmd = f"powershell -Command {cmd!r}"
        cmd = cmd.replace("grep", "Select-String -Pattern")

    monkeypatch.setattr("orchestra.publish.CMD_FMT", cmd)
    res = dispatch_workflow(Path(__file__).parent / "scm.toml")
    out = res.stdout.decode("utf8")
    if "echo" in cmd:
        assert all(token in out for token in CONF["workflow"].values())
    else:
        *_, token = cmd.split()
        # the .strip is required on windows as we call powershell explicitly
        assert token.strip("'\"") in out
