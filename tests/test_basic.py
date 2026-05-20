"""Pytest tests for SnowFrame core functionality."""

import pytest
import pandas as pd
from snowframe import SnowFrame, SnowFrameError


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sales_df() -> pd.DataFrame:
    return pd.DataFrame({
        "customer_id": [1, 1, 2, 3],
        "amount":      [100, 2500, 700, 1800],
    })


@pytest.fixture
def customers_df() -> pd.DataFrame:
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "name":        ["Amit", "Riya", "Kabir"],
    })


@pytest.fixture
def sf() -> SnowFrame:
    return SnowFrame()


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestLoad:
    def test_load_dict_registers_tables(self, sf, sales_df, customers_df):
        sf.load({"sales": sales_df, "customers": customers_df})
        table_names = sf.tables()["table_name"].tolist()
        assert "sales" in table_names
        assert "customers" in table_names

    def test_load_tuple_auto_names(self, sf, sales_df, customers_df):
        sf.load((sales_df, customers_df))
        table_names = sf.tables()["table_name"].tolist()
        assert "table1" in table_names
        assert "table2" in table_names

    def test_load_list_auto_names(self, sf, sales_df, customers_df):
        sf.load([sales_df, customers_df])
        table_names = sf.tables()["table_name"].tolist()
        assert "table1" in table_names
        assert "table2" in table_names

    def test_load_wrong_type_raises(self, sf):
        with pytest.raises(TypeError):
            sf.load("not_a_dataframe")  # type: ignore[arg-type]

    def test_register_non_dataframe_raises(self, sf):
        with pytest.raises(TypeError):
            sf.register("oops", [1, 2, 3])  # type: ignore[arg-type]


class TestSQL:
    def test_select_returns_self_for_chaining(self, sf, sales_df):
        sf.load({"sales": sales_df})
        result = sf.sql("CREATE TABLE s2 AS SELECT * FROM sales WHERE amount > 500")
        assert result is sf

    def test_simple_select_via_to_df(self, sf, sales_df):
        sf.load({"sales": sales_df})
        df = sf.to_df("sales")
        assert len(df) == 4
        assert set(df.columns) == {"customer_id", "amount"}

    def test_create_table_and_to_df(self, sf, sales_df, customers_df):
        sf.load({"sales": sales_df, "customers": customers_df})
        sf.sql("""
            CREATE TABLE final AS
            SELECT
                c.name,
                SUM(s.amount) AS total_amount
            FROM sales s
            JOIN customers c ON s.customer_id = c.customer_id
            GROUP BY c.name
        """)
        final_df = sf.to_df("final")
        assert len(final_df) == 3
        assert "name" in final_df.columns
        assert "total_amount" in final_df.columns

    def test_aggregation_values(self, sf, sales_df, customers_df):
        sf.load({"sales": sales_df, "customers": customers_df})
        sf.sql("""
            CREATE TABLE agg AS
            SELECT
                c.name,
                SUM(s.amount) AS total
            FROM sales s
            JOIN customers c ON s.customer_id = c.customer_id
            GROUP BY c.name
        """)
        df = sf.to_df("agg")
        totals = dict(zip(df["name"], df["total"]))
        assert totals["Amit"] == 2600   # 100 + 2500
        assert totals["Riya"] == 700
        assert totals["Kabir"] == 1800

    def test_bad_sql_raises_snowframe_error(self, sf):
        with pytest.raises(SnowFrameError, match="SQL execution failed"):
            sf.sql("SELECT * FROM table_that_does_not_exist")

    def test_error_message_lists_available_tables(self, sf, sales_df):
        sf.load({"sales": sales_df})
        with pytest.raises(SnowFrameError, match="sales"):
            sf.sql("SELECT * FROM ghost_table")


class TestToDF:
    def test_missing_table_raises_snowframe_error(self, sf):
        with pytest.raises(SnowFrameError, match="nonexistent"):
            sf.to_df("nonexistent")

    def test_error_lists_available_tables(self, sf, sales_df):
        sf.load({"sales": sales_df})
        with pytest.raises(SnowFrameError, match="sales"):
            sf.to_df("missing")


class TestRunFile:
    def test_run_file_executes_statements(self, sf, sales_df, customers_df, tmp_path):
        sf.load({"sales": sales_df, "customers": customers_df})
        sql_file = tmp_path / "test.sql"
        sql_file.write_text(
            "CREATE TABLE result AS "
            "SELECT c.name, SUM(s.amount) AS total "
            "FROM sales s "
            "JOIN customers c ON s.customer_id = c.customer_id "
            "GROUP BY c.name;\n"
        )
        sf.run_file(sql_file)
        result = sf.to_df("result")
        assert len(result) == 3

    def test_run_file_multi_statement(self, sf, sales_df, customers_df, tmp_path):
        sf.load({"sales": sales_df, "customers": customers_df})
        sql_file = tmp_path / "multi.sql"
        sql_file.write_text(
            "CREATE TABLE t1 AS SELECT * FROM sales WHERE amount > 500;\n"
            "CREATE TABLE t2 AS SELECT * FROM t1 WHERE amount > 1000;\n"
        )
        sf.run_file(sql_file)
        t1 = sf.to_df("t1")
        t2 = sf.to_df("t2")
        assert len(t1) == 3  # 2500, 700 > 500 wait: 2500, 700, 1800 → 3 rows
        assert len(t2) == 2  # 2500, 1800

    def test_run_file_not_found_raises(self, sf):
        with pytest.raises(FileNotFoundError):
            sf.run_file("/tmp/does_not_exist_ever.sql")


