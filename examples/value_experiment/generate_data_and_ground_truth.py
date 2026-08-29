"""
Deterministic, hand-authored synthetic data generator for the
Structifact Value Experiment. Everything here is a literal, explicit
data structure -- no randomness -- so the ground truth can be derived
by inspection and checked by a human.

Business scenario: orders -> order_lines, orders -> customers,
customers -> customer_status_history (status changes over time).
Correct customer status for an order = the status_history row with
the latest effective_date <= order_date (NOT the customer's current/
most-recent status overall).

Outputs (raw tables, seen by both experiment arms):
  customers.csv
  customer_status_history.csv
  orders.csv
  order_lines.csv

Ground truth (deliberately kept out of this directory until both
experiment arms had finished, so neither could see it):
  expected_result_per_order.csv (was ground_truth_per_order.csv)
  expected_result_summary.csv   (was ground_truth_summary.csv)
  GROUND_TRUTH_DERIVATION.md    (was DERIVATION_NOTES.md)

This copy is kept as-is (including its original scratchpad output
paths, now stale) for audit purposes -- it's the exact script that
produced every CSV in this directory. Do not re-run it in place; it
would overwrite the committed files at slightly different paths than
where they now live.
"""
import csv
import os

OUT_RAW = "/Users/michaellewis/dev/structifact/examples/value_experiment"
OUT_GT = "/private/tmp/claude-501/-Users-michaellewis-dev-structifact/ab566d4b-5e48-41e1-a87b-30b5cd5de8d0/scratchpad/value_experiment"

# ---------------------------------------------------------------------
# customers: customer_id, customer_name, signup_date
# ---------------------------------------------------------------------
customers = [
    ("C01", "Alder Manufacturing", "2023-11-01"),
    ("C02", "Brightview Logistics", "2023-12-10"),
    ("C03", "Cascade Retail Group", "2023-10-05"),
    ("C04", "Driftwood Supply Co", "2024-01-15"),
    ("C05", "Elmhurst Foods", "2023-09-20"),
    ("C06", "Fenwick Hardware", "2024-02-01"),
    ("C07", "Granite Peak Industrial", "2023-08-01"),
    ("C08", "Harborline Freight", "2023-11-20"),
    ("C09", "Ironwood Fabrication", "2023-07-15"),
    ("C10", "Juniper Textiles", "2024-01-01"),
    ("C11", "Kestrel Components", "2023-10-25"),
    ("C12", "Lakeside Provisions", "2024-04-15"),
    ("C13", "Meridian Tools", "2023-06-01"),
    ("C14", "Northfield Chemicals", "2023-09-01"),
    ("C15", "Oakridge Electronics", "2023-12-01"),
]

# ---------------------------------------------------------------------
# customer_status_history: customer_id, effective_date, status
# One row per status period; a customer with N status changes has N
# rows. status in {trial, active, at_risk, churned, reactivated}.
# ---------------------------------------------------------------------
status_history = [
    # C01 -- single status, never changes
    ("C01", "2024-01-01", "trial"),

    # C02 -- trial -> active (change lands between several order dates)
    ("C02", "2024-01-01", "trial"),
    ("C02", "2025-02-15", "active"),

    # C03 -- trial -> active -> at_risk (two changes)
    ("C03", "2024-01-01", "trial"),
    ("C03", "2025-01-10", "active"),
    ("C03", "2025-04-01", "at_risk"),

    # C04 -- single status, never changes
    ("C04", "2024-06-01", "active"),

    # C05 -- active -> churned -> reactivated
    ("C05", "2024-01-01", "active"),
    ("C05", "2025-03-01", "churned"),
    ("C05", "2025-05-01", "reactivated"),

    # C06 -- trial -> active, but the change happens BEFORE any order
    # in this dataset, so as-of and current agree on every order here
    # (included as a control case that still exercises "pick the
    # latest effective_date <= order_date" without producing a
    # divergence).
    ("C06", "2024-03-01", "trial"),
    ("C06", "2024-09-01", "active"),

    # C07 -- single status, never changes
    ("C07", "2024-01-01", "at_risk"),

    # C08 -- active -> at_risk
    ("C08", "2024-02-01", "active"),
    ("C08", "2025-03-15", "at_risk"),

    # C09 -- single status, never changes
    ("C09", "2024-01-01", "churned"),

    # C10 -- single status, never changes
    ("C10", "2024-04-01", "active"),

    # C11 -- trial -> active -> churned (two changes)
    ("C11", "2024-05-01", "trial"),
    ("C11", "2024-12-01", "active"),
    ("C11", "2025-05-20", "churned"),

    # C12 -- single status; deliberately has one order (see below)
    # placed BEFORE this row's effective_date, to test the "no status
    # history exists yet as of this order" edge case.
    ("C12", "2024-06-01", "trial"),

    # C13 -- single status, never changes
    ("C13", "2024-01-01", "active"),

    # C14 -- single status, never changes
    ("C14", "2024-02-01", "at_risk"),

    # C15 -- single status, never changes
    ("C15", "2024-03-01", "active"),
]

