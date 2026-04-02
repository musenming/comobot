"""
Entry point for running comobot as a module: python -m comobot

When built as a PyInstaller binary, sys.executable points to the binary itself.
Multiprocessing (used by loguru's enqueue=True) may re-invoke the binary with
Python interpreter flags like ``-B -c "from multiprocessing..."``.  We intercept
these invocations so they don't reach Typer, which would reject them as unknown
options.
"""

import sys

# On Windows, force UTF-8 console encoding to prevent UnicodeEncodeError when
# Rich renders Unicode status characters (✓, ✗, →, etc.) on GBK/cp936 systems.
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

# Python interpreter flags that may be passed when the binary is re-invoked
# by multiprocessing or other internal mechanisms.
_PYTHON_FLAGS = frozenset(
    {
        "-b",
        "-bb",
        "-B",
        "-d",
        "-E",
        "-i",
        "-I",
        "-O",
        "-OO",
        "-q",
        "-R",
        "-s",
        "-S",
        "-u",
        "-v",
        "-W",
        "-x",
        "-X",
    }
)


def _handle_frozen_multiprocessing() -> bool:
    """Handle multiprocessing child invocations in a PyInstaller frozen binary.

    Returns True if this invocation was a multiprocessing child (and has been
    handled), False otherwise (normal CLI invocation).
    """
    if not getattr(sys, "frozen", False):
        return False

    import multiprocessing

    multiprocessing.freeze_support()

    # Multiprocessing resource_tracker / spawn invocations pass:
    #   sys.executable -B -c "from multiprocessing.resource_tracker import ..."
    # Detect this pattern and execute the code directly.
    argv = sys.argv[1:]  # skip binary name

    # Strip Python interpreter flags (-B, -s, -S, -E, -u, -O, etc.)
    while argv and argv[0] in _PYTHON_FLAGS:
        argv.pop(0)

    if len(argv) >= 2 and argv[0] == "-c":
        code = argv[1]
        exec(code)  # noqa: S102 — trusted multiprocessing/interpreter bootstrap code
        sys.exit(0)

    # If only interpreter flags remain (no valid comobot subcommand), exit
    # silently — this is likely a Python internal re-invocation we didn't
    # recognise above.
    if not argv:
        sys.exit(0)

    # Strip interpreter flags from sys.argv so Typer only sees valid commands.
    # This prevents leftover flags (e.g. -B) from reaching Click/Typer.
    cleaned = [sys.argv[0]]
    for arg in sys.argv[1:]:
        if arg in _PYTHON_FLAGS:
            continue
        cleaned.append(arg)
    sys.argv = cleaned

    return False


if __name__ == "__main__":
    if not _handle_frozen_multiprocessing():
        from comobot.cli.commands import app

        app()
