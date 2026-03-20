#!/usr/bin/env python3
"""
Samsung Health CSV Importer for Grafana / InfluxDB
====================================================
Reads exported Samsung Health data (from the Galaxy Watch 7 / Samsung Health
app) and writes the time-series measurements to InfluxDB so they can be
visualised in Grafana.

Supported Samsung Health export files
--------------------------------------
  com.samsung.health.heart_rate.*.csv
  com.samsung.health.step_count.*.csv
  com.samsung.shealth.calories_burnt.*.csv
  com.samsung.shealth.tracker.pedometer_step_count.*.csv
  com.samsung.health.sleep.*.csv
  com.samsung.health.sleep_stage.*.csv
  com.samsung.health.blood_oxygen.*.csv     (SpO2)
  com.samsung.health.stress.*.csv
  com.samsung.health.body.*.csv             (body composition / weight)

How to export data from Samsung Health
---------------------------------------
1. Open the Samsung Health app on your phone.
2. Tap the three-dot menu → Settings → Download personal data.
3. Extract the downloaded ZIP to a folder.
4. Point this script at that folder with --input-dir.

Usage
-----
    python ingest_samsung_health.py --input-dir /path/to/export [options]

Options
    --input-dir   Directory containing Samsung Health CSV files  (required)
    --url         InfluxDB URL           (default: http://localhost:8086)
    --token       InfluxDB API token     (default: my-super-secret-token)
    --org         InfluxDB organisation  (default: samsung_health)
    --bucket      InfluxDB bucket        (default: galaxy_watch)
    --dry-run     Parse files but do NOT write to InfluxDB
"""

import argparse
import csv
import glob
import os
import sys
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(raw: str) -> datetime:
    """Parse a Samsung Health timestamp string to a UTC datetime."""
    raw = raw.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {raw!r}")


def _float(val: str, default: float = 0.0) -> float:
    try:
        return float(val.strip()) if val.strip() else default
    except (ValueError, AttributeError):
        return default


def _int(val: str, default: int = 0) -> int:
    try:
        return int(float(val.strip())) if val.strip() else default
    except (ValueError, AttributeError):
        return default


# ---------------------------------------------------------------------------
# Per-measurement parsers
# Each returns a list of influxdb_client Point objects.
# ---------------------------------------------------------------------------

def parse_heart_rate(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower() or "time" in k.lower()), None)
            bpm_col = next((k for k in row if "heart_rate" in k.lower() or "bpm" in k.lower()), None)
            if not ts_col or not bpm_col or not row.get(ts_col) or not row.get(bpm_col):
                continue
            try:
                p = (
                    Point("heart_rate")
                    .field("bpm", _float(row[bpm_col]))
                    .time(_ts(row[ts_col]), WritePrecision.S)
                )
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_steps(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower()), None)
            cnt_col = next((k for k in row if "count" in k.lower() or "step" in k.lower()), None)
            cal_col = next((k for k in row if "calorie" in k.lower()), None)
            dist_col = next((k for k in row if "distance" in k.lower()), None)
            if not ts_col or not cnt_col or not row.get(ts_col):
                continue
            try:
                p = (
                    Point("steps")
                    .field("count", _int(row.get(cnt_col, "0")))
                    .time(_ts(row[ts_col]), WritePrecision.S)
                )
                if cal_col and row.get(cal_col):
                    p = p.field("kcal", _float(row[cal_col]))
                if dist_col and row.get(dist_col):
                    p = p.field("distance_m", _float(row[dist_col]))
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_calories(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower() or "day_time" in k.lower()), None)
            cal_col = next((k for k in row if "calorie" in k.lower()), None)
            if not ts_col or not cal_col or not row.get(ts_col) or not row.get(cal_col):
                continue
            try:
                p = (
                    Point("calories")
                    .field("kcal", _float(row[cal_col]))
                    .time(_ts(row[ts_col]), WritePrecision.S)
                )
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_sleep(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower()), None)
            dur_col = next((k for k in row if "duration" in k.lower()), None)
            score_col = next((k for k in row if "score" in k.lower()), None)
            if not ts_col or not row.get(ts_col):
                continue
            try:
                p = Point("sleep").time(_ts(row[ts_col]), WritePrecision.S)
                if dur_col and row.get(dur_col):
                    # Samsung Health stores duration in milliseconds
                    dur_ms = _float(row[dur_col])
                    p = p.field("duration_minutes", dur_ms / 60000.0)
                if score_col and row.get(score_col):
                    p = p.field("score", _float(row[score_col]))
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_sleep_stage(path: str) -> List[Point]:
    """
    Samsung Health sleep stage values:
      40001 = Awake, 40002 = Light, 40003 = Deep, 40004 = REM
    """
    stage_map = {
        "40001": "Awake",
        "40002": "Light",
        "40003": "Deep",
        "40004": "REM",
    }
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower()), None)
            end_col = next((k for k in row if "end_time" in k.lower()), None)
            stage_col = next((k for k in row if "stage" in k.lower()), None)
            if not ts_col or not row.get(ts_col):
                continue
            try:
                start_dt = _ts(row[ts_col])
                stage_raw = str(_int(row.get(stage_col or "", "0")))
                stage_name = stage_map.get(stage_raw, "Unknown")
                duration_min = 0.0
                if end_col and row.get(end_col):
                    end_dt = _ts(row[end_col])
                    duration_min = (end_dt - start_dt).total_seconds() / 60.0
                p = (
                    Point("sleep_stage")
                    .tag("stage", stage_name)
                    .field("minutes", duration_min)
                    .time(start_dt, WritePrecision.S)
                )
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_spo2(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower() or "time" in k.lower()), None)
            spo2_col = next((k for k in row if "spo2" in k.lower() or "oxygen" in k.lower()), None)
            if not ts_col or not spo2_col or not row.get(ts_col) or not row.get(spo2_col):
                continue
            try:
                p = (
                    Point("spo2")
                    .field("percent", _float(row[spo2_col]))
                    .time(_ts(row[ts_col]), WritePrecision.S)
                )
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_stress(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower() or "time" in k.lower()), None)
            score_col = next((k for k in row if "stress" in k.lower() or "score" in k.lower()), None)
            if not ts_col or not score_col or not row.get(ts_col) or not row.get(score_col):
                continue
            try:
                p = (
                    Point("stress")
                    .field("score", _float(row[score_col]))
                    .time(_ts(row[ts_col]), WritePrecision.S)
                )
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


