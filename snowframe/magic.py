"""Optional IPython / Jupyter magic for SnowFrame.

Load in a notebook with:
    %load_ext snowframe

Then set an active session and write SQL in cells:
    %%snowframe        (or the shorter alias %%sf)
    SELECT * FROM sales LIMIT 5;
"""

from __future__ import annotations

import re
from typing import Optional

from snowframe.core import SnowFrameError

# Single module-level slot for the active session.
_ACTIVE: Optional[object] = None  # holds a SnowFrame instance at runtime

# SQL keywords whose statements return rows and should be displayed as DataFrames.
_QUERY_RE = re.compile(
    r"^\s*(SELECT|WITH|SHOW|DESCRIBE|DESC|PRAGMA|EXPLAIN|VALUES|FROM)\b",
    re.IGNORECASE,
)


def _is_query(sql: str) -> bool:
    """Return True if *sql* is a row-returning statement.

    Strips leading ``--`` comment lines before checking the first real keyword.
    """
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return bool(_QUERY_RE.match(stripped))
    return False


def set_active_session(sf: object) -> None:
    """Set the SnowFrame session used by %%snowframe / %%sf magic cells.

    Args:
        sf: A SnowFrame instance that subsequent magic cells will run against.
    """
    global _ACTIVE
    _ACTIVE = sf


def get_active_session() -> Optional[object]:
    """Return the currently active SnowFrame session, or None."""
    return _ACTIVE


def load_ipython_extension(ipython: object) -> None:
    """Called by IPython when the user runs ``%load_ext snowframe``.

    Registers the ``%%snowframe`` and ``%%sf`` cell magics.

    SELECT / WITH / SHOW / DESCRIBE / PRAGMA / EXPLAIN:
        Executes the query and displays the result DataFrame inline.

    CREATE / INSERT / UPDATE / DELETE / DROP / ALTER and any other DDL/DML:
        Executes the statement and prints a success message with the
        current table list.
    """
    try:
        from IPython.core.magic import register_cell_magic
        from IPython.display import display
    except ImportError:
        print(
            "IPython is required for SnowFrame magic.\n"
            "Install it with:  pip install 'snowframe[notebook]'"
        )
        return

    def _run_sql(line: str, cell: str) -> None:
        sf = get_active_session()
        if sf is None:
            print(
                "No active SnowFrame session.\n"
                "Create one and call set_active_session(sf) before using %%snowframe."
            )
            return

        sql = cell.strip()
        if not sql:
            return

        try:
            if _is_query(sql):
                result = sf.query_df(sql)  # type: ignore[attr-defined]
                display(result)
            else:
                sf.sql(sql)  # type: ignore[attr-defined]
                tables = sf.tables()["table_name"].tolist()  # type: ignore[attr-defined]
                print(f"Done.  Tables: {tables}")
        except SnowFrameError as exc:
            print(f"SnowFrameError: {exc}")

    register_cell_magic("snowframe")(_run_sql)
    register_cell_magic("sf")(_run_sql)
    print("SnowFrame magic loaded. Use %%snowframe or %%sf in any cell.")
