import pytest


pytest.importorskip("pydantic")

from pydantic import ValidationError

from follow_the_money.contracts import Provenance, TxOutput, canonical, strict_json


@pytest.mark.parametrize(
    "amount", [True, 1.2, "10", -1, 2_100_000_000_000_001, float("nan"), float("inf")]
)
def test_satoshis_are_exact_bounded_integers(amount):
    with pytest.raises(ValidationError):
        TxOutput(address="syn_a", value=amount, script_type="p2pkh")


@pytest.mark.parametrize(
    "raw", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}']
)
def test_untrusted_json_rejects_ambiguity(raw):
    with pytest.raises(ValueError):
        strict_json(raw)


def test_provenance_is_required_and_timezone_aware(provenance):
    with pytest.raises(ValidationError):
        Provenance(**{**provenance.to_dict(), "retrieved_at": "2026-10-26"})
    with pytest.raises(ValidationError):
        Provenance(**{**provenance.to_dict(), "sha256": "abc"})
    assert provenance.model_validate_json(provenance.model_dump_json()) == provenance


def test_records_are_frozen_and_reject_unknown_fields():
    out = TxOutput(address=None, value=0, script_type="op_return")
    with pytest.raises(ValidationError):
        out.value = 4
    with pytest.raises(ValidationError):
        TxOutput(address=None, value=0, script_type="op_return", owner="invented")
    assert canonical({"z": 1, "a": 2}) == '{"a":2,"z":1}'
