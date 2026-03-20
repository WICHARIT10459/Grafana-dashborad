"""
Tests for Samsung Health CSV importer and REST API ingestion layer.
"""
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Make the ingestion package importable without installation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))

# ---------------------------------------------------------------------------
# ingest_samsung_health tests
# ---------------------------------------------------------------------------
from ingest_samsung_health import (
    _float,
    _int,
    _ts,
    dispatch,
    parse_body_composition,
    parse_calories,
    parse_heart_rate,
    parse_sleep,
    parse_sleep_stage,
    parse_spo2,
    parse_steps,
    parse_stress,
)


class TestHelpers:
    def test_ts_standard(self):
        dt = _ts("2024-01-15 10:30:00")
        assert dt == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_ts_with_ms(self):
        dt = _ts("2024-01-15 10:30:00.000")
        assert dt.year == 2024

    def test_ts_iso(self):
        dt = _ts("2024-01-15T10:30:00")
        assert dt.tzinfo is not None

    def test_ts_invalid_raises(self):
        with pytest.raises(ValueError):
            _ts("not-a-date")

    def test_float_valid(self):
        assert _float("3.14") == pytest.approx(3.14)

    def test_float_empty(self):
        assert _float("") == 0.0

    def test_float_default(self):
        assert _float("bad", default=99.0) == 99.0

    def test_int_valid(self):
        assert _int("42") == 42

    def test_int_float_string(self):
        assert _int("42.9") == 42

    def test_int_empty(self):
        assert _int("") == 0


def _write_csv(path: str, rows: list, fieldnames: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestParseHeartRate:
    def test_basic(self, tmp_path):
        p = tmp_path / "heart_rate.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "heart_rate": "72"}],
                   ["start_time", "heart_rate"])
        points = parse_heart_rate(str(p))
        assert len(points) == 1

    def test_skips_empty_bpm(self, tmp_path):
        p = tmp_path / "heart_rate.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "heart_rate": ""}],
                   ["start_time", "heart_rate"])
        points = parse_heart_rate(str(p))
        assert len(points) == 0

    def test_multiple_rows(self, tmp_path):
        rows = [{"start_time": f"2024-01-15 10:0{i}:00", "heart_rate": str(60 + i)} for i in range(5)]
        p = tmp_path / "heart_rate.csv"
        _write_csv(str(p), rows, ["start_time", "heart_rate"])
        points = parse_heart_rate(str(p))
        assert len(points) == 5


class TestParseSteps:
    def test_basic(self, tmp_path):
        p = tmp_path / "step_count.csv"
        _write_csv(str(p),
                   [{"start_time": "2024-01-15 10:00:00", "count": "500",
                     "calorie": "20.5", "distance": "400.0"}],
                   ["start_time", "count", "calorie", "distance"])
        points = parse_steps(str(p))
        assert len(points) == 1

    def test_no_optional_fields(self, tmp_path):
        p = tmp_path / "step_count.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "step_count": "100"}],
                   ["start_time", "step_count"])
        points = parse_steps(str(p))
        assert len(points) == 1


class TestParseCalories:
    def test_basic(self, tmp_path):
        p = tmp_path / "calories.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "calorie": "150.5"}],
                   ["start_time", "calorie"])
        points = parse_calories(str(p))
        assert len(points) == 1


class TestParseSleep:
    def test_with_duration_and_score(self, tmp_path):
        p = tmp_path / "sleep.csv"
        _write_csv(str(p),
                   [{"start_time": "2024-01-15 23:00:00", "duration": "27000000", "score": "82"}],
                   ["start_time", "duration", "score"])
        points = parse_sleep(str(p))
        assert len(points) == 1

    def test_duration_conversion_minutes(self, tmp_path):
        p = tmp_path / "sleep.csv"
        # 3600000 ms = 60 minutes
        _write_csv(str(p), [{"start_time": "2024-01-15 23:00:00", "duration": "3600000"}],
                   ["start_time", "duration"])
        points = parse_sleep(str(p))
        assert len(points) == 1


class TestParseSleepStage:
    def test_deep_stage(self, tmp_path):
        p = tmp_path / "sleep_stage.csv"
        _write_csv(str(p),
                   [{"start_time": "2024-01-15 01:00:00", "end_time": "2024-01-15 01:30:00",
                     "stage": "40003"}],
                   ["start_time", "end_time", "stage"])
        points = parse_sleep_stage(str(p))
        assert len(points) == 1

    def test_all_stages_mapped(self, tmp_path):
        rows = [
            {"start_time": "2024-01-15 00:00:00", "end_time": "2024-01-15 00:10:00", "stage": "40001"},
            {"start_time": "2024-01-15 00:10:00", "end_time": "2024-01-15 00:30:00", "stage": "40002"},
            {"start_time": "2024-01-15 00:30:00", "end_time": "2024-01-15 01:00:00", "stage": "40003"},
            {"start_time": "2024-01-15 01:00:00", "end_time": "2024-01-15 01:30:00", "stage": "40004"},
        ]
        p = tmp_path / "sleep_stage.csv"
        _write_csv(str(p), rows, ["start_time", "end_time", "stage"])
        points = parse_sleep_stage(str(p))
        assert len(points) == 4


class TestParseSpO2:
    def test_basic(self, tmp_path):
        p = tmp_path / "blood_oxygen.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "spo2": "98.5"}],
                   ["start_time", "spo2"])
        points = parse_spo2(str(p))
        assert len(points) == 1


class TestParseStress:
    def test_basic(self, tmp_path):
        p = tmp_path / "stress.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "stress_score": "35"}],
                   ["start_time", "stress_score"])
        points = parse_stress(str(p))
        assert len(points) == 1