# ---------------------------------------------------------------------
# orders: order_id, customer_id, order_date
# ---------------------------------------------------------------------
orders = [
    # C01 -- control, always trial
    ("O001", "C01", "2024-12-01"),
    ("O002", "C01", "2025-02-10"),
    ("O003", "C01", "2025-05-01"),

    # C02 -- DIVERGENT: two orders before the trial->active change,
    # two after
    ("O004", "C02", "2024-12-01"),
    ("O005", "C02", "2025-01-20"),
    ("O006", "C02", "2025-03-10"),
    ("O007", "C02", "2025-05-01"),

    # C03 -- DIVERGENT: one order in each of the three status windows,
    # plus one more in the final window
    ("O008", "C03", "2024-12-15"),
    ("O009", "C03", "2025-02-01"),
    ("O010", "C03", "2025-04-15"),
    ("O011", "C03", "2025-06-01"),

    # C04 -- control, always active
    ("O012", "C04", "2024-12-05"),
    ("O013", "C04", "2025-04-01"),

    # C05 -- DIVERGENT: active window, churned window, reactivated window
    ("O014", "C05", "2024-12-01"),
    ("O015", "C05", "2025-03-15"),
    ("O016", "C05", "2025-05-10"),

    # C06 -- control (status change predates all orders here)
    ("O017", "C06", "2024-12-01"),
    ("O018", "C06", "2025-02-01"),
    ("O019", "C06", "2025-05-15"),

    # C07 -- control, always at_risk
    ("O020", "C07", "2024-12-10"),
    ("O021", "C07", "2025-03-01"),

    # C08 -- DIVERGENT: active window (two orders), at_risk window
    ("O022", "C08", "2024-11-10"),
    ("O023", "C08", "2025-02-01"),
    ("O024", "C08", "2025-04-01"),

    # C09 -- control, always churned
    ("O025", "C09", "2025-01-15"),

    # C10 -- control, always active
    ("O026", "C10", "2024-12-20"),
    ("O027", "C10", "2025-03-05"),
    ("O028", "C10", "2025-06-01"),

    # C11 -- DIVERGENT: trial window, active window, churned window
    ("O029", "C11", "2024-11-15"),
    ("O030", "C11", "2025-01-05"),
    ("O031", "C11", "2025-06-10"),

    # C12 -- EDGE CASE: this order predates the customer's only
    # status_history row entirely (order 2024-05-01 vs. status
    # effective 2024-06-01) -- no status is in effect yet as of this
    # order date. Second order is normal (after the status exists).
    ("O032", "C12", "2024-05-01"),
    ("O033", "C12", "2025-01-10"),

    # C13 -- control, always active
    ("O034", "C13", "2024-12-01"),
    ("O035", "C13", "2025-04-20"),

    # C14 -- control, always at_risk
    ("O036", "C14", "2024-12-15"),
    ("O037", "C14", "2025-05-01"),

    # C15 -- control, always active
    ("O038", "C15", "2024-12-10"),
    ("O039", "C15", "2025-03-20"),
]

# ---------------------------------------------------------------------
# order_lines: order_line_id, order_id, sku, quantity, unit_price
# Deterministic (not random) -- derived from a fixed per-order pattern
# so every order's revenue is easy to hand-verify. Each order gets 1
# or 2 lines depending on the order's position (even index -> 1 line,
# odd index -> 2 lines), with quantity/unit_price derived from the
# order's numeric suffix so no two orders accidentally collide.
# ---------------------------------------------------------------------
SKUS = ["WIDGET-A", "WIDGET-B", "GADGET-C", "PART-D", "KIT-E"]

order_lines = []
line_seq = 1
for idx, (order_id, _cust, _date) in enumerate(orders):
    n = int(order_id[1:])  # e.g. "O014" -> 14
    num_lines = 1 if idx % 2 == 0 else 2
    for j in range(num_lines):
        sku = SKUS[(n + j) % len(SKUS)]
        quantity = 1 + ((n * 3 + j * 7) % 6)          # 1..6
        unit_price = round(10.00 + ((n * 13 + j * 5) % 40) + 0.50, 2)  # varied, .50-ending
        order_lines.append((f"L{line_seq:04d}", order_id, sku, quantity, unit_price))
        line_seq += 1

# ---------------------------------------------------------------------
# Write raw tables (these four files are ALL either experiment arm
# gets to see, along with REQUIREMENTS.md)
# ---------------------------------------------------------------------
os.makedirs(OUT_RAW, exist_ok=True)
os.makedirs(OUT_GT, exist_ok=True)