class TestExport:
    def test_to_csv(self, sf, sales_df, tmp_path):
        sf.load({"sales": sales_df})
        out = tmp_path / "out.csv"
        sf.to_csv("sales", out)
        read_back = pd.read_csv(out)
        assert len(read_back) == 4
        assert set(read_back.columns) == {"customer_id", "amount"}

    def test_to_excel(self, sf, sales_df, tmp_path):
        pytest.importorskip("openpyxl")
        sf.load({"sales": sales_df})
        out = tmp_path / "out.xlsx"
        sf.to_excel("sales", out)
        read_back = pd.read_excel(out)
        assert len(read_back) == 4


# ── Polish tests (new requirements) ───────────────────────────────────────────

class TestQuoteIdentifier:
    def test_to_df_normal_name_works(self, sf, sales_df):
        """Simple identifiers round-trip without quoting issues."""
        sf.load({"sales": sales_df})
        df = sf.to_df("sales")
        assert len(df) == 4

    def test_empty_string_raises(self, sf):
        with pytest.raises(SnowFrameError, match="non-empty string"):
            sf.to_df("")

    def test_whitespace_only_raises(self, sf):
        with pytest.raises(SnowFrameError, match="non-empty string"):
            sf.to_df("   ")

    def test_non_string_raises(self, sf):
        with pytest.raises(SnowFrameError, match="non-empty string"):
            sf.to_df(None)  # type: ignore[arg-type]

    def test_quoted_identifier_reaches_duckdb(self, sf, sales_df):
        """A name that requires quoting is safely passed to DuckDB."""
        # Register a table, then try to retrieve a non-existent quoted name —
        # the error should come from DuckDB (table not found), not from
        # identifier validation, proving the quoting path was exercised.
        sf.load({"sales": sales_df})
        with pytest.raises(SnowFrameError, match="Could not retrieve"):
            sf.to_df("my table")  # space → gets quoted → DuckDB rejects missing table


class TestQueryAlias:
    def test_query_returns_self(self, sf, sales_df):
        sf.load({"sales": sales_df})
        result = sf.query("CREATE TABLE q1 AS SELECT * FROM sales WHERE amount > 500")
        assert result is sf

    def test_query_result_readable(self, sf, sales_df):
        sf.load({"sales": sales_df})
        sf.query("CREATE TABLE q2 AS SELECT * FROM sales WHERE amount > 1000")
        df = sf.to_df("q2")
        assert len(df) == 2  # 2500, 1800

    def test_query_raises_snowframe_error_on_bad_sql(self, sf):
        with pytest.raises(SnowFrameError, match="SQL execution failed"):
            sf.query("SELECT * FROM no_such_table")


class TestRunFilePolish:
    def test_skips_empty_statements(self, sf, sales_df, tmp_path):
        sf.load({"sales": sales_df})
        sql_file = tmp_path / "empty.sql"
        sql_file.write_text(
            ";\n"
            "  ;\n"
            "CREATE TABLE t1 AS SELECT * FROM sales;\n"
            ";\n"
        )
        sf.run_file(sql_file)
        assert len(sf.to_df("t1")) == 4

    def test_skips_comment_only_blocks(self, sf, sales_df, tmp_path):
        sf.load({"sales": sales_df})
        sql_file = tmp_path / "comments.sql"
        sql_file.write_text(
            "-- header comment\n"
            "-- another line\n"
            ";\n"
            "CREATE TABLE t1 AS SELECT * FROM sales;\n"
        )
        sf.run_file(sql_file)
        assert len(sf.to_df("t1")) == 4

    def test_error_shows_statement_number(self, sf, sales_df, tmp_path):
        sf.load({"sales": sales_df})
        sql_file = tmp_path / "err.sql"
        sql_file.write_text(
            "CREATE TABLE t1 AS SELECT * FROM sales;\n"
            "SELECT * FROM nonexistent_table;\n"
        )
        with pytest.raises(SnowFrameError, match="Statement 2"):
            sf.run_file(sql_file)

    def test_error_shows_file_name(self, sf, tmp_path):
        sql_file = tmp_path / "named.sql"
        sql_file.write_text("SELECT * FROM ghost;\n")
        with pytest.raises(SnowFrameError, match="named.sql"):
            sf.run_file(sql_file)

    def test_missing_table_error_includes_available(self, sf, sales_df):
        """to_df() on a missing table lists what tables exist."""
        sf.load({"sales": sales_df})
        with pytest.raises(SnowFrameError) as exc_info:
            sf.to_df("missing")
        assert "sales" in str(exc_info.value)


# ── Notebook feature tests ─────────────────────────────────────────────────────

