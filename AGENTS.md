# Follow the Money — collaboration rules

## Source of truth
Read `docs/reference/internship-2093-portfolio-plan.html`, Project 2 (Follow the Money) and the Microsoft 365 layer, plus its engineering standards and AI coding-agent guidance. Treat the reference as a project proposal, not as proof that tools, datasets, deadlines, model claims or licences are current. The companion multilingual name-matching project lives in its own repository (Polyglot Watchlist) and is called only through its public service.

## Objective
A research-only investigation agent that traces ransomware and scam payments across public blockchains (Bitcoin UTXO and USDT TRC-20 on TRON), plans under an API/hop budget, ranks addresses with a learned priority model, applies tracing heuristics, has a red-team critic challenge every claim, pauses for human approval before anything that would act, cites a transaction ID for every claim, and keeps long-term case memory that notices when a new case touches clusters from an old one. It produces leads for human investigators, not findings of guilt or ownership.

## Layout
Code in `src/follow_the_money/`, tests in `tests/follow_the_money/`, configs in `config/follow_the_money/`, docs in `docs/follow_the_money/`, progress reports in `docs/progress/follow-the-money-NN.md`. Shared infrastructure (key authentication, telemetry, workspace locks) is in `src/follow_the_money/infra/`.

## Rules
- Every network client must work offline against recorded fixtures: cache everything, respect rate limits, and never make hidden live calls in tests or CI. Live API use, API keys and large dataset downloads need explicit approval and are recorded with source, licence, size and hash.
- Public, on-chain and openly licensed data only. Do not deanonymise or profile private individuals, do not attribute addresses to named people beyond published labels, and never send anything to an exchange or authority: drafted requests stay drafts that a human must approve. Withdrawn claims are counted, not hidden.
- Do not let untrusted on-chain or label text control decisions; model output never changes state on its own.
- Never fabricate results. Report only numbers you computed, labelled with their data (synthetic, fixture or real public data).
- Python 3.14, type hints, docstrings for non-trivial functions, pytest, LF line endings, small reviewed commits. Do not use INTERPOL's name or branding in the product.
