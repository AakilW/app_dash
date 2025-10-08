import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import gdown
from io import BytesIO

# -------------------- CONFIG --------------------
st.set_page_config(page_title="📊 APP Dashboard", layout="wide")

# -------------------- AUTH --------------------
def login():
    st.title("🔐 Login")
    st.markdown("Enter your credentials to access the dashboard.")
    username = st.text_input("Username", key="username")
    password = st.text_input("Password", type="password", key="password")
    login_btn = st.button("Login")

    if login_btn:
        if username == "streamdash" and password == "Billing@2025":
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid credentials. Access denied.")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login()
    st.stop()

# -------------------- DATA LOADER --------------------
st.title("📊 APP Client Dashboard")

file_id = "1PlTbACUnIAOkTzM-m06j_lQvX62kiFKB"
download_url = f"https://drive.google.com/uc?id={file_id}"

@st.cache_data
def load_excel_from_drive(url):
    try:
        output = BytesIO()
        gdown.download(url, output, quiet=True)
        output.seek(0)
        xls = pd.ExcelFile(output, engine='openpyxl')

        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])

        cpt_ref = pd.DataFrame()
        if "Sheet1" in xls.sheet_names:
            cpt_ref = pd.read_excel(xls, sheet_name="Sheet1")
            cpt_ref['CPT Code'] = cpt_ref['CPT Code'].astype(str).str.strip()
            for col in ['Charge/Unit', 'Expected']:
                if col in cpt_ref.columns:
                    cpt_ref[col] = pd.to_numeric(
                        cpt_ref[col].replace('[\$,]', '', regex=True),
                        errors='coerce'
                    )

        df['Visit Date'] = pd.to_datetime(df['Visit Date'], errors='coerce')
        df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], errors='coerce')
        df['Week'] = df['Visit Date'].dt.to_period('W').astype(str)
        df['Month'] = df['Visit Date'].dt.to_period('M').astype(str)
        df['Encounter Lag'] = (df['Transaction Date'] - df['Visit Date']).dt.days
        df['CPT Code'] = df['CPT Code'].astype(str).str.strip()
        df['CPT Category'] = df['CPT Code'].map(
            lambda x: 'Initial' if x in ['99304','99305','99306']
            else 'Follow-up' if x in ['99307','99308','99309','99310']
            else 'Other'
        )

        if not cpt_ref.empty:
            df = df.merge(cpt_ref, on="CPT Code", how="left")

        return df

    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None

# -------------------- LOAD DATA --------------------
df = load_excel_from_drive(download_url)

