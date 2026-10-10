import streamlit as st
import pandas as pd
import os
import datetime
import re
import json
import gspread
from gspread_dataframe import set_with_dataframe
from fpdf import FPDF
from streamlit_option_menu import option_menu

st.set_page_config(page_title="ImmoClean ERP", page_icon="🏢", layout="wide")

# --- كود الديزاين (CSS) النقي والمضيء ---
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetric"] { background-color: white; border-left: 5px solid #1E88E5; padding: 15px 20px; border-radius: 10px; box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.05); }
    h1, h2, h3 { color: #0b3d91 !important; font-family: 'Segoe UI', Tahoma, sans-serif; }
</style>
""", unsafe_allow_html=True)

# --- 🚀 الاتصال بقاعدة البيانات (Google Sheets) 🚀 ---
@st.cache_resource(ttl=60)
def init_gsheets():
    try:
        creds_dict = json.loads(st.secrets["google_json"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("ImmoClean_Data")
        return sh
    except Exception as e:
        st.error(f"⚠️ هاهو المشكل التقني بالضبط: {e}")
        st.stop()

sh = init_gsheets()

# --- دوال جلب وحفظ البيانات ---
def load_data(sheet_name, columns):
    ws = sh.worksheet(sheet_name)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records)

def
