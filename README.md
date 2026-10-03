# ⛓ ChainSight — Bank ⇄ Urząd Secure Data Gateway

**Customer PII never leaves the bank, and no man-in-the-middle can touch the data in transit.**

Banks must regularly report customer data to government offices (urząd — tax office, ZUS, courts).
ChainSight protects that channel **before** an attack (tokenization + signed, replay-proof packets)
and **after** one (breach yields only tokens, mass detokenization auto-revokes the key, and a
tamper-evident hash chain provides regulatory-grade forensics).

Full concept: [IDEA.md](IDEA.md) · Team questionnaire: [QUESTIONNAIRE.md](QUESTIONNAIRE.md)

## Quick start

```bash
docker compose up -d --build
```

Then open the dashboard: **http://localhost:8000**

| Service | Port | Role |
|---|---|---|
| gateway | 8000 | Tokenization + packet signing, detokenization policy, web dashboard |
| vault | 8001 | Encrypted token↔PII mapping (bank-internal only) |
| audit | 8002 | Hash-chained append-only audit log |
| urzad | 8003 | Mock government office — verifies signature, timestamp and nonce |

## Threat model & defences

| Attack | Defence | When |
|---|---|---|
| MITM intercepts the channel | PII already tokenized at the bank's edge — attacker sees random tokens | before |
| MITM tampers with a packet (e.g. swaps an IBAN) | HMAC signature over the canonical payload — urząd rejects it | before |
| MITM replays a captured packet | Per-packet nonce + timestamp freshness — duplicate is rejected | before |
| Urząd itself is breached | Its DB holds tokens only; the mapping never left the bank | after |
| Stolen API key, mass detokenization | Rate limit fires → key auto-revoked | after |
| Attacker covers their tracks | Hash-chained audit log — any tampering breaks the chain | after |

## Demo flow (on the dashboard)

1. **Report customer data** — PII is tokenized and the packet signed at the bank's edge; the urząd receives tokens.
2. **Man-in-the-middle** — tamper with a signed packet or replay a captured one: the urząd rejects both.
3. **Breach the urząd** — dump its DB: attacker gets only useless tokens.
4. **Legitimate detokenization** — the urząd exchanges a token via the bank's policy-enforced API.
5. **Mass exfiltration attempt** — rate limit fires, the key is auto-revoked, everything is on the audit chain.

## Run tests

```bash
docker compose up -d --build
pip install pytest httpx
pytest -v
```

Tests prove: no PII at the urząd, format-preserving idempotent tokens, MITM tamper/replay/stale-packet
rejection, unsigned injection rejection, key auth, auto-revocation on mass detokenization,
audit-chain integrity, and no PII in audit logs.

## Architecture

```
[Bank Core] → [Gateway :8000] ══signed packets══> [Urząd :8003]   (tokens only)
                  │       │                        (verifies HMAC + ts + nonce)
            [Vault :8001] [Audit :8002]
            (encrypted     (hash-chained
             mapping)       event log)
```

> ⚠️ Demo-grade: keys live in compose env vars and signing is a shared HMAC key. In production:
> HSM/KMS for keys, mTLS + asymmetric signatures (e.g. Ed25519) between the parties, and the
> audit chain anchored to a permissioned blockchain (e.g. Hyperledger Fabric).
