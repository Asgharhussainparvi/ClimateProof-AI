# ClimateProof AI

ClimateProof AI is an environmental dataset analysis and integrity-verification project for the IEEE Global ClimateChain Hackathon 2026. Primary track: Climate Data & Environmental Monitoring.

## Milestone 1: CSV analysis API

The API validates a documented CSV schema and returns missing-value counts, duplicate-row count, timestamp/numeric parsing issues, descriptive statistics, and exploratory IQR outlier counts. Statistical outliers are not evidence of fraud or regulatory violations. The included sample is synthetic and is not real-world environmental measurement data.

### Required CSV columns

`timestamp`, `location`, `temperature_c`, `humidity_pct`, `pm25`, `source_id`

### Setup

Python 3.11+ is recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Run API

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API docs. Health check: `GET /health`. Upload a CSV using `POST /analyze-csv`.

Example with curl:

```bash
curl -X POST "http://127.0.0.1:8000/analyze-csv" -F "file=@sample_data/environmental_sample.csv"
```

### Tests

```bash
pytest -q
```

### Current limitations

- Local API only; no Streamlit dashboard, database, LLM, fingerprint registry, or blockchain integration yet.
- IQR outlier checks are basic exploratory signals and may not suit every environmental variable or distribution.
- Schema is currently fixed to the six required columns.
- Upload limit is 5 MiB.
