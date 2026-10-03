"""Tokenization Gateway — the bank's edge, sitting between the bank core and the
urząd (government office).

Before the attack (prevention):
  * PII is replaced with random format-preserving tokens before it leaves the bank
  * every outgoing packet is HMAC-signed with a timestamp + nonce, so a
    man-in-the-middle cannot tamper with or replay it

After the attack (detection & response):
  * detokenization is rate-limited; a mass-exfiltration attempt auto-revokes the key
  * every event is anchored in a tamper-evident hash chain (audit service)
"""
import json
import hashlib
import hmac
import os
import secrets
import time
from collections import deque

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

VAULT_URL = os.environ["VAULT_URL"]
AUDIT_URL = os.environ["AUDIT_URL"]
URZAD_URL = os.environ["URZAD_URL"]
URZAD_API_KEY = os.environ["URZAD_API_KEY"]
SIGNING_KEY = os.environ["SIGNING_KEY"].encode()
MAX_DETOKENIZE_PER_MINUTE = int(os.environ.get("MAX_DETOKENIZE_PER_MINUTE", "5"))

PII_FIELDS = {"name", "pesel", "iban", "phone", "email"}

app = FastAPI(title="chainsight-gateway")

detokenize_timestamps: deque[float] = deque()
revoked_keys: set[str] = set()


def audit(event_type: str, payload: dict):
    httpx.post(f"{AUDIT_URL}/log", json={"event_type": event_type, "payload": payload}, timeout=10).raise_for_status()


def sign(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(SIGNING_KEY, canonical.encode(), hashlib.sha256).hexdigest()


def tokenize_records(records: list[dict], client: httpx.Client) -> list[dict]:
    tokenized = []
    for record in records:
        sanitized = {}
        for key, value in record.items():
            if key in PII_FIELDS and isinstance(value, str):
                r = client.post(f"{VAULT_URL}/tokenize", json={"field_type": key, "value": value})
                r.raise_for_status()
                sanitized[key] = r.json()["token"]
            else:
                sanitized[key] = value
        tokenized.append(sanitized)
    return tokenized


class ShareRequest(BaseModel):
    records: list[dict]


class DetokenizeRequest(BaseModel):
    token: str


@app.post("/share")
def share(req: ShareRequest):
    """Tokenize PII, sign the packet, deliver to the urząd."""
    with httpx.Client(timeout=10) as client:
        tokenized_records = tokenize_records(req.records, client)
        body = {"records": tokenized_records, "ts": int(time.time()), "nonce": secrets.token_hex(16)}
        r = client.post(f"{URZAD_URL}/ingest", json=body, headers={"X-Signature": sign(body)})
        r.raise_for_status()
    audit("data_shared", {"recipient": "urzad", "record_count": len(tokenized_records)})
    return {"shared": len(tokenized_records), "records": tokenized_records}


@app.post("/demo/mitm-tamper")
def demo_mitm_tamper(req: ShareRequest):
    """Simulate a man-in-the-middle: the packet is signed by the bank, then a
    field is altered in transit (e.g. IBAN swapped for the attacker's). The urząd
    must reject it because the signature no longer matches."""
    with httpx.Client(timeout=10) as client:
        tokenized_records = tokenize_records(req.records, client)
        body = {"records": tokenized_records, "ts": int(time.time()), "nonce": secrets.token_hex(16)}
        signature = sign(body)  # bank signs the honest packet
        # --- attacker modifies the payload after signing ---
        tampered = json.loads(json.dumps(body))
        if tampered["records"]:
            tampered["records"][0]["iban"] = "PL00ATTACKER00000000000000"
        r = client.post(f"{URZAD_URL}/ingest", json=tampered, headers={"X-Signature": signature})
    if r.status_code == 200:
        audit("mitm_not_detected", {"status": r.status_code})
        return {"blocked": False, "urzad_response": r.json()}
    audit("mitm_blocked", {"status": r.status_code, "reason": "bad_signature"})
    return {"blocked": True, "status": r.status_code, "urzad_response": r.json()}


@app.post("/demo/replay")
def demo_replay(req: ShareRequest):
    """Simulate a replay attack: capture a legitimate signed packet and send it twice.
    The urząd accepts the first and rejects the duplicate (nonce already seen)."""
    with httpx.Client(timeout=10) as client:
        tokenized_records = tokenize_records(req.records, client)
        body = {"records": tokenized_records, "ts": int(time.time()), "nonce": secrets.token_hex(16)}
        headers = {"X-Signature": sign(body)}
        first = client.post(f"{URZAD_URL}/ingest", json=body, headers=headers)
        replayed = client.post(f"{URZAD_URL}/ingest", json=body, headers=headers)
    blocked = replayed.status_code != 200
    audit("replay_blocked" if blocked else "replay_not_detected", {"status": replayed.status_code})
    return {
        "first_delivery": first.status_code,
        "replay_status": replayed.status_code,
        "blocked": blocked,
        "urzad_response": replayed.json(),
    }


@app.post("/detokenize")
def detokenize(req: DetokenizeRequest, x_api_key: str = Header()):
    """Urząd-facing detokenization with policy enforcement."""
    if x_api_key in revoked_keys:
        audit("detokenize_denied", {"reason": "revoked_key"})
        raise HTTPException(403, "API key revoked")
    if x_api_key != URZAD_API_KEY:
        audit("detokenize_denied", {"reason": "bad_key"})
        raise HTTPException(401, "invalid API key")

    now = time.monotonic()
    while detokenize_timestamps and now - detokenize_timestamps[0] > 60:
        detokenize_timestamps.popleft()
    if len(detokenize_timestamps) >= MAX_DETOKENIZE_PER_MINUTE:
        # Anomaly: mass detokenization attempt — revoke the key automatically.
        revoked_keys.add(x_api_key)
        audit("key_revoked", {"reason": "rate_limit_exceeded", "limit": MAX_DETOKENIZE_PER_MINUTE})
        raise HTTPException(429, "rate limit exceeded; key revoked")
    detokenize_timestamps.append(now)

    r = httpx.post(f"{VAULT_URL}/detokenize", json={"token": req.token}, timeout=10)
    if r.status_code == 404:
        audit("detokenize_failed", {"token": req.token, "reason": "unknown_token"})
        raise HTTPException(404, "unknown token")
    r.raise_for_status()
    data = r.json()
    audit("detokenized", {"token": req.token, "field_type": data["field_type"]})
    return data


@app.post("/admin/restore-key")
def restore_key(x_api_key: str = Header()):
    """Bank-side manual re-enable after investigating an incident (demo helper)."""
    revoked_keys.discard(x_api_key)
    detokenize_timestamps.clear()  # incident resolved — reset the rate-limit window
    audit("key_restored", {})
    return {"restored": True}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- UI proxy endpoints (avoid CORS; the dashboard talks only to the gateway) ----

@app.get("/api/audit/events")
def proxy_audit_events():
    return httpx.get(f"{AUDIT_URL}/events", timeout=10).json()


@app.get("/api/audit/verify")
def proxy_audit_verify():
    return httpx.get(f"{AUDIT_URL}/verify", timeout=10).json()


@app.get("/api/urzad/data")
def proxy_urzad_data():
    return httpx.get(f"{URZAD_URL}/data", timeout=10).json()


@app.get("/api/urzad/rejections")
def proxy_urzad_rejections():
    return httpx.get(f"{URZAD_URL}/rejections", timeout=10).json()


@app.delete("/api/urzad/data")
def proxy_urzad_clear():
    return httpx.delete(f"{URZAD_URL}/data", timeout=10).json()


app.mount("/", StaticFiles(directory="static", html=True), name="ui")
