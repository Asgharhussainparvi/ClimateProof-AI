from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SAMPLE_CSV = b"""timestamp,location,temperature_c,humidity_pct,pm25,source_id
2026-10-01T10:00:00Z,Skardu,18.5,42,12.1,sensor-01
2026-10-01T11:00:00Z,Skardu,19.0,40,13.0,sensor-01
2026-10-01T12:00:00Z,Skardu,21.0,38,14.0,sensor-01
2026-10-01T13:00:00Z,Skardu,20.0,39,15.0,sensor-01
2026-10-01T14:00:00Z,Skardu,19.5,40,65.0,sensor-01
"""


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analyze_valid_csv_returns_summary_and_flags_outlier():
    response = client.post(
        "/analyze-csv", files={"file": ("sample.csv", SAMPLE_CSV, "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 5
    assert body["missing_values"]["temperature_c"] == 0
    assert body["invalid_timestamps"] == 0
    assert body["numeric_summary"]["temperature_c"]["mean"] == 19.6
    assert body["anomaly_counts"]["pm25"] == 1
    assert "do not establish fraud" in body["note"]


def test_rejects_non_csv_file():
    response = client.post(
        "/analyze-csv", files={"file": ("sample.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 415


def test_missing_required_column_returns_422():
    csv = b"timestamp,location,temperature_c\n2026-10-01T10:00:00Z,Skardu,18.5\n"
    response = client.post(
        "/analyze-csv", files={"file": ("incomplete.csv", csv, "text/csv")}
    )
    assert response.status_code == 422
    assert "humidity_pct" in response.json()["detail"]