class TestNotebookFeatures:
    # ── query_df ──────────────────────────────────────────────────────────────

    def test_query_df_select_returns_dataframe(self, sf, sales_df):
        sf.load({"sales": sales_df})
        df = sf.query_df("SELECT * FROM sales WHERE amount > 1000")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2  # 2500, 1800

    def test_query_df_with_cte_returns_dataframe(self, sf, sales_df):
        sf.load({"sales": sales_df})
        df = sf.query_df(
            "WITH big AS (SELECT * FROM sales WHERE amount > 500) "
            "SELECT COUNT(*) AS n FROM big"
        )
        assert df.iloc[0]["n"] == 3  # 2500, 700, 1800

    def test_query_df_bad_sql_raises_snowframe_error(self, sf):
        with pytest.raises(SnowFrameError, match="SQL query failed"):
            sf.query_df("SELECT * FROM nonexistent_table_xyz")

    # ── show ──────────────────────────────────────────────────────────────────

    def test_show_returns_limited_rows(self, sf, sales_df):
        sf.load({"sales": sales_df})
        df = sf.show("sales", limit=2)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_show_default_limit_is_ten(self, sf, sales_df):
        # sales_df has 4 rows, all fit within default limit of 10
        sf.load({"sales": sales_df})
        df = sf.show("sales")
        assert len(df) == 4

    def test_show_missing_table_raises(self, sf):
        with pytest.raises(SnowFrameError):
            sf.show("nonexistent")

    # ── describe ──────────────────────────────────────────────────────────────

    def test_describe_returns_schema_info(self, sf, sales_df):
        sf.load({"sales": sales_df})
        df = sf.describe("sales")
        assert isinstance(df, pd.DataFrame)
        assert "column_name" in df.columns
        assert set(df["column_name"]) == {"customer_id", "amount"}

    def test_describe_missing_table_raises(self, sf):
        with pytest.raises(SnowFrameError):
            sf.describe("nonexistent")

    # ── auto ──────────────────────────────────────────────────────────────────

    def test_auto_registers_dataframes_from_caller_scope(self, sales_df, customers_df):
        # sales_df and customers_df are local variables in this test function;
        # auto() should discover and register them.
        sf = SnowFrame()
        sf.auto()
        names = sf.tables()["table_name"].tolist()
        assert "sales_df" in names
        assert "customers_df" in names

    def test_auto_ignores_non_dataframes(self, sales_df):
        x = 42
        y = "hello"
        sf = SnowFrame()
        sf.auto()
        names = sf.tables()["table_name"].tolist()
        assert "x" not in names
        assert "y" not in names

    def test_auto_ignores_underscore_names(self):
        _hidden = pd.DataFrame({"a": [1]})
        sf = SnowFrame()
        sf.auto()
        assert "_hidden" not in sf.tables()["table_name"].tolist()

    # ── magic active session ──────────────────────────────────────────────────

    def test_set_and_get_active_session(self):
        from snowframe import set_active_session, get_active_session
        sf = SnowFrame()
        set_active_session(sf)
        assert get_active_session() is sf

    def test_active_session_can_be_replaced(self):
        from snowframe import set_active_session, get_active_session
        sf1, sf2 = SnowFrame(), SnowFrame()
        set_active_session(sf1)
        set_active_session(sf2)
        assert get_active_session() is sf2

    # ── _is_query helper ─────────────────────────────────────────────────────

    def test_is_query_detects_select(self):
        from snowframe.magic import _is_query
        assert _is_query("SELECT * FROM sales") is True
        assert _is_query("  select * from sales") is True
        assert _is_query("WITH cte AS (SELECT 1) SELECT * FROM cte") is True
        assert _is_query("SHOW TABLES") is True
        assert _is_query("DESCRIBE sales") is True
        assert _is_query("EXPLAIN SELECT 1") is True

    def test_is_query_rejects_ddl_dml(self):
        from snowframe.magic import _is_query
        assert _is_query("CREATE TABLE t AS SELECT 1") is False
        assert _is_query("INSERT INTO t VALUES (1)") is False
        assert _is_query("DROP TABLE t") is False
        assert _is_query("ALTER TABLE t ADD COLUMN x INT") is False

    def test_is_query_strips_leading_comments(self):
        from snowframe.magic import _is_query
        sql = "-- header comment\n-- another line\nSELECT * FROM sales"
        assert _is_query(sql) is True
        sql_ddl = "-- create something\nCREATE TABLE t AS SELECT 1"
        assert _is_query(sql_ddl) is False

    # ── query-like path produces DataFrame, DDL path executes ────────────────

    def test_create_table_sql_path_executes_successfully(self, sf, sales_df):
        sf.load({"sales": sales_df})
        sf.sql("CREATE TABLE big AS SELECT * FROM sales WHERE amount > 1000")
        df = sf.to_df("big")
        assert len(df) == 2

    def test_query_df_is_the_select_path_for_magic(self, sf, sales_df):
        """query_df() is what magic calls for SELECT — verify it returns rows."""
        sf.load({"sales": sales_df})
        df = sf.query_df("SELECT * FROM sales")
        assert len(df) == len(sales_df)
