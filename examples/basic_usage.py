"""SnowFrame basic usage example.

Run with:
    python examples/basic_usage.py
"""

import pandas as pd
from snowframe import SnowFrame

# ── Sample data ────────────────────────────────────────────────────────────────

sales_df = pd.DataFrame({
    "customer_id": [1, 1, 2, 3],
    "amount":      [100, 2500, 700, 1800],
})

customers_df = pd.DataFrame({
    "customer_id": [1, 2, 3],
    "name":        ["Amit", "Riya", "Kabir"],
})

# ── Create a session and load data ─────────────────────────────────────────────

sf = SnowFrame()
sf.load({
    "sales":     sales_df,
    "customers": customers_df,
})

print("Registered tables:")
print(sf.tables(), "\n")

# ── Run SQL ────────────────────────────────────────────────────────────────────

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
    ORDER BY total_amount DESC
""")

# ── Convert back to Pandas ─────────────────────────────────────────────────────

final_df = sf.to_df("final")
print("Query result:")
print(final_df, "\n")

# ── Export ─────────────────────────────────────────────────────────────────────

sf.to_csv("final", "/tmp/snowframe_final.csv")
print("Exported to /tmp/snowframe_final.csv")

# ── Run a SQL file ─────────────────────────────────────────────────────────────

sf.run_file("examples/analysis.sql")

summary_df = sf.to_df("summary")
print("\nSummary (from SQL file):")
print(summary_df)

high_value_df = sf.to_df("high_value")
print("\nHigh-value customers (from SQL file):")
print(high_value_df)

# ── Auto-naming with tuple load ────────────────────────────────────────────────

sf2 = SnowFrame()
sf2.load((sales_df, customers_df))
print("\nAuto-named tables:")
print(sf2.tables())
