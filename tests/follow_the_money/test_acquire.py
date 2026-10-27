import io

import pytest


pytest.importorskip("pydantic")

from follow_the_money.acquire import acquire
from follow_the_money.contracts import FtmError


class Response(io.BytesIO):
    headers = {}


def source(**changes):
    return {
        "id": "synthetic-source",
        "url": "https://example.invalid/data",
        "license": "Authored fictional test data",
        "approved": True,
        "max_bytes": 100,
        "evidence_kind": "synthetic",
        **changes,
    }


def test_bounded_download_receipt_and_cached_integrity(tmp_path):
    calls = []

    def opener(request, **kwargs):
        calls.append(request)
        return Response(b"fictional bytes")

    receipt = acquire(source(), tmp_path, opener=opener)
    assert receipt["size_bytes"] == 15
    assert receipt["download_operations_this_run"] == 1
    assert (
        acquire(source(), tmp_path, opener=opener)["download_operations_this_run"] == 0
    )
    assert len(calls) == 1
    (tmp_path / "synthetic-source").write_bytes(b"tampered")
    with pytest.raises(FtmError):
        acquire(source(), tmp_path, opener=opener)


def test_size_limit_and_partial_cleanup(tmp_path):
    with pytest.raises(FtmError) as exc:
        acquire(
            source(max_bytes=4), tmp_path, opener=lambda *a, **k: Response(b"oversized")
        )
    assert exc.value.code == "source_too_large"
    assert not list(tmp_path.iterdir())


def test_unapproved_source_never_calls_opener(tmp_path):
    with pytest.raises(FtmError):
        acquire(
            source(approved=False),
            tmp_path,
            opener=lambda *a, **k: pytest.fail("network"),
        )


def test_checksum_mismatch_never_publishes(tmp_path):
    with pytest.raises(FtmError):
        acquire(
            source(sha256="a" * 64), tmp_path, opener=lambda *a, **k: Response(b"other")
        )
    assert not list(tmp_path.iterdir())


def test_another_writers_partial_is_preserved_without_network(tmp_path):
    partial = tmp_path / "synthetic-source.partial"
    partial.write_bytes(b"other writer")
    with pytest.raises(FileExistsError):
        acquire(source(), tmp_path, opener=lambda *a, **k: pytest.fail("network"))
    assert partial.read_bytes() == b"other writer"
