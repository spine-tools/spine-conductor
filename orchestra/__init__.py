from enum import IntEnum


class ErrorCodes(IntEnum):
    CONFIG_ERR = 1
    BRANCH_ERR = 2
    COMMIT_ERR = 3


def format_exc(exc: Exception, notes: str = "") -> str:
    """Format an exception as a string."""
    if notes:
        exc.add_note(notes)
    err = f"[red][bold]{exc.__class__.__name__}:[/red][/bold] {exc}"
    trailer = ", ".join(getattr(exc, "__notes__", []))
    if trailer:
        err += f"\n\n[bold]{trailer}"
    return err
