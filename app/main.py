"""RVCS — Resilient Volunteer Coordination System (hackathon prototype).

FastAPI backend with an in-memory SSOT. Serves:
  /            -> Coordinator dashboard (Leaflet map)
  /onboard     -> Mock BankID onboarding
  /phone       -> Mock USSD phone dialer
"""

import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="RVCS")

STATIC = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# SSOT (in-memory for the demo)
# ---------------------------------------------------------------------------
# Volunteer statuses: AVAILABLE -> PENDING -> DISPATCHED / DECLINED

SECTORS = {
    "A": (50.0647, 19.9450),  # Kraków Main Square area
    "B": (50.0545, 19.9353),
    "C": (50.0755, 19.9570),
}

VOLUNTEERS = {}
MISSIONS = {}
EVENTS = []


def log(msg: str):
    EVENTS.insert(0, {"t": time.strftime("%H:%M:%S"), "msg": msg})
    del EVENTS[50:]


def seed():
    demo = [
        ("Anna Kowalska", "medic", "A", 50.0661, 19.9449, "+48 600 111 222"),
        ("Jan Nowak", "medic", "A", 50.0630, 19.9500, "+48 600 333 444"),
        ("Petr Svoboda", "engineer", "A", 50.0650, 19.9380, "+48 600 555 666"),
        ("Olena Shevchenko", "driver_4x4", "B", 50.0540, 19.9300, "+48 600 777 888"),
        ("Marek Wiśniewski", "drone_operator", "C", 50.0760, 19.9600, "+48 600 999 000"),
    ]
    for name, skill, sector, lat, lng, phone in demo:
        vid = uuid.uuid4().hex[:8]
        VOLUNTEERS[vid] = {
            "id": vid, "name": name, "skill": skill, "sector": sector,
            "lat": lat, "lng": lng, "phone": phone,
            "status": "AVAILABLE", "verified": True, "mission_id": None,
        }
    log("SSOT seeded with verified volunteers (BankID KYC ✓)")


seed()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class OnboardReq(BaseModel):
    name: str
    skill: str
    sector: str = "A"
    phone: str = ""


class DispatchReq(BaseModel):
    skill: str
    sector: str
    count: int = 2
    message: str = "URGENT: Medic needed at Main Square."


class UssdReq(BaseModel):
    volunteer_id: str
    code: str  # e.g. *111*1#


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/state")
def state():
    return {
        "volunteers": list(VOLUNTEERS.values()),
        "missions": list(MISSIONS.values()),
        "events": EVENTS,
        "sectors": SECTORS,
    }


@app.post("/api/onboard")
def onboard(req: OnboardReq):
    """Mock BankID: identity is instantly 'bank-verified'."""
    vid = uuid.uuid4().hex[:8]
    base_lat, base_lng = SECTORS.get(req.sector, SECTORS["A"])
    import random
    VOLUNTEERS[vid] = {
        "id": vid, "name": req.name, "skill": req.skill, "sector": req.sector,
        "lat": base_lat + random.uniform(-0.004, 0.004),
        "lng": base_lng + random.uniform(-0.006, 0.006),
        "phone": req.phone or "+48 6XX XXX XXX",
        "status": "AVAILABLE", "verified": True, "mission_id": None,
    }
    log(f"BankID KYC passed → {req.name} ({req.skill}) added to SSOT")
    return VOLUNTEERS[vid]


@app.post("/api/dispatch")
def dispatch(req: DispatchReq):
    """Coordinator requests N volunteers of a skill in a sector.

    Pushes a (mock) USSD flash to matching AVAILABLE volunteers.
    """
    matches = [
        v for v in VOLUNTEERS.values()
        if v["skill"] == req.skill and v["sector"] == req.sector
        and v["status"] == "AVAILABLE"
    ][: req.count]
    if not matches:
        raise HTTPException(404, "No available volunteers match in that sector")
    mid = uuid.uuid4().hex[:8]
    MISSIONS[mid] = {
        "id": mid, "skill": req.skill, "sector": req.sector,
        "message": req.message, "needed": req.count,
        "accepted": 0, "pending": [v["id"] for v in matches],
    }
    for v in matches:
        v["status"] = "PENDING"
        v["mission_id"] = mid
        log(f"USSD flash → {v['name']}: \"{req.message} Reply *111*1# / *111*2#\"")
    return MISSIONS[mid]


@app.post("/api/ussd")
def ussd(req: UssdReq):
    """Telco gateway mock: volunteer replies via USSD code from the dialer."""
    v = VOLUNTEERS.get(req.volunteer_id)
    if not v:
        raise HTTPException(404, "Unknown MSISDN")
    code = req.code.strip()
    if v["status"] != "PENDING":
        return {"reply": "RVCS: No pending request for this number."}
    mission = MISSIONS.get(v["mission_id"])
    if code == "*111*1#":
        v["status"] = "DISPATCHED"
        if mission:
            mission["accepted"] += 1
            mission["pending"] = [p for p in mission["pending"] if p != v["id"]]
        log(f"USSD reply *111*1# ← {v['name']} → SSOT updated: DISPATCHED ✅")
        return {"reply": "RVCS: Confirmed. Proceed to location. Stay safe."}
    if code == "*111*2#":
        v["status"] = "DECLINED"
        v["mission_id"] = None
        if mission:
            mission["pending"] = [p for p in mission["pending"] if p != v["id"]]
        log(f"USSD reply *111*2# ← {v['name']} → SSOT updated: DECLINED ❌")
        return {"reply": "RVCS: Understood. You were marked unavailable."}
    return {"reply": "RVCS: Unknown code. Use *111*1# (accept) or *111*2# (decline)."}


@app.post("/api/reset")
def reset():
    VOLUNTEERS.clear()
    MISSIONS.clear()
    EVENTS.clear()
    seed()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/onboard")
def onboard_page():
    return FileResponse(STATIC / "onboard.html")


@app.get("/phone")
def phone_page():
    return FileResponse(STATIC / "phone.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
