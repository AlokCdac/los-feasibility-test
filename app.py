import html
import io
import json
import math
import sqlite3
from datetime import datetime
import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="LC LYNC LOS Feasibility (Trial)", page_icon="📡", layout="wide")

R = 6371000.0  # Earth radius in meters
DB_FILE = "los_surveys.db"
ARCHIVE_PASSWORD = "alok123"  # Change this to your desired password


# ==========================================
# DATABASE STORAGE MANAGEMENT
# ==========================================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_label TEXT,
                name_a TEXT,
                name_b TEXT,
                created_at TEXT,
                metadata_json TEXT,
                profile_json TEXT
            )
        """)
        conn.commit()


def save_survey_to_db(record: dict):
    survey_label = f"{record['name_a']} → {record['name_b']}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    clean_meta = {k: v for k, v in record.items() if k != "profile_df"}
    profile_df = record.get("profile_df", pd.DataFrame())

    meta_json = json.dumps(clean_meta)
    profile_json = profile_df.to_json() if not profile_df.empty else "{}"

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO surveys (survey_label, name_a, name_b, created_at, metadata_json, profile_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (survey_label, record["name_a"], record["name_b"], now_str, meta_json, profile_json),
        )
        conn.commit()


def get_saved_surveys_list() -> list:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, survey_label, created_at FROM surveys ORDER BY id DESC")
        rows = cursor.fetchall()
        return [(r[0], f"#{r[0]} | {r[1]} ({r[2]})") for r in rows]


def load_survey_from_db(survey_id: int) -> dict:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT metadata_json, profile_json FROM surveys WHERE id = ?", (survey_id,))
        row = cursor.fetchone()
        if not row:
            return None

        record = json.loads(row[0])
        if row[1] and row[1] != "{}":
            record["profile_df"] = pd.read_json(io.StringIO(row[1]))
        else:
            record["profile_df"] = pd.DataFrame()
        return record


init_db()

# ==========================================
# REPORT FORMATTING & SCHEMA DEFINITIONS
# ==========================================
EXACT_REPORT_COLUMNS = [
    "Name_A",
    "Lat_A",
    "Lon_A",
    "Name_b",
    "Lat_B",
    "Lon_B",
    "Distance (meters)",
    "Azimuth_AB",
    "Azimuth_BA",
    "status",
    "Expected Throughput Aggregated",
]

KEY_TO_FULL_NAME = {
    "name_a": "Name_A",
    "lat_a": "Lat_A",
    "lon_a": "Lon_A",
    "name_b": "Name_b",
    "lat_b": "Lat_B",
    "lon_b": "Lon_B",
    "dist_m": "Distance (meters)",
    "az_ab": "Azimuth_AB",
    "az_ba": "Azimuth_BA",
    "status": "status",
    "expected_throughput": "Expected Throughput Aggregated",
    "clearance": "Clearance Margin (m)",
    "ha": "Height A (m AGL)",
    "hb": "Height B (m AGL)",
    "ga": "Ground Elevation A (m AMSL)",
    "gb": "Ground Elevation B (m AMSL)",
    "beam": "Beam Diameter (m)",
    "power_mode": "Power Mode",
    "power_len": "Power Cable Length (m)",
    "data_port": "Data Port",
    "data_len": "Data Cable Length (m)",
    "reqa": "Raise Site A Only (m AGL)",
    "reqb": "Raise Site B Only (m AGL)",
    "eqa": "Equal Raise A (m
