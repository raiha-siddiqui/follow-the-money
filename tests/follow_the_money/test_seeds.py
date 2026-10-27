import pytest


pytest.importorskip("pydantic")

from follow_the_money.contracts import FtmError
from follow_the_money.seeds import load_ransomwhere


def test_seeds_deduplicate_only_exact_family_pairs(provenance):
    result = load_ransomwhere(
        b'[{"address":"syn_a","family":"Fictional A"},{"address":"syn_a","family":"Fictional A"},{"address":"syn_a","family":"Fictional B"}]',
        provenance,
    )
    assert len(result) == 2
    assert all(x.provenance == provenance for x in result)


def test_unknown_family_is_not_invented(provenance):
    assert (
        load_ransomwhere(b'[{"address":"syn_a"}]', provenance)[0].family
        == "unattributed in source"
    )
    with pytest.raises(FtmError):
        load_ransomwhere(b"{}", provenance)
