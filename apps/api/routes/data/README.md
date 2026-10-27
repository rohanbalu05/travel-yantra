# Rail data

## rail_stations.json, rail_trains.json (real, the default)

Source: [datameet/railways](https://github.com/datameet/railways)
(stations.json, trains.json, schedules.json). Licence: CC0 1.0 (public domain
dedication). Data date: about 2016, so the timetables are old; the app says so
and sends people to IRCTC to check the train before booking. Running days are
not in the source, so every train is treated as daily.

Filter: the demo corridors, every station inside the box lat 11.5-16.0, lon
73.6-78.0 (Bengaluru, Mysuru and the Coorg side, Hassan, Chikkamagaluru,
Hosapete for Hampi, Hubballi, Goa), whatever its state field (many datameet
stations have none, Yesvantpur and Chikkamagaluru among them), and the trains
with two or more stops there: 427 stations, 513 trains. `rail_meta.json`
records the source, licence, filter and counts.

Rebuild (the same script `build-rail.yml` runs):

```
curl -fsSL -o <dir>/stations.json https://raw.githubusercontent.com/datameet/railways/master/stations.json
# likewise trains.json and schedules.json
python apps/api/routes/scripts/build_rail.py --src <dir> --out apps/api/routes/data --bbox demo
```

Without `--bbox` the script keeps the six-state subset (Karnataka, Goa,
Maharashtra, Kerala, Tamil Nadu, Andhra Pradesh; 1,173 stations, 1,518 trains).

## sample/ (fictional, fallback only)

`sample/rail_stations.json` and `sample/rail_trains.json` are built from
`sample_raw/`, a tiny hand-made dataset in the datameet format: 16 stations, 14
FICTIONAL trains numbered 90001-90014. They are used only when
`ROUTES_RAIL=sample` is set, when the real files are missing, by the PNR mock
(`sample_pnrs.json` names sample trains) and by unit tests that need a small
fixed network.

```
python apps/api/routes/scripts/build_rail.py --src apps/api/routes/data/sample_raw --out apps/api/routes/data/sample
```

## Other files

- `sample_stays.json`: fictional stays, used when SerpApi Hotels is off.
- `sample_pnrs.json`: fictional PNRs for the PNR timeline mock.
