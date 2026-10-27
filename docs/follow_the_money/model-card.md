# Priority models — synthetic pipeline verification

These models are research experiments, not classifiers of guilt, ownership or
operational risk. No real Elliptic model was trained. Elliptic++ dataset licence
verification is blocked; Elliptic2 exceeds the approved download limit.

The seeded generator creates 600 fictional nodes across 30 periods. Periods
1–18 train (360 nodes), 19–24 select epochs (120), and 25–30 test (120).
IDs do not cross splits. Directed messages flow from earlier to later nodes;
training removes later edges. Scaling uses training rows only. Perturbing test
features must leave saved weights and validation metrics identical.

GraphSAGE, GAT and XGBoost receive the same numeric features and temporal split;
the GNNs additionally receive graph edges. Six synthetic feature proxies include
one deliberately privileged signal. A second fit removes it. The five remaining
columns correspond to live-computable definitions in `features.py`, but their
synthetic values are generated, not measurements from public addresses.

Measured test average precision (seed 47, 40 GNN epochs maximum):

| Model | Full features | Five-feature subset | Drop |
|---|---:|---:|---:|
| GraphSAGE | 0.946293 | 0.699059 | 0.247234 |
| GAT | 0.572325 | 0.562924 | 0.009401 |
| XGBoost | 0.930949 | 0.711873 | 0.219076 |

All metrics, split counts, scalers, hashes and measured fit times are in
`config/follow_the_money/training-results.json`. They establish executable
experiments, not generalization. No confidence intervals or search over seeds
was performed. GAT AP 0.572325 is near the positive base rate 0.516667;
its 0.009401 full-to-live drop is not meaningful evidence of robustness. Similarity/priority scores are
uncalibrated. The Brier metric does not itself establish calibration.

`DistributionGuard` checks feature schema, chain and standardized distance using
training statistics. Synthetic training provenance cannot pass as Bitcoin/TRON.
Missing, out-of-distribution or invalid model outputs fall back to a bounded
heuristic. A suitable real-data model requires licence review, mapped features,
new temporal evaluation and calibration before operational consideration.

The change classifier is library/experiment only; tracing uses the explicit
heuristic. It derives weak labels from later synthetic co-spends. The generator
now varies script match, roundness, relative size and input-address reuse; the
previous perfect scores came from tautological feature construction and are
superseded by the review rerun. It
trains only when the label was observed before the cutoff. Paired negatives are
assumptions, and collaborative transactions can invalidate the positive label.
The optional value regressor requires at least three completed training case
IDs; distinct IDs alone do not establish independent examples. Its trace experiment follows in the evaluation phase.

PyG installs and runs on Linux Python 3.14; wheel resolution also succeeded for
Windows. Windows runtime was not tested. TorchScript and PyG annotation warnings
are upstream compatibility warnings, retained in test output. No TorchScript or
compiled PyG extension is used. Model weights remain under gitignored `data/`;
torch weights must be loaded with `weights_only=True`. Never load arbitrary
pickle models supplied by an LLM, source label or API client.

The final evaluation trains a separate trace-value model on three completed,
explicitly simulated fixture reviews (51 rows) and probes a renamed fourth (17 rows). Every probe feature row duplicates a
training row. This is an **in-sample fit diagnostic**, not held-out validation.
It uses critic-retained observed edges and censored distance penalty 25. Its
three features are parent heuristic priority, hop count and log incoming units.
Cases/identifiers are disjoint, but graphs share the same authored structure.
The MAE uses graph hops or censoring penalty, never API-call units; a constant
mean-predictor baseline is reported. Label observation time is the latest evidence
timestamp, not wall-clock build time. The split is not temporal validation.
The reported fit and search gains are toy-family diagnostics only. The optional
`demo --learned-synthetic` exercises this policy; real wallets and TRON trigger
fallback. See `evaluation-results.json` for final measured results.

The GNNs are not validated production frontier scorers. Their synthetic chain
provenance cannot be relabeled Bitcoin. A real deployment would require licensed
point-in-time training features, complete neighborhood/coverage semantics,
independent temporal evaluation, a search benchmark and calibration. The current
public gold replay correctly uses heuristics and reports no GNN benefit.

Review rerun: the varied-signal change classifier has AP **0.828147**, ROC AUC
**0.786848**, accuracy **0.761905** (118 training / 42 test output rows). The
branching search reaches its endpoint in **16 queries with BFS**, **3 with
heuristic priority**, and **3 with the optional toy value policy**, at a common
budget of 32. The value model’s **0.358491** in-sample MAE compares with a
constant-mean baseline of **8.456747**, in hops-or-penalty units; all **17** probe
rows duplicate training features. The independent critic set retains **3/3**
supported cases and withdraws **5/5** planted errors. These are constructed
software checks, not real-world effectiveness estimates.
