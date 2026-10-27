# Fuel Route Planner API

A Django 6.1 + Django REST Framework API. You give it a `start` and a `finish` in the USA,
and it returns:

- the Route;
- the cheapest Fuel stops for a vehicle with a 500-mile Range at 10 MPG that starts with an
  empty tank;
- the total fuel cost;
- the map as GeoJSON, plus a link to an interactive map page.

Prices come from the supplied file (`data/fuel-prices-for-be-assessment.csv`, about 8,000
truck stops). An uncached request makes **one** external call, to the free OSRM routing
service. A repeated request is answered from the cache in about 3 ms.

**Vocabulary.**

- **Station:** one truck stop from the price file.
- **Route:** one driving path from start to finish.
- **Corridor:** the 8-mile band either side of a Route.
- **Start zone:** the first 8 miles of a Route.
- **Mile marker:** how far along the Route a Station is.
- **Fuel stop:** a Station where the plan buys fuel.
- **Range:** 500 miles on a full tank.

## Quick start

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.12 for you if needed.

```bash
uv sync                    # install dependencies
cp .env.example .env       # local settings
uv run python -c "import secrets, pathlib; p = pathlib.Path('.env'); p.write_text(p.read_text().replace('SECRET_KEY=change-me', 'SECRET_KEY=' + secrets.token_urlsafe(50)))"
make load                  # create SQLite and load 6,738 Stations (offline, about 1 s)
make run                   # http://localhost:8000
```

Then try one of these:

- **Swagger UI:** <http://localhost:8000/api/docs/>. Every parameter has the named examples.
- **Postman:** import `postman/fuel-route-planner.postman_collection.json`. Its `baseUrl`
  variable defaults to `http://localhost:8000`.
- **curl:** `curl "http://localhost:8000/api/route/?start=Chicago,%20IL&finish=Los%20Angeles,%20CA"`
- **Map:** <http://localhost:8000/api/route/map/?start=Chicago,%20IL&finish=Los%20Angeles,%20CA>

## API

| Method and path | Returns |
|---|---|
| `GET /api/route/?start=…&finish=…` | the plan as JSON |
| `GET /api/route/map/?start=…&finish=…` | the same plan on a Leaflet map (HTML) |
| `GET /api/places/?q=…` | "City, ST" suggestions from the local Census file (powers the map page's autocomplete; 0 external calls) |
| `GET /api/docs/` | Swagger UI |
| `GET /api/schema/` | OpenAPI 3 schema |

`start` and `finish` each accept three forms. They are tried in this order:

1. `"lat,lng"`, for example `41.8781,-87.6298`. Parsed locally, with no external call.
2. `"City, ST"`, for example `Chicago, IL`. Looked up in a local Census places file, with
   no external call. Consolidated city-counties are found by their city's name (Census
   calls Nashville "Nashville-Davidson metropolitan government (balance)"), and so are
   Honolulu and Boise.
3. Any other US address or place, for example `233 S Wacker Dr, Chicago, IL`. Sent to
   Nominatim (one call), and the result is cached for 30 days.

Planning creates nothing, so the API is GET only, and a POST returns 405. Every response,
errors included, has two headers: `X-External-Calls` and `X-Response-Time-Ms`.

### Example

This is a real response to `GET /api/route/?start=Dallas, TX&finish=Houston, TX`. Only the
GeoJSON features are left out here:

