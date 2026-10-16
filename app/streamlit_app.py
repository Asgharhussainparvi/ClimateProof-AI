
import httpx
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="ClimateProof AI",
    page_icon="🌍",
    layout="wide",
)

st.title("🌍 ClimateProof AI")
st.caption("Environmental Data Analysis & Integrity Verification")

with st.sidebar:
    st.header("Settings")
    api_url = st.text_input(
        "FastAPI Backend URL",
        value="http://127.0.0.1:8000",
    ).rstrip("/")

    st.divider()
    st.caption("ClimateProof AI MVP")

try:
    health = httpx.get(f"{api_url}/health", timeout=5)
    health.raise_for_status()
    st.success("FastAPI backend connected")
except httpx.HTTPError:
    st.error("Backend connect nahi ho raha. Pehle FastAPI server start karein.")
    st.stop()

uploaded_file = st.file_uploader(
    "Environmental CSV upload karein",
    type=["csv"],
    help="Required columns: timestamp, location, temperature_c, "
         "humidity_pct, pm25, source_id",
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name

    st.write(f"**File:** {filename} | **Size:** {len(file_bytes):,} bytes")

    if st.button("Analyze CSV", type="primary"):
        with st.spinner("Dataset analyze ho raha hai..."):
            try:
                files = {
                    "file": (filename, file_bytes, "text/csv")
                }

                analysis_response = httpx.post(
                    f"{api_url}/analyze-csv",
                    files=files,
                    timeout=60,
                )
                analysis_response.raise_for_status()
                analysis_data = analysis_response.json()

                st.write("DEBUG — API status:", analysis_response.status_code)
                st.write("DEBUG — API response type:", type(analysis_data).__name__)
                st.write("DEBUG — API response:", analysis_data)

                st.session_state["analysis"] = analysis_data
                st.session_state["analysis_filename"] = filename
                st.session_state["analysis_filename"] = filename

                report_response = httpx.post(
                    f"{api_url}/integrity-report",
                    files={
                        "file": (filename, file_bytes, "text/csv")
                    },
                    timeout=60,
                )
                report_response.raise_for_status()
                st.session_state["report"] = report_response.json()
                st.session_state["report_filename"] = filename

            except httpx.HTTPError as exc:
                st.error(f"API request fail hui: {exc}")
            except ValueError:
                st.error("API ne valid JSON response return nahi kiya.")

    analysis = st.session_state.get("analysis")
    if not isinstance(analysis, dict):
        analysis = None
    report = st.session_state.get("report")

    if (
        analysis
        and st.session_state.get("analysis_filename") == filename
    ):
        st.divider()
        st.header("📊 Analysis Results")

                
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Total Rows",
                analysis.get("row_count", 0),
            )

        with col2:
            st.metric(
                "Duplicate Rows",
                analysis.get("duplicate_rows", 0),
            )

        with col3:
            domain_violations = analysis.get("domain_violations", 0)

            if isinstance(domain_violations, dict):
                total_violations = sum(
                    value for value in domain_violations.values()
                    if isinstance(value, (int, float))
                )
            else:
                total_violations = (
                    domain_violations
                    if isinstance(domain_violations, (int, float))
                    else 0
                )

            st.metric("Domain Violations", total_violations)


        st.subheader("🔐 SHA-256 Fingerprint")
        sha256 = analysis.get("sha256", "")
        st.code(sha256 or "Fingerprint unavailable")
    if isinstance(analysis, dict):
        st.subheader("Data Quality")

        def count_values(value):
            """Dictionary ya number ko numeric count mein convert kare."""
            if isinstance(value, dict):
                return sum(
                    item for item in value.values()
                    if isinstance(item, (int, float)) and not isinstance(item, bool)
                )

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value

            return 0


        quality_cols = st.columns(3)

        metrics = [
            ("Missing Values", count_values(analysis.get("missing_values", 0))),
            ("Invalid Timestamps", count_values(analysis.get("invalid_timestamps", 0))),
            (
                "Invalid Numeric Values",
                count_values(analysis.get("invalid_numeric_values", 0)),
            ),
        ]

        for col, (label, value) in zip(quality_cols, metrics):
            col.metric(label, value)


        st.subheader("📈 Environmental Charts")

        try:
            df = pd.read_csv(
                __import__("io").BytesIO(file_bytes)
            )

            chart_columns = [
                "temperature_c",
                "humidity_pct",
                "pm25",
            ]

            available = [
                column for column in chart_columns
                if column in df.columns
            ]

            if available:
                for column in available:
                    st.markdown(f"**{column.replace('_', ' ').title()}**")
                    chart_df = pd.DataFrame({
                        column: pd.to_numeric(
                            df[column], errors="coerce"
                        )
                    }).dropna()

                    if not chart_df.empty:
                        st.line_chart(chart_df)
                    else:
                        st.info(f"{column} mein chart ke liye valid values nahi hain.")
            else:
                st.info("CSV mein chart banane ke liye environmental columns nahi mile.")

        except (ValueError, KeyError, pd.errors.ParserError) as exc:
            st.warning(f"CSV preview/chart nahi ban saka: {exc}")

        with st.expander("Numeric Summary"):
            st.json(analysis.get("numeric_summary", {}))

        with st.expander("Anomaly Counts"):
            st.json(analysis.get("anomaly_counts", {}))

        warnings = analysis.get("warnings", [])
        st.subheader("⚠️ Warnings")

        if warnings:
            for warning in warnings:
                st.warning(str(warning))
        else:
            st.success("API ne koi warning report nahi ki.")

        if analysis.get("note"):
            st.caption(str(analysis["note"]))

        st.divider()
        st.header("🔎 CSV Integrity Verification")

        st.write(
            "Agar aap ke paas trusted SHA-256 hash hai, "
            "to us se uploaded CSV verify karein."
        )

        with st.form("csv_verification_form"):
            expected_hash = st.text_input(
                "Expected SHA-256",
                placeholder="64 hexadecimal characters",
            )
            verify_clicked = st.form_submit_button("Verify CSV")

        if verify_clicked:
            if not expected_hash.strip():
                st.warning("Expected SHA-256 hash enter karein.")
            else:
                try:
                    verify_response = httpx.post(
                        f"{api_url}/verify-csv",
                        files={
                            "file": (filename, file_bytes, "text/csv")
                        },
                        data={"expected_sha256": expected_hash.strip()},
                        timeout=60,
                    )
                    verify_response.raise_for_status()
                    result = verify_response.json()

                    if result.get("verified") is True:
                        st.success("CSV fingerprint match ho gaya.")
                    else:
                        st.error("CSV fingerprint match nahi hua.")

                    st.json(result)

                except httpx.HTTPStatusError as exc:
                    st.error(
                        f"Verification reject hui: "
                        f"{exc.response.text}"
                    )
                except httpx.HTTPError as exc:
                    st.error(f"Verification request fail hui: {exc}")

        st.divider()
        st.header("📄 JSON Integrity Report")

        if (
            report
            and st.session_state.get("report_filename") == filename
        ):
            st.json(report)

            st.download_button(
                "Download JSON Integrity Report",
                data=__import__("json").dumps(
                    report, indent=2, ensure_ascii=False
                ),
                file_name="integrity_report.json",
                mime="application/json",
            )

        if st.button("Refresh JSON Report"):
            try:
                response = httpx.post(
                    f"{api_url}/integrity-report/download",
                    files={
                        "file": (filename, file_bytes, "text/csv")
                    },
                    timeout=60,
                )
                response.raise_for_status()

                st.download_button(
                    "Download Report from API",
                    data=response.content,
                    file_name="integrity_report.json",
                    mime="application/json",
                )
            except httpx.HTTPError as exc:
                st.error(f"Report download fail hui: {exc}")

else:
    st.info("Analysis shuru karne ke liye CSV file upload karein.")

    st.subheader("Dashboard Modules")
    col1, col2, col3 = st.columns(3)

    col1.markdown("### 📊 Data Analysis")
    col1.write("Environmental data aur quality checks.")

    col2.markdown("### 🔐 SHA-256 Integrity")
    col2.write("Dataset fingerprint aur CSV verification.")

    col3.markdown("### 📄 Integrity Report")
    col3.write("JSON report aur downloadable results.")
