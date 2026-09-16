import os
import pathlib
import sys


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1] / "apps" / "backend-python"
sys.path.insert(0, str(BACKEND_DIR))

from app.mt5.terminal_detection import find_running_terminal_paths  # noqa: E402


def main() -> int:
    print("Running MT5 process visibility check...")
    terminal_paths = find_running_terminal_paths()
    if terminal_paths:
        for path in terminal_paths:
            print(f"MT5 process visible: path={path}")
    else:
        print("No terminal.exe/terminal64.exe process is visible to this Python session.")

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        print(f"MetaTrader5 import failed: {exc}")
        return 1

    print(f"MetaTrader5 package version: {getattr(mt5, '__version__', 'unknown')}")
    initialize_kwargs = {"timeout": 10_000}
    if terminal_paths:
        initialize_kwargs["path"] = terminal_paths[0]

    initialized = mt5.initialize(**initialize_kwargs)
    print(f"mt5.initialize({initialize_kwargs}): {initialized}")
    if not initialized:
        print(f"mt5.last_error(): {mt5.last_error()}")
        return 1

    try:
        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()
        print(f"terminal_info: {terminal_info}")
        print(f"account_info: {account_info}")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
