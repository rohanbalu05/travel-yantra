#!/usr/bin/env python3
"""Record API fixtures into fixtures/recorded/. Stub: TY6-05 fills it in.

Live calls happen only here, from the record-fixtures workflow, with keys
read from the env vars GOOGLE_MAPS_API_KEY and SERPAPI_API_KEY.
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.parse_args()
    print("record.py is a stub; nothing recorded (TY6-05 implements it).")


if __name__ == "__main__":
    main()
