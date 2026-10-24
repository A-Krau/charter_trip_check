# Charter Trip Check: Requirements

_Status: draft v1, 2026-10-24_

## Purpose

Competitive analysis for charter trips. The operator announces possible ASAP
trips between two airports, and crews are told to get ready, but many of those
trips end up flown by someone else. The tool shows which aircraft (and, where
possible, which operator) flew or plans to fly a route in a time window, so the
trip can be sold better next time.

## Users

- A single user (a charter pilot) to start.
- No login or multi-user features in v1.

## Inputs

- Departure airport (ICAO, e.g. `KTEB`; IATA accepted and converted where possible).
- Arrival airport (ICAO/IATA).
- Time window: a start and an end date/time. The UI defaults to recent presets
  (e.g. "yesterday", "last 3 days"), since most lookups cover a few days.

## Outputs

A table of flights matching the route in the window, one row per flight:

| Field | Notes |
|---|---|
| Tail number (registration) | From the ICAO24 hex via an aircraft database |
| Aircraft type | e.g. C56X, CL35, GLF4 |
| Operator / owner | From the aircraft database, or inferred from the callsign prefix (e.g. `EJA` = NetJets) |
| Callsign | As broadcast |
| Departure time | First seen / actual off time |
| Arrival time | Last seen / actual on time |
| Status | Completed (v1). Scheduled, en route (v2) |
| Source | Which data provider produced the row |

Nice to have: sort/filter by operator or type, and export to CSV.

## Interface

- A simple but well-built single-page web UI: a search form plus a results table.
- Runs in a Docker container (Docker Compose), opened in a browser.
- Reasonable on a phone screen.

## Data sources

### v1: past flights (free)

**OpenSky Network REST API**
- `GET /flights/departure?airport=<ICAO>&begin=<unix>&end=<unix>`, filtered by
  `estArrivalAirport` to the requested destination.
- Max 7 days per query. Longer windows are split into chunks.
- Flight data is batch-processed, so the most recent flights appear with a
  delay (typically by the next day).
- Auth: OAuth2 client credentials (a free account). Free accounts get a daily
  credit budget, so results are cached.
- Tail number, type, and operator come from the OpenSky aircraft metadata
  database, joined on ICAO24.

### v2: near-term and planned flights

The main long-term use is "today / tomorrow". Free sources do not reliably
publish filed private or charter flight plans. Candidates:

- **FlightAware AeroAPI** (personal tier with a small monthly free credit): route
  search including scheduled and filed flights.
- **OpenSky live state vectors**: aircraft airborne right now, matched against
  the destination (rough heuristic, no plan data).
- **FAA SWIM (TFMS flight data)**: free, but needs approval and integration work.

The backend uses a provider interface, so these can be added without changing
the UI.

### v3: longer history

Build up a local history (store every lookup's results in SQLite) to spot
repeat competitors on a route over weeks or months.

## Known limitations

- **Privacy programs:** aircraft in FAA LADD or PIA may be hidden or use
  rotating ICAO addresses, so some flights will be missing or unattributable.
- **Coverage:** ADS-B receiver coverage at smaller airports can be thin, so
  departure or arrival airport estimates may be missing for some flights.
- **Operator attribution** is best-effort. A registered owner is often an LLC,
  not the certificate holder.

## Technical constraints

- Python backend (FastAPI), with a lightweight frontend (server-rendered or a
  small static page, no heavy build chain).
- SQLite for the cache and history, kept on a Docker volume.
- API credentials come from environment variables / a `.env` file and are
  never committed.
- One `docker compose up` brings everything up.

## Open questions

1. **OpenSky terms:** free access is meant for non-commercial and research use,
   and OpenSky offers a separate commercial tier. Confirm that personal
   competitive analysis is acceptable, or plan for the commercial tier or
   another provider.
2. Which v2 source to use for planned flights (AeroAPI is the likely choice).
3. Where the container will run (a home server, a laptop, or a cloud VM).
