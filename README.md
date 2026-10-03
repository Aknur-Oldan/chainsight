# ChainSight

**Supply chain risk mapping & disruption simulation** — HackYeah 2025, "Defence" open task.

Corporations depend on supplier networks they can't see past tier 1. ChainSight maps the
full supplier graph (tier 1→3), overlays live risk signals (sanctions, cyber incidents,
geopolitics, weather), and simulates *"what if supplier X goes down"* — showing cascade
effects and suggesting alternatives.

## Why corporations need this
- Visibility: most companies don't know their tier-2/3 suppliers
- Early warning: risk signals mapped to *your* suppliers, not generic news
- Resilience planning: simulate disruptions before they happen
- Compliance: sanctions / ownership screening built in

## Architecture

```
frontend/   React + Vite — supplier graph & map visualization, simulation UI
backend/    FastAPI — graph API, risk scoring, simulation engine
data/       Sample supplier networks, sanctions lists, risk feeds
docs/       Pitch deck, architecture notes
```

## Core features (MVP)
1. **Supplier graph** — import suppliers (CSV), visualize dependency network
2. **Risk overlay** — score each node from external signals (news, sanctions lists)
3. **Disruption simulation** — click a node, see the cascade, get alternatives
4. **Risk dashboard** — top exposures, single points of failure

## Quick start

```bash
# backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# frontend
cd frontend && npm install && npm run dev
```

## Team
_(fill in — 5 members)_

| Role | Who |
|------|-----|
| Frontend — graph/map viz | |
| Frontend — UI/design | |
| Backend — API & graph model | |
| AI/Data — risk scoring & ingestion | |
| Pitch & demo | |

## License
MIT