with open(os.path.join(OUT_RAW, "customers.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["customer_id", "customer_name", "signup_date"])
    w.writerows(customers)

with open(os.path.join(OUT_RAW, "customer_status_history.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["customer_id", "effective_date", "status"])
    w.writerows(status_history)

with open(os.path.join(OUT_RAW, "orders.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "customer_id", "order_date"])
    w.writerows(orders)

with open(os.path.join(OUT_RAW, "order_lines.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order_line_id", "order_id", "sku", "quantity", "unit_price"])
    w.writerows(order_lines)

# ---------------------------------------------------------------------
# Ground truth computation -- plain Python, no SQL of any kind.
# ---------------------------------------------------------------------
from collections import defaultdict
from datetime import date

def d(s):
    y, m, day = s.split("-")
    return date(int(y), int(m), int(day))

history_by_customer = defaultdict(list)
for cust, eff, status in status_history:
    history_by_customer[cust].append((d(eff), status))
for cust in history_by_customer:
    history_by_customer[cust].sort()

def as_of_status(cust, order_date):
    od = d(order_date)
    candidates = [s for (eff, s) in history_by_customer[cust] if eff <= od]
    if not candidates:
        return None  # no status history in effect yet
    # last candidate in sorted order = latest eff <= od
    eligible = [(eff, s) for (eff, s) in history_by_customer[cust] if eff <= od]
    eligible.sort()
    return eligible[-1][1]

def current_status(cust):
    return history_by_customer[cust][-1][1]  # latest effective_date overall

revenue_by_order = defaultdict(float)
for _lid, order_id, _sku, qty, price in order_lines:
    revenue_by_order[order_id] += round(qty * price, 2)

rows = []
for order_id, cust, order_date in orders:
    aos = as_of_status(cust, order_date)
    cur = current_status(cust)
    rows.append({
        "order_id": order_id,
        "customer_id": cust,
        "order_date": order_date,
        "as_of_status": aos if aos is not None else "UNKNOWN_NO_HISTORY_YET",
        "current_status": cur,
        "diverges": (aos != cur),
        "order_revenue": round(revenue_by_order[order_id], 2),
    })

with open(os.path.join(OUT_GT, "ground_truth_per_order.csv"), "w", newline="") as f:
    fieldnames = ["order_id", "customer_id", "order_date", "as_of_status",
                  "current_status", "diverges", "order_revenue"]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

# Aggregate: total revenue by status, computed two ways
agg_as_of = defaultdict(float)
agg_current = defaultdict(float)
for r in rows:
    agg_as_of[r["as_of_status"]] += r["order_revenue"]
    agg_current[r["current_status"]] += r["order_revenue"]

all_statuses = sorted(set(agg_as_of) | set(agg_current))
with open(os.path.join(OUT_GT, "ground_truth_summary.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["status", "total_revenue_as_of_order_date", "total_revenue_current_status"])
    for s in all_statuses:
        w.writerow([s, round(agg_as_of.get(s, 0.0), 2), round(agg_current.get(s, 0.0), 2)])

diverging = [r for r in rows if r["diverges"]]

notes = []
notes.append("# Ground truth derivation notes\n")
notes.append(
    "Computed entirely in plain Python (see generate.py) by, for each "
    "order, scanning that customer's status_history rows and picking "
    "the one with the latest effective_date <= the order's order_date. "
    "No SQL was written or run to produce this file.\n"
)
notes.append(f"\nTotal orders: {len(rows)}. Orders where as-of-date status "
             f"differs from the customer's current/most-recent status: "
             f"{len(diverging)}.\n")
notes.append("\n## Diverging orders (as-of status != current status)\n")
for r in diverging:
    notes.append(
        f"- {r['order_id']} (customer {r['customer_id']}, dated "
        f"{r['order_date']}): as-of status = **{r['as_of_status']}**, "
        f"but current status = **{r['current_status']}**. Revenue "
        f"${r['order_revenue']:.2f} would be attributed to the wrong "
        f"status bucket if 'current status' were used instead of "
        f"'status as of order date'.\n"
    )
unknowns = [r for r in rows if r["as_of_status"] == "UNKNOWN_NO_HISTORY_YET"]
notes.append("\n## Edge case: order predates any status history\n")
for r in unknowns:
    notes.append(
        f"- {r['order_id']} (customer {r['customer_id']}, dated "
        f"{r['order_date']}): no status_history row has "
        f"effective_date <= {r['order_date']} yet, so no status can "
        f"be determined as of that date. Current status is "
        f"'{r['current_status']}', which would be WRONG to backfill "
        f"onto this order.\n"
    )

with open(os.path.join(OUT_GT, "DERIVATION_NOTES.md"), "w") as f:
    f.write("".join(notes))

print(f"Wrote raw tables to {OUT_RAW}")
print(f"Wrote ground truth to {OUT_GT}")
print(f"{len(rows)} orders, {len(diverging)} diverging, {len(unknowns)} unknown-history edge case(s)")
