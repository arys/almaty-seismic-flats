# Almaty seismic flats

2- and 3-room apartments for sale and for rent in Almaty (krisha.kz) overlaid on the city's seismic microzoning map (Institute of Seismology, 2021, via Tengrinews), on Yandex map tiles.

Open `index.html` in a browser. Each flat gets a rating from:

| | good | medium | weak |
|---|---|---|---|
| Seismic zone | 9 | 9 or 10 | 10 |
| Distance to fault | > 500 m | 200–500 m | < 200 m |
| Building | monolithic, 2006+ | older monolithic, panel 1990+, brick 2000+ | older panel/brick |

Good = all three good; weak = any one weak.

## Files

- `index.html` — the map (Leaflet + Yandex tiles, EPSG:3395); buy/rent toggle and room filter load `data/<deal>-<rooms>.js` on demand
- `data/` — tagged listings (`sale-2.js`, `sale-3.js`, `rent-2.js`, `rent-3.js`) and `meta.js` (update date, counts)
- `seismic-zones.webp` — original map, georeferenced and cropped to the city
- `zones-clean.png` — simplified zone/fault layer extracted from the map colours
- `scrape.py` — downloads listings (coordinates from the map API, house type/year from search cards) into `raw/`
- `build.py` — tags listings with zone and fault distance, fills missing house type/year from other ads in the same complex, writes `data/`
- `fit.json`, `counts2.npy`, `fault.npy` — georeferencing fit and per-block zone/fault rasters used by `build.py`

## Daily update

`.github/workflows/update.yml` runs every day at 06:00 Almaty time (and on demand from the Actions tab): scrape → build → commit `data/`. Vercel redeploys on each push.

Run locally: `python3 scrape.py && python3 build.py`

## Caveats

Zones are placed to within ~50 m (image fitted to the OSM city boundary). Fault detection misses short stretches in the city and picks up a few terrain patches in the southern foothills. House type/year come from sellers' ads; for rentals they are often borrowed from other ads in the same complex (marked «по ЖК»). Not a substitute for the building's state expert review and geological survey.
