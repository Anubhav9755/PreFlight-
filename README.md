# PreFlight — Build Notes

This is the demo-scoped build. Full architecture per the synopsis; some
pieces are simulated instead of wired to real GitHub/CI infrastructure —
see "Known simplifications" at the bottom for exactly what's simulated
and why.

## 1. One-time setup (whoever gets here first, ~10 min)

```bash
cd preflight
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env, paste your GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)

cd sandbox
docker compose up -d
cd ..
python sandbox/seed.py             # takes ~30-60s, seeds 5k users / 100k orders
```

Verify the sandbox is alive:
```bash
docker exec -it preflight_sandbox_db psql -U preflight -d preflight_sandbox -c "SELECT count(*) FROM orders;"
```
Should print ~100000.

## 2. Everyone's individual pieces

Each agent works standalone against `seeded_incidents/*.json` — you don't need
the whole pipeline running to test your piece. Feed it a hand-written incident
JSON (see `schemas/incident.json` for the shape) or run the upstream agent
first to generate a real one.

Quick manual tests:
```bash
# Monitor
python monitor/ci_watcher.py --file sandbox/weaknesses/001_add_status_index.sql --pr 142 --commit a1b2c3d
python monitor/prod_watcher.py --simulate-traffic 25

# Diagnoser (needs an incident_id from above)
python diagnoser/diagnoser.py <incident_id>

# Fixer (needs a diagnosed incident_id)
python fixer/fixer.py <incident_id>
```

## 3. Full pipeline (once your own piece works standalone)

```bash
python demo/demo_premerge.py
python demo/demo_postmerge.py
streamlit run dashboard/app.py     # click Approve to finish beat 2
```

## 4. Resetting between rehearsals

```bash
bash sandbox/reset_sandbox.sh      # full wipe + reseed, ~1 min
rm seeded_incidents/*.json         # just clear incident history, keep data
```

The demo scripts (`demo_premerge.py` / `demo_postmerge.py`) also drop their
own index before running, so you can re-run them repeatedly without a full
sandbox reset — only do the full reset if numbers look off or you want a
totally clean slate before the real presentation.

## Project layout

```
common/          shared config, DB helpers, LLM wrapper, incident read/write
schemas/         incident.json - the contract, don't change without telling everyone
sandbox/         docker-compose, schema, seed script, the two seeded weaknesses
monitor/         CI Watcher + Production Watcher
diagnoser/       EXPLAIN ANALYZE / lock timing + deploy-history bisection + Claude
fixer/           fix generation + real benchmark + risk scoring
reporter/        PR comment + postmortem markdown + approve/reject
dashboard/       Streamlit app
orchestration/   the actual LangGraph graph wiring it all together
demo/            the two rehearsed demo scripts
```

## Known simplifications (say these out loud if judges ask, don't hide them)

- CI Watcher is triggered by a script pointed at a file, not a live GitHub
  webhook — same input/output shape, swap-in-able later.
- Deploy history for bisection is a short hardcoded JSON list, not `git log`.
- No real GitHub PR is posted to; the PR comment is rendered and shown, not
  posted (posting for real is the stretch goal in the roadmap if there's time).
- No Chroma / knowledge base yet — every other piece of the architecture in
  the synopsis is real and running.
