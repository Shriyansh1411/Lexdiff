# Lexdiff: diff the law, test the code

When a regulation changes, Lexdiff finds the code that now breaks it, writes the failing test first,
proves the fix (**fails on the base, passes on the fix**), and issues a graded certificate that
**never says "compliant"**. *AI proposes; deterministic checks decide.*

The bundled demo is **Lendwise**, a fictional non-bank lender, checked against excerpts of the FTC
Safeguards Rule (16 CFR 314): multi-factor authentication (§314.4(c)(5)), no readable customer data
(§314.4(c)(3)), the 30-day FTC notice (§314.4(j)(1)), and change management (§314.4(c)(7), human review).

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make test        # engine tests
make demo        # all nine stages on the demo, writes .lexdiff/certificate.html
make guard-base  # the CI gate on the broken app: one finding per violation, exit 1
make benchmark   # Lexdiff vs a keyword search on the tagged demo app
make dashboard   # Streamlit UI
make demo-git    # the same proof with base/head taken from git refs
```

No API key or network is needed: without `LEXDIFF_LLM_API_KEY` a deterministic drafter is used.

## Architecture

```
 INPUTS                       LEXDIFF ENGINE (Python)                      OUTPUTS
 ┌────────────────┐     ┌──────────────────────────────────────┐     ┌──────────────────────┐
 │ regulation v1  │ ──▶ │ 2 Redline ─▶ 3 Obligations           │ ──▶ │ locked obligation    │
 │ regulation v2  │     │ 1 Screen     (verbatim quotes)       │     │ tests                │
 │ target repo    │ ──▶ │ 4 Impact map ─▶ 5 Failing tests      │ ──▶ │ graded certificate   │
 │ (base + fix)   │     │ 6 Canary ─▶ 7 Prove ─▶ 8 Evidence    │     │ (JSON + HTML)        │
 └────────────────┘     │ 9 Guard (zero LLM, CI)               │ ──▶ │ CI check + annotations│
                        └───────▲──────────────────▲───────────┘     └──────────────────────┘
                                │                  │
                  LLM API (temp 0, JSON,     Named human approves
                  drafts + screening only)   obligations and test rewrites
