import hashlib

import pytest


pytest.importorskip("pydantic")
pytest.importorskip("httpx")

from follow_the_money.clients import parse_bitcoin
from follow_the_money.contracts import (
    FreezeEvent,
    FtmError,
    Transfer,
    TxInput,
    TxOutput,
    USDT_TRON,
)
from follow_the_money.heuristics import (
    ClusterBook,
    account_signals,
    detect_change,
    detect_coinjoin,
    detect_peel_chain,
    weak_change_labels,
)


def inputs(tx, addresses):
    return tx.model_copy(
        update={
            "inputs": tuple(
                TxInput(
                    txid=hashlib.sha256(a.encode()).hexdigest(),
                    vout=0,
                    prevout=TxOutput(address=a, value=100000, script_type="v0_p2wpkh"),
                )
                for a in addresses
            )
        }
    )


def test_common_inputs_merge_but_cap_never_bridges(make_tx, provenance):
    tx = parse_bitcoin(make_tx(), provenance)
    book = ClusterBook(cap=3)
    assert book.cluster_common_input(inputs(tx, ["syn_a", "syn_b"])).members == (
        "syn_a",
        "syn_b",
    )
    assert book.cluster_common_input(inputs(tx, ["syn_b", "syn_c"])).members == (
        "syn_a",
        "syn_b",
        "syn_c",
    )
    decision = book.cluster_common_input(inputs(tx, ["syn_c", "syn_d"]))
    assert decision.stop and decision.reason == "service_or_cluster_cap"
    assert book.members("syn_a") == {"syn_a", "syn_b", "syn_c"}
    assert book.members("syn_d") == {"syn_d"}
    assert not book.linkable("syn_d") and not book.linkable("syn_a")


def test_known_service_contaminates_neither_wallet_group(make_tx, provenance):
    tx = parse_bitcoin(make_tx(), provenance)
    book = ClusterBook()
    book.mark_service("syn_exchange")
    assert book.cluster_common_input(inputs(tx, ["syn_exchange", "syn_a"])).stop
    assert book.members("syn_a") == {"syn_a"}
    assert not book.linkable("syn_a")


def test_coinjoin_stops_before_merging(make_tx, provenance):
    tx = inputs(parse_bitcoin(make_tx(), provenance), ["syn_a", "syn_b", "syn_c"])
    tx = tx.model_copy(
        update={
            "outputs": tuple(
                TxOutput(address=f"syn_o{i}", value=5000, script_type="p2pkh")
                for i in range(3)
            )
        }
    )
    assert detect_coinjoin(tx).suspected
    book = ClusterBook()
    assert book.cluster_common_input(tx).reason == "coinjoin_stop"
    assert not book.groups
    assert detect_change(tx).none_probability == 1


def test_counterparty_cap_is_service_stop(make_tx, provenance):
    book = ClusterBook(counterparty_cap=2)
    for i in range(3):
        decision = book.cluster_common_input(
            parse_bitcoin(make_tx(i, destination=f"syn_o{i}"), provenance)
        )
    assert decision.stop and not book.linkable("syn_seed_a")


def test_snapshot_roundtrip_preserves_stops(make_tx, provenance):
    book = ClusterBook()
    book.cluster_common_input(
        inputs(parse_bitcoin(make_tx(), provenance), ["syn_a", "syn_b"])
    )
    book.mark_service("syn_a")
    restored = ClusterBook.restore(book.snapshot())
    assert restored.snapshot() == book.snapshot()
    assert not restored.linkable("syn_b")
    bad = book.snapshot()
    bad["groups"].append(bad["groups"][0])
    with pytest.raises(FtmError):
        ClusterBook.restore(bad)


def test_change_is_a_distribution_with_abstention(make_tx, provenance):
    tx = parse_bitcoin(make_tx(amount=100000), provenance)
    tx = tx.model_copy(
        update={
            "outputs": (
                TxOutput(address="syn_payment", value=10000, script_type="p2pkh"),
                TxOutput(address="syn_change", value=89137, script_type="v0_p2wpkh"),
            )
        }
    )
    result = detect_change(tx, seen_addresses={"syn_payment"})
    assert sum(result.probabilities) + result.none_probability == pytest.approx(1)
    assert result.candidate == 1 and result.probabilities[1] < 1
    assert not result.calibrated
    unknown = detect_change(tx)
    assert unknown.probabilities[1] < result.probabilities[1]


def peel_fixture(make_tx, provenance):
    chain = []
    for i in range(3):
        tx = parse_bitcoin(make_tx(i, amount=101000), provenance)
        tx = tx.model_copy(
            update={
                "outputs": (
                    TxOutput(address=f"syn_pay{i}", value=1000, script_type="p2pkh"),
                    TxOutput(
                        address=f"syn_c{i}",
                        value=100000 - i * 2000,
                        script_type="v0_p2wpkh",
                    ),
                )
            }
        )
        if chain:
            prev = chain[-1]
            tx = tx.model_copy(
                update={
                    "inputs": (
                        TxInput(txid=prev.txid, vout=1, prevout=prev.outputs[1]),
                    )
                }
            )
        chain.append(tx)
    return chain


def test_peel_requires_outpoint_continuity(make_tx, provenance):
    chain = peel_fixture(make_tx, provenance)
    assert detect_peel_chain(chain).detected
    last = chain[-1]
    chain[-1] = last.model_copy(
        update={"inputs": (last.inputs[0].model_copy(update={"txid": "f" * 64}),)}
    )
    assert not detect_peel_chain(chain).detected
    assert not detect_peel_chain(chain[:1]).detected


def test_weak_labels_preserve_future_observation_time(make_tx, provenance):
    original = peel_fixture(make_tx, provenance)[0]
    later = parse_bitcoin(make_tx(100), provenance)
    later = later.model_copy(
        update={
            "inputs": (
                TxInput(txid=original.txid, vout=1, prevout=original.outputs[1]),
                original.inputs[0].model_copy(update={"txid": "e" * 64}),
            )
        }
    )
    rows = weak_change_labels([original, later])
    assert [r.label for r in rows] == [0, 1]
    assert all(r.label_observed_at > r.timestamp for r in rows)
    assert all(r.evidence_txid == later.txid for r in rows)
    mismatched = later.model_copy(
        update={
            "inputs": (
                later.inputs[0].model_copy(update={"prevout": original.outputs[0]}),
                later.inputs[1],
            )
        }
    )
    assert weak_change_labels([original, mismatched]) == ()


def test_tron_uses_no_bitcoin_heuristics(provenance):
    transfer = Transfer(
        txid="a" * 64,
        sender="syn_t",
        recipient="syn_u",
        contract=USDT_TRON,
        amount=100,
        decimals=6,
        timestamp=1,
        provenance=provenance,
    )
    event = FreezeEvent(
        txid="b" * 64,
        address="syn_t",
        contract=USDT_TRON,
        action="AddedBlackList",
        timestamp=2,
        provenance=provenance,
    )
    result = account_signals("syn_t", [transfer], [event])
    assert result["change"] is None and result["common_input_cluster"] is None
    assert result["freeze_txids"] == ["b" * 64]
    assert result["counterparties"] == ["syn_u"]
    for method in (detect_change, detect_coinjoin, ClusterBook().cluster_common_input):
        with pytest.raises(FtmError) as exc:
            method(transfer)
        assert exc.value.code == "wrong_chain"
