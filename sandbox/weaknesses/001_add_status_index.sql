-- Simulated pull request: "Add index on orders.status to speed up admin dashboard filtering"
--
-- This is the file CI Watcher will be pointed at for the pre-merge demo beat.
-- It LOOKS like a reasonable, well-intentioned migration. The problem: on a
-- 100k+ row table, a plain CREATE INDEX takes an ACCESS EXCLUSIVE lock for the
-- duration of the build, blocking writes to `orders` (including new orders
-- coming in) until it finishes. That's the bug PreFlight should catch.
--
-- PR metadata (used by ci_watcher.py to build the incident):
--   pr_number: 142
--   commit_sha: a1b2c3d
--   file_path: migrations/0007_add_status_index.sql

CREATE INDEX idx_orders_status ON orders (status);