```json
{
  "start":  {"query": "Dallas, TX",  "lat": 32.793333, "lon": -96.766513, "resolved_by": "census"},
  "finish": {"query": "Houston, TX", "lat": 29.785743, "lon": -95.388806, "resolved_by": "census"},
  "route": {"distance_miles": 238.25, "duration_hours": 4.25},
  "fuel_stops": [
    {"station_id": 72773, "name": "RaceTrac #2626", "address": "I-20 Exit 472",
     "city": "Dallas", "state": "TX", "lat": 32.793333, "lon": -96.766513,
     "price_per_gallon": 2.864, "mile_marker": 0.0, "gallons": 1.597, "cost": 4.57,
     "on_route": true},
    {"station_id": 63669, "name": "One9 #1248", "address": "I-45, EXIT 271",
     "city": "Wilmer", "state": "TX", "lat": 32.599015, "lon": -96.681585,
     "price_per_gallon": 2.75566666, "mile_marker": 16.0, "gallons": 22.228, "cost": 61.25,
     "on_route": true}
  ],
  "total_gallons": 23.825,
  "total_fuel_cost": 65.82,
  "alternatives": [],
  "assumptions": {"range_miles": 500.0, "mpg": 10.0, "tank_gallons": 50.0,
                  "starting_fuel": "empty", "reserve_miles": 0.0, "corridor_miles": 8.0,
                  "start_zone_miles": 8.0,
                  "station_locations": "city-level; the detour to reach a Station is ignored"},
  "map": {
    "geojson": {"type": "FeatureCollection", "features": ["route line, start, finish, 2 numbered stops"]},
    "url": "http://localhost:8000/api/route/map/?start=Dallas%2C+TX&finish=Houston%2C+TX"
  },
  "meta": {"external_calls": 1, "cache": "miss",
           "timings_ms": {"geocode": 0.0, "routing": 4661.2, "corridor": 3.1, "optimize": 0.2, "total": 4673.5}}
}
```

The fields work like this:

- **`fuel_stops`:** the stops in driving order. The costs add up exactly, to the cent, to
  `total_fuel_cost`.
- **`total_gallons`:** always the Route distance divided by MPG.
- **`alternatives`:** the other Routes OSRM offered, each with its distance, duration and fuel
  cost. A Route that can't be fuelled (a gap longer than the Range) is left out.
- **`map.geojson`:** the chosen Route and the alternatives as lines, plus the start, the
  finish and the numbered Fuel stops as points.

### Errors

Every error has the same shape: `{"error": {"code", "message", "details"}}`.

| Status | `code` | When |
|---|---|---|
| 400 | `INVALID_INPUT` | `start` or `finish` is missing, blank, too long or bad coordinates; or both are the same place |
| 405 | `METHOD_NOT_ALLOWED` | anything but GET |
| 422 | `LOCATION_NOT_FOUND` | the place can't be found |
| 422 | `LOCATION_OUTSIDE_USA` | the place is outside the USA's 50 states (e.g. `Toronto, ON`, or `San Juan, PR`) |
| 422 | `NO_ROUTE` | OSRM has no drivable Route between the points |
| 422 | `NO_STATION_AT_START` | no Stations are loaded at all, so an empty tank can't leave |
| 422 | `UNREACHABLE` | a gap longer than the Range; `details.mile_marker` says where the tank runs dry |
| 502 | `ROUTING_PROVIDER_ERROR` | OSRM or Nominatim failed or was unreachable |
| 504 | `ROUTING_PROVIDER_TIMEOUT` | OSRM or Nominatim was too slow |
| 500 | `INTERNAL_ERROR` | a bug (logged) |

The map page shows the same code and HTTP status on a short HTML error page.

## How it works

At startup, every Station is loaded from SQLite into an in-memory KD-tree
(`routing/services/station_index.py`), so requests never query the database. A request to
`GET /api/route/` then goes through five steps:

1. **View and cache** (`routing/views.py`). `RouteQuerySerializer` validates `start` and
   `finish`. `plan_trip_body` returns the cached plan if there is one (kept 24 h, keyed on
   the normalised text plus the vehicle settings and OSRM server). The API and the map page share this function, so opening the map
   after calling the API costs nothing.
2. **Resolve the locations** (`routing/services/locations.py`). Each input is parsed as
   `"lat,lng"`, or looked up as `"City, ST"` (`places.py`, Census data), or sent to
   Nominatim (`nominatim.py`). Whichever form was used, the point must be inside a coarse
   outline of the 50 states (`usa.py`), so Puerto Rico and the other territories are
   rejected (no road reaches them anyway).
3. **Route** (`routing/services/osrm.py`). One OSRM call with `alternatives=true` returns
   up to 3 Routes, as compact `polyline6` geometry.
4. **Corridor** (`routing/services/corridor.py`). Each Route is resampled to one point per
   mile. One KD-tree query finds every Station within 8 miles of the Route. A Station's
   Mile marker is the mileage of its nearest sample point, and Stations in the Start zone
   count as Mile marker 0. If the Start zone has none, the Station nearest the start is
   put at Mile marker 0: the truck is assumed to start there.
