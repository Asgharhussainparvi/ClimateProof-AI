
from fastapi.testclient import TestClient
import hashlib
from app.main import app

client = TestClient(app)

SAMPLE_CSV = b"""timestamp,location,temperature_c,humidity_pct,pm25,source_id
2026-10-01T10:00:00Z,Skardu,18.5,42,12.1,sensor-01
2026-10-01T11:00:00Z,Skardu,19.0,40,13.0,sensor-01
2026-10-01T12:00:00Z,Skardu,21.0,38,14.0,sensor-01
2026-10-01T13:00:00Z,Skardu,20.0,39,15.0,sensor-01
2026-10-01T14:00:00Z,Skardu,19.5,40,65.0,sensor-01
"""


def upload_csv(content: bytes, filename: str = "sample.csv"):
    return client.post(
        "/analyze-csv",
        files={"file": (filename, content, "text/csv")},
    )


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_valid_csv_returns_summary_and_flags_outlier():
    response = upload_csv(SAMPLE_CSV)

    assert response.status_code == 200
    body = response.json()

    assert body["row_count"] == 5
    assert body["missing_values"]["temperature_c"] == 0
    assert body["invalid_timestamps"] == 0
    assert body["numeric_summary"]["temperature_c"]["mean"] == 19.6
    assert body["anomaly_counts"]["pm25"] == 1
    assert body["domain_violations"]["humidity_pct"] == 0
    assert body["domain_violations"]["pm25"] == 0
    assert "establishes fraud" in body["note"]


def test_rejects_non_csv_file():
    response = upload_csv(b"hello", "sample.txt")

    assert response.status_code == 415


def test_missing_required_column_returns_422():
    csv = (
        b"timestamp,location,temperature_c\n"
        b"2026-10-01T10:00:00Z,Skardu,18.5\n"
    )

    response = upload_csv(csv, "incomplete.csv")

    assert response.status_code == 422
    assert "humidity_pct" in response.json()["detail"]


def test_flags_humidity_outside_domain():
    csv = (
        b"timestamp,location,temperature_c,humidity_pct,pm25,source_id\n"
        b"2026-10-01T10:00:00Z,Skardu,18.5,150,12,sensor-01\n"
        b"2026-10-01T11:00:00Z,Skardu,19.0,-5,13,sensor-01\n"
    )

    response = upload_csv(csv)

    assert response.status_code == 200
    body = response.json()
    assert body["domain_violations"]["humidity_pct"] == 2


def test_flags_negative_pm25():
    csv = (
        b"timestamp,location,temperature_c,humidity_pct,pm25,source_id\n"
        b"2026-10-01T10:00:00Z,Skardu,18.5,42,-1,sensor-01\n"
    )

    response = upload_csv(csv)

    assert response.status_code == 200
    assert response.json()["domain_violations"]["pm25"] == 1


def test_counts_unparseable_numeric_values():
    csv = (
        b"timestamp,location,temperature_c,humidity_pct,pm25,source_id\n"
        b"2026-10-01T10:00:00Z,Skardu,unknown,42,12,sensor-01\n"
    )

    response = upload_csv(csv)

    assert response.status_code == 200
    body = response.json()
    assert body["invalid_numeric_values"]["temperature_c"] == 1
    assert body["numeric_summary"]["temperature_c"]["count"] == 0


def test_flags_invalid_timestamp():
    csv = (
        b"timestamp,location,temperature_c,humidity_pct,pm25,source_id\n"
        b"not-a-date,Skardu,18.5,42,12,sensor-01\n"
    )

    response = upload_csv(csv)

    assert response.status_code == 200
    assert response.json()["invalid_timestamps"] == 1


def test_rejects_empty_csv():
    response = upload_csv(b"")

    assert response.status_code == 400


def test_sha256_matches_uploaded_csv_bytes():
    response = upload_csv(SAMPLE_CSV)

    assert response.status_code == 200
    expected_hash = hashlib.sha256(SAMPLE_CSV).hexdigest()

    assert response.json()["sha256"] == expected_hash


def test_sha256_changes_when_uploaded_bytes_change():
    original = SAMPLE_CSV
    modified = SAMPLE_CSV + b"\n"

    original_response = upload_csv(original)
    modified_response = upload_csv(modified)

    assert original_response.status_code == 200
    assert modified_response.status_code == 200

    assert original_response.json()["sha256"] != (
        modified_response.json()["sha256"]
    )



