import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import gdown
from io import BytesIO

# CONFIG
st.set_page_config(page_title="APP Dashboard", layout="wide")

# AUTH
def login():
    st.title("Login")
    st.markdown("Enter credentials to access the dashboard.")
    username = st.text_input("Username", key="username")
    password = st.text_input("Password", type="password", key="password")
    if st.button("Login"):
        if username == "streamdash" and password == "Billing@2025":
            st.session_state["authenticated"] = True
            st.experimental_rerun()
        else:
            st.error("Invalid credentials. Access denied.")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login()
    st.stop()

# DATA LOADER
file_id = "1PlTbACUnIAOkTzM-m06j_lQvX62kiFKB"
download_url = f"https://drive.google.com/uc?id={file_id}&export=download"

@st.cache_data
def load_excel_from_drive(url):
    try:
        output = BytesIO()
        gdown.download(url, output, quiet=True)
        output.seek(0)
        xls = pd.ExcelFile(output, engine="openpyxl")
        # Primary sheet -> first sheet
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])

        # Optional CPT reference sheet handling
        cpt_ref = pd.DataFrame()
        if "Sheet1" in xls.sheet_names:
            cpt_ref = pd.read_excel(xls, sheet_name="Sheet1")
            if "CPT Code" in cpt_ref.columns:
                cpt_ref["CPT Code"] = cpt_ref["CPT Code"].astype(str).str.strip()
            # sanitize numeric currency columns if present
            for col in ["Charge/Unit", "Expected"]:
                if col in cpt_ref.columns:
                    # use raw string to avoid invalid escape sequence warnings
                    cpt_ref[col] = pd.to_numeric(
                        cpt_ref[col].replace(r"[\$,]", "", regex=True),
                        errors="coerce",
                    )

        # Standardize and coerce date columns
        if "Visit Date" in df.columns:
            df["Visit Date"] = pd.to_datetime(df["Visit Date"], errors="coerce")
        if "Transaction Date" in df.columns:
            df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")

        # Derived fields
        if "Visit Date" in df.columns:
            df["Week"] = df["Visit Date"].dt.to_period("W").astype(str)
            df["Month"] = df["Visit Date"].dt.to_period("M").astype(str)
        else:
            df["Week"] = pd.NA
            df["Month"] = pd.NA

        if "Transaction Date" in df.columns and "Visit Date" in df.columns:
            df["Encounter Lag"] = (df["Transaction Date"] - df["Visit Date"]).dt.days
        else:
            df["Encounter Lag"] = pd.NA

        if "CPT Code" in df.columns:
            df["CPT Code"] = df["CPT Code"].astype(str).str.strip()
            em_initial_set = {"99304", "99305", "99306"}
            em_followup_set = {"99307", "99308", "99309", "99310"}
            def cpt_category(code):
                if code in em_initial_set:
                    return "Initial"
                if code in em_followup_set:
                    return "Follow-up"
                return "Other"
            df["CPT Category"] = df["CPT Code"].map(cpt_category)
        else:
            df["CPT Code"] = pd.NA
            df["CPT Category"] = pd.NA

        # Merge CPT reference if available and has matching key
        if (not cpt_ref.empty) and ("CPT Code" in cpt_ref.columns) and ("CPT Code" in df.columns):
            df = df.merge(cpt_ref, on="CPT Code", how="left")

        # Ensure Visit ID exists for counts; create if missing
        if "Visit ID" not in df.columns:
            df.insert(0, "Visit ID", range(1, len(df) + 1))

        return df

    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None

df = load_excel_from_drive(download_url)

if df is None:
    st.warning("Unable to load data from Google Drive Excel file.")
    st.stop()

# FILTERS
st.sidebar.header("Filters")
today = datetime.today()

dos_filter = st.sidebar.selectbox(
    "Date of Service (Visit Date)",
    [
        "Last 30 Days",
        "Current Week",
        "Last 14 Days",
        "Current Month",
        "Current Quarter",
        "Current Year",
        "Custom Range",
    ],
)