if df is not None:
    # -------------------- FILTERS --------------------
    st.sidebar.header("🔎 Filters")
    today = datetime.today()

    dos_filter = st.sidebar.selectbox(
        "Date of Service (Visit Date)",
        ["Last 30 Days", "Current Week", "Last 14 Days", "Current Month",
         "Current Quarter", "Current Year", "Custom Range"]
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
        start_date, end_date = datetime(today.year, 3*(q-1)+1, 1), today
    elif dos_filter == "Current Year":
        start_date, end_date = datetime(today.year, 1, 1), today
    else:
        start_date = pd.to_datetime(st.sidebar.date_input("Start Date", today - timedelta(days=30)))
        end_date = pd.to_datetime(st.sidebar.date_input("End Date", today))

    df = df.query("`Visit Date` >= @start_date and `Visit Date` <= @end_date")

    providers = st.sidebar.multiselect("Provider", sorted(df['Provider Name'].dropna().unique()))
    facilities = st.sidebar.multiselect("Facility", sorted(df['Facility Name'].dropna().unique()))
    states = st.sidebar.multiselect("State/Region", sorted(df['State'].dropna().unique()) if "State" in df else [])
    payer_class = st.sidebar.multiselect("Payer Class", sorted(df['Payer Class'].dropna().unique()) if "Payer Class" in df else [])
    encounter_type = st.sidebar.multiselect("Encounter Type", sorted(df['Encounter Type'].dropna().unique()) if "Encounter Type" in df else [])

    if providers: df = df[df['Provider Name'].isin(providers)]
    if facilities: df = df[df['Facility Name'].isin(facilities)]
    if states: df = df[df['State'].isin(states)]
    if payer_class: df = df[df['Payer Class'].isin(payer_class)]
    if encounter_type: df = df[df['Encounter Type'].isin(encounter_type)]

    # -------------------- DASHBOARD TABS --------------------
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Executive", "⚙️ Operations", "📊 Growth", "✅ Quality"])

    # ---------------- EXECUTIVE ----------------
    with tab1:
        st.markdown("### 🗓️ Provider Weekly Visit Count")
        weekly = df.groupby(['Provider Name', 'Week'])['Visit ID'].count().reset_index()
        st.plotly_chart(px.bar(weekly, x='Week', y='Visit ID', color='Provider Name', barmode='group'),
                        use_container_width=True)

        st.markdown("### 🎯 % to Target (Provider)")
        weekly['% to Target'] = (weekly['Visit ID'] / 120) * 100
        fig2 = px.bar(weekly, x='Week', y='% to Target', color='Provider Name', barmode='group')
        fig2.update_yaxes(range=[0, 150])
        st.plotly_chart(fig2, use_container_width=True)

    # ---------------- OPERATIONS ----------------
    with tab2:
        st.markdown("### 🏥 Visit Count by Facility (Monthly)")
        monthly_facility = df.groupby(['Facility Name', 'Month'])['Visit ID'].count().reset_index()
        st.plotly_chart(px.bar(monthly_facility, x='Month', y='Visit ID', color='Facility Name', barmode='stack'),
                        use_container_width=True)

        st.markdown("### 📊 % to Target (Facility)")
        monthly_facility['% to Target'] = (monthly_facility['Visit ID'] / 120) * 100
        fig4 = px.line(monthly_facility, x='Month', y='% to Target', color='Facility Name', markers=True)
        fig4.update_yaxes(range=[0, 150])
        st.plotly_chart(fig4, use_container_width=True)

        st.markdown("### 🚀 New Facility Ramp Tracker")
        ramp = df.groupby(['Facility Name', 'Week'])['Visit ID'].count().reset_index()
        ramp['% Ramp'] = (ramp['Visit ID'] / 120) * 100
        st.plotly_chart(px.area(ramp, x='Week', y='% Ramp', color='Facility Name'),
                        use_container_width=True)

        st.markdown("### 📅 Working Days by Provider")
        working_days = df.groupby(['Provider Name', 'Month'])['Visit Date'].nunique().reset_index()
        working_days.rename(columns={'Visit Date': 'Working Days'}, inplace=True)
        st.plotly_chart(px.bar(working_days, x='Month', y='Working Days', color='Provider Name', barmode='group'),
                        use_container_width=True)

    # ---------------- GROWTH ----------------
    with tab3:
        st.markdown("### ⏱️ CCM Start Delay by Facility")
        em_codes = ['99304','99305','99306','99307','99308','99309','99310']
        df_em = df[df['CPT Code'].isin(em_codes)]
        df_99487 = df[df['CPT Code'] == '99487']

        if not df_em.empty and not df_99487.empty:
            delay_df = pd.merge(df_em, df_99487, on='Patient ID', suffixes=('_EM', '_99487'))
            delay_df['CCM Delay'] = (delay_df['Visit Date_99487'] - delay_df['Visit Date_EM']).dt.days
            delay_summary = delay_df.groupby('Facility Name_EM')['CCM Delay'].mean().reset_index()
            st.dataframe(delay_summary.style.background_gradient(cmap='Oranges'))
        else:
            st.warning("⚠️ No CCM delay data found.")

    # ---------------- QUALITY ----------------
    with tab4:
        st.markdown("### 🕒 Provider Encounter Lag")
        lag_df = df.groupby(['Provider Name', 'Week'])['Encounter Lag'].mean().reset_index()
        st.plotly_chart(px.line(lag_df, x='Week', y='Encounter Lag', color='Provider Name', markers=True),
                        use_container_width=True)

        st.markdown("### 🧬 Provider CPT Mix – Initial vs Follow-Up")
        cpt_init = df[df['CPT Category'] == 'Initial'].groupby('Provider Name')['Visit ID'].count().reset_index()
        cpt_follow = df[df['CPT Category'] == 'Follow-up'].groupby('Provider Name')['Visit ID'].count().reset_index()

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(px.pie(cpt_init, names='Provider Name', values='Visit ID',
                                   title='Initial Visits (99304–99306)'), use_container_width=True)
        with col2:
            st.plotly_chart(px.pie(cpt_follow, names='Provider Name', values='Visit ID',
                                   title='Follow-up Visits (99307–99310)'), use_container_width=True)

else:
    st.warning("⚠️ Unable to load data from Google Drive Excel file.")
