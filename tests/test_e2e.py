"""End-to-end tests against the running docker compose stack.

Run:  docker compose up -d --build && pip install pytest httpx && pytest -v
"""
import hashlib
import hmac
import json
import secrets
import time

import httpx
import pytest

GATEWAY = "http://localhost:8000"
VAULT = "http://localhost:8001"
AUDIT = "http://localhost:8002"
URZAD = "http://localhost:8003"
API_KEY = "urzad-key-123"
SIGNING_KEY = b"demo-signing-key-change-me"

PII = {"name": "Anna Kowalska", "pesel": "85010112345", "iban": "PL61109010140000071219812874", "phone": "+48601234567"}


def sign(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(SIGNING_KEY, canonical.encode(), hashlib.sha256).hexdigest()


@pytest.fixture(scope="session", autouse=True)
def wait_for_stack():
    deadline = time.time() + 60
    urls = [f"{u}/health" for u in (GATEWAY, VAULT, AUDIT, URZAD)]
    while time.time() < deadline:
        try:
            if all(httpx.get(u, timeout=2).status_code == 200 for u in urls):
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    pytest.fail("stack did not become healthy in 60s")


@pytest.fixture(autouse=True)
def clean_urzad():
    httpx.delete(f"{URZAD}/data")
    httpx.post(f"{GATEWAY}/admin/restore-key", headers={"X-API-Key": API_KEY})


def share_one():
    r = httpx.post(f"{GATEWAY}/share", json={"records": [{"id": 1, **PII, "segment": "premium"}]}, timeout=30)
    r.raise_for_status()
    return r.json()["records"][0]


def test_urzad_never_sees_pii():
    tokenized = share_one()
    dump = httpx.get(f"{URZAD}/data").json()["records"]
    assert len(dump) == 1
    for value in PII.values():
        assert value not in str(dump), f"PII leaked to urzad: {value}"
    # non-PII passes through unchanged
    assert dump[0]["segment"] == "premium"
    assert dump[0] == tokenized


def test_tokens_are_format_preserving_and_random():
    tokenized = share_one()
    assert tokenized["pesel"] != PII["pesel"]
    assert len(tokenized["pesel"]) == len(PII["pesel"]) and tokenized["pesel"].isdigit()
    assert tokenized["phone"].startswith("+") and len(tokenized["phone"]) == len(PII["phone"])
    assert tokenized["iban"] != PII["iban"]
    assert len(tokenized["iban"]) == len(PII["iban"])


def test_tokenization_is_idempotent():
    t1, t2 = share_one(), share_one()
    assert t1["pesel"] == t2["pesel"]


def test_mitm_tampering_is_rejected():
    """A packet modified in transit must be refused by the urzad (bad signature)."""
    r = httpx.post(
        f"{GATEWAY}/demo/mitm-tamper",
        json={"records": [{"id": 9, **PII}]},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    assert d["blocked"] is True
    assert d["status"] == 400
    # nothing from the tampered packet landed in storage
    dump = httpx.get(f"{URZAD}/data").json()["records"]
    assert all(rec.get("iban") != "PL00ATTACKER00000000000000" for rec in dump)


def test_replayed_packet_is_rejected():
    """A captured, re-sent packet must be refused (nonce already seen)."""
    r = httpx.post(f"{GATEWAY}/demo/replay", json={"records": [{"id": 9, **PII}]}, timeout=30)
    r.raise_for_status()
    d = r.json()
    assert d["first_delivery"] == 200
    assert d["blocked"] is True
    assert d["replay_status"] == 409


def test_unsigned_direct_injection_is_rejected():
    """An attacker talking straight to the urzad without the signing key gets rejected."""
    body = {"records": [{"id": 666, "name": "Evil"}], "ts": int(time.time()), "nonce": secrets.token_hex(16)}
    r = httpx.post(f"{URZAD}/ingest", json=body, headers={"X-Signature": "f" * 64})
    assert r.status_code == 400


def test_stale_timestamp_is_rejected():
    """A correctly-signed but old packet (delayed replay) is refused."""
    body = {"records": [{"id": 7, "segment": "x"}], "ts": int(time.time()) - 3600, "nonce": secrets.token_hex(16)}
    r = httpx.post(f"{URZAD}/ingest", json=body, headers={"X-Signature": sign(body)})
    assert r.status_code == 400


def test_detokenize_with_valid_key():
    tokenized = share_one()
    r = httpx.post(f"{GATEWAY}/detokenize", json={"token": tokenized["pesel"]}, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["value"] == PII["pesel"]


def test_detokenize_rejects_bad_key():
    tokenized = share_one()
    r = httpx.post(f"{GATEWAY}/detokenize", json={"token": tokenized["pesel"]}, headers={"X-API-Key": "stolen"})
    assert r.status_code == 401


def test_mass_detokenization_revokes_key():
    tokenized = share_one()
    statuses = []
    for _ in range(12):
        r = httpx.post(f"{GATEWAY}/detokenize", json={"token": tokenized["pesel"]}, headers={"X-API-Key": API_KEY})
        statuses.append(r.status_code)
    assert 429 in statuses, "rate limit never fired"
    assert statuses[-1] == 403, "key was not revoked after the rate limit"
    # restore and confirm it works again
    httpx.post(f"{GATEWAY}/admin/restore-key", headers={"X-API-Key": API_KEY})
    r = httpx.post(f"{GATEWAY}/detokenize", json={"token": tokenized["pesel"]}, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200


def test_audit_chain_records_and_verifies():
    share_one()
    events = httpx.get(f"{AUDIT}/events").json()
    assert any(e["event_type"] == "data_shared" for e in events)
    verify = httpx.get(f"{AUDIT}/verify").json()
    assert verify["valid"] is True
    assert verify["length"] == len(events)


def test_audit_payloads_contain_no_pii():
    share_one()
    events = httpx.get(f"{AUDIT}/events").json()
    for value in PII.values():
        assert value not in str(events), f"PII leaked into audit log: {value}"
