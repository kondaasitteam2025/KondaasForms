import streamlit as st
import pandas as pd
import sqlite3
from datetime import date

# ================= PAGE CONFIG =================
st.set_page_config(page_title="Irrigation Dashboard", layout="wide")

# ================= DATABASE =================
conn = sqlite3.connect("data.db", check_same_thread=False)

# ================= CREATE TABLES =================
conn.execute("""
CREATE TABLE IF NOT EXISTS excel_data (
    valve TEXT,
    motor TEXT,
    crop TEXT,
    excel_flow TEXT,
    entry_date TEXT
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS supervisor_data (
    valve TEXT,
    motor TEXT,
    entry_date TEXT,
    supervisor_flow TEXT,
    remarks TEXT
)
""")
conn.commit()

# ================= CONSTANTS =================
REMARK_OPTIONS = ["Pipe Leakage", "Extra", "Other"]

# ================= HELPERS =================
def norm_crop(v):
    return "NO CROP" if "NO" in str(v).upper() else "CROP AVAILABLE"

def time_to_flow(v):
    if pd.isna(v):
        return "NO"
    v = str(v).strip()
    return "NO" if v in ["-", "0", "00:00"] else "YES"

def get_status(crop, excel_flow, sup_flow):
    if crop == "CROP AVAILABLE" and excel_flow == "YES" and not sup_flow:
        return "🟡"
    if crop == "CROP AVAILABLE" and excel_flow == "YES" and sup_flow == "YES":
        return "🟢"
    if crop == "CROP AVAILABLE" and excel_flow == "NO" and sup_flow == "YES":
        return "🔵"
    if crop == "NO CROP" and sup_flow == "YES":
        return "🔴"
    return "—"

def df_excel():
    return pd.read_sql("SELECT * FROM excel_data", conn)

def df_sup():
    return pd.read_sql("SELECT * FROM supervisor_data", conn)

# ================= SIDEBAR =================
st.sidebar.title("Menu")
role = st.sidebar.selectbox("Role", ["Admin", "Supervisor", "Dashboard"])

today_str = date.today().strftime("%Y-%m-%d")
sel_date_str = today_str if role == "Supervisor" else st.sidebar.date_input(
    "Date", date.today()
).strftime("%Y-%m-%d")

# ================= ADMIN =================
if role == "Admin":
    st.title("⬆️ Upload Irrigation Excel")

    files = st.file_uploader(
        "Upload Excel (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=True
    )

    for file in files:
        motor = file.name.replace(".xlsx", "")
        df = pd.read_excel(file)

        valve_col, crop_col = df.columns[:2]
        date_cols = df.columns[2:]

        for _, r in df.iterrows():
            for d in date_cols:
                parsed = pd.to_datetime(d, dayfirst=True, errors="coerce")
                if pd.isna(parsed):
                    continue

                conn.execute("""
                    INSERT INTO excel_data
                    (valve, motor, crop, excel_flow, entry_date)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    r[valve_col],
                    motor,
                    norm_crop(r[crop_col]),
                    time_to_flow(r[d]),
                    parsed.strftime("%Y-%m-%d")
                ))

    if files:
        conn.commit()
        st.success("Excel uploaded successfully")

# ================= SUPERVISOR =================
elif role == "Supervisor":
    st.title("👨‍🌾 Supervisor Entry")
    st.info(f"📅 Today Only: {sel_date_str}")

    ex = df_excel()

    # SAFETY CHECK
    if ex.empty:
        st.info("No Excel data. Please upload Excel first (Admin).")
        st.stop()

    ex = ex[
        (ex["entry_date"] == sel_date_str) &
        (ex["crop"] == "CROP AVAILABLE")
    ]

    if ex.empty:
        st.info("No crop available for today.")
        st.stop()

    for _, r in ex.iterrows():
        st.subheader(f"{r.valve} | {r.motor}")

        flow = st.radio(
            "Water Flow",
            ["YES", "NO"],
            horizontal=True,
            key=f"f_{r.valve}_{r.motor}"
        )

        remark = st.selectbox(
            "Remark",
            ["None"] + REMARK_OPTIONS,
            key=f"r_{r.valve}_{r.motor}"
        )

        if st.button("Save", key=f"s_{r.valve}_{r.motor}"):
            conn.execute("""
                INSERT INTO supervisor_data
                (valve, motor, entry_date, supervisor_flow, remarks)
                VALUES (?, ?, ?, ?, ?)
            """, (
                r.valve,
                r.motor,
                sel_date_str,
                flow,
                remark if remark != "None" else ""
            ))
            conn.commit()
            st.success("Saved")

# ================= DASHBOARD =================
else:
    st.title("📊 Irrigation Dashboard")

    ex = df_excel()
    su = df_sup()

    st.subheader("📌 Remark Count")
    if su.empty:
        st.info("No remarks yet")
    else:
        st.dataframe(su["remarks"].value_counts())

    st.subheader("🟢 Daily Status")

    ex = ex[ex["entry_date"] == sel_date_str]
    su_today = su[su["entry_date"] == sel_date_str]

    if ex.empty:
        st.info("No data for selected date")
    else:
        for _, r in ex.iterrows():
            s = su_today[
                (su_today.valve == r.valve) &
                (su_today.motor == r.motor)
            ]

            sup_flow = s.iloc[0].supervisor_flow if not s.empty else ""
            status = get_status(r.crop, r.excel_flow, sup_flow)

            st.write(f"{r.valve} | {r.motor} → {status}")
