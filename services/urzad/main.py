"""Urząd (government office) — the receiving party outside the bank's perimeter.

Defence-in-depth on the receiving side:
  * HMAC signature check  → a man-in-the-middle who tampers with the payload is rejected
  * timestamp freshness   → old captured packets are useless
  * nonce replay guard    → an intercepted packet cannot be re-sent

It stores only what it accepts; a 'breach' dump shows an attacker gets tokens only.
"""
import hashlib
import hmac
import json
import os
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

SIGNING_KEY = os.environ["SIGNING_KEY"].encode()
MAX_CLOCK_SKEW_SECONDS = int(os.environ.get("MAX_CLOCK_SKEW_SECONDS", "60"))

app = FastAPI(title="chainsight-urzad")

storage: list[dict] = []
seen_nonces: set[str] = set()
rejections: list[dict] = []


class IngestRequest(BaseModel):
    records: list[dict]
    ts: int
    nonce: str


def expected_signature(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(SIGNING_KEY, canonical.encode(), hashlib.sha256).hexdigest()


def reject(status: int, reason: str, detail: str):
    rejections.append({"reason": reason, "detail": detail, "ts": int(time.time())})
    raise HTTPException(status, {"reason": reason, "detail": detail})


@app.post("/ingest")
def ingest(req: IngestRequest, x_signature: str = Header()):
    body = {"records": req.records, "ts": req.ts, "nonce": req.nonce}
    if not hmac.compare_digest(expected_signature(body), x_signature):
        reject(400, "bad_signature", "payload was modified in transit — man-in-the-middle blocked")
    if abs(time.time() - req.ts) > MAX_CLOCK_SKEW_SECONDS:
        reject(400, "stale_timestamp", "packet too old — delayed replay blocked")
    if req.nonce in seen_nonces:
        reject(409, "replay", "nonce already seen — replay attack blocked")
    seen_nonces.add(req.nonce)
    storage.extend(req.records)
    return {"stored": len(req.records), "total": len(storage)}


@app.get("/data")
def data():
    """What an attacker sees after breaching the urząd: tokens only."""
    return {"records": storage}


@app.get("/rejections")
def get_rejections():
    """Packets the urząd refused to accept (tampered / replayed)."""
    return {"rejections": rejections}


@app.delete("/data")
def clear():
    storage.clear()
    seen_nonces.clear()
    rejections.clear()
    return {"cleared": True}


@app.get("/health")
def health():
    return {"status": "ok"}
