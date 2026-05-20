-- SnowFrame example SQL file
-- Run with: sf.run_file("examples/analysis.sql")
--
-- Assumes "sales" and "customers" tables are already loaded in the session:
--   sf.load({"sales": sales_df, "customers": customers_df})

CREATE OR REPLACE TABLE summary AS
SELECT
    c.name,
    COUNT(s.amount)         AS num_orders,
    SUM(s.amount)           AS total_amount,
    ROUND(AVG(s.amount), 2) AS avg_amount
FROM sales s
JOIN customers c
    ON s.customer_id = c.customer_id
GROUP BY c.name
ORDER BY total_amount DESC;

CREATE OR REPLACE TABLE high_value AS
SELECT *
FROM summary
WHERE total_amount > 1000
ORDER BY total_amount DESC;