class TestParseBodyComposition:
    def test_basic(self, tmp_path):
        p = tmp_path / "body.csv"
        _write_csv(str(p),
                   [{"start_time": "2024-01-15 08:00:00", "weight": "70.5",
                     "fat_percent": "18.2", "muscle_percent": "38.5", "bmi": "22.1"}],
                   ["start_time", "weight", "fat_percent", "muscle_percent", "bmi"])
        points = parse_body_composition(str(p))
        assert len(points) == 1


class TestDispatch:
    def test_heart_rate_file_dispatched(self, tmp_path):
        p = tmp_path / "com.samsung.health.heart_rate.20240115.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "heart_rate": "72"}],
                   ["start_time", "heart_rate"])
        points = dispatch(str(p))
        assert len(points) == 1

    def test_unknown_file_returns_empty(self, tmp_path):
        p = tmp_path / "unknown_file.csv"
        _write_csv(str(p), [{"col1": "val1"}], ["col1"])
        points = dispatch(str(p))
        assert points == []

    def test_step_count_file_dispatched(self, tmp_path):
        p = tmp_path / "com.samsung.health.step_count.20240115.csv"
        _write_csv(str(p), [{"start_time": "2024-01-15 10:00:00", "step_count": "500"}],
                   ["start_time", "step_count"])
        points = dispatch(str(p))
        assert len(points) == 1

    def test_sleep_stage_takes_priority_over_sleep(self, tmp_path):
        p = tmp_path / "com.samsung.health.sleep_stage.20240115.csv"
        _write_csv(str(p),
                   [{"start_time": "2024-01-15 01:00:00", "end_time": "2024-01-15 01:30:00",
                     "stage": "40003"}],
                   ["start_time", "end_time", "stage"])
        points = dispatch(str(p))
        assert len(points) == 1


# ---------------------------------------------------------------------------
# samsung_health_api tests
# ---------------------------------------------------------------------------

# Patch InfluxDB writes so tests don't need a running server
@pytest.fixture
def api_client():
    with patch("samsung_health_api.get_write_api") as mock_get_write_api:
        mock_write_api = MagicMock()
        mock_get_write_api.return_value = mock_write_api
        from samsung_health_api import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client, mock_write_api


class TestHealthEndpoint:
    def test_liveness(self, api_client):
        client, _ = api_client
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"


class TestHeartRateEndpoint:
    def test_valid(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/heart_rate",
                           json={"bpm": 72, "timestamp": "2024-01-15T10:30:00Z"})
        assert resp.status_code == 201
        mock_write.write.assert_called_once()

    def test_missing_bpm(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/heart_rate", json={"timestamp": "2024-01-15T10:30:00Z"})
        assert resp.status_code == 400

    def test_no_timestamp_uses_now(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/heart_rate", json={"bpm": 65})
        assert resp.status_code == 201


class TestStepsEndpoint:
    def test_valid_with_extras(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/steps",
                           json={"count": 500, "kcal": 20.5, "distance_m": 400.0,
                                 "timestamp": "2024-01-15T10:30:00Z"})
        assert resp.status_code == 201
        # steps + calories + distance = 3 writes
        assert mock_write.write.call_count == 3

    def test_missing_count(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/steps", json={"kcal": 5.0})
        assert resp.status_code == 400


class TestSpO2Endpoint:
    def test_valid(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/spo2",
                           json={"percent": 98.0, "timestamp": "2024-01-15T10:30:00Z"})
        assert resp.status_code == 201

    def test_missing_percent(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/spo2", json={})
        assert resp.status_code == 400


class TestStressEndpoint:
    def test_valid(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/stress",
                           json={"score": 35, "timestamp": "2024-01-15T10:30:00Z"})
        assert resp.status_code == 201

    def test_missing_score(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/stress", json={})
        assert resp.status_code == 400


class TestSleepEndpoint:
    def test_valid(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/sleep",
                           json={"duration_minutes": 450, "score": 82,
                                 "timestamp": "2024-01-15T07:00:00Z"})
        assert resp.status_code == 201


class TestSleepStageEndpoint:
    def test_valid_deep(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/sleep_stage",
                           json={"stage": "Deep", "minutes": 30.0,
                                 "timestamp": "2024-01-15T02:00:00Z"})
        assert resp.status_code == 201

    def test_invalid_stage(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/sleep_stage",
                           json={"stage": "Coma", "minutes": 10.0})
        assert resp.status_code == 400

    def test_missing_stage(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/sleep_stage", json={"minutes": 10.0})
        assert resp.status_code == 400


class TestBodyCompositionEndpoint:
    def test_valid(self, api_client):
        client, mock_write = api_client
        resp = client.post("/api/v1/body_composition",
                           json={"weight_kg": 70.5, "body_fat_percent": 18.2,
                                 "muscle_mass_percent": 38.5, "bmi": 22.1,
                                 "timestamp": "2024-01-15T08:00:00Z"})
        assert resp.status_code == 201


class TestBatchEndpoint:
    def test_mixed_batch(self, api_client):
        client, mock_write = api_client
        payload = [
            {"measurement": "heart_rate", "bpm": 72, "timestamp": "2024-01-15T10:00:00Z"},
            {"measurement": "spo2",       "percent": 98, "timestamp": "2024-01-15T10:00:00Z"},
            {"measurement": "unknown_metric", "value": 1},
        ]
        resp = client.post("/api/v1/batch", json=payload)
        assert resp.status_code == 207
        results = resp.get_json()["results"]
        assert results[0]["status"] == "ok"
        assert results[1]["status"] == "ok"
        assert results[2]["status"] == "skipped"

    def test_not_a_list(self, api_client):
        client, _ = api_client
        resp = client.post("/api/v1/batch", json={"measurement": "heart_rate", "bpm": 72})
        assert resp.status_code == 400
