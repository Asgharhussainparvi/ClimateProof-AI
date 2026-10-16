
"""FastAPI entry point for ClimateProof AI."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile , Form
from pydantic import BaseModel
import hashlib
import hmac
app = FastAPI(
    title="ClimateProof AI API",
    version="0.2.0",
    description="Environmental CSV validation and exploratory analysis.",
)

MAX_FILE_BYTES = 5 * 1024 * 1024

REQUIRED_COLUMNS = {
    "timestamp",
    "location",
    "temperature_c",
    "humidity_pct",
    "pm25",
    "source_id",
}

NUMERIC_COLUMNS = ("temperature_c", "humidity_pct", "pm25")

# Only enforce domain constraints that are broadly applicable.
DOMAIN_RANGES = {
    "humidity_pct": (0.0, 100.0),
    "pm25": (0.0, None),
}


class AnalysisResponse(BaseModel):
    filename: str
    row_count: int
    columns: list[str]
    missing_values: dict[str, int]
    duplicate_rows: int
    invalid_timestamps: int
    invalid_numeric_values: dict[str, int]
    domain_violations: dict[str, int]
    numeric_summary: dict[str, dict[str, float | int | None]]
    anomaly_counts: dict[str, int]
    warnings: list[str]
    note: str
    sha256: str = ""


class VerificationResponse(BaseModel):
    filename: str
    expected_sha256: str
    actual_sha256: str
    verified: bool
    note: str


class IntegrityReport(BaseModel):
    report_version: str
    filename: str
    dataset: dict[str, Any]
    integrity: dict[str, Any]
    quality: dict[str, Any]
    warnings: list[str]
    limitations: list[str]


def analyze_dataframe(
    df: pd.DataFrame,
    filename: str = "dataset.csv",
) -> dict[str, Any]:
    """Validate and analyze an environmental dataframe."""
    missing_columns = sorted(REQUIRED_COLUMNS - set(df.columns))

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_columns)}"
        )

    frame = df.copy()

    missing_values = {
        str(column): int(count)
        for column, count in frame.isna().sum().items()
    }
    duplicate_rows = int(frame.duplicated().sum())

    timestamps = pd.to_datetime(
        frame["timestamp"], errors="coerce", utc=True
    )
    invalid_timestamps = int(timestamps.isna().sum())

    invalid_numeric_values: dict[str, int] = {}
    domain_violations: dict[str, int] = {}
    numeric_summary: dict[str, dict[str, float | int | None]] = {}
    anomaly_counts: dict[str, int] = {}
    warnings: list[str] = []

    for column in NUMERIC_COLUMNS:
        raw = frame[column]
        converted = pd.to_numeric(raw, errors="coerce")

        # Non-empty values that cannot be parsed or are non-finite
        # are invalid numeric values.
        finite_mask = pd.Series(
            np.isfinite(converted.to_numpy(dtype=float, na_value=np.nan)),
            index=converted.index,
        )
        invalid_mask = raw.notna() & (
            converted.isna() | ~finite_mask
        )
        invalid_numeric_values[column] = int(invalid_mask.sum())

        valid = converted.where(finite_mask).dropna()

        # Domain checks are separate from statistical anomaly checks.
        violation_count = 0
        if column in DOMAIN_RANGES:
            lower, upper = DOMAIN_RANGES[column]
            violations = pd.Series(False, index=valid.index)

            if lower is not None:
                violations |= valid < lower
            if upper is not None:
                violations |= valid > upper

            violation_count = int(violations.sum())

        domain_violations[column] = violation_count

        if len(valid):
            numeric_summary[column] = {
                "count": int(valid.count()),
                "mean": round(float(valid.mean()), 4),
                "min": round(float(valid.min()), 4),
                "max": round(float(valid.max()), 4),
                "std": (
                    round(float(valid.std(ddof=1)), 4)
                    if len(valid) > 1
                    else 0.0
                ),
            }

            q1, q3 = valid.quantile([0.25, 0.75])
            iqr = q3 - q1

            if iqr == 0:
                outliers = valid != q1
            else:
                outliers = (
                    (valid < q1 - 1.5 * iqr)
                    | (valid > q3 + 1.5 * iqr)
                )

            anomaly_counts[column] = int(outliers.sum())
        else:
            numeric_summary[column] = {
                "count": 0,
                "mean": None,
                "min": None,
                "max": None,
                "std": None,
            }
            anomaly_counts[column] = 0

        if invalid_numeric_values[column]:
            warnings.append(
                f"{column}: {invalid_numeric_values[column]} "
                "value(s) are invalid, unparseable, or non-finite."
            )

        if violation_count:
            warnings.append(
                f"{column}: {violation_count} value(s) violate "
                "the configured domain constraints."
            )

    if invalid_timestamps:
        warnings.append(
            f"timestamp: {invalid_timestamps} value(s) could not "
            "be parsed as timestamps."
        )

    if duplicate_rows:
        warnings.append(f"Found {duplicate_rows} duplicate row(s).")

    if not warnings:
        warnings.append(
            "No parsing, domain, or duplicate-row warnings "
            "detected by these checks."
        )

    return AnalysisResponse(
        filename=filename,
        row_count=int(len(frame)),
        columns=[str(column) for column in frame.columns],
        missing_values=missing_values,
        duplicate_rows=duplicate_rows,
        invalid_timestamps=invalid_timestamps,
        invalid_numeric_values=invalid_numeric_values,
        domain_violations=domain_violations,
        numeric_summary=numeric_summary,
        anomaly_counts=anomaly_counts,
        warnings=warnings,
        note=(
            "Domain violations indicate configured constraint failures. "
            "IQR flags indicate statistical outliers only; neither "
            "establishes fraud, causation, or a regulatory violation."
        ),
    ).model_dump()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "climateproof-ai-api"}


@app.post("/analyze-csv", response_model=AnalysisResponse)
async def analyze_csv(file: UploadFile = File(...)) -> AnalysisResponse:
    filename = file.filename or "upload.csv"

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail="Only .csv files are supported.",
        )

    content = await file.read(MAX_FILE_BYTES + 1)
    sha256 = hashlib.sha256(content).hexdigest()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 5 MiB upload limit.",
        )

    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Uploaded CSV is empty.",
        )

    try:
        df = pd.read_csv(BytesIO(content))
    except pd.errors.EmptyDataError as exc:
        raise HTTPException(
            status_code=400,
            detail="CSV contains no readable columns.",
        ) from exc
    except (
        pd.errors.ParserError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse CSV: {exc}",
        ) from exc
    
    try:
        result = analyze_dataframe(df, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result["sha256"] = sha256

    return AnalysisResponse(**result)


@app.post("/verify-csv", response_model=VerificationResponse)
async def verify_csv(
    file: UploadFile = File(...),
    expected_sha256: str = Form(...),
) -> VerificationResponse:
    filename = file.filename or "upload.csv"

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail="Only .csv files are supported.",
        )

    expected_hash = expected_sha256.strip().lower()

    if (
        len(expected_hash) != 64
        or any(c not in "0123456789abcdef" for c in expected_hash)
    ):
        raise HTTPException(
            status_code=422,
            detail="Expected SHA-256 must contain exactly 64 hexadecimal characters.",
        )

    content = await file.read(MAX_FILE_BYTES + 1)

    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 5 MiB upload limit.",
        )

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded CSV is empty.",
        )

    actual_hash = hashlib.sha256(content).hexdigest()
    verified = hmac.compare_digest(actual_hash, expected_hash)

    return VerificationResponse(
        filename=filename,
        expected_sha256=expected_hash,
        actual_sha256=actual_hash,
        verified=verified,
        note=(
            "The uploaded file bytes match the expected hash."
            if verified
            else "The uploaded file bytes do not match the expected hash."
        ),
    )


@app.post("/integrity-report", response_model=IntegrityReport)
async def integrity_report(
    file: UploadFile = File(...),
) -> IntegrityReport:
    filename = file.filename or "upload.csv"

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail="Only .csv files are supported.",
        )

    content = await file.read(MAX_FILE_BYTES + 1)

    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 5 MiB upload limit.",
        )

    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Uploaded CSV is empty.",
        )

    sha256 = hashlib.sha256(content).hexdigest()

    try:
        df = pd.read_csv(BytesIO(content))
    except pd.errors.EmptyDataError as exc:
        raise HTTPException(
            status_code=400,
            detail="CSV contains no readable columns.",
        ) from exc
    except (
        pd.errors.ParserError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse CSV: {exc}",
        ) from exc

    try:
        analysis = analyze_dataframe(df, filename=filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return IntegrityReport(
        report_version="1.0",
        filename=filename,
        dataset={
            "sha256": sha256,
            "row_count": analysis["row_count"],
            "columns": analysis["columns"],
        },
        integrity={
            "fingerprint_algorithm": "SHA-256",
            "fingerprint_available": True,
            "verification_status": "not_verified",
            "verification_note": (
                "No trusted expected hash was provided. "
                "The fingerprint identifies these uploaded bytes "
                "but does not prove their origin or authenticity."
            ),
        },
        quality={
            "missing_values": analysis["missing_values"],
            "duplicate_rows": analysis["duplicate_rows"],
            "invalid_timestamps": analysis["invalid_timestamps"],
            "invalid_numeric_values": (
                analysis["invalid_numeric_values"]
            ),
            "domain_violations": analysis["domain_violations"],
            "numeric_summary": analysis["numeric_summary"],
            "anomaly_counts": analysis["anomaly_counts"],
        },
        warnings=analysis["warnings"],
        limitations=[
            "Statistical outliers are not proof of fraud.",
            "Domain violations depend on configured constraints.",
            "SHA-256 alone does not prove source authenticity.",
        ],
    )