```

| # | Stage | Module | Uses a model? |
|---|-------|--------|---------------|
| 1 | **Screen**: flag comments aimed at AI agents (prompt injection) | `lexdiff/screen.py` | optional second opinion |
| 2 | **Redline**: clause-level diff, renumbering set aside | `lexdiff/regulation/` | no |
| 3 | **Obligations**: draft from clause text; quotes must be verbatim; human approves | `lexdiff/obligations/` | optional drafter |
| 4 | **Impact**: code graph of routes, mounted blueprints, SQL view aliases (`ssn → tin`), log/file sinks | `lexdiff/graph.py` | no |
| 5 | **Failing tests first**: checks planned from the graph, tests generated and hash-locked | `obligations/planner.py`, `testgen.py` | no |
| 6 | **Canary**: plant a synthetic SSN + account, run the app, sweep logs, exports, database | `lexdiff/canary/` | no |
| 7 | **Prove**: every test must fail on base and pass on the fix; own tests stay green; locked tests unchanged | `lexdiff/proof/` | no |
| 8 | **Evidence**: Verified / Partially verified / Unverified / Human review required | `lexdiff/evidence.py` | no |
| 9 | **Guard**: static CI gate, fails the PR on the exact line and cites the clause | `lexdiff/guard.py` | no |

Only steps 1 and 3 can call a model. Every pass or fail comes from code.

## Tech stack

Python 3.12 · `difflib` (redline) · `ast` (code graph) · Flask + SQLite (demo target) · OpenAI-compatible
LLM API at temperature 0 with JSON output · pytest (with a built-in unittest fallback) · git (`repo@ref`
sources) · GitHub Actions (PR check) · Streamlit (dashboard) · argparse CLI.

## Commands

```
python -m lexdiff run        --base DIR --head DIR --reg-old FILE --reg-new FILE --approver "Name"
python -m lexdiff redline    --old FILE --new FILE
python -m lexdiff draft      --old FILE --new FILE
python -m lexdiff validate   compliance/drafts --regulation FILE     # rejects paraphrased quotes
python -m lexdiff approve    SG-5 --by "Name"
python -m lexdiff graph      --target DIR
python -m lexdiff gen-tests  --target DIR [--allow-rewrite --by NAME --reason WHY]
python -m lexdiff canary     --target DIR
python -m lexdiff verify     --base DIR|repo@ref --head DIR|repo@ref
python -m lexdiff guard      --target DIR [--format text|json|github]   # exit 1 on findings
python -m lexdiff benchmark  --target DIR
python -m lexdiff fetch-ecfr --date 2026-09-01 --out FILE               # needs network
python -m lexdiff dashboard
```

`run` stops after stage 3 until a named human approves the obligations (`--approver`).

## Use it on your own repository

Add a `lexdiff_target.json` at the root of the repo (see `demo/lendwise_base/lexdiff_target.json`):

| Key | Meaning |
|-----|---------|
| `app_factory` | `module:function` returning a Flask app |
| `data_dir_env` | env var your app reads for its log/export/db directory (lets the canary sandbox it) |
| `public_routes` | routes allowed without a second factor |
| `sensitive_names` | column/variable names that hold regulated data |
| `mfa` | decorator name, request header, `module:function` returning a valid code, denial header |
| `notice` | `module` + `function` that decides FTC notification |
| `canary` | synthetic values, store paths, an HTTP scenario, background jobs |

The engine is framework-agnostic except the route detector and canary driver, which currently support
Flask-style decorators (`@bp.get`, `@app.route`) and the Flask test client.

## LLM configuration

```bash
export LEXDIFF_LLM_API_KEY=sk-...           # enables the model; unset = deterministic offline drafter
export LEXDIFF_LLM_MODEL=gpt-4o-mini        # any chat model
export LEXDIFF_LLM_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible server
```

A model may only draft from the verbatim clause text it is given. Every quote it returns passes the same
verbatim validator as a human-written one, and bad output falls back to the offline drafter.

## Demo results (computed, not hard-coded)

Lendwise has **11 planted violations and 2 decoys**, tagged `PLANTED:` / `DECOY:` in the source.
Run `make benchmark`. Expected: Lexdiff finds 9 of 11 with 8 guard findings (each citing a clause) plus the
canary's database hit, flags 0 decoys, and **reports the 2 it misses** (MD5 password hashing, hard-coded secret:
no rule pack yet). `make demo` grades SG-5 and SG-9 **Verified**, SG-3 **Partially verified** (plaintext
`ssn` / `account_number` remain in SQLite on purpose), SG-7 **Human review required**.

## Limits (read before relying on it)

* The regulation files in `data/regulation/` are **abridged demo excerpts**. Fetch and check the official text
  from eCFR before using any output; clause wording here is not a substitute for the law.
* One seeded app, built by us. The numbers show the method works, not that it works on your codebase.
* Only obligations that can be checked in code are covered; policies, training and vendor oversight are not.
* Route detection and the canary currently target Flask. The graph is static analysis and will miss dynamic routing.
* Not legal advice. A certificate states what automated checks verified and never that anyone is compliant.

## Layout

```
lexdiff/            engine (cli, pipeline, regulation, obligations, graph, guard, canary, proof, evidence, benchmark)
demo/lendwise_base  non-compliant demo lender (11 planted violations, 2 decoys)
demo/lendwise_fixed the same app after remediation
compliance/         drafts (a rejected paraphrase), approved test-rewrite log; obligations + locked tests are generated
data/regulation/    demo regulation excerpts (2021 and 2026 versions)
dashboard/app.py    Streamlit view over the pipeline's outputs
tests/              engine test-suite
.github/workflows/  PR check
```
