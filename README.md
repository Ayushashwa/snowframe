# SnowFrame

SnowFrame is a lightweight SQL workspace for Pandas DataFrames. It lets you register DataFrames as SQL tables, run warehouse-style SQL using DuckDB, and export final outputs back to Pandas.

```
Pandas DataFrames  →  SnowFrame tables  →  SQL operations  →  Pandas DataFrame
```

---

## Installation

```bash
# Clone or download the repo, then install in editable mode
pip install -e .

# With Jupyter / notebook magic support
pip install -e ".[notebook]"

# With Excel export support
pip install -e ".[excel]"

# Full dev install (includes pytest, openpyxl, ipython)
pip install -e ".[dev]"
```

---

## Quick start

```python
import pandas as pd
from snowframe import SnowFrame

sales_df = pd.DataFrame({
    "customer_id": [1, 1, 2, 3],
    "amount":      [100, 2500, 700, 1800],
})

customers_df = pd.DataFrame({
    "customer_id": [1, 2, 3],
    "name":        ["Amit", "Riya", "Kabir"],
})

sf = SnowFrame()
sf.load({
    "sales":     sales_df,
    "customers": customers_df,
})

sf.sql("""
    CREATE TABLE final AS
    SELECT
        c.customer_id,
        c.name,
        SUM(s.amount) AS total_amount
    FROM sales s
    JOIN customers c
        ON s.customer_id = c.customer_id
    GROUP BY c.customer_id, c.name
""")

final_df = sf.to_df("final")
print(final_df)
```

---

## API reference

### `SnowFrame()`
Creates a new session backed by an in-memory DuckDB connection.

### `sf.load(data)`
Register one or more DataFrames.

```python
# Dict → named tables
sf.load({"sales": sales_df, "customers": customers_df})

# Tuple / list → auto-named table1, table2, …
sf.load((df1, df2, df3))
```

### `sf.register(name, df)`
Register a single DataFrame as a named table.

```python
sf.register("products", products_df)
```

### `sf.tables()`
Return a Pandas DataFrame listing all registered table names.

```python
sf.tables()
#    table_name
# 0   customers
# 1       sales
```

### `sf.sql(query)`
Execute any DuckDB SQL statement. Returns `self` for chaining.

```python
sf.sql("CREATE TABLE big AS SELECT * FROM sales WHERE amount > 1000")
sf.sql("DROP TABLE big")
```

### `sf.to_df(table_name)`
Read a table back into a Pandas DataFrame.

```python
final_df = sf.to_df("final")
```

### `sf.run_file(path)`
Execute all SQL statements in a `.sql` file (split on `;`).

```python
sf.run_file("examples/analysis.sql")
final_df = sf.to_df("final")
```

### `sf.to_csv(table_name, path)` / `sf.to_excel(table_name, path)`
Export a table to CSV or Excel.

```python
sf.to_csv("final", "output/final.csv")
sf.to_excel("final", "output/final.xlsx")   # requires openpyxl
```

### `sf.auto()`
Scan the calling scope and auto-register every Pandas DataFrame as a table.

```python
sales     = pd.DataFrame(...)
customers = pd.DataFrame(...)

sf = SnowFrame()
sf.auto()          # registers 'sales' and 'customers' automatically
```

### `sf.query_df(sql_text)`
Run a SELECT-style query and return a Pandas DataFrame directly.

```python
df = sf.query_df("SELECT * FROM sales WHERE amount > 1000")
```

### `sf.show(table_name, limit=10)`
Preview the first N rows of a table.

```python
sf.show("sales")           # first 10 rows
sf.show("final", limit=5)  # first 5 rows
```

### `sf.describe(table_name)`
Show column names and types (DuckDB `DESCRIBE`).

```python
sf.describe("sales")
```

### `sf.close()`
Close the underlying DuckDB connection.

---

## SQL file usage

Write SQL in a dedicated file and run it against a live session:

```sql
-- examples/analysis.sql
CREATE OR REPLACE TABLE summary AS
SELECT
    c.name,
    COUNT(s.amount)         AS num_orders,
    SUM(s.amount)           AS total_amount,
    ROUND(AVG(s.amount), 2) AS avg_amount
FROM sales s
JOIN customers c ON s.customer_id = c.customer_id
GROUP BY c.name
ORDER BY total_amount DESC;

CREATE OR REPLACE TABLE high_value AS
SELECT * FROM summary WHERE total_amount > 1000;
```

```python
sf = SnowFrame()
sf.load({"sales": sales_df, "customers": customers_df})
sf.run_file("examples/analysis.sql")

summary_df    = sf.to_df("summary")
high_value_df = sf.to_df("high_value")
```

---

## Notebook / Databricks-style usage

### Install

```bash
pip install -e ".[notebook]"
jupyter lab
```

### Setup cell

```python
%load_ext snowframe

import pandas as pd
from snowframe import SnowFrame, set_active_session

sales = pd.DataFrame({
    "customer_id": [1, 1, 2, 3, 3],
    "amount":      [100, 2500, 700, 1800, 300],
})
customers = pd.DataFrame({
    "customer_id": [1, 2, 3],
    "name":        ["Amit", "Riya", "Kabir"],
})

sf = SnowFrame()
sf.auto()              # auto-registers 'sales' and 'customers' from this scope
set_active_session(sf)
sf.tables()
```

### DDL cell — creates a table, prints success + table list

```sql
%%sf

CREATE OR REPLACE TABLE final AS
SELECT
    c.name,
    SUM(s.amount) AS total_amount
FROM sales s
JOIN customers c
    ON s.customer_id = c.customer_id
GROUP BY c.name
ORDER BY total_amount DESC;
```

### SELECT cell — displays result DataFrame inline

```sql
%%sf
SELECT * FROM final;
```

### SHOW TABLES cell

```sql
%%sf
SHOW TABLES;
```

### Back in Python

```python
final_df = sf.to_df("final")

sf.show("final")          # first 10 rows
sf.describe("final")      # column names and types
```

> **Databricks users:** The same pattern works in Databricks notebooks.
> Replace `%%sf` with a Python cell calling `sf.query_df("SELECT …")` or
> `sf.sql("CREATE …")` if cell magics are unavailable.

---

## CLI

```bash
# Execute a SQL file (no pre-loaded DataFrames; useful for DuckDB file-based tables)
snowframe run examples/analysis.sql
```

---

## Running the examples

```bash
pip install -e .
python examples/basic_usage.py
```

---

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Limitations

- **In-memory only** — all tables live in DuckDB's in-memory database. Nothing is persisted to disk unless you call `to_csv` / `to_excel`.
- **Single connection** — each `SnowFrame()` instance has its own isolated DuckDB connection; tables are not shared between sessions.
- **SQL file parsing** — `run_file` splits on `;`. SQL comments that contain semicolons (`-- note; ignore`) may cause incorrect splits. Use `--` comments without semicolons inside SQL files.
- **Table name safety** — `to_df(name)` interpolates the table name directly into SQL. Use only valid SQL identifiers as table names.
- **Excel export** — requires `openpyxl`: `pip install openpyxl` or `pip install -e ".[excel]"`.
- **CLI** — the `snowframe run` command has no mechanism to load Python DataFrames. It is useful for SQL that reads from DuckDB-native sources (e.g. `READ_CSV`, `READ_PARQUET`).
