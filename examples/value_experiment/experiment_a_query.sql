-- Order revenue attributed to customer status as-of the order date.
--
-- Note on an oddity in the sample data: order O032 (customer C12,
-- order_date 2024-05-01) is dated *before* C12's earliest recorded
-- status (2024-06-01, trial). Per REQUIREMENTS.md ("don't guess ...
-- that order simply has no determinable status as of its date"),
-- this order correctly resolves to a NULL status below and is
-- reported that way in the outputs, not hand-corrected.

-- Revenue per order, from line items.
WITH order_revenue AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        SUM(ol.quantity * ol.unit_price) AS revenue
    FROM read_csv_auto('orders.csv') AS o
    JOIN read_csv_auto('order_lines.csv') AS ol
        ON ol.order_id = o.order_id
    GROUP BY o.order_id, o.customer_id, o.order_date
),

-- For each order, the most recent status change for that customer
-- with an effective_date on or before the order date. If no such
-- row exists, resolved_status is left NULL (no determinable status).
per_order AS (
    SELECT
        r.order_id,
        r.customer_id,
        r.order_date,
        r.revenue,
        (
            SELECT h.status
            FROM read_csv_auto('customer_status_history.csv') AS h
            WHERE h.customer_id = r.customer_id
              AND h.effective_date <= r.order_date
            ORDER BY h.effective_date DESC
            LIMIT 1
        ) AS resolved_status
    FROM order_revenue r
)

SELECT
    order_id,
    customer_id,
    order_date,
    resolved_status,
    revenue
FROM per_order
ORDER BY order_id;
