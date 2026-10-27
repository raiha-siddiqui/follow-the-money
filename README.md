# Follow the Money

A research agent that traces ransomware and scam payments across public blockchains (Bitcoin and USDT on TRON) under a fixed budget, has a red-team critic challenge every claim, and pauses for **human approval** before anything is reported. Every claim cites a transaction ID, and approved cases are remembered so that a new case touching money from an old one is flagged.

> Research prototype. It produces **leads for human investigators**, not findings of identity, ownership, guilt or current sanctions status. Nothing is ever sent to an exchange or an authority: drafted requests stay drafts. Tests and the default configuration replay recorded data and make no live network calls.

## What is inside

| Part | What it does |
| --- | --- |
| Explorer clients | Typed Bitcoin (Esplora/mempool.space) and TRON (TronGrid/TronScan) clients with caching, rate limits, budgets and a replay mode used by every test. |
| Tracing heuristics | Common-input clustering with a size cap, change detection as a probability, peel-chain and CoinJoin detection, TRC-20 transfer and Tether freeze handling. |
| Priority models | GraphSAGE, GAT and XGBoost trained with a temporal split, an out-of-distribution guard with heuristic fallback, a change-output classifier and a value model trained on the agent's own traces. |
| Agent | A LangGraph loop: planner → pick next address → call tools → reflect (continue, backtrack or stop) → independent critic → human approval interrupt → case report → case memory. |
| Interfaces | FastAPI, an MCP server (stdio and streamable HTTP), a Streamlit review UI, and Microsoft 365 artefacts (Copilot Studio instructions, declarative-agent manifest, API plugin, Adaptive Card approvals, local Agents SDK wrapper). |
| Name resolution (optional) | When a sanctioned wallet has a published owner name, it can be resolved across scripts by the companion project [Polyglot Watchlist](https://github.com/raiha-siddiqui/Polyglot_watchlist), if that package is installed. |

Model-facing clients (MCP, Copilot) hold **agent** keys: they can start traces and read bounded summaries. Only a separate human **approver** key can approve, and the creator of a case cannot approve it.

## Quick start

Python 3.14 and [uv](https://docs.astral.sh/uv/) 0.13.5.

```bash
uv sync --locked --dev
uv run --no-sync python -m follow_the_money demo --workspace data/follow_the_money/my-demo
uv run --no-sync pytest -q
```

Add `--extra ml` for the model experiments and `--extra m365` for the Microsoft 365 wrapper. The full guide — keys, API, UI, MCP, evaluation and Microsoft 365 — is in [docs/follow_the_money/README.md](docs/follow_the_money/README.md). The original project brief is in [docs/reference](docs/reference/internship-2093-portfolio-plan.html), and the phase-by-phase records are in [docs/progress](docs/progress/follow-the-money-final.md).

## Results so far

- Reproduces a hop described in the public US Department of Justice filing on the 2021 Colonial Pipeline ransom (1.33272285 BTC, then 1.2401626 BTC onward), from recorded data.
- On synthetic tasks, priority search reaches the endpoint in 3 queries where breadth-first search needs 16.
- Priority models were trained on a **synthetic** temporal graph; real-data accuracy is not claimed yet.

## Still to do

| Item | Needs |
| --- | --- |
| Train the priority models on real labelled data | Licensed access to the Elliptic++ dataset |
| Live TRON tracing | A TronGrid API key and an approved, bounded recording run |
| Hosting and Microsoft 365 deployment | Azure, Hugging Face and Microsoft 365 tenant accounts |
| Real-world evaluation | Independently adjudicated real cases |

## License

[MIT](LICENSE). Not affiliated with any law-enforcement agency.
