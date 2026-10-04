-- Simulated production query: the "look up my orders" endpoint.
--
-- This is the query demo_postmerge.py will run repeatedly to trigger a live
-- regression. `customer_email` has no index (see sandbox/init.sql), so on a
-- 100k+ row `orders` table this forces a sequential scan every single call.
--
-- Query metadata (used by prod_watcher.py to build the incident):
--   query_fingerprint: qf_orders_by_customer_email
--   introduced_by_commit_sha: e4f5a6b   (a fake "deploy" that shipped this endpoint)

SELECT id, status, total_cents, created_at
FROM orders
WHERE customer_email = %(email)s
ORDER BY created_at DESC;
