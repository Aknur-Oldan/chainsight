# 🛰️ RVCS — Resilient Volunteer Coordination System

> **Crisis-response platform that coordinates bank-verified volunteers over USSD/GSM — even when the internet is down.**

Hackathon prototype · Defense / Civil Resilience track

---

## 1. The Problem

In 2022, Ukraine faced coordination chaos:

- Volunteers organized through **unverified Telegram groups** → security risk (infiltration, spam, sabotage).
- When mobile internet went down, **coordination collapsed** → infrastructure risk.

There is no system that combines **strict identity verification** with **communication resilience**.

## 2. The Solution

RVCS merges **bank-grade KYC** with **legacy GSM network resilience**:

| Component | What it does |
|---|---|
| 🏦 **BankID integration** | Volunteers onboard via their banking app. 100% verified identities — no fake accounts, no enemy infiltration. |
| 🗄️ **Central Asset Database (SSOT)** | Single Source of Truth: verified skills (medics, engineers) and assets (4x4 vehicles, generators, drones), mapped by sector. |
| 📟 **USSD/SMS Gateway** | Fallback channel over the cellular **signaling channel** — works with zero mobile data, as long as there is minimal GSM signal. |

### Why USSD?

USSD (`*111*1#`-style codes) runs on the voice/signaling layer of the cellular network, **not** on 4G/LTE data. During a blackout that kills IP networks, USSD keeps working on any phone — including button phones. No app, no internet, no battery-hungry smartphone required.

## 3. How it works

```
PEACETIME                         CRISIS (IP networks down)
─────────                         ─────────────────────────
Volunteer ──BankID──► SSOT        Coordinator ──Starlink──► RVCS backend
  "I'm a medic,                        │ "Need 2 medics, Sector A"
   I own a 4x4"                        ▼
                                  SSOT query → match volunteers
                                       │
                                       ▼
                                  Telco USSD gateway ──GSM──► Volunteer's phone
                                                                 │
                                  SSOT: DISPATCHED ✅ ◄──GSM── dials *111*1#
                                       │
                                       ▼
                                  Dashboard: dot turns green, live
```

1. **Onboarding (peacetime):** volunteer logs in via BankID, fills the *Asset Matrix*, lands in the SSOT as verified.
2. **Dispatch (blackout):** coordinator requests "2 medics in Sector A" → system pushes USSD flash to matching volunteers.
3. **Confirmation (offline):** volunteer dials `*111*1#` (accept) or `*111*2#` (decline) from a standard dialer → Telco routes the reply back → SSOT updates in real time.

## 4. Running the prototype

Requires Python 3.10+.

```bash
python -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]"
.venv/bin/uvicorn app.main:app --port 8000
```

| Page | URL | Role |
|---|---|---|
| 🗺️ Coordinator dashboard | http://127.0.0.1:8000/ | Live map (Leaflet), dispatch form, signal log |
| 🏦 Volunteer onboarding | http://127.0.0.1:8000/onboard | Mock BankID login → Asset Matrix → SSOT |
| 📱 Volunteer phone | http://127.0.0.1:8000/phone | Dialer simulator — reply via USSD codes |

### Demo script (the "wow" moment)

1. Open the **dashboard** and the **phone** page side by side.
2. Dashboard: select **Medic / Sector A**, hit **🚨 DISPATCH via USSD** → volunteer dots turn **🟡 yellow (PENDING)**.
3. Phone: the volunteer sees the USSD flash message, dials **`*111*1#`**, presses 📞.
4. Dashboard: within ~2 s the dot flips **🟢 green (DISPATCHED)** and the signal log updates.
5. Decline with `*111*2#` → 🔴 red. **Reset demo** button restores seed data.

## 5. What's mocked vs. real

| Layer | Prototype | Production |
|---|---|---|
| BankID | One-click fake login | OAuth/OIDC against bank identity providers (BankID, mojeID) |
| USSD gateway | Web dialer simulator → HTTP POST | Telco integration (SMPP / USSD gateway API) |
| SSOT | In-memory Python dicts | Encrypted DB, replicated across coordinator nodes |
| Coordinator uplink | localhost | Starlink / military network |

## 6. Roadmap: distributed SSOT (blockchain layer)

Volunteers stay blockchain-free (GSM phone + USSD is all they need). Resilience of the **backend** comes from a permissioned ledger:

- 3–7 coordinator nodes (Territorial Defense, Fire Dept, Voivodeship) each hold a full SSOT replica.
- Dispatch orders, acceptances, and KYC attestations (hashes only, no PII) are written to a hash-chained, signed journal.
- If a node is destroyed or cut off, any other node continues operating autonomously and merges history when connectivity returns (offline-first, eventual consistency).
- Result: no single point of failure, tamper-evident audit trail of every order.

## 7. Project structure

```
app/
├── main.py              # FastAPI backend + in-memory SSOT + mock USSD/BankID APIs
└── static/
    ├── index.html       # Coordinator dashboard (Leaflet map, dispatch, signal log)
    ├── onboard.html     # Mock BankID onboarding + Asset Matrix
    └── phone.html       # Phone dialer simulator (USSD)
```

**API:** `GET /api/state` · `POST /api/onboard` · `POST /api/dispatch` · `POST /api/ussd` · `POST /api/reset`

## 8. Pitch angles

- **Defense & resilience:** survives infrastructure attacks; verified identities block infiltration.
- **Sponsor value:** positions the bank as a pillar of national security and civic resilience — BankID becomes critical civil infrastructure.
- **Inclusivity:** works on any phone, any generation of user, zero apps to install.