if dos_filter == "Last 30 Days":
    start_date, end_date = today - timedelta(days=30), today
elif dos_filter == "Current Week":
    start_date, end_date = today - timedelta(days=today.weekday()), today
elif dos_filter == "Last 14 Days":
    start_date, end_date = today - timedelta(days=14), today
elif dos_filter == "Current Month":
    start_date, end_date = today.replace(day=1), today
elif dos_filter == "Current Quarter":
    q = (today.month - 1) // 3 + 1
    start_date, end_date = datetime(today.year, 3 * (q - 1) + 1, 1), today
elif dos_filter == "Current Year":
    start_date, end_date = datetime(today.year, 1, 1), today
else:
    start_date = pd.to_datetime(st.sidebar.date_input("Start Date", today - timedelta(days=30)))
    end_date = pd.to_datetime(st.sidebar.date_input("End Date", today))

# apply date filter only if Visit Date exists
if "Visit Date" in df.columns:
    df = df[(df["Visit Date"] >= pd.to_datetime(start_date)) & (df["Visit Date"] <= pd.to_datetime(end_date))]

# other sidebar filters
providers = st.sidebar.multiselect("Provider", sorted(df["Provider Name"].dropna().unique()) if "Provider Name" in df.columns else [])
facilities = st.sidebar.multiselect("Facility", sorted(df["Facility Name"].dropna().unique()) if "Facility Name" in df.columns else [])
states = st.sidebar.multiselect("State/Region", sorted(df["State"].dropna().unique()) if "State" in df.columns else [])
payer_class = st.sidebar.multiselect("Payer Class", sorted(df["Payer Class"].dropna().unique()) if "Payer Class" in df.columns else [])
encounter_type = st.sidebar.multiselect("Encounter Type", sorted(df["Encounter Type"].dropna().unique()) if "Encounter Type" in df.columns else [])

if providers:
    df = df[df["Provider Name"].isin(providers)]
if facilities:
    df = df[df["Facility Name"].isin(facilities)]
if states:
    df = df[df["State"].isin(states)]
if payer_class:
    df = df[df["Payer Class"].isin(payer_class)]
if encounter_type:
    df = df[df["Encounter Type"].isin(encounter_type)]

# TABS
tab1, tab2, tab3, tab4 = st.tabs(["Executive", "Operations", "Growth", "Quality"])

with tab1:
    st.header("Provider Weekly Visit Count")
    if "Provider Name" in df.columns and "Week" in df.columns:
        weekly = df.groupby(["Provider Name", "Week"])["Visit ID"].count().reset_index(name="Visit Count")
        if not weekly.empty:
            fig = px.bar(weekly, x="Week", y="Visit Count", color="Provider Name", barmode="group")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No weekly visit data available for selected filters.")
    else:
        st.info("Provider or Week field missing in dataset.")

    st.header("% to Target (Provider)")
    if "Visit Count" in locals():
        weekly["% to Target"] = (weekly["Visit Count"] / 120) * 100
        fig2 = px.bar(weekly, x="Week", y="% to Target", color="Provider Name", barmode="group")
        fig2.update_yaxes(range=[0, 150])
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Insufficient data to calculate % to target for providers.")

with tab2:
    st.header("Visit Count by Facility (Monthly)")
    if "Facility Name" in df.columns and "Month" in df.columns:
        monthly_facility = df.groupby(["Facility Name", "Month"])["Visit ID"].count().reset_index(name="Visit Count")
        if not monthly_facility.empty:
            fig3 = px.bar(monthly_facility, x="Month", y="Visit Count", color="Facility Name", barmode="stack")
            st.plotly_chart(fig3, use_container_width=True)
            monthly_facility["% to Target"] = (monthly_facility["Visit Count"] / 120) * 100
            fig4 = px.line(monthly_facility, x="Month", y="% to Target", color="Facility Name", markers=True)
            fig4.update_yaxes(range=[0, 150])
            st.plotly_chart(fig4, use_container_width=True)
            st.header("New Facility Ramp Tracker")
            ramp = df.groupby(["Facility Name", "Week"])["Visit ID"].count().reset_index(name="Visit Count")
            ramp["% Ramp"] = (ramp["Visit Count"] / 120) * 100
            st.plotly_chart(px.area(ramp, x="Week", y="% Ramp", color="Facility Name"), use_container_width=True)
        else:
            st.info("No monthly facility data available for selected filters.")
    else:
        st.info("Facility or Month field missing in dataset.")

    st.header("Working Days by Provider")
    if "Provider Name" in df.columns and "Month" in df.columns and "Visit Date" in df.columns:
        working_days = df.groupby(["Provider Name", "Month"])["Visit Date"].nunique().reset_index(name="Working Days")
        st.plotly_chart(px.bar(working_days, x="Month", y="Working Days", color="Provider Name", barmode="group"), use_container_width=True)
    else:
        st.info("Insufficient data to compute working days.")

