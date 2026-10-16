"""FastAPI entry point for ClimateProof AI's first milestone."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(
    title="ClimateProof AI API",
    version="0.1.0",
    description="Environmental CSV validation and exploratory analysis.",
)

MAX_FILE_BYTES = 5 * 1024 * 1024
REQUIRED_COLUMNS = {
    "timestamp", "location", "temperature_c", "humidity_pct", "pm25", "source_id"
}
NUMERIC_COLUMNS = ("temperature_c", "humidity_pct", "pm25")


class AnalysisResponse(BaseModel):
    filename: str
    row_count: int
    columns: list[str]
    missing_values: dict[str, int]
    duplicate_rows: int
    invalid_timestamps: int
    invalid_numeric_values: dict[str, int]
    numeric_summary: dict[str, dict[str, float | None]]
    anomaly_counts: dict[str, int]
    warnings: list[str]
    note: str


def analyze_dataframe(df: pd.DataFrame, filename: str = "dataset.csv") -> dict[str, Any]:
    """Analyze a dataframe without mutating the caller's dataframe."""
    missing_columns = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    frame = df.copy()
    missing_values = {str(col): int(count) for col, count in frame.isna().sum().items()}
    duplicate_rows = int(frame.duplicated().sum())

    parsed_timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    invalid_timestamps = int(parsed_timestamps.isna().sum())

    invalid_numeric_values: dict[str, int] = {}
    numeric_summary: dict[str, dict[str, float | None]] = {}
    anomaly_counts: dict[str, int] = {}
    warnings: list[str] = []

    for column in NUMERIC_COLUMNS:
        raw = frame[column]
        converted = pd.to_numeric(raw, errors="coerce")
        invalid_mask = raw.notna() & converted.isna()
        invalid_numeric_values[column] = int(invalid_mask.sum())
        valid = converted.replace([np.inf, -np.inf], np.nan).dropna()

        if len(valid):
            numeric_summary[column] = {
                "count": int(valid.count()),
                "mean": round(float(valid.mean()), 4),
                "min": round(float(valid.min()), 4),
                "max": round(float(valid.max()), 4),
                "std": round(float(valid.std(ddof=1)), 4) if len(valid) > 1 else 0.0,
            }
            q1, q3 = valid.quantile([0.25, 0.75])
            iqr = q3 - q1
            # IQR flags are exploratory signals, not evidence of fraud or violations.
            if iqr == 0:
                outliers = valid != q1
            else:
                outliers = (valid < q1 - 1.5 * iqr) | (valid > q3 + 1.5 * iqr)
            anomaly_counts[column] = int(outliers.sum())
        else:
            numeric_summary[column] = {
                "count": 0, "mean": None, "min": None, "max": None, "std": None
            }
            anomaly_counts[column] = 0

        if invalid_numeric_values[column]:
            warnings.append(f"{column}: {invalid_numeric_values[column]} value(s) could not be parsed as numbers.")

    if invalid_timestamps:
        warnings.append(f"timestamp: {invalid_timestamps} value(s) could not be parsed as timestamps.")
    if duplicate_rows:
        warnings.append(f"Found {duplicate_rows} duplicate row(s).")
    if not warnings:
        warnings.append("No parsing or duplicate-row warnings detected by these checks.")

    return AnalysisResponse(
        filename=filename,
        row_count=int(len(frame)),
        columns=[str(c) for c in frame.columns],
        missing_values=missing_values,
        duplicate_rows=duplicate_rows,
        invalid_timestamps=invalid_timestamps,
        invalid_numeric_values=invalid_numeric_values,
        numeric_summary=numeric_summary,
        anomaly_counts=anomaly_counts,
        warnings=warnings,
        note="IQR flags indicate statistical outliers only; they do not establish fraud, causation, or a regulatory violation.",
    ).model_dump()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "climateproof-ai-api"}


@app.post("/analyze-csv", response_model=AnalysisResponse)
async def analyze_csv(file: UploadFile = File(...)) -> AnalysisResponse:
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only .csv files are supported.")

    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 5 MiB upload limit.")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty.")

    try:
        df = pd.read_csv(BytesIO(content))
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    try:
        result = analyze_dataframe(df, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AnalysisResponse(**result)
