from enum import IntEnum
import sys


class ErrorCodes(IntEnum):
    CONFIG_ERR = 1
    BRANCH_ERR = 2
    COMMIT_ERR = 3

    def exit(self, msg: str = ""):
        if msg:
            print(f"{self.name}: {msg}", file=sys.stderr)
        sys.exit(int(self))


def format_exc(exc: Exception, notes: str = "") -> str:
    """Format an exception as a string."""
    # FIXME: maybe support multiple lines by making notes a list[str]?
    if notes:
        # NOTE: the get-set madness is to pass linting on 3.10
        _notes = getattr(exc, "__notes__", [])
        _notes += [notes]
        setattr(exc, "__notes__", _notes)
    err = f"[red][bold]{exc.__class__.__name__}:[/red][/bold] {exc}"
    trailer = ", ".join(getattr(exc, "__notes__", []))
    if trailer:
        err += f"\n\n[bold]{trailer}"
    return err