5. **Optimize and choose** (`routing/services/optimizer.py`, `planner.py`). The greedy
   optimizer plans each Route, and the Route with the cheapest fuel wins. A tie within
   $0.01 goes to the faster Route. `serializers.py` and `route_map.py` build the JSON and
   the GeoJSON. `routing/middleware.py` adds the headers and logs one line per request.

The services are small typed functions with plain-data inputs and outputs. Errors are
exceptions that carry a `code`, and `routing/errors.py` maps each code to its HTTP status
in one place.

## Assumptions

- **Empty tank at the start.** With 0 fuel the truck has to begin at a pump, so the first
  Fuel stop is at Mile marker 0:
  - the cheapest Station in the Start zone (the first 8 miles of the Route), or
  - when the Start zone has none, the Station nearest the start, **however far away**.
    The truck is assumed to start there, and the drive to it is not costed. That stop has
    `"on_route": false`, and the map tags it "trip starts here".

  The fallback matters for small towns: 58% of the 31,825 places the autocomplete offers
  have no Station within 8 miles. For half of those the nearest is within 15 miles, but it
  can be far: Key West starts at Marathon, FL (49 miles), and Fairbanks, AK at Whitehorse, Yukon
  (488 miles). The nearest Station can even lie past the finish: Española → Santa Fe, NM
  starts at Algodones, 50 miles away, for a 28-mile trip.
- **Fuel bought.** The total gallons equal Route distance / MPG. No fuel is left over at
  the finish, and the Reserve is 0. A 0-mile Route (two points that snap to the same spot
  on the road) needs no fuel and has no Fuel stops.
- **Only Routes that can be fuelled are offered.** OSRM returns up to 3 Routes. Any Route
  with a gap longer than the Range between Stations is dropped. It appears neither in
  `alternatives` nor on the map. If no Route can be fuelled, the request fails with
  `UNREACHABLE` (or `NO_STATION_AT_START`).
- **8-mile Corridor.** A Station counts as on the Route if it is within 8 miles of it. I
  checked this on 5 real Routes with 160 Stations at interstate exits on the Route. An
  8-mile Corridor catches 86% of them, against 68% at 3 miles and 82% at 5 miles. Going to
  10 miles catches nothing more (86%), and 15 miles reaches only 88% while adding false
  positives.
