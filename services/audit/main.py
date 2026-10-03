"""Audit log — hash-chained append-only event log (blockchain-style integrity).
Each event's hash includes the previous hash, so tampering breaks the chain."""
import hashlib
import json
import os

import psycopg
from fastapi import FastAPI
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
GENESIS = "0" * 64

app = FastAPI(title="chainsight-audit")


def db():
    return psycopg.connect(DATABASE_URL)


@app.on_event("startup")
def init_schema():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_chain (
                seq BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )


def compute_hash(prev_hash: str, event_type: str, payload: dict) -> str:
    data = prev_hash + event_type + json.dumps(payload, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


class LogRequest(BaseModel):
    event_type: str
    payload: dict


@app.post("/log")
def log_event(req: LogRequest):
    with db() as conn:
        row = conn.execute("SELECT hash FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = row[0] if row else GENESIS
        h = compute_hash(prev_hash, req.event_type, req.payload)
        seq = conn.execute(
            "INSERT INTO audit_chain (event_type, payload, prev_hash, hash) VALUES (%s, %s, %s, %s) RETURNING seq",
            (req.event_type, json.dumps(req.payload), prev_hash, h),
        ).fetchone()[0]
    return {"seq": seq, "hash": h}


@app.get("/events")
def events():
    with db() as conn:
        rows = conn.execute(
            "SELECT seq, event_type, payload, prev_hash, hash, created_at FROM audit_chain ORDER BY seq"
        ).fetchall()
    return [
        {"seq": r[0], "event_type": r[1], "payload": r[2], "prev_hash": r[3], "hash": r[4], "created_at": r[5].isoformat()}
        for r in rows
    ]


@app.get("/verify")
def verify():
    with db() as conn:
        rows = conn.execute(
            "SELECT seq, event_type, payload, prev_hash, hash FROM audit_chain ORDER BY seq"
        ).fetchall()
    prev = GENESIS
    for seq, event_type, payload, prev_hash, h in rows:
        if prev_hash != prev or compute_hash(prev_hash, event_type, payload) != h:
            return {"valid": False, "broken_at_seq": seq}
        prev = h
    return {"valid": True, "length": len(rows)}


@app.get("/health")
def health():
    return {"status": "ok"}
