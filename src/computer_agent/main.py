from __future__ import annotations

import sys
import traceback
from pathlib import Path

from platformdirs import user_data_dir

from .ui import run_app


def _install_crash_logger() -> Path:
    log_path = Path(user_data_dir("ComputerAgent")) / "crash.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def handle_exception(exc_type, exc_value, exc_traceback):
        try:
            with log_path.open("a", encoding="utf-8") as log:
                log.write("\n=== Unhandled Computer Agent exception ===\n")
                traceback.print_exception(
                    exc_type,
                    exc_value,
                    exc_traceback,
                    file=log,
                )
        finally:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception
    return log_path


def main() -> None:
    _install_crash_logger()
    raise SystemExit(run_app())


if __name__ == "__main__":
    main()
