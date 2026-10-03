# RVCS — Resilient Volunteer Coordination System

Hackathon prototype of a crisis-response platform that coordinates **bank-verified volunteers**
over **USSD/GSM fallback** when IP networks go down.

- **BankID (mocked):** bank-grade KYC — no fake accounts, no infiltration.
- **SSOT:** central database of verified skills & assets (medics, 4x4s, drones).
- **USSD gateway (mocked):** dispatch & confirmations work with *zero* mobile internet.

## Run

```bash
python -m venv .venv && .venv/bin/pip install fastapi "uvicorn[standard]"
.venv/bin/uvicorn app.main:app --reload
```

Open:

| Page | URL | Role |
|---|---|---|
| Coordinator dashboard | http://127.0.0.1:8000/ | Map + dispatch + live signal log |
| Volunteer onboarding | http://127.0.0.1:8000/onboard | Mock BankID login + Asset Matrix |
| Volunteer phone | http://127.0.0.1:8000/phone | Fake dialer — reply via USSD codes |

## Demo flow (the "wow")

1. Dashboard: pick **Medic / Sector A**, press **🚨 DISPATCH via USSD** — dots turn **yellow (PENDING)**.
2. Phone page: volunteer sees the USSD flash message, dials **`*111*1#`** and presses 📞.
3. Dashboard: the dot flips to **green (DISPATCHED)** in real time; SSOT + signal log update.
4. Decline with **`*111*2#`** → red.

Everything is in-memory (`app/main.py`) — restart or press *Reset demo* to start over.
