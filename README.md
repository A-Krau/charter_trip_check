# Charter Trip Check

Find out who flew a charter trip you were told to get ready for. Enter a
departure airport, an arrival airport and a time window, and the app lists the
aircraft that flew that route, with tail number, type and operator, on a dark
live-map style page.

Flight data comes from the free [OpenSky Network](https://opensky-network.org)
API, for personal, non-commercial use. See [docs/requirements.md](docs/requirements.md)
for the full requirements and roadmap.

## Run it

You need Docker with the Compose plugin on the machine that will host it.

```sh
git clone https://github.com/A-Krau/charter_trip_check.git
cd charter_trip_check
cp .env.example .env        # then add your OpenSky API client (optional but recommended)
docker compose up -d --build
```

Open `http://<host>:8080`. Change the port with `HOST_PORT` in `.env`.

The image builds natively on both x86-64 and ARM (for example a Raspberry Pi).
There is no login, so keep it on your home network, or put it behind a VPN or
reverse proxy if you want to reach it from outside.

### OpenSky account

Without credentials the app runs anonymously, with a small daily allowance.
For a much bigger allowance, create a free account at opensky-network.org, open
your account page, create an **API client**, and put its `client_id` and
`client_secret` in `.env` as `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`.
Then run `docker compose up -d` again.

## How to read the results

- **Confirmed flights** were seen leaving the departure airport and landing at
  the arrival airport. Times are first and last seen by ADS-B receivers, close
  to takeoff and landing.
- **Unconfirmed flights** had one end that OpenSky could not determine, such as
  a jet that left your departure airport but dropped out of receiver coverage
  before landing. They are worth a look, not proof.
- Click a flight to see its track, colored by altitude, plus links to ADS-B
  Exchange, FlightAware, Flightradar24 and the FAA registry for that aircraft.
- **Time window:** use a preset, **Around a time** (a moment plus or minus 1 to
  12 hours, handy for a trip you were told about), or **Custom** start and end.
- **Filters:** **General Aviation** covers private, charter, fractional and
  corporate flights. **Airline** covers airliner types and airline callsigns.
  The operator list is built from the current results. Like FlightAware's
  filter, the split is a best guess from callsign and aircraft type.
- **CSV** downloads the flights currently shown.

### Limits to know

- OpenSky builds flight lists in a nightly batch. Today's flights usually show
  up tomorrow. Planned and near-term flights are on the roadmap (v2).
- Aircraft in the FAA LADD or PIA privacy programs may be missing or show an
  unfamiliar hex code.
- Tail numbers for US aircraft are derived directly from the transponder code.
  Type and operator come from OpenSky's aircraft metadata when available, and
  from the callsign prefix (for example `EJA` is NetJets).

### Making operator names better

- Add callsign prefixes you run into to `operators.json`. Copy
  `app/data/operators.json`, edit it, and place it in the data volume as
  `/data/operators.json`. Your entries are merged over the built-in list.
- For wider type/operator coverage, download OpenSky's aircraft database CSV,
  place it in the data volume, and set `AIRCRAFT_DB_PATH=/data/<file>.csv` in `.env`.

Copy a file into the volume with:
`docker compose cp operators.json charter-trip-check:/data/operators.json`

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Try the UI without an OpenSky account using the bundled fake API:

```sh
python scripts/mock_opensky.py &
OPENSKY_API_URL=http://127.0.0.1:9100/api DATA_DIR=./data \
  uvicorn app.main:create_app --factory --reload --port 8000
```

Then search KTEB to KPBI. Airport data comes from
[OurAirports](https://ourairports.com/data/) (public domain). Refresh it with
`python scripts/update_airports.py`.
