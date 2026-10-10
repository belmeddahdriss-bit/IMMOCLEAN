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

def save_data(sheet_name, df):
    ws = sh.worksheet(sheet_name)
    ws.clear()
    set_with_dataframe(ws, df)

# --- أسماء الأعمدة في كل ورقة ---
COLS_CLIENTS = ["Résidence", "Secteur", "Responsable", "Téléphone", "Services", "Produits", "Prix (MAD)", "Jour de paiement"]
COLS_HIST = ["Date", "Résidence", "Employé", "Tâches", "Statut"]
COLS_EMP = ["Nom", "Téléphone", "Poste", "Photo"]
COLS_FIN = ["Date", "Type", "Categorie", "Montant (MAD)", "Description"]
COLS_PLAN = ["Employe", "Jour", "Slot1", "Slot2", "Slot3"]

# --- القائمة الجانبية (Menu Moderne) ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    elif os.path.exists("logo.jpg"): st.image("logo.jpg", use_container_width=True)
    elif os.path.exists("logo.jpeg"): st.image("logo.jpeg", use_container_width=True)
    elif os.path.exists("logo.webp"): st.image("logo.webp", use_container_width=True)
    else:
        st.markdown("<h2 style='text-align: center; color: #1E88E5;'>🏢 ImmoClean</h2>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    menu = option_menu(
        menu_title=None, 
        options=[
            "Tableau de bord", 
            "Nouveau Client",
            "Gérer les clients",
            "Pointage & Paiements", 
            "Finances & Trésorerie", 
            "Générer Reçu",
            "Générer Devis",
            "Gestion d'Équipe",
            "Planning"
        ],
        icons=['graph-up-arrow', 'building-add', 'pencil-square', 'currency-dollar', 'wallet2', 'receipt', 'file-earmark-ruled', 'people', 'calendar-week'],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "5!important", "background-color": "white", "border-radius": "10px", "border": "1px solid #e0e0e0"},
            "icon": {"color": "#1E88E5", "font-size": "18px"}, 
            "nav-link": {"font-size": "15px", "text-align": "left", "margin":"5px 0px", "color": "#333", "--hover-color": "#f0f2f6"},
            "nav-link-selected": {"background-color": "#1E88E5", "color": "white", "font-weight": "bold", "border-radius": "8px"},
        }
    )

st.title("ImmoClean FACILITY 🏢")

# --- 1. Tableau de bord ---
if menu == "Tableau de bord":
    st.header("📊 Tableau de bord (نظرة عامة)")
    
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_emp = load_data("Employes", COLS_EMP)
    df_hist = load_data("Historique", COLS_HIST)
    df_fin = load_data("Finances", COLS_FIN)
    
    total_clients = len(df_clients) if not df_clients.empty else 0
    total_employes = len(df_emp) if not df_emp.empty else 0
    
    residences_a_facturer = 0
    if not df_clients.empty and not df_hist.empty:
        for _, row in df_clients.iterrows():
            client = row["Résidence"]
            services = str(row.get("Services", "")).lower()
            
            if "2 fois" in services: cible = 8
            elif "2/mois" in services or "15 jours" in services: cible = 2
            else: cible = 4
            
            passages_non_payes = len(df_hist[(df_hist["Résidence"] == client) & (df_hist["Statut"] == "En attente")])
            if passages_non_payes >= cible:
                residences_a_facturer += 1

    total_revenus = pd.to_numeric(df_fin[df_fin["Type"] == "Entrée (Revenu)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    total_depenses = pd.to_numeric(df_fin[df_fin["Type"] == "Sortie (Dépense)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    solde_net = total_revenus - total_depenses
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric(label="🏢 Total Clients", value=f"{total_clients}")
    with col2: st.metric(label="🚨 Résidences à Facturer", value=f"{residences_a_facturer}")
    with col3: st.metric(label="💰 Total Entrées", value=f"{total_revenus} MAD")
    with col4: st.metric(label="💎 Solde Net (الصافي)", value=f"{solde_net} MAD", delta=f"{solde_net} MAD")
        
    st.markdown("---")
    st.subheader("📋 Liste des Clients Actifs")
    if not df_clients.empty:
        st.dataframe(df_clients, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun client enregistré.")

# --- 2. Nouveau Client ---
elif menu == "Nouveau Client":
    st.header("➕ Ajouter un nouveau client")
    with st.form("form_client"):
        residence = st.text_input("Nom de la résidence / Client")
        secteur = st.text_input("Secteur Géographique (ex: Centre Ville, Maamora...)")
        responsable = st.text_input("Nom du responsable (Syndic)")
        telephone = st.text_input("Téléphone")
        
        services_choisis = st.multiselect("Type de service", [
            "Escalier 1 passage par semaine", 
            "Escalier 2 fois par semaine", 
            "Escalier 1 passage tous les 15 jours (2/mois)", 
            "Sous-sol (Parking)", 
            "Terrasse", 
            "Bureau"
        ])
        
        produit = st.radio("Les produits de nettoyage :", ["À notre charge", "À la charge du client"])
        prix = st.number_input("Prix de l'abonnement mensuel (MAD)", min_value=0)
        jour_paiement = st.selectbox("Jour de paiement préféré:", [f"Le {i}" for i in range(1, 32)])
        
        if st.form_submit_button("Enregistrer le client"):
            if not residence or not services_choisis:
                st.warning("عافاك دخل سمية الإقامة واختار على الأقل خدمة وحدة.")
            else:
                nouveau = pd.DataFrame({
                    "Résidence": [residence], "Secteur": [secteur], "Responsable": [responsable], 
                    "Téléphone": [str(telephone)], "Services": [" + ".join(services_choisis)], 
                    "Produits": [produit], "Prix (MAD)": [prix], "Jour de paiement": [jour_paiement]
                })
                df_existant = load_data("Clients", COLS_CLIENTS)
                df_final = pd.concat([df_existant, nouveau], ignore_index=True)
                save_data("Clients", df_final)
                st.success(f"Le client {residence} a été ajouté avec succès dans Google Sheets !")

# --- 3. Gérer les clients ---
elif menu == "Gérer les clients":
    st.header("✏️ Modifier ou Supprimer un client")
    df = load_data("Clients", COLS_CLIENTS)
    if not df.empty:
        client_choisi = st.selectbox("اختار الكليان اللي بغيتي تعدل أو تمسح:", df["Résidence"].tolist())
        client_info = df[df["Résidence"] == client_choisi].iloc[0]
        
        with st.form("form_modifier"):
            n_secteur = st.text_