- **City-level Station locations.** The addresses are highway exits ("I-44, EXIT 283 &
  US-69"), which street geocoders can't place. So each Station sits at its city's Census
  point, and the detour from the Route to the Station is ignored.
- **One price per Station.** When an OPIS ID appears more than once, the cheapest price is
  used. 678 IDs repeat, and 597 of them with different prices. Exact duplicate rows (26)
  are dropped, and whitespace is trimmed.
- **Canadian Stations are kept.** The file has 112 of them after cleaning, priced in USD per
  gallon, and they count when a Route passes near Canada. The start and finish must still
  be in the USA.
- **Money.** Each stop's cost is rounded to cents, and the total is the sum of the rounded
  stop costs.
- **Locations.**
  - Coordinates are written latitude first (`"41.8781,-87.6298"`). If they look swapped,
    the error suggests the right order.
  - `"City, ST"` uses the Census point of that place. About 200 names repeat within a state (two
    "Springfield, PA"); the first in the Census file is used.
  - Autocomplete offers only places that pass the USA check, so every suggestion plans
    without a geocoding call.
- **Configurable.** Range, MPG, Reserve and Corridor width are settings in `.env`.

## Why the plan is the cheapest

Treat fuel as miles of driving.

1. Every mile of road must be driven on fuel bought at a Station before that mile, and no
   more than 500 miles back (the Range).
2. So no plan can beat paying, for each mile, the lowest price among the Stations in the
   500 miles before it.
3. The greedy achieves exactly that. At each Station, if a cheaper Station is within Range,
   it buys just enough fuel to reach it. If not, it fills the tank (or buys just enough to
   finish), because every mile it can reach is best paid for here.
4. Suppose some plan bought fuel for a mile at a pricier Station when a cheaper one was in
   Range. Moving that gallon to the cheaper Station lowers the cost and keeps the plan
   feasible, because the tank never holds more than 500 miles of fuel.
5. Repeat this swap until none is left, and you have the greedy's plan. So nothing is
   cheaper.

The tests confirm this. On 200 random trips, the greedy total matches an exhaustive search
over every purchase in 0.1-gallon steps, to within $0.019, and the whole difference comes
from rounding to cents. It also matches on the real Chicago→LA trip.

### Why a plan can include tiny top-ups

The optimizer minimises fuel cost only, and a stop costs nothing extra. So it will buy a
little fuel just to reach a slightly cheaper Station a few miles on, because every gallon
bought there instead saves money.

- **Dallas→Houston (the example above).** The plan buys 1.6 gallons at $2.864 in Dallas
  and the other 22.2 at $2.756 in Wilmer, 16 miles on.
- **Chicago→LA, measured on the chosen 2,028.93-mile Route.** The cheapest plan has 18
  Fuel stops and costs **$615.79**. An imagined $5 charge per stop would cut it to 7 stops
  at $621.87 of fuel, and the fewest stops possible (5) cost $646.15.

I kept the pure cheapest plan because the brief asks for cost-effective stops. If drivers
prefer fewer stops, a per-stop penalty would be a small change to the optimizer.

## Performance

Measured on 2026-10-27, on a laptop with `make run` (the Django dev server) against the
public OSRM demo server.

| Request | Time (server) | External calls |
|---|---|---|
| Chicago, IL → Los Angeles, CA, uncached | 1.26 s: OSRM 1.17 s, corridor 14 ms (2 Routes), optimizer 0.8 ms | 1 |
| Denver, CO → Kansas City, MO, first request after server start | 0.37 s | 1 |
| Same request again (cache hit) | 2.0–2.6 ms | 0 |
| Map page for it, after the API call | 11.5 ms | 0 |
| Dallas, TX → Houston, TX, uncached | 3.0–4.7 s, almost all OSRM | 1 |
| Error before routing (e.g. `Toronto, ON`, missing field) | 1–3 ms | 0 |

Other measurements:

- **Response size.** The Chicago→LA JSON is 64.7 KB, because the map lines are simplified
  for display. OSRM's own answer for that trip is about 210 KB as `polyline6`, against
  about 1 MB as GeoJSON, which is why the API asks for `polyline6`.
- **Keep-alive connection.** All external calls share one keep-alive session, and the server
  opens the OSRM connection at startup. A reused TLS connection saves about 0.3 s per call
  (a small OSRM request: 0.48 s fresh, 0.15 s reused).
- **Station index.** Building the KD-tree over 6,738 Stations takes 3.2 ms. Querying it
  with the 2,016 one-mile samples of Chicago→LA takes 2.7 ms, where brute-force numpy takes
  328 ms for the same answer.
- **Loading the data.** `load_stations` reads the 8,151 rows and loads the Stations in
  0.2 s.
- **OSRM varies.** Almost all of the uncached time is OSRM, and it varies a lot. Within
  minutes of each other, the same Chicago→LA request took 1.4 s and then timed out (see
  below).

## External services and their limits

| Service | Used for | Limits |
|---|---|---|
| [OSRM demo server](https://router.project-osrm.org) | routing, 1 call per uncached request | at most 1 request/s, non-commercial use, no uptime guarantee |
| [Nominatim](https://nominatim.openstreetmap.org) | free-text addresses only | at most 1 request/s, an identifying User-Agent, cache the results ([policy](https://operations.osmfoundation.org/policies/nominatim/)) |
| OpenStreetMap tiles and Leaflet (unpkg) | the map page, loaded by the browser | no API key; OSM blocks tile requests without a Referer, so the tile layer sends one explicitly |
| US Census Gazetteer 2024 | Station and city coordinates, offline only | public domain |

**Timeouts.** Every OSRM and Nominatim call gets 10 seconds in total, from connecting to
the last byte, and no retries, so one request never makes more than one routing call.
`requests` only times the connect and each read separately, so `routing/services/http.py`
downloads in a worker thread and stops waiting for it once the 10 s are up; the worker
then stops reading too.

**The OSRM demo server is best-effort.** It sometimes overloads. During development it
returned a 504 after 21 s and a 502 after 13 s, while a small request still answered in
1.6 s. While I wrote this, long Routes timed out several times in a row for a few minutes.
The API reports these as `ROUTING_PROVIDER_TIMEOUT` or `ROUTING_PROVIDER_ERROR`.

There are two ways around it:

- **Switch to FOSSGIS.** The server behind openstreetmap.org's directions speaks the same
  API and returns the same Routes. Set this in `.env`:

  ```
  OSRM_BASE_URL=https://routing.openstreetmap.de/routed-car
  ```

  It is slower. In one comparison it took 8.9 s against the demo server's 2.1 s, and a
  raw Chicago→LA call took 18.8 s while the demo server was overloaded. So also raise
  `HTTP_TIMEOUT_SECONDS` (e.g. to 30) when you switch. This is a manual switch, not
  automatic failover, so a request still makes one call.
- **Self-host OSRM** with Docker and a US extract, and point `OSRM_BASE_URL` at it.

**Nominatim User-Agent.** Nominatim answers 403 to placeholder contacts such as
`you@example.com`. The default in `.env.example` works, but put your own contact there if
you have one.

## Known limitations

- **Detours are ignored.** Station locations are city-level, so the detour from the Route
  to a Station isn't counted. A Station in a big city can sit a few miles from the exit it
  serves.
- **The Corridor misses some Stations.** It catches about 86% of the Stations at exits on
  the Route, so a slightly cheaper Station can occasionally be missed.
- **Static prices.** They come from the file, with no live prices, one fuel grade and one
  vehicle profile.
- **The plan cache ignores the price data.** It is keyed on `start`, `finish`, the vehicle
  settings (`RANGE_MILES`, `MPG`, `MIN_RESERVE_MILES`, `CORRIDOR_MILES`) and
  `OSRM_BASE_URL`, so changing those never serves an old plan. After reloading Stations
  from a new price file, restart the server (the default in-memory cache) or clear the
  cache.
- **The default cache is per process.** Set `CACHE_URL` (e.g. `redis://…`) to share it
  between workers.
- **Nominatim pacing is per process.** Nominatim calls are spaced at least 1 s apart within
  one server process (a request with two free-text places waits about 1 s for the second).
  Several worker processes would each keep their own pace. Results are cached, which is
  fine for a demo but not for heavy traffic.
- **Unreachable places.** Hawaii and other places with no road to the start can't be
  planned (`NO_ROUTE`).
- **Gaps in the price file.** Some Routes run longer than the Range between Stations in
  the file. Anchorage → Seattle crosses Yukon and British Columbia, and fails with
  `UNREACHABLE` at Mile marker 500. The highway has fuel, but the file has no Station there.
- **The fallback start can be far away.** With no distance limit, the Station the truck
  starts at can be hundreds of miles from the place typed (488 miles for Fairbanks).
- **No production setup.** There is no authentication, rate limiting or production server
  configuration.

## Data

| File | What it is |
|---|---|
| `data/fuel-prices-for-be-assessment.csv` | the supplied price file, never modified: 8,151 rows, no coordinates |
| `data/city_coords.csv` | one row per city and state in the price file (3,898): lat, lon and source (3,658 Census, 240 Nominatim) |
| `data/us_places.csv` | Census places (32,333) for resolving `"City, ST"` input |

`make load` (migrate + `load_stations`) builds the Station table from these files offline.
It is safe to re-run. `make build-data` (`build_city_coords`) regenerates the two
coordinate files:

1. It downloads the 2024 Census Gazetteer.
2. It matches each city locally after normalising case, "St."/"Saint" and place-type
   suffixes.
3. It sends only the leftovers to Nominatim, at 1 request/s. This step is incremental:
   cities already resolved are skipped.

It needs the internet, and only a maintainer runs it after a new price file arrives.

## Development

```bash
make test     # pytest: 197 tests, about 6 s; real network access is blocked
make lint     # ruff check + ruff format --check
make format   # apply ruff fixes and formatting
```

The tests mock OSRM and Nominatim at the HTTP layer, with a real recorded OSRM response.
They cover:

- the HTTP API: every input form, every error code, caching and headers;
- the optimizer: hand-built cases plus the brute-force optimality check;
- Corridor matching, location resolution and the data commands;
- the OpenAPI schema and its examples.

All settings are in `.env.example`, read through django-environ in `fuelroute/settings.py`.
