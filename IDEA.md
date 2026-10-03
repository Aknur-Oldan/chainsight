# Idea: **ChainSight** — Bank-Side Tokenization Gateway for the Bank ⇄ Urząd Channel

## Problem
A bank must report customer data to government offices (urząd — tax office, ZUS, courts) over a
channel neither party fully controls. A man-in-the-middle can intercept PII, tamper with payloads
(e.g. swap an IBAN), or replay captured packets; and if the urząd itself is breached, customer PII
could leak.

## Concept
The bank never sends real customer data outside its perimeter. A gateway at the bank's edge replaces
PII with meaningless tokens and cryptographically signs every outgoing packet. A MITM sees only
tokens and cannot modify or replay packets; a breach at the urząd yields only useless tokens.

## Architecture

```
[Bank Core Systems] → [Tokenization Gateway] ══signed══> [Urząd (gov office)]
         │                    │                           verifies HMAC+ts+nonce
   [Token Vault]       [Blockchain Audit Layer]
   (mapping DB,         (hash-anchored logs of
    HSM-protected)       every share/detokenize)
```

## How it works

1. **Outbound flow:** The gateway intercepts outgoing datasets, detects PII (PESEL, name, IBAN, phone), and replaces each value with a random, format-preserving token (e.g., `PESEL 85010112345` → PESEL-like `00293847561`). The urząd's systems work unchanged because tokens preserve the original format. Each packet is then signed (HMAC over the canonical payload + timestamp + nonce), so a man-in-the-middle can neither tamper with nor replay it.

2. **Token vault:** The token↔PII mapping lives only inside the bank, encrypted at rest, with keys protected by an HSM. Tokens are fully random (no derivation from the original value — nothing to brute-force).

3. **Detokenization on demand:** If the urząd must act on a real identity (e.g., contact a client), it calls a bank API with the token; the bank performs the action (sends the SMS/email) without ever revealing PII to the urząd.

4. **Blockchain layer (permissioned, e.g., Hyperledger Fabric):**
   - Every data share, detokenization request, and consent grant is hashed and anchored on-chain → immutable, tamper-proof audit trail.
   - Smart contracts enforce policy: who may detokenize which fields, rate limits, grant expiry — a compromised API key cannot mass-detokenize.
   - Anomaly detection: an unusual spike of detokenization requests triggers automatic on-chain revocation of the access grant.

## Why it defeats the threat
- **MITM in transit → attacker sees tokens only and cannot tamper/replay** (signature + nonce + timestamp).
- **Urząd breach → attacker gets tokens only.** The mapping never left the bank.
- **Mass detokenization blocked** by smart-contract rate limits and instant revocation.
- **Full, tamper-proof forensics** of what was shared and when — usable as regulatory evidence (GDPR / DORA).

## Anti-pattern to avoid
Never put customer data (even hashed or encrypted) on-chain — it conflicts with GDPR right-to-erasure, and hashes of low-entropy PII are brute-forceable. The chain stores only event hashes and policy state.

## MVP scope (3 components)
1. **REST tokenization proxy** (Python/Go) with format-preserving random tokens
2. **Vault service** with an encrypted token↔PII mapping store
3. **Audit layer** — Hyperledger Fabric chaincode (or initially a hash-chained append-only log) anchoring audit events and enforcing detokenization policy
