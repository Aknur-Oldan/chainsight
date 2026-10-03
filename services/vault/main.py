"""Token Vault — stores token<->PII mapping. PII never leaves this service unencrypted at rest."""
import hashlib
import hmac
import os
import secrets
import string

import psycopg
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
fernet = Fernet(os.environ["FERNET_KEY"].encode())
HMAC_KEY = os.environ["HMAC_KEY"].encode()

app = FastAPI(title="chainsight-vault")


def db():
    return psycopg.connect(DATABASE_URL)


@app.on_event("startup")
def init_schema():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS token_map (
                token TEXT PRIMARY KEY,
                field_type TEXT NOT NULL,
                lookup_hash TEXT NOT NULL UNIQUE,
                encrypted_value BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )


def format_preserving_token(value: str) -> str:
    """Random token with the same character structure as the input. No derivation
    from the value itself — nothing to brute-force."""
    out = []
    for ch in value:
        if ch.isdigit():
            out.append(secrets.choice(string.digits))
        elif ch.isalpha():
            pool = string.ascii_uppercase if ch.isupper() else string.ascii_lowercase
            out.append(secrets.choice(pool))
        else:
            out.append(ch)
    return "".join(out)


def lookup_hash(field_type: str, value: str) -> str:
    return hmac.new(HMAC_KEY, f"{field_type}:{value}".encode(), hashlib.sha256).hexdigest()


class TokenizeRequest(BaseModel):
    field_type: str
    value: str


class DetokenizeRequest(BaseModel):
    token: str


@app.post("/tokenize")
def tokenize(req: TokenizeRequest):
    lh = lookup_hash(req.field_type, req.value)
    with db() as conn:
        row = conn.execute("SELECT token FROM token_map WHERE lookup_hash = %s", (lh,)).fetchone()
        if row:
            return {"token": row[0], "reused": True}
        for _ in range(10):
            token = format_preserving_token(req.value)
            exists = conn.execute("SELECT 1 FROM token_map WHERE token = %s", (token,)).fetchone()
            if not exists:
                break
        else:
            raise HTTPException(500, "token collision")
        conn.execute(
            "INSERT INTO token_map (token, field_type, lookup_hash, encrypted_value) VALUES (%s, %s, %s, %s)",
            (token, req.field_type, lh, fernet.encrypt(req.value.encode())),
        )
    return {"token": token, "reused": False}


@app.post("/detokenize")
def detokenize(req: DetokenizeRequest):
    with db() as conn:
        row = conn.execute(
            "SELECT encrypted_value, field_type FROM token_map WHERE token = %s", (req.token,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "unknown token")
    return {"value": fernet.decrypt(bytes(row[0])).decode(), "field_type": row[1]}


@app.get("/health")
def health():
    return {"status": "ok"}