def parse_body_composition(path: str) -> List[Point]:
    points: List[Point] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_col = next((k for k in row if "start_time" in k.lower() or "time" in k.lower()), None)
            weight_col = next((k for k in row if "weight" in k.lower()), None)
            fat_col = next((k for k in row if "fat" in k.lower() and "percent" in k.lower()), None)
            muscle_col = next((k for k in row if "muscle" in k.lower() and "percent" in k.lower()), None)
            bmi_col = next((k for k in row if "bmi" in k.lower()), None)
            if not ts_col or not row.get(ts_col):
                continue
            try:
                p = Point("body_composition").time(_ts(row[ts_col]), WritePrecision.S)
                if weight_col and row.get(weight_col):
                    p = p.field("weight_kg", _float(row[weight_col]))
                if fat_col and row.get(fat_col):
                    p = p.field("body_fat_percent", _float(row[fat_col]))
                if muscle_col and row.get(muscle_col):
                    p = p.field("muscle_mass_percent", _float(row[muscle_col]))
                if bmi_col and row.get(bmi_col):
                    p = p.field("bmi", _float(row[bmi_col]))
                points.append(p)
            except (ValueError, KeyError):
                continue
    return points


# ---------------------------------------------------------------------------
# File dispatcher
# ---------------------------------------------------------------------------

FILE_PARSERS = {
    "heart_rate":    parse_heart_rate,
    "step_count":    parse_steps,
    "pedometer":     parse_steps,
    "calories":      parse_calories,
    "sleep_stage":   parse_sleep_stage,
    "sleep":         parse_sleep,
    "blood_oxygen":  parse_spo2,
    "stress":        parse_stress,
    "body":          parse_body_composition,
}


def dispatch(filepath: str) -> List[Point]:
    name = os.path.basename(filepath).lower()
    for keyword, parser in FILE_PARSERS.items():
        if keyword in name:
            return parser(filepath)
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Samsung Health CSV exports into InfluxDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input-dir", required=True, help="Directory with Samsung Health CSV files")
    parser.add_argument("--url",    default=os.getenv("INFLUXDB_URL",    "http://localhost:8086"))
    parser.add_argument("--token",  default=os.getenv("INFLUXDB_TOKEN",  "my-super-secret-token"))
    parser.add_argument("--org",    default=os.getenv("INFLUXDB_ORG",    "samsung_health"))
    parser.add_argument("--bucket", default=os.getenv("INFLUXDB_BUCKET", "galaxy_watch"))
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to InfluxDB")
    args = parser.parse_args()

    csv_files = glob.glob(os.path.join(args.input_dir, "**", "*.csv"), recursive=True)
    if not csv_files:
        print(f"No CSV files found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    client = None
    write_api = None
    if not args.dry_run:
        client = InfluxDBClient(url=args.url, token=args.token, org=args.org)
        write_api = client.write_api(write_options=SYNCHRONOUS)

    total_written = 0
    for filepath in sorted(csv_files):
        points = dispatch(filepath)
        if not points:
            print(f"  [skip]  {os.path.basename(filepath)} — unrecognised or empty")
            continue
        print(f"  [parse] {os.path.basename(filepath)} — {len(points)} point(s)")
        if not args.dry_run:
            write_api.write(bucket=args.bucket, org=args.org, record=points)
            total_written += len(points)

    if args.dry_run:
        print("\nDry-run complete — no data written to InfluxDB.")
    else:
        print(f"\nDone. {total_written} point(s) written to InfluxDB bucket '{args.bucket}'.")

    if client:
        client.close()


if __name__ == "__main__":
    main()
