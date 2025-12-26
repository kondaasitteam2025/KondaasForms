import streamlit as st
import pandas as pd
from datetime import date
import os
from sqlalchemy import create_engine, text

# ================= PAGE CONFIG =================
st.set_page_config("Irrigation Dashboard", layout="wide")

# ================= DATABASE (SUPABASE) =================
DATABASE_URL = "postgresql://postgres:Kondaas%23Irrigation95%21@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

engine = create_engine(DATABASE_URL)
conn = engine.connect()

# ================= TABLES =================
conn.execute(text("""
CREATE TABLE IF NOT EXISTS excel_data (
    valve TEXT,
    motor TEXT,
    crop TEXT,
    excel_flow TEXT,
    entry_date TEXT,
    PRIMARY KEY (valve, motor, entry_date)
)
"""))

conn.execute(text("""
CREATE TABLE IF NOT EXISTS supervisor_data (
    valve TEXT,
    motor TEXT,
    entry_date TEXT,
    supervisor_flow TEXT,
    remarks TEXT,
    image BYTEA,
    PRIMARY KEY (valve, motor, entry_date)
)
"""))

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
        return "YELLOW"
    if not sup_flow:
        return ""
    if crop == "CROP AVAILABLE" and excel_flow == "YES" and sup_flow == "YES":
        return "GREEN"
    if crop == "CROP AVAILABLE" and excel_flow == "NO" and sup_flow == "YES":
        return "BLUE"
    if crop == "NO CROP" and sup_flow == "YES":
        return "RED"
    return ""

def df_excel():
    return pd.read_sql(text("SELECT * FROM excel_data"), conn)

def df_sup():
    return pd.read_sql(text("SELECT * FROM supervisor_data"), conn)

# ================= SIDEBAR =================
st.sidebar.title("Menu")
role = st.sidebar.selectbox("Role", ["Admin", "Supervisor", "Dashboard"])

today_str = date.today().strftime("%Y-%m-%d")

if role == "Supervisor":
    sel_date_str = today_str
else:
    sel_date = st.sidebar.date_input("Date", date.today())
    sel_date_str = sel_date.strftime("%Y-%m-%d")

# ================= ADMIN =================
if role == "Admin":
    st.title("⬆️ Upload Irrigation Excel")

    files = st.file_uploader(
        "Upload Excel", type=["xlsx"], accept_multiple_files=True
    )

    for file in files:
        motor = file.name.replace(".xlsx", "")
        df = pd.read_excel(file)

        valve_col, crop_col = df.columns[:2]
        date_cols = df.columns[2:]

        for _, r in df.iterrows():
            for d in date_cols:
                parsed_date = pd.to_datetime(d, dayfirst=True, errors="coerce")
                if pd.isna(parsed_date):
                    continue

                date_str = parsed_date.strftime("%Y-%m-%d")

                conn.execute(text("""
                    INSERT INTO excel_data
                    (valve, motor, crop, excel_flow, entry_date)
                    VALUES (:v, :m, :c, :f, :d)
                    ON CONFLICT (valve, motor, entry_date)
                    DO UPDATE SET
                        crop = EXCLUDED.crop,
                        excel_flow = EXCLUDED.excel_flow
                """), {
                    "v": r[valve_col],
                    "m": motor,
                    "c": norm_crop(r[crop_col]),
                    "f": time_to_flow(r[d]),
                    "d": date_str
                })

    if files:
        st.success("Excel uploaded successfully")

