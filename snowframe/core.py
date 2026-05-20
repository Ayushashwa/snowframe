"""Core SnowFrame session — wraps a DuckDB in-memory connection."""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Dict, List, Union

import duckdb
import pandas as pd


class SnowFrameError(Exception):
    """Raised when a SnowFrame operation fails."""


# Matches bare identifiers that need no quoting: letters/digits/underscore,
# must start with a letter or underscore.
_SIMPLE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_comment_only(stmt: str) -> bool:
    """Return True if stmt contains nothing but whitespace and -- line comments."""
    for line in stmt.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


class SnowFrame:
    """Lightweight SQL workspace for Pandas DataFrames, powered by DuckDB.

    Typical flow:
        sf = SnowFrame()
        sf.load({"sales": sales_df, "customers": customers_df})
        sf.sql("CREATE TABLE final AS SELECT ...")
        result = sf.to_df("final")
    """

    def __init__(self) -> None:
        self._conn: duckdb.DuckDBPyConnection = duckdb.connect()
        # Tracks names registered via Python (views aren't always in SHOW TABLES)
        self._registry: Dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Loading data
    # ------------------------------------------------------------------

    def load(
        self,
        data: Union[
            Dict[str, pd.DataFrame],
            tuple,  # tuple[pd.DataFrame, ...]
            List[pd.DataFrame],
        ],
    ) -> "SnowFrame":
        """Register one or more DataFrames as SQL tables.

        Args:
            data: A dict mapping names to DataFrames, or a tuple/list of
                  DataFrames that are auto-named table1, table2, …
        """
        if isinstance(data, dict):
            for name, df in data.items():
                self.register(name, df)
        elif isinstance(data, (tuple, list)):
            for idx, df in enumerate(data, start=1):
                self.register(f"table{idx}", df)
        else:
            raise TypeError(
                f"load() expects dict, tuple, or list — got {type(data).__name__}"
            )
        return self

    def register(self, name: str, df: pd.DataFrame) -> "SnowFrame":
        """Register a single DataFrame as a named SQL table.

        Args:
            name: Table name to use in subsequent SQL queries.
            df: Pandas DataFrame to register.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                f"register() expects a Pandas DataFrame — got {type(df).__name__}"
            )
        self._conn.register(name, df)
        self._registry[name] = df
        return self

    def auto(self) -> "SnowFrame":
        """Auto-register all Pandas DataFrames visible in the caller's local scope.

        Scans the calling frame's local variables and registers every
        pd.DataFrame under its variable name.  Names that start with '_'
        are skipped.  Call this once after defining your DataFrames:

            sales = pd.DataFrame(...)
            sf = SnowFrame()
            sf.auto()         # registers 'sales' automatically
        """
        frame = inspect.currentframe()
        try:
            if frame is not None and frame.f_back is not None:
                for name, value in frame.f_back.f_locals.items():
                    if isinstance(value, pd.DataFrame) and not name.startswith("_"):
                        self.register(name, value)
        finally:
            del frame  # prevent reference cycle
        return self

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def tables(self) -> pd.DataFrame:
        """Return a DataFrame listing all known table and view names."""
        names: set = set(self._registry.keys())
        # Also pick up tables created by SQL (CREATE TABLE …)
        try:
            result = self._conn.execute("SHOW TABLES").fetchdf()
            if not result.empty:
                names.update(result.iloc[:, 0].tolist())
        except Exception:
            pass
        return pd.DataFrame({"table_name": sorted(names)})

    # ------------------------------------------------------------------
    # SQL execution
    # ------------------------------------------------------------------

    def sql(self, query: str) -> "SnowFrame":
        """Execute a SQL statement against the registered tables.

        Args:
            query: Any valid DuckDB SQL statement.

        Returns:
            self — allows method chaining.

        Raises:
            SnowFrameError: With a descriptive message including available tables.
        """
        try:
            self._conn.execute(query)
        except duckdb.Error as exc:
            available = self._known_tables()
            raise SnowFrameError(
                f"SQL execution failed.\n"
                f"  Error  : {exc}\n"
                f"  Tables : {available}"
            ) from exc
        return self

    def query(self, query: str) -> "SnowFrame":
        """Alias for sql(). Execute a SQL statement against the registered tables."""
        return self.sql(query)

    def query_df(self, sql_text: str) -> pd.DataFrame:
        """Execute a SQL query and return the result as a Pandas DataFrame.

        Designed for SELECT / WITH / SHOW-style statements that produce rows.
        Also called internally by the %%snowframe / %%sf notebook magic.

        Args:
            sql_text: Any SQL that returns a result set.

        Raises:
            SnowFrameError: On DuckDB execution error.
        """
        try:
            return self._conn.execute(sql_text).fetchdf()
        except duckdb.Error as exc:
            available = self._known_tables()
            raise SnowFrameError(
                f"SQL query failed.\n"
                f"  Error  : {exc}\n"
                f"  Tables : {available}"
            ) from exc

    def run_file(self, path: Union[str, Path]) -> "SnowFrame":
        """Execute every SQL statement in a .sql file.

        Splits on semicolons. Skips empty segments and comment-only blocks.
        On failure, raises SnowFrameError naming the statement number and the
        original DuckDB error.

        Args:
            path: Path to the .sql file.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"SQL file not found: {file_path}")

        sql_text = file_path.read_text(encoding="utf-8")
        stmt_num = 0
        for segment in sql_text.split(";"):
            stmt = segment.strip()
            if not stmt or _is_comment_only(stmt):
                continue
            stmt_num += 1
            try:
                self._conn.execute(stmt)
            except duckdb.Error as exc:
                available = self._known_tables()
                preview = stmt[:100] + ("..." if len(stmt) > 100 else "")
                raise SnowFrameError(
                    f"Statement {stmt_num} in '{file_path.name}' failed.\n"
                    f"  Statement : {preview}\n"
                    f"  Error     : {exc}\n"
                    f"  Tables    : {available}"
                ) from exc
        return self

    # ------------------------------------------------------------------
    # Exporting data
    # ------------------------------------------------------------------

    def to_df(self, table_name: str) -> pd.DataFrame:
        """Read a named table or view back into a Pandas DataFrame.

        Args:
            table_name: Name of a table or view registered in this session.

        Raises:
            SnowFrameError: If the name is invalid or the table does not exist.
        """
        quoted = self._quote_identifier(table_name)
        try:
            return self._conn.execute(f"SELECT * FROM {quoted}").fetchdf()
        except duckdb.Error as exc:
            available = self._known_tables()
            raise SnowFrameError(
                f"Could not retrieve table '{table_name}'.\n"
                f"  Error  : {exc}\n"
                f"  Tables : {available}"
            ) from exc

    def show(self, table_name: str, limit: int = 10) -> pd.DataFrame:
        """Return the first *limit* rows of a table as a Pandas DataFrame.

        Args:
            table_name: Name of the table or view.
            limit: Maximum number of rows to return (default: 10).

        Raises:
            SnowFrameError: If the name is invalid or the table does not exist.
        """
        quoted = self._quote_identifier(table_name)
        try:
            return self._conn.execute(
                f"SELECT * FROM {quoted} LIMIT {int(limit)}"
            ).fetchdf()
        except duckdb.Error as exc:
            available = self._known_tables()
            raise SnowFrameError(
                f"Could not show table '{table_name}'.\n"
                f"  Error  : {exc}\n"
                f"  Tables : {available}"
            ) from exc

    def describe(self, table_name: str) -> pd.DataFrame:
        """Return DuckDB DESCRIBE output for a table (column names and types).

        Args:
            table_name: Name of the table or view to describe.

        Raises:
            SnowFrameError: If the name is invalid or the table does not exist.
        """
        quoted = self._quote_identifier(table_name)
        try:
            return self._conn.execute(f"DESCRIBE {quoted}").fetchdf()
        except duckdb.Error as exc:
            available = self._known_tables()
            raise SnowFrameError(
                f"Could not describe table '{table_name}'.\n"
                f"  Error  : {exc}\n"
                f"  Tables : {available}"
            ) from exc

    def to_csv(self, table_name: str, path: Union[str, Path]) -> None:
        """Export a table to a CSV file.

        Args:
            table_name: Name of the table to export.
            path: Destination CSV file path.
        """
        self.to_df(table_name).to_csv(path, index=False)

    def to_excel(self, table_name: str, path: Union[str, Path]) -> None:
        """Export a table to an Excel file (requires openpyxl).

        Args:
            table_name: Name of the table to export.
            path: Destination .xlsx file path.
        """
        self.to_df(table_name).to_excel(path, index=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying DuckDB connection and free resources."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _quote_identifier(self, name: str) -> str:
        """Return a safely quoted SQL identifier for DuckDB.

        Rules:
        - name must be a non-empty string.
        - Simple identifiers (letters, digits, underscore; starts with letter
          or underscore) are returned as-is.
        - Everything else is wrapped in double quotes; any embedded double
          quotes are escaped by doubling them ("").

        Raises:
            SnowFrameError: If name is not a non-empty string.
        """
        if not isinstance(name, str) or not name.strip():
            raise SnowFrameError(
                f"Table name must be a non-empty string — got {name!r}"
            )
        if _SIMPLE_IDENT.match(name):
            return name
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def _known_tables(self) -> List[str]:
        """Return a sorted list of all table names known to this session."""
        return self.tables()["table_name"].tolist()

    def __repr__(self) -> str:
        return f"SnowFrame(tables={sorted(self._registry.keys())})"
