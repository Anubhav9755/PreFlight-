"""
Seeds the PreFlight sandbox with realistic data volume.

Run this AFTER `docker compose up -d` (the container needs to exist first).
Safe to re-run: truncates and reloads every time so the demo is repeatable.

Usage:
    python seed.py                 # default: 5,000 users / 100,000 orders
    python seed.py --orders 20000  # smaller/faster for quick iteration
"""

import argparse
import random
import sys
import time
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import SANDBOX_DSN as DB_DSN

REGIONS = ["us-east", "us-west", "eu-west", "ap-south", "sa-east"]
ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled", "refunded"]
SKUS = [f"SKU-{i:04d}" for i in range(1, 201)]


def wait_for_db(retries: int = 20, delay: float = 1.5) -> None:
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(DB_DSN)
            conn.close()
            return
        except psycopg2.OperationalError:
            print(f"  ...sandbox not ready yet, retrying ({attempt + 1}/{retries})")
            time.sleep(delay)
    raise RuntimeError(
        "Could not connect to the sandbox. Is `docker compose up -d` running in sandbox/?"
    )


def seed(num_users: int, num_orders: int) -> None:
    print("Waiting for sandbox to accept connections...")
    wait_for_db()

    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    print("Truncating existing data (safe to re-run)...")
    cur.execute("TRUNCATE order_items, orders, users RESTART IDENTITY CASCADE;")

    print(f"Inserting {num_users:,} users...")
    users = [
        (f"user{i}@example.com", random.choice(REGIONS))
        for i in range(1, num_users + 1)
    ]
    execute_values(
        cur, "INSERT INTO users (email, region) VALUES %s", users, page_size=2000
    )

    print(f"Inserting {num_orders:,} orders (this is the table the demo weaknesses target)...")
    orders = []
    for _ in range(num_orders):
        user_id = random.randint(1, num_users)
        orders.append(
            (
                user_id,
                f"user{user_id}@example.com",
                random.choice(ORDER_STATUSES),
                random.randint(500, 50000),
            )
        )
    execute_values(
        cur,
        "INSERT INTO orders (user_id, customer_email, status, total_cents) VALUES %s",
        orders,
        page_size=5000,
    )

    print("Inserting order_items (1-4 per order)...")
    cur.execute("SELECT id FROM orders;")
    order_ids = [row[0] for row in cur.fetchall()]
    items = []
    for oid in order_ids:
        for _ in range(random.randint(1, 4)):
            items.append(
                (
                    oid,
                    random.choice(SKUS),
                    random.randint(1, 5),
                    random.randint(300, 20000),
                )
            )
    execute_values(
        cur,
        "INSERT INTO order_items (order_id, product_sku, quantity, unit_price_cents) VALUES %s",
        items,
        page_size=5000,
    )

    print("Running ANALYZE so the planner has real statistics (matters for EXPLAIN ANALYZE realism)...")
    cur.execute("ANALYZE users; ANALYZE orders; ANALYZE order_items;")
    cur.execute("SELECT pg_stat_statements_reset();")

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Seeded {num_users:,} users, {num_orders:,} orders, {len(items):,} order_items.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=5000)
    parser.add_argument("--orders", type=int, default=100000)
    args = parser.parse_args()
    seed(args.users, args.orders)
