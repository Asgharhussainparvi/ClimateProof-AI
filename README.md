# ClimateProof AI

ClimateProof AI is an environmental dataset analysis and data-integrity verification MVP developed for the IEEE Global ClimateChain Hackathon 2026.

**Primary track:** Climate Data & Environmental Monitoring

The project provides a FastAPI backend and a Streamlit dashboard for uploading environmental CSV datasets, analyzing data quality, verifying file integrity, and downloading integrity reports.

## Current Features

- CSV upload and schema validation.
- Missing-value detection, including whitespace-only `location` and `source_id` values.
- Duplicate-row detection.
- Invalid timestamp and numeric-value detection.
- Environmental data checks for humidity and PM2.5.
- Descriptive statistics and exploratory IQR-based outlier counts.
- CSV file-integrity verification.
- Integrity report generation and download.
- Streamlit dashboard connected to the FastAPI backend.
- API documentation through Swagger UI.

Statistical outliers are exploratory signals; they do not independently establish fraud, data manipulation, or regulatory violations.

## Required CSV Schema

CSV files must contain these columns:

`timestamp`, `location`, `temperature_c`, `humidity_pct`, `pm25`, `source_id`

Example:

```csv
timestamp,location,temperature_c,humidity_pct,pm25,source_id
2026-10-01T10:00:00Z,Skardu,18.5,42,12,station-01
2026-10-01T11:00:00Z,Skardu,19.1,40,14,station-01
```

The included sample dataset is synthetic and is not real-world environmental measurement data.

## Requirements

- Python 3.11 or newer recommended.
- Windows, macOS, or Linux.
- Dependencies listed in `requirements.txt`.

## Installation

Clone the repository and open its directory:

```bash
git clone https://github.com/Asgharhussainparvi/ClimateProof-AI.git
cd ClimateProof-AI
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run the Application

The API and Streamlit dashboard run in separate terminals.

### 1. Start the FastAPI backend

```bash
uvicorn app.main:app --reload
```

API base URL:

`http://127.0.0.1:8000`

Interactive API documentation:

`http://127.0.0.1:8000/docs`

Health endpoint:

`GET /health`

### 2. Start the Streamlit dashboard

Activate the same virtual environment in a second terminal, then run:

```bash
streamlit run app/streamlit_app.py
```

Open the local URL displayed in the terminal, usually:

`http://localhost:8501`

Ensure the FastAPI backend is running before using dashboard features. The dashboard's API URL defaults to `http://127.0.0.1:8000`.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check API health |
| POST | `/analyze-csv` | Analyze an uploaded CSV |
| POST | `/verify-csv` | Verify uploaded CSV integrity |
| POST | `/integrity-report` | Generate an integrity report |
| POST | `/integrity-report/download` | Download an integrity report |

Refer to `/docs` for the actual request parameters, response schemas, and supported options.

## Run Tests

```bash
python -m pytest -q
```

## Current Limitations

- The CSV schema is fixed to the six required columns.
- The upload size limit is 5 MiB.
- IQR-based outlier detection is exploratory and may not suit every environmental variable or distribution.
- The sample dataset is synthetic.
- The current MVP does not include a database, LLM-based analysis, a fingerprint registry, or blockchain integration.
- File-integrity verification can help detect changes relative to a trusted reference, but does not independently prove that the original measurements are authentic.
- The application is configured for local development; production deployment requires additional security and operational configuration.

## Project Structure

```text
ClimateProof-AI/
├── app/
│   ├── main.py
│   └── streamlit_app.py
├── sample_data/
├── tests/
│   └── test_api.py
├── requirements.txt
└── README.md
```

## Development Status

The MVP currently includes a CSV analysis API, an interactive Streamlit dashboard, file-integrity verification, and integrity-report functionality.

Future work may include persistent storage, trusted fingerprint registries, stronger provenance tracking, and blockchain integration.

