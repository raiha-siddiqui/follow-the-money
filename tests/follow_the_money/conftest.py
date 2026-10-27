"""Fail closed on external sockets in every Project 2 test."""

import hashlib
import os
import socket

import pytest

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original_dns = socket.getaddrinfo

    def resolve(host, *args, **kwargs):
        if host not in ("127.0.0.1", "::1", "localhost", None):
            raise AssertionError("external DNS forbidden in tests")
        return original_dns(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            raise AssertionError("external network forbidden in tests")
        return original(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            raise AssertionError("external network forbidden in tests")
        return original_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TRON_PRO_API_KEY",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def provenance():
    pytest.importorskip("pydantic")
    from follow_the_money.contracts import Provenance

    return Provenance(
        source_url="fixture://ftm/authored-v1",
        retrieved_at="2026-10-26T00:00:00+00:00",
        sha256="a" * 64,
        license="Authored fictional test data",
        evidence_kind="synthetic",
    )


@pytest.fixture
def make_tx():
    def make(
        index=1,
        source="syn_seed_a",
        destination="syn_next",
        amount=10000,
        confirmed=True,
    ):
        return {
            "txid": hashlib.sha256(f"synthetic-tx-{index}".encode()).hexdigest(),
            "vin": [
                {
                    "txid": "0" * 64,
                    "vout": 0,
                    "prevout": {
                        "scriptpubkey_address": source,
                        "value": amount + 100,
                        "scriptpubkey_type": "v0_p2wpkh",
                    },
                    "is_coinbase": False,
                }
            ],
            "vout": [
                {
                    "scriptpubkey_address": destination,
                    "value": amount,
                    "scriptpubkey_type": "v0_p2wpkh",
                }
            ],
            "status": {"confirmed": confirmed, "block_time": 1700000000 + index},
        }

    return make
