# Rail data

Source: datameet/railways (stations.json, trains.json, schedules.json).
Licence: CC0 1.0. Data date: about 2016 (timetables are old; use for graph
structure and rough timings only, never as live schedules).

## Current contents: SAMPLE ONLY

`sample_raw/` holds a tiny hand-made dataset in the datameet format (15
stations, 9 fictional trains numbered 90001-90009, approximate coordinates;
90008 and 90009 run Bengaluru-Mysuru).
`rail_stations.json` and `rail_trains.json` are built from it. The real
datameet files could not be downloaded from the cloud session (egress policy
blocked raw.githubusercontent.com), so the full six-state subset is still to be
generated.

## Regenerate

```
python apps/api/routes/scripts/build_rail.py --src <dir with the three datameet files>
```

Keeps stations in Karnataka, Goa, Maharashtra, Kerala, Tamil Nadu and Andhra
Pradesh and trains with two or more stops in them. Output is gzipped
(`*.json.gz`) when over 5 MB. Run it in GitHub Actions or on a machine with
network access, then commit the output.
