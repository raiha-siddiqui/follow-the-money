from dataclasses import replace
import hashlib

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("httpx")
pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("torch_geometric")
pytest.importorskip("xgboost")
pytest.importorskip("sklearn")

import numpy as np
import torch

from follow_the_money.contracts import FtmError
from follow_the_money.datasets import (
    load_csv_graph,
    synthetic_change_examples,
    synthetic_graph,
)
from follow_the_money.features import LIVE_FEATURES, live_features
from follow_the_money.clients import parse_bitcoin
from follow_the_money.heuristics import WeakChangeExample
from follow_the_money.models import DistributionGuard, fit_trace_value, score_address
from follow_the_money.training import train_change, train_one


def test_temporal_split_rejects_future_edges():
    graph = synthetic_graph(nodes=90)
    train, valid, test = graph.masks(18, 24)
    assert not (train & valid).any() and not (valid & test).any()
    assert graph.times[train].max() < graph.times[valid].min() < graph.times[test].min()
    with pytest.raises(FtmError, match="past to present"):
        replace(graph, edges=np.array([[89], [0]])).validate()


@pytest.mark.parametrize("kind", ["sage", "gat", "xgboost"])
def test_training_is_reproducible_and_test_future_does_not_train(kind, tmp_path):
    graph = synthetic_graph(nodes=90)
    a = train_one(graph, kind=kind, live=True, epochs=4, output=tmp_path / "a")
    changed = graph.features.copy()
    changed[graph.times > 24] += 10000
    b = train_one(
        replace(graph, features=changed),
        kind=kind,
        live=True,
        epochs=4,
        output=tmp_path / "b",
    )
    assert a["scaler"] == b["scaler"] and a["validation"] == b["validation"]
    if kind != "xgboost":
        first = torch.load(tmp_path / "a" / f"{kind}-live.pt", weights_only=True)
        second = torch.load(tmp_path / "b" / f"{kind}-live.pt", weights_only=True)
        assert all(torch.equal(first[k], second[k]) for k in first)
    else:
        assert (tmp_path / "a/xgboost-live.json").read_bytes() == (
            tmp_path / "b/xgboost-live.json"
        ).read_bytes()
    assert a["counts"] == {"train": 54, "validation": 18, "test": 18}
    assert all(v is None or 0 <= v <= 1 for v in a["test"].values())


def test_ood_and_model_failure_fall_back():
    x = synthetic_graph(nodes=90).features[:, :5]
    guard = DistributionGuard.fit(x, chain="synthetic", feature_names=LIVE_FEATURES)
    predict = lambda x: [0.9]  # noqa: E731
    kwargs = dict(
        guard=guard,
        predict=predict,
        chain="synthetic",
        feature_names=LIVE_FEATURES,
        heuristic=0.3,
    )
    assert score_address(x.mean(axis=0), **kwargs)["method"] == "priority_model"
    assert score_address([10000] * 5, **kwargs)["score"] == 0.3
    kwargs["chain"] = "bitcoin"
    assert score_address(x[0], **kwargs)["reason"] == "schema_or_chain_mismatch"
    kwargs["chain"], kwargs["predict"] = "synthetic", lambda x: [float("nan")]
    assert score_address(x.mean(axis=0), **kwargs)["method"] == "heuristic_fallback"


def test_features_ignore_future_and_unconfirmed(make_tx, provenance):
    tx = parse_bitcoin(make_tx(), provenance)
    now = tx.timestamp
    first = live_features("syn_seed_a", [tx], as_of=now)
    future = tx.model_copy(update={"timestamp": now + 1})
    unconfirmed = tx.model_copy(update={"confirmed": False})
    assert live_features("syn_seed_a", [tx, future, unconfirmed], as_of=now) == first
    assert live_features("absent", [tx], as_of=now) == (0, 0, 0, 0, 0)


def test_csv_import_requires_hash_license_and_explicit_mapping(tmp_path):
    features = tmp_path / "features.csv"
    edges = tmp_path / "edges.csv"
    features.write_text(
        "id,t,label,f\na,1,illicit,2\nb,2,unknown,3\nc,3,licit,4\n", encoding="utf-8"
    )
    edges.write_text("source,target\na,b\nb,c\n", encoding="utf-8")
    schema = dict(
        id="id",
        time="t",
        label="label",
        features=["f"],
        live_features=["f"],
        source="source",
        target="target",
        label_map={"illicit": 1, "licit": 0},
    )
    receipts = {
        name: {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "license": "synthetic-test",
            "license_approved": True,
        }
        for name, path in (("features", features), ("edges", edges))
    }
    graph = load_csv_graph(features, edges, schema=schema, receipts=receipts)
    assert graph.labels.tolist() == [1, -1, 0]
    features.write_text(
        features.read_text(encoding="utf-8").replace("2\n", "9\n"), encoding="utf-8"
    )
    with pytest.raises(FtmError, match="licence"):
        load_csv_graph(features, edges, schema=schema, receipts=receipts)


def test_change_classifier_uses_label_observation_time():
    rows = [
        WeakChangeExample(
            (i % 2, 0.3, 0.2, 0), i % 2, f"{i // 2:064x}", 10, 20, "a" * 64
        )
        for i in range(12)
    ]
    rows += [
        WeakChangeExample(
            (i % 2, 0.3, 0.2, 0), i % 2, f"{100 + i // 2:064x}", 60, 70, "b" * 64
        )
        for i in range(4)
    ]
    rows += [WeakChangeExample((0, 0, 0, 0), 1, "c" * 64, 49, 51, "d" * 64)]
    report = train_change(rows, train_end=50, test_start=60)
    assert report["train_count"] == 12 and report["test_count"] == 4
    assert report["calibrated"] is False


def test_value_requires_completed_independent_cases():
    rows = [
        dict(
            case_id=str(i),
            features=[i, 1],
            remaining_hops_or_penalty=i,
            label_observed_at=10,
            split="train",
        )
        for i in range(6)
    ]
    model = fit_trace_value(rows, train_end=20)
    assert np.isfinite(model.predict([[1, 1]])).all()
    with pytest.raises(FtmError, match="three"):
        fit_trace_value(rows, train_end=9)
    with pytest.raises(FtmError, match="three"):
        fit_trace_value([{**r, "case_id": "same"} for r in rows], train_end=20)


def test_synthetic_weak_training_is_derived_from_cospends():
    examples = synthetic_change_examples()
    assert len(examples) == 180
    assert len({r.txid for r in examples}) == 90
    result = train_change(examples, train_end=6000, test_start=7000)
    assert result["train_count"] == 118 and result["test_count"] == 42
    assert all(r.timestamp < r.label_observed_at for r in examples)


def test_synthetic_change_signals_overlap_instead_of_encoding_the_answer():
    rows = synthetic_change_examples()
    for label in (0, 1):
        selected = [row for row in rows if row.label == label]
        assert {row.features[0] for row in selected} == {0, 1}
        assert {row.features[1] for row in selected} == {0, 1}
        assert {row.features[2] > 0.5 for row in selected} == {False, True}
    assert {row.features[3] for row in rows if row.label == 1} == {0, 1}
