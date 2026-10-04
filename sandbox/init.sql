-- Runs automatically on first container start (docker-entrypoint-initdb.d)

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Baseline schema for the "target system" PreFlight is protecting.
-- Deliberately realistic e-commerce shape so the demo weaknesses feel real.

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    region          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    customer_email  TEXT NOT NULL,          -- intentionally NOT indexed (weakness #2 target)
    status          TEXT NOT NULL,
    total_cents     INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(id),
    product_sku     TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL
);

-- Baseline indexes that a normal team WOULD have (so the two weaknesses stand out
-- as specific, deliberate gaps rather than "nothing is indexed").
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Reset pg_stat_statements so demo numbers aren't polluted by seed/init queries.
SELECT pg_stat_statements_reset();