def test_verify_csv_matching_hash():
    expected_hash = hashlib.sha256(SAMPLE_CSV).hexdigest()

    response = client.post(
        "/verify-csv",
        files={"file": ("sample.csv", SAMPLE_CSV, "text/csv")},
        data={"expected_sha256": expected_hash},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["actual_sha256"] == expected_hash


def test_verify_csv_mismatching_hash():
    expected_hash = hashlib.sha256(b"different file").hexdigest()

    response = client.post(
        "/verify-csv",
        files={"file": ("sample.csv", SAMPLE_CSV, "text/csv")},
        data={"expected_sha256": expected_hash},
    )

    assert response.status_code == 200
    assert response.json()["verified"] is False


def test_verify_csv_rejects_invalid_hash():
    response = client.post(
        "/verify-csv",
        files={"file": ("sample.csv", SAMPLE_CSV, "text/csv")},
        data={"expected_sha256": "not-a-valid-hash"},
    )

    assert response.status_code == 422


def test_integrity_report_returns_fingerprint_and_quality():
    response = client.post(
        "/integrity-report",
        files={"file": ("sample.csv", SAMPLE_CSV, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["report_version"] == "1.0"
    assert body["dataset"]["row_count"] == 5
    assert body["dataset"]["sha256"] == hashlib.sha256(
        SAMPLE_CSV
    ).hexdigest()
    assert body["integrity"]["verification_status"] == "not_verified"
    assert body["quality"]["invalid_timestamps"] == 0
    assert "limitations" in body


def test_integrity_report_rejects_non_csv():
    response = client.post(
        "/integrity-report",
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415


def test_integrity_report_rejects_missing_required_columns():
    csv = (
        b"timestamp,location,temperature_c\n"
        b"2026-10-01T10:00:00Z,Skardu,18.5\n"
    )

    response = client.post(
        "/integrity-report",
        files={"file": ("incomplete.csv", csv, "text/csv")},
    )

    assert response.status_code == 422


def test_integrity_report_download_returns_json_attachment():
    response = client.post(
        "/integrity-report/download",
        files={"file": ("sample.csv", SAMPLE_CSV, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/json"
    )
    assert response.headers["content-disposition"] == (
        'attachment; filename="integrity_report.json"'
    )

    body = response.json()

    assert body["report_version"] == "1.0"
    assert body["dataset"]["sha256"] == hashlib.sha256(
        SAMPLE_CSV
    ).hexdigest()
    assert body["integrity"]["verification_status"] == "not_verified"
    assert "quality" in body
    assert "limitations" in body


def test_integrity_report_download_rejects_non_csv():
    response = client.post(
        "/integrity-report/download",
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415


def test_integrity_report_download_rejects_oversized_file():
    oversized_csv = b"x" * (5 * 1024 * 1024 + 1)

    response = client.post(
        "/integrity-report/download",
        files={
            "file": (
                "large.csv",
                oversized_csv,
                "text/csv",
            )
        },
    )

    assert response.status_code == 413


def test_analyze_csv_rejects_oversized_file():
    oversized_csv = b"x" * (5 * 1024 * 1024 + 1)

    response = client.post(
        "/analyze-csv",
        files={"file": ("large.csv", oversized_csv, "text/csv")},
    )

    assert response.status_code == 413


def test_verify_csv_rejects_oversized_file():
    oversized_csv = b"x" * (5 * 1024 * 1024 + 1)
    expected_hash = hashlib.sha256(oversized_csv).hexdigest()

    response = client.post(
        "/verify-csv",
        files={"file": ("large.csv", oversized_csv, "text/csv")},
        data={"expected_sha256": expected_hash},
    )

    assert response.status_code == 413


def test_integrity_report_rejects_oversized_file():
    oversized_csv = b"x" * (5 * 1024 * 1024 + 1)

    response = client.post(
        "/integrity-report",
        files={"file": ("large.csv", oversized_csv, "text/csv")},
    )

    assert response.status_code == 413
def test_rejects_csv_with_invalid_encoding():
    invalid_csv = b"\xff\xfe\xfa\xfb"

    response = upload_csv(invalid_csv)

    assert response.status_code == 400


def test_invalid_encoding_returns_generic_error():
    invalid_csv = b"\xff\xfe\xfa\xfb"

    response = upload_csv(invalid_csv)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Could not parse CSV. Check the file format and encoding."
    )
    assert "UnicodeDecodeError" not in response.text


def test_integrity_report_returns_generic_error_for_invalid_encoding():
    invalid_csv = b"\xff\xfe\xfa\xfb"

    response = client.post(
        "/integrity-report",
        files={"file": ("invalid.csv", invalid_csv, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Could not parse CSV. Check the file format and encoding."
    )
    assert "UnicodeDecodeError" not in response.text
