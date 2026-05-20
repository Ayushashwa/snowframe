"""SnowFrame CLI — entry point for the ``snowframe`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_run(path: str) -> None:
    """Execute a .sql file through a SnowFrame session."""
    from snowframe.core import SnowFrame

    file_path = Path(path)
    if not file_path.exists():
        print(f"Error: file not found — {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running: {file_path}")
    print(
        "Note: CLI mode has no pre-loaded DataFrames.\n"
        "Any SQL that references Python-registered tables will fail here.\n"
        "For full DataFrame support, use SnowFrame inside a Python script\n"
        "or Jupyter notebook.\n"
    )

    try:
        sf = SnowFrame()
        sf.run_file(file_path)
        tables = sf.tables()
        if not tables.empty:
            print(f"Tables created: {tables['table_name'].tolist()}")
        else:
            print("SQL file executed. No tables were created.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Entry point for the ``snowframe`` CLI command."""
    parser = argparse.ArgumentParser(
        prog="snowframe",
        description="SnowFrame: lightweight SQL workspace for Pandas DataFrames",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    run_p = sub.add_parser("run", help="Execute a .sql file")
    run_p.add_argument("file", help="Path to the .sql file to execute")

    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args.file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
