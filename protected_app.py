import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import gdown
from io import BytesIO

# ---------------- CONFIG ----------------
st.set_page_config(page_title="APP Dashboard", layout="wide")

# ---------------- AUTH ----------------
def login_page():
    st.title("Login")
    st.markdown("Enter credentials to access the dashboard.")
    username = st.text_input("Username", key="username")
    password = st.text_input("Password", type="password", key="password")
    login_btn = st.button("Login", use_container_width=True)
    if login_btn:
        if username == "admin" and password == "admin123":  # Change as needed
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid credentials")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login_page()
    st.stop()

# ---------------- DATA LOADER ----------------
file_id = "1PlTbACUnIAOkTzM-m06j_lQvX62kiFKB"
download_url = f"https://drive.google.com/uc?id={file_id}&export=download"

@st.cache_data
def load_excel_from_drive(url):
    output = BytesIO()
    gdown.download(url, output, quiet=True)
    output.seek(0)
    xls = pd.ExcelFile(output, engine="openpyxl")

    df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])

    # Load optional CPT reference
    cpt_ref = pd.DataFrame()
    if "Sheet1" in xls.sheet_names:
        cpt_ref = pd.read_excel(xls, sheet_name="Sheet1")
        if "CPT Code" in cpt_ref.columns:
            cpt_ref["CPT Code"] = cpt_ref["CPT Code"].astype(str).str.strip()
        for col in ["Charge/Unit", "Expected"]:
            if col in cpt_ref.columns:
                cpt_ref[col] = pd.to_numeric(cpt_ref[col].replace(r"[\$,]", "", regex=True), errors="coerce")

    # Date parsing
    for col in ["Visit Date", "Transaction Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Derived time fields
    if "Visit Date" in df.columns:
        df["Week"] = df["Visit Date"].dt.to_period("W").astype(str)
        df["Month"] = df["Visit Date"].dt.to_period("M").astype(str)
    else:
        df["Week"] = pd.NA
        df["Month"] = pd.NA

    if {"Visit Date", "Transaction Date"}.issubset(df.columns):
        df["Encounter Lag"] = (df["Transaction Date"] - df["Visit Date"]).dt.days
    else:
        df["Encounter Lag"] = pd.NA

    # CPT Classification
    if "CPT Code" in df.columns:
        df["CPT Code"] = df["CPT Code"].astype(str).str.strip()
        em_init = {"99304", "99305", "99306"}
        em_follow = {"99307", "99308", "99309", "99310"}
        df["CPT Category"] = df["CPT Code"].apply(
            lambda x: "Initial" if x in em_init else "Follow-up" if x in em_follow else "Other"
        )
    else:
        df["CPT Code"] = pd.NA
        df["CPT Category"] = pd.NA

    # Merge reference if available
    if not cpt_ref.empty and "CPT Code" in cpt_ref.columns:
        df = df.merge(cpt_ref, on="CPT Code", how="left")

    if "Visit ID" not in df.columns:
        df.insert(0, "Visit ID", range(1, len(df) + 1))

    return df

df = load_excel_from_drive(download_url)

if df is None or df.empty:
    st.error("Failed to load dataset.")
    st.stop()

# ---------------- FILTERS ----------------
st.sidebar.header("Filters")
today = datetime.today()

date_option = st.sidebar.selectbox(
    "Date of Service",
    ["Last 30 Days", "Current Week", "Last 14 Days", "Current Month", "Current Quarter", "Current Year", "Custom Range"],
)

if date_option == "Last 30 Days":
    start_date, end_date = today - timedelta(days=30), today
elif date_option == "Current Week":
    start_date, end_date = today - timedelta(days=today.weekday()), today
elif date_option == "Last 14 Days":
    start_date, end_date = today - timedelta(days=14), today
elif date_option == "Current Month":
    start_date, end_date = today.replace(day=1), today
elif date_option == "Current Quarter":
    q = (today.month - 1) // 3 + 1
    start_date, end_date = datetime(today.year, 3 * (q - 1) + 1, 1), today
elif date_option == "Current Year":
    start_date, end_date = datetime(today.year, 1, 1), today
else:
    start_date = pd.to_datetime(st.sidebar.date_input("Start Date", today - timedelta(days=30)))
    end_date = pd.to_datetime(st.sidebar.date_input("End Date", today))

if "Visit Date" in df.columns:
    df = df[(df["Visit Date"] >= start_date) & (df["Visit Date"] <= end_date)]

filters = {
    "Provider Name": st.sidebar.multiselect("Provider", sorted(df.get("Provider Name", pd.Series()).dropna().unique())),
    "Facility Name": st.sidebar.multiselect("Facility", sorted(df.get("Facility Name", pd.Series()).dropna().unique())),
    "State": st.sidebar.multiselect("State/Region", sorted(df.get("State", pd.Series()).dropna().unique())),
    "Payer Class": st.sidebar.multiselect("Payer Class", sorted(df.get("Payer Class", pd.Series()).dropna().unique())),
    "Encounter Type": st.sidebar.multiselect("Encounter Type", sorted(df.get("Encounter Type", pd.Series()).dropna().unique())),
}

for col, selected in filters.items():
    if selected and col in df.columns:
        df = df[df[col].isin(selected)]

# ---------------- DASHBOARD ----------------
tab1, tab2, tab3, tab4 = st.tabs(["Executive", "Operations", "Growth", "Quality"])

# EXECUTIVE TAB
with tab1:
    st.subheader("Provider Weekly Visit Count")
    if {"Provider Name", "Week"}.issubset(df.columns):
        weekly = df.groupby(["Provider Name", "Week"])["Visit ID"].count().reset_index(name="Visit Count")
        fig = px.bar(weekly, x="Week", y="Visit Count", color="Provider Name", barmode="group")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("% to Target (Provider)")
        weekly["% to Target"] = (weekly["Visit Count"] / 120) * 100
        fig2 = px.bar(weekly, x="Week", y="% to Target", color="Provider Name", barmode="group")
        fig2.update_yaxes(range=[0, 150])
        st.plotly_chart(fig2, use_container_width=True)

# OPERATIONS TAB
with tab2:
    st.subheader("Visit Count by Facility (Monthly)")
    if {"Facility Name", "Month"}.issubset(df.columns):
        monthly = df.groupby(["Facility Name", "Month"])["Visit ID"].count().reset_index(name="Visit Count")
        fig3 = px.bar(monthly, x="Month", y="Visit Count", color="Facility Name", barmode="stack")
        st.plotly_chart(fig3, use_container_width=True)

        monthly["% to Target"] = (monthly["Visit Count"] / 120) * 100
        fig4 = px.line(monthly, x="Month", y="% to Target", color="Facility Name", markers=True)
        fig4.update_yaxes(range=[0, 150])
        st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Working Days by Provider")
    if {"Provider Name", "Month", "Visit Date"}.issubset(df.columns):
        work = df.groupby(["Provider Name", "Month"])["Visit Date"].nunique().reset_index(name="Working Days")
        st.plotly_chart(px.bar(work, x="Month", y="Working Days", color="Provider Name", barmode="group"), use_container_width=True)

# GROWTH TAB
with tab3:
    st.subheader("CCM Start Delay by Facility")
    em_codes = {"99304", "99305", "99306", "99307", "99308", "99309", "99310"}
    if {"CPT Code", "Patient ID", "Visit Date"}.issubset(df.columns):
        df_em = df[df["CPT Code"].isin(em_codes)]
        df_ccm = df[df["CPT Code"] == "99487"]
        if not df_em.empty and not df_ccm.empty:
            em_first = df_em.sort_values("Visit Date").groupby("Patient ID").first().reset_index()
            ccm_first = df_ccm.sort_values("Visit Date").groupby("Patient ID").first().reset_index()
            delay = pd.merge(em_first, ccm_first, on="Patient ID", suffixes=("_EM", "_CCM"))
            delay["CCM Delay (days)"] = (delay["Visit Date_CCM"] - delay["Visit Date_EM"]).dt.days
            delay_summary = delay.groupby("Facility Name_EM")["CCM Delay (days)"].mean().reset_index()
            st.dataframe(delay_summary.style.background_gradient(cmap="RdYlGn_r"))
        else:
            st.info("No CCM data found.")

# QUALITY TAB
with tab4:
    st.subheader("Provider Encounter Lag")
    if {"Provider Name", "Week", "Encounter Lag"}.issubset(df.columns):
        lag = df.groupby(["Provider Name", "Week"])["Encounter Lag"].mean().reset_index()
        st.plotly_chart(px.line(lag, x="Week", y="Encounter Lag", color="Provider Name", markers=True), use_container_width=True)

    st.subheader("Provider CPT Mix – Initial vs Follow-Up")
    if {"Provider Name", "CPT Category"}.issubset(df.columns):
        init = df[df["CPT Category"] == "Initial"].groupby("Provider Name")["Visit ID"].count().reset_index(name="Count")
        follow = df[df["CPT Category"] == "Follow-up"].groupby("Provider Name")["Visit ID"].count().reset_index(name="Count")

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.pie(init, names="Provider Name", values="Count", title="Initial Visits"), use_container_width=True)
        with c2:
            st.plotly_chart(px.pie(follow, names="Provider Name", values="Count", title="Follow-Up Visits"), use_container_width=True)
