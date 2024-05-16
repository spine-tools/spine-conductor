from io import StringIO
from pathlib import Path
import sys

from git import Remote
import pytest

from orchestra import ErrorCodes
from orchestra.publish import dispatch_workflow, push_tags

from .conftest import commit, edit, example_pkgs


@pytest.mark.parametrize("dup_repos", ["scm"], indirect=True)
@pytest.mark.parametrize("response", ["0", None])
def test_push_tags(CONF, dup_repos, response, monkeypatch):
    name, _, src, dst = dup_repos
    if response is None:
        Remote.rm(dst, "upstream")  # created in fixture
    else:
        monkeypatch.setattr("sys.stdin", StringIO(response))

    dst.create_tag("test_tag")
    push_tags(CONF, example_pkgs[name], dst, "test_tag")  # test_tag from fixture
    assert any(t for t in src.tags if t.name == "test_tag")


@pytest.mark.parametrize("dup_repos", ["scm"], indirect=True)
@pytest.mark.parametrize("response", ["bad", "\n"])
def test_push_tags_bad_prompt(CONF, dup_repos, response, monkeypatch, capsys):
    name, _, _, dst = dup_repos
    monkeypatch.setattr("sys.stdin", StringIO(response))

    # FIXME: in Python 3.10 str(IntEnum.ENUM) returns "ENUM" instead of "ENUM.value"
    with pytest.raises(SystemExit, match=str(int(ErrorCodes.USERINPUT_ERR))):
        push_tags(CONF, example_pkgs[name], dst, "dummy")

    captured = capsys.readouterr()
    match response:
        case "bad":
            assert "invalid selection" in captured.out
        case "\n":
            assert "empty response" in captured.out


def conflicting_edit(repo1, repo2, fname):
    edit(f"{repo2.working_dir}/{fname}", "upstream")
    commit(repo2, [fname], "upstream edit")
    repo2.remotes[0].push()  # master
    repo2.git.reset("--hard", "HEAD~1")

    edit(f"{repo2.working_dir}/{fname}", "downstream")
    commit(repo2, [fname], "downstream edit")


def conflicting_tags(repo1, repo2, fname, tag):
    edit(f"{repo2.working_dir}/{fname}", "downstream")
    commit(repo2, [fname], "downstream edit")

    repo1.create_tag(tag)
    repo2.create_tag(tag)


@pytest.mark.parametrize("dup_repos", ["scm"], indirect=True)
@pytest.mark.parametrize("err", [ErrorCodes.DUPTAG_ERR, ErrorCodes.REMOTE_ERR])
def test_push_tags_err(CONF, dup_repos, err, capsys):
    name, _, src, dst = dup_repos
    Remote.rm(dst, "upstream")  # simplify choice of remotes

    if err == ErrorCodes.REMOTE_ERR:
        # edit README.md to trigger a merge conflict
        conflicting_edit(src, dst, "README.md")
    if err == ErrorCodes.DUPTAG_ERR:
        # create the same tag on both repos
        conflicting_tags(src, dst, "README.md", "test_tag")

    # FIXME: in Python 3.10 str(IntEnum.ENUM) returns "ENUM" instead of "ENUM.value"
    with pytest.raises(SystemExit, match=str(int(err))):
        push_tags(CONF, example_pkgs[name], dst, "test_tag")  # test_tag from fixture

    captured = capsys.readouterr()
    if err == ErrorCodes.REMOTE_ERR:
        ref = CONF["branches"][example_pkgs[name]]
        assert f"pushing {ref=}" in captured.out
    if err == ErrorCodes.DUPTAG_ERR:
        tag = "test_tag"
        assert f"pushing {tag=}" in captured.out


@pytest.mark.parametrize("cmd", ["echo {repo} {workflow}", "grep packagename_regex"])
def test_dispatch_workflow(CONF, cmd, monkeypatch):
    """NOTE: echo to test config substitution, grep to test PIPE"""

    if sys.platform in ("win32",):
        # pytest.skip(reason="FIXME: can't test PIPE on Windows")
        cmd = f"powershell -Command {cmd!r}"
        cmd = cmd.replace("grep", "Select-String -Pattern")

    monkeypatch.setattr("orchestra.publish.CMD_FMT", cmd)
    res = dispatch_workflow(CONF, Path(__file__).parent / "scm.toml")
    assert not isinstance(res, Exception)
    out = res.stdout.decode("utf8")
    if "echo" in cmd:
        assert all(token in out for token in CONF["workflow"].values())
    else:
        *_, token = cmd.split()
        # the .strip is required on windows as we call powershell explicitly
        assert token.strip("'\"") in out