# ================= SUPERVISOR =================
elif role == "Supervisor":
    st.title("👨‍🌾 Supervisor Entry")
    st.info(f"📅 Today Only: {sel_date_str}")

    df = df_excel()
    df = df[(df.entry_date == sel_date_str) & (df.crop == "CROP AVAILABLE")]

    for _, r in df.iterrows():
        st.subheader(f"{r.valve} | {r.motor}")

        flow = st.radio(
            "Water Flow",
            ["YES", "NO"],
            horizontal=True,
            key=f"f{r.valve}{r.motor}"
        )

        remark = st.selectbox(
            "Remark",
            ["None"] + REMARK_OPTIONS,
            key=f"r{r.valve}{r.motor}"
        )

        extra = ""
        if remark in ["Extra", "Other"]:
            extra = st.text_input(
                "Specify",
                key=f"e{r.valve}{r.motor}"
            )

        image_bytes = None
        if remark != "None":
            img = st.file_uploader(
                "Upload Photo (Mandatory)",
                type=["jpg", "png"],
                key=f"i{r.valve}{r.motor}"
            )
            if img:
                image_bytes = img.getvalue()

        if st.button("Save", key=f"s{r.valve}{r.motor}"):
            if remark != "None" and not image_bytes:
                st.error("Image required")
            else:
                final_remark = f"{remark} - {extra}" if extra else remark

                conn.execute(text("""
                    INSERT INTO supervisor_data
                    (valve, motor, entry_date, supervisor_flow, remarks, image)
                    VALUES (:v, :m, :d, :f, :r, :i)
                    ON CONFLICT (valve, motor, entry_date)
                    DO UPDATE SET
                        supervisor_flow = EXCLUDED.supervisor_flow,
                        remarks = EXCLUDED.remarks,
                        image = EXCLUDED.image
                """), {
                    "v": r.valve,
                    "m": r.motor,
                    "d": sel_date_str,
                    "f": flow,
                    "r": final_remark if remark != "None" else "",
                    "i": image_bytes
                })

                st.success("Saved")

# ================= DASHBOARD =================
else:
    st.title("📊 Irrigation Dashboard")

    ex = df_excel()
    su = df_sup()

    col1, col2 = st.columns(2)
    with col1:
        remark_filter = st.selectbox(
            "Filter Remark", ["All"] + REMARK_OPTIONS
        )
    with col2:
        show_history = st.checkbox(
            "Show Remark History", True
        )

    if remark_filter != "All":
        su = su[su.remarks.str.contains(remark_filter, na=False)]

    st.subheader("📌 Remark Count")
    if not su.empty:
        counts = su.remarks.str.extract(
            r"(Pipe Leakage|Extra|Other)"
        )[0].value_counts()
        st.dataframe(counts.rename("Count"))
    else:
        st.info("No remarks found")

    if show_history and not su.empty:
        st.subheader("📜 Remark History")
        st.dataframe(
            su[["entry_date", "valve", "motor", "remarks"]]
        )

    st.subheader("🟢 Daily Status")

    ex = ex[ex.entry_date == sel_date_str]
    su_today = su[su.entry_date == sel_date_str]

    valves = sorted(ex.valve.unique())
    motors = sorted(ex.motor.unique())

    header = st.columns(len(motors) + 1)
    header[0].markdown("### Valve")
    for i, m in enumerate(motors):
        header[i + 1].markdown(f"### {m}")

    for valve in valves:
        row = st.columns(len(motors) + 1)
        row[0].markdown(f"**{valve}**")

        for i, motor in enumerate(motors):
            e = ex[(ex.valve == valve) & (ex.motor == motor)]
            s = su_today[
                (su_today.valve == valve) &
                (su_today.motor == motor)
            ]

            if e.empty:
                row[i + 1].write("—")
                continue

            status = get_status(
                e.iloc[0].crop,
                e.iloc[0].excel_flow,
                s.iloc[0].supervisor_flow if not s.empty else ""
            )

            if status == "GREEN":
                row[i + 1].markdown("🟢")
            elif status == "YELLOW":
                row[i + 1].markdown("🟡")
            elif status == "RED":
                row[i + 1].markdown("🔴")
            elif status == "BLUE":
                if row[i + 1].button("🔵", key=f"{valve}{motor}"):
                    st.info(s.iloc[0].remarks)
                    if s.iloc[0].image:
                        st.image(s.iloc[0].image, width=300)
            else:
                row[i + 1].write("")
