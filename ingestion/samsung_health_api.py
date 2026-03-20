#!/usr/bin/env python3
"""
Samsung Galaxy Watch 7 — Real-Time Data Ingestion API
======================================================
A lightweight Flask REST API that receives health measurements pushed from
a Samsung Galaxy Watch 7 (via a companion Tizen/Galaxy-Watch app or Samsung
Health SDK integration) and stores them in InfluxDB for Grafana visualisation.

Endpoints
---------
POST /api/v1/heart_rate
    Body: {"bpm": 72, "timestamp": "2024-01-15T10:30:00Z"}

POST /api/v1/steps
    Body: {"count": 120, "kcal": 5.2, "distance_m": 90.0,
           "timestamp": "2024-01-15T10:30:00Z"}

POST /api/v1/spo2
    Body: {"percent": 98.0, "timestamp": "2024-01-15T10:30:00Z"}

POST /api/v1/stress
    Body: {"score": 35, "timestamp": "2024-01-15T10:30:00Z"}

POST /api/v1/sleep
    Body: {"duration_minutes": 450, "score": 82,
           "timestamp": "2024-01-15T07:00:00Z"}

POST /api/v1/sleep_stage
    Body: {"stage": "Deep", "minutes": 25.0,
           "timestamp": "2024-01-15T02:00:00Z"}
    stage values: "Awake" | "Light" | "Deep" | "REM"

POST /api/v1/body_composition
    Body: {"weight_kg": 70.5, "body_fat_percent": 18.2,
           "muscle_mass_percent": 38.5, "bmi": 22.1,
           "timestamp": "2024-01-15T08:00:00Z"}

POST /api/v1/batch
    Body: [{"measurement": "heart_rate", "bpm": 72, ...}, ...]
    Send multiple measurements in one request.

GET  /health   — liveness check

Usage
-----
    python samsung_health_api.py [--port 5000]

Environment variables (or use a .env file)
    INFLUXDB_URL    http://localhost:8086
    INFLUXDB_TOKEN  my-super-secret-token
    INFLUXDB_ORG    samsung_health
    INFLUXDB_BUCKET galaxy_watch
    API_PORT        5000
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

app = Flask(__name__)

INFLUXDB_URL    = os.getenv("INFLUXDB_URL",    "http://localhost:8086")
INFLUXDB_TOKEN  = os.getenv("INFLUXDB_TOKEN",  "my-super-secret-token")
INFLUXDB_ORG    = os.getenv("INFLUXDB_ORG",    "samsung_health")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "galaxy_watch")

_client: InfluxDBClient | None = None
_write_api = None


def get_write_api():
    global _client, _write_api
    if _write_api is None:
        _client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        _write_api = _client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def _parse_ts(data: Dict[str, Any]) -> datetime:
    raw = data.get("timestamp")
    if raw:
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%S",  "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(tz=timezone.utc)


def _write(point: Point) -> None:
    get_write_api().write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------

def _handle_heart_rate(data: Dict[str, Any]) -> None:
    bpm = float(data["bpm"])
    p = Point("heart_rate").field("bpm", bpm).time(_parse_ts(data), WritePrecision.S)
    _write(p)


def _handle_steps(data: Dict[str, Any]) -> None:
    p = (
        Point("steps")
        .field("count", int(data["count"]))
        .time(_parse_ts(data), WritePrecision.S)
    )
    if "kcal" in data:
        p = p.field("kcal", float(data["kcal"]))
        _write(Point("calories").field("kcal", float(data["kcal"])).time(_parse_ts(data), WritePrecision.S))
    if "distance_m" in data:
        p = p.field("distance_m", float(data["distance_m"]))
        _write(Point("distance").field("meters", float(data["distance_m"])).time(_parse_ts(data), WritePrecision.S))
    _write(p)


def _handle_spo2(data: Dict[str, Any]) -> None:
    p = Point("spo2").field("percent", float(data["percent"])).time(_parse_ts(data), WritePrecision.S)
    _write(p)


def _handle_stress(data: Dict[str, Any]) -> None:
    p = Point("stress").field("score", float(data["score"])).time(_parse_ts(data), WritePrecision.S)
    _write(p)


def _handle_sleep(data: Dict[str, Any]) -> None:
    p = Point("sleep").time(_parse_ts(data), WritePrecision.S)
    if "duration_minutes" in data:
        p = p.field("duration_minutes", float(data["duration_minutes"]))
    if "score" in data:
        p = p.field("score", float(data["score"]))
    _write(p)


def _handle_sleep_stage(data: Dict[str, Any]) -> None:
    valid_stages = {"Awake", "Light", "Deep", "REM"}
    stage = data.get("stage", "Unknown")
    if stage not in valid_stages:
        raise ValueError(f"Invalid stage '{stage}'. Must be one of {valid_stages}")
    p = (
        Point("sleep_stage")
        .tag("stage", stage)
        .field("minutes", float(data.get("minutes", 0)))
        .time(_parse_ts(data), WritePrecision.S)
    )
    _write(p)


def _handle_body_composition(data: Dict[str, Any]) -> None:
    p = Point("body_composition").time(_parse_ts(data), WritePrecision.S)
    for field in ("weight_kg", "body_fat_percent", "muscle_mass_percent", "bmi"):
        if field in data:
            p = p.field(field, float(data[field]))
    _write(p)


MEASUREMENT_HANDLERS = {
    "heart_rate":       _handle_heart_rate,
    "steps":            _handle_steps,
    "spo2":             _handle_spo2,
    "stress":           _handle_stress,
    "sleep":            _handle_sleep,
    "sleep_stage":      _handle_sleep_stage,
    "body_composition": _handle_body_composition,
}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "samsung-health-api"})


@app.route("/api/v1/heart_rate", methods=["POST"])
def heart_rate():
    data = request.get_json(force=True)
    if "bpm" not in data:
        return jsonify({"error": "Missing required field: bpm"}), 400
    try:
        _handle_heart_rate(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/steps", methods=["POST"])
def steps():
    data = request.get_json(force=True)
    if "count" not in data:
        return jsonify({"error": "Missing required field: count"}), 400
    try:
        _handle_steps(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/spo2", methods=["POST"])
def spo2():
    data = request.get_json(force=True)
    if "percent" not in data:
        return jsonify({"error": "Missing required field: percent"}), 400
    try:
        _handle_spo2(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/stress", methods=["POST"])
def stress():
    data = request.get_json(force=True)
    if "score" not in data:
        return jsonify({"error": "Missing required field: score"}), 400
    try:
        _handle_stress(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/sleep", methods=["POST"])
def sleep():
    data = request.get_json(force=True)
    try:
        _handle_sleep(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/sleep_stage", methods=["POST"])
def sleep_stage():
    data = request.get_json(force=True)
    if "stage" not in data:
        return jsonify({"error": "Missing required field: stage"}), 400
    try:
        _handle_sleep_stage(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/body_composition", methods=["POST"])
def body_composition():
    data = request.get_json(force=True)
    try:
        _handle_body_composition(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"status": "ok"}), 201


@app.route("/api/v1/batch", methods=["POST"])
def batch():
    items = request.get_json(force=True)
    if not isinstance(items, list):
        return jsonify({"error": "Request body must be a JSON array"}), 400

    results = []
    for item in items:
        measurement = item.get("measurement")
        handler = MEASUREMENT_HANDLERS.get(measurement)
        if not handler:
            results.append({"measurement": measurement, "status": "skipped",
                            "reason": f"Unknown measurement '{measurement}'"})
            continue
        try:
            handler(item)
            results.append({"measurement": measurement, "status": "ok"})
        except Exception as exc:
            results.append({"measurement": measurement, "status": "error", "reason": str(exc)})

    return jsonify({"results": results}), 207


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Samsung Health real-time ingestion API")
    ap.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "5000")))
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    print(f"Starting Samsung Health API on {args.host}:{args.port}")
    print(f"InfluxDB: {INFLUXDB_URL}  org={INFLUXDB_ORG}  bucket={INFLUXDB_BUCKET}")
    app.run(host=args.host, port=args.port)