with tab3:
    st.header("CCM Start Delay by Facility")
    em_codes = {"99304", "99305", "99306", "99307", "99308", "99309", "99310"}
    if {"CPT Code", "Patient ID", "Visit Date"}.issubset(df.columns):
        df_em = df[df["CPT Code"].isin(em_codes)]
        df_99487 = df[df["CPT Code"] == "99487"]
        if not df_em.empty and not df_99487.empty:
            # align by Patient ID and find earliest EM and earliest 99487 per patient
            em_first = df_em.sort_values("Visit Date").groupby("Patient ID").first().reset_index()
            ccm_first = df_99487.sort_values("Visit Date").groupby("Patient ID").first().reset_index()
            delay_df = pd.merge(em_first, ccm_first, on="Patient ID", suffixes=("_EM", "_99487"))
            delay_df["CCM Delay"] = (delay_df["Visit Date_99487"] - delay_df["Visit Date_EM"]).dt.days
            # group by facility where CCM occurred, fallback to EM facility if 99487 facility is missing
            facility_col = "Facility Name_99487" if "Facility Name_99487" in delay_df.columns else "Facility Name_EM"
            delay_summary = delay_df.groupby(facility_col)["CCM Delay"].mean().reset_index()
            delay_summary = delay_summary.rename(columns={facility_col: "Facility Name", "CCM Delay": "Average CCM Delay (days)"})
            st.dataframe(delay_summary.style.background_gradient())
        else:
            st.info("No CCM delay data found for selected filters.")
    else:
        st.info("Required fields for CCM delay analysis are missing (CPT Code, Patient ID, Visit Date).")

with tab4:
    st.header("Provider Encounter Lag")
    if {"Provider Name", "Week", "Encounter Lag"}.issubset(df.columns):
        lag_df = df.groupby(["Provider Name", "Week"])["Encounter Lag"].mean().reset_index(name="Avg Encounter Lag")
        st.plotly_chart(px.line(lag_df, x="Week", y="Avg Encounter Lag", color="Provider Name", markers=True), use_container_width=True)
    else:
        st.info("Insufficient data to compute encounter lag.")

    st.header("Provider CPT Mix – Initial vs Follow-Up")
    if "CPT Category" in df.columns and "Provider Name" in df.columns:
        cpt_init = df[df["CPT Category"] == "Initial"].groupby("Provider Name")["Visit ID"].count().reset_index(name="Count")
        cpt_follow = df[df["CPT Category"] == "Follow-up"].groupby("Provider Name")["Visit ID"].count().reset_index(name="Count")
        col1, col2 = st.columns(2)
        with col1:
            if not cpt_init.empty:
                st.plotly_chart(px.pie(cpt_init, names="Provider Name", values="Count", title="Initial Visits (99304–99306)"), use_container_width=True)
            else:
                st.info("No initial visit data available.")
        with col2:
            if not cpt_follow.empty:
                st.plotly_chart(px.pie(cpt_follow, names="Provider Name", values="Count", title="Follow-up Visits (99307–99310)"), use_container_width=True)
            else:
                st.info("No follow-up visit data available.")
    else:
        st.info("CPT Category or Provider Name missing for CPT mix analysis.")
