import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("yaml")

from follow_the_money.contracts import Label
from follow_the_money.labels import (
    LabelStore,
    parse_ofac,
    parse_opensanctions,
    parse_tagpack,
)


def test_tagpack_inheritance_and_provenance(provenance):
    rows = parse_tagpack(
        b"currency: BTC\nlabel: Fictional Exchange\ncategory: exchange\nsource: https://example.invalid/published\ntags:\n- address: syn_exchange\n- address: syn_other\n  label: Fictional Other\n",
        provenance,
    )
    assert len(rows) == 2
    assert rows[0].category == "exchange" and rows[1].label == "Fictional Other"
    assert rows[0].provenance == provenance


def test_ofac_snapshot_never_invents_owner(provenance):
    labels = parse_ofac(b'["syn_wallet"]', provenance, chain="bitcoin")
    assert labels[0].category == "sanctioned"
    assert labels[0].owner_name is None


def test_opensanctions_wallet_not_automatically_sanctioned(provenance):
    raw = json.dumps(
        {
            "schema": "CryptoWallet",
            "caption": "Fictional Wallet",
            "properties": {"currency": ["BTC"], "publicKey": ["syn_wallet"]},
        }
    ).encode()
    (label,) = parse_opensanctions(raw, provenance)
    assert label.category == "other"
    assert label.owner_name is None


def test_label_store_preserves_conflicts_and_chain_scope(tmp_path, provenance):
    store = LabelStore(tmp_path / "labels.sqlite")
    store.initialize()
    base = Label(
        chain="bitcoin",
        address="syn_a",
        label="Fictional A",
        category="exchange",
        source_ref="fixture://a",
        provenance=provenance,
    )
    other = Label(**{**base.model_dump(), "label": "Fictional B", "category": "other"})
    assert store.add([base, other]) == 2
    assert store.add([base]) == 0
    assert len(store.lookup_labels("bitcoin", "syn_a")) == 2
    assert store.lookup_labels("tron", "syn_a") == ()
    assert store.lookup_labels("bitcoin", "' OR 1=1 --") == ()
