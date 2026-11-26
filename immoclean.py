import streamlit as st
import pandas as pd
import gspread
import json
from datetime import datetime, date, timedelta
from fpdf import FPDF
from google.oauth2.service_account import Credentials

# ==========================================
# 1. CONFIGURATION & CONSTANTES ENTREPRISE
# ==========================================
st.set_page_config(
    page_title="ImmoClean FACILITY - ERP",
    page_icon="🧹",
    layout="wide"
)

COMPANY_NAME = "IMMOCLEAN FACILITY SARL"
COMPANY_SUBTITLE = "Nettoyage Professionnel & Entretien"
COMPANY_RC = "204133"
COMPANY_ICE = "004037999000087"
COMPANY_ADDRESS = "Imm 7 Rue Moulay Rachid Appt N 10 Etage 4 Hassan Rabat"
COMPANY_CITY = "Kénitra"
COMPANY_PHONE = "06 49 92 43 54"

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
JOURS_MAP = {i: jour for i, jour in enumerate(JOURS_SEMAINE)}

# ==========================================
# 2. CONNEXION GOOGLE SHEETS (CACHE 60s)
# ==========================================
@st.cache_resource(ttl=60)
def get_spreadsheet():
    creds_dict = json.loads(st.secrets["google_json"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("ImmoClean_Data")

def load_sheet(sh, sheet_name, expected_cols):
    try:
        ws = sh.worksheet(sheet_name)
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=expected_cols)
        df.columns = [str(c).strip() for c in df.columns]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"Erreur de lecture de l'onglet '{sheet_name}': {e}")
        return pd.DataFrame(columns=expected_cols)

def save_sheet(sh, sheet_name, df):
    ws = sh.worksheet(sheet_name)
    df_clean = df.fillna("").astype(str)
    ws.clear()
    ws.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())

def get_price_col(df_clients):
    if "Prix TTC (MAD)" in df_clients.columns:
        return "Prix TTC (MAD)"
    return "Prix (MAD)"

def to_float(val):
    try:
        s = str(val).replace("MAD", "").replace(" ", "").replace(",", ".").strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0

# ==========================================
# 3. SYNCHRONISATION AUTOMATIQUE (AUTO-POINTAGE)
# ==========================================
def sync_historique_auto(sh, df_planning, df_hist, date_debut):
    """
    Enregistre automatiquement toutes les séances du Planning entre date_debut
    et aujourd'hui dans l'onglet Historique avec le statut 'Effectuée', sans doublons.
    """
    if df_planning.empty:
        return 0

    ws_hist = sh.worksheet("Historique")
    aujourdhui = date.today()

    # Clés existantes pour éviter les doublons
    existants = set()
    if not df_hist.empty:
        for _, row in df_hist.iterrows():
            cle = (
                str(row.get("Date", "")).strip(),
                str(row.get("Résidence", "")).strip(),
                str(row.get("Employé", "")).strip()
            )
            existants.add(cle)

    nouvelles_lignes = []
    current_date = date_debut

    while current_date <= aujourdhui:
        jour_nom = JOURS_MAP[current_date.weekday()]
        date_str = current_date.strftime("%Y-%m-%d")

        plan_jour = df_planning[
            df_planning["Jour"].astype(str).str.strip().str.lower() == jour_nom.lower()
        ]

        for _, prow in plan_jour.iterrows():
            emp = str(prow.get("Employe", "")).strip()
            for slot in ["Slot1", "Slot2", "Slot3"]:
                res = str(prow.get(slot, "")).strip()
                if res and res not in ["-", "Aucun", "nan", "None"]:
                    cle = (date_str, res, emp)
                    if cle not in existants:
                        nouvelles_lignes.append([
                            date_str, res, emp, "Nettoyage programmé", "Effectuée"
                        ])
                        existants.add(cle)

        current_date += timedelta(days=1)

    if nouvelles_lignes:
        ws_hist.append_rows(nouvelles_lignes)

    return len(nouvelles_lignes)

# ==========================================
# 4. OUTILS PDF (FPDF)
# ==========================================
def clean_pdf(text):
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "€": "EUR"
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")

class ImmoCleanPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 15)
        self.set_text_color(20, 60, 110)
        self.cell(0, 8, clean_pdf(COMPANY_NAME), ln=True, align="L")
        self.set_font("Arial", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(0, 5, clean_pdf(f"{COMPANY_SUBTITLE} | RC: {COMPANY_RC} | ICE: {COMPANY_ICE}"), ln=True, align="L")
        self.cell(0, 5, clean_pdf(f"Siège: {COMPANY_ADDRESS} | Tél: {COMPANY_PHONE}"), ln=True, align="L")
        self.ln(3)
        self.set_draw_color(20, 60, 110)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, clean_pdf(f"{COMPANY_NAME} - {COMPANY_CITY} | Tél: {COMPANY_PHONE} | Page {self.page_no()}"), align="C")

def generate_recu_pdf(client, mois, montant, mode, date_paiement):
    pdf = ImmoCleanPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, clean_pdf("REÇU DE PAIEMENT"), ln=True, align="C")
    pdf.ln(6)

    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, clean_pdf(f"Date : {date_paiement}"), ln=True)
    pdf.cell(0, 8, clean_pdf(f"Reçu de : {client}"), ln=True)
    pdf.cell(0, 8, clean_pdf(f"Objet : Frais de nettoyage et d'entretien - {mois}"), ln=True)
    pdf.cell(0, 8, clean_pdf(f"Mode de règlement : {mode}"), ln=True)
    pdf.ln(4)

    pdf.set_font("Arial", "B", 13)
    pdf.set_fill_color(235, 243, 252)
    pdf.cell(0, 12, clean_pdf(f"  MONTANT REÇU : {montant:,.2f} MAD"), ln=True, fill=True)
    pdf.ln(15)

    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 8, clean_pdf(f"Fait à {COMPANY_CITY}, le {date_paiement}"), ln=True, align="R")
    pdf.ln(8)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 8, clean_pdf("Cachet et Signature IMMOCLEAN FACILITY"), ln=True, align="R")
    return pdf.output(dest="S").encode("latin-1")

def generate_devis_pdf(num_devis, client, ice_client, lieu, description, montant_ttc, validite):
    pdf = ImmoCleanPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, clean_pdf(f"DEVIS N° {num_devis}"), ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, clean_pdf(f"Date : {date.today().strftime('%d/%m/%Y')}"), ln=True)
    pdf.cell(0, 6, clean_pdf(f"Client : {client}"), ln=True)
    if ice_client:
        pdf.cell(0, 6, clean_pdf(f"ICE Client : {ice_client}"), ln=True)
    pdf.cell(0, 6, clean_pdf(f"Lieu du chantier : {lieu}"), ln=True)
    pdf.ln(6)

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(20, 60, 110)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(140, 8, clean_pdf("Désignation des prestations"), border=1, fill=True)
    pdf.cell(50, 8, clean_pdf("Total TTC (MAD)"), border=1, fill=True, align="R", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 10)
    y_start = pdf.get_y()
    pdf.multi_cell(140, 6, clean_pdf(description), border=1)
    y_end = pdf.get_y()
    h = max(8, y_end - y_start)
    pdf.set_xy(150, y_start)
    pdf.cell(50, h, clean_pdf(f"{montant_ttc:,.2f} MAD"), border=1, align="R", ln=True)
    pdf.set_y(y_end + 6)

    ht = round(montant_ttc / 1.20, 2)
    tva = round(montant_ttc - ht, 2)
    pdf.set_font("Arial", "", 10)
    pdf.cell(140, 7, clean_pdf("Total HT :"), align="R")
    pdf.cell(50, 7, clean_pdf(f"{ht:,.2f} MAD"), align="R", ln=True)
    pdf.cell(140, 7, clean_pdf("TVA (20%) :"), align="R")
    pdf.cell(50, 7, clean_pdf(f"{tva:,.2f} MAD"), align="R", ln=True)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(140, 8, clean_pdf("TOTAL TTC :"), align="R")
    pdf.cell(50, 8, clean_pdf(f"{montant_ttc:,.2f} MAD"), align="R", ln=True)

    pdf.ln(8)
    pdf.set_font("Arial", "I", 9)
    pdf.cell(0, 6, clean_pdf(f"Validité du devis : {validite} jours."), ln=True)
    return pdf.output(dest="S").encode("latin-1")

def generate_facture_pdf(num_fac, client, ice_client, adresse_client, description, montant_ttc, acompte, ras_taux, mode_solde):
    pdf = ImmoCleanPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, clean_pdf(f"FACTURE N° {num_fac}"), ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, clean_pdf(f"Date d'émission : {date.today().strftime('%d/%m/%Y')}"), ln=True)
    pdf.cell(0, 6, clean_pdf(f"Client : {client}"), ln=True)
    if ice_client:
        pdf.cell(0, 6, clean_pdf(f"ICE Client : {ice_client}"), ln=True)
    if adresse_client:
        pdf.cell(0, 6, clean_pdf(f"Adresse : {adresse_client}"), ln=True)
    pdf.ln(6)

    ht = round(montant_ttc / 1.20, 2)
    tva = round(montant_ttc - ht, 2)
    ras_montant = round(tva * (ras_taux / 100.0), 2)
    net_a_payer_client = round(montant_ttc - ras_montant, 2)
    solde_restant = round(net_a_payer_client - acompte, 2)

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(20, 60, 110)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(140, 8, clean_pdf("Désignation"), border=1, fill=True)
    pdf.cell(50, 8, clean_pdf("Montant HT (MAD)"), border=1, fill=True, align="R", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 10)
    y_start = pdf.get_y()
    pdf.multi_cell(140, 6, clean_pdf(description), border=1)
    y_end = pdf.get_y()
    h = max(8, y_end - y_start)
    pdf.set_xy(150, y_start)
    pdf.cell(50, h, clean_pdf(f"{ht:,.2f} MAD"), border=1, align="R", ln=True)
    pdf.set_y(y_end + 6)

    pdf.cell(140, 7, clean_pdf("Total HT :"), align="R")
    pdf.cell(50, 7, clean_pdf(f"{ht:,.2f} MAD"), align="R", ln=True)
    pdf.cell(140, 7, clean_pdf("TVA (20%) :"), align="R")
    pdf.cell(50, 7, clean_pdf(f"{tva:,.2f} MAD"), align="R", ln=True)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(140, 8, clean_pdf("TOTAL TTC :"), align="R")
    pdf.cell(50, 8, clean_pdf(f"{montant_ttc:,.2f} MAD"), align="R", ln=True)

    pdf.set_font("Arial", "", 10)
    if ras_taux > 0:
        pdf.cell(140, 7, clean_pdf(f"Retenue à la source TVA ({ras_taux}%) :"), align="R")
        pdf.cell(50, 7, clean_pdf(f"- {ras_montant:,.2f} MAD"), align="R", ln=True)
    if acompte > 0:
        pdf.cell(140, 7, clean_pdf("Acompte reçu (Espèces) :"), align="R")
        pdf.cell(50, 7, clean_pdf(f"- {acompte:,.2f} MAD"), align="R", ln=True)

    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(235, 243, 252)
    pdf.cell(140, 9, clean_pdf(f"NET RESTANT À PAYER ({mode_solde}) :"), align="R", fill=True)
    pdf.cell(50, 9, clean_pdf(f"{solde_restant:,.2f} MAD"), align="R", fill=True, ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 8, clean_pdf("Cachet et Signature IMMOCLEAN FACILITY"), ln=True, align="R")
    return pdf.output(dest="S").encode("latin-1")

def generate_planning_pdf(df_planning, df_clients):
    pdf = ImmoCleanPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, clean_pdf("PLANNING HEBDOMADAIRE DES INTERVENTIONS"), ln=True, align="C")
    pdf.ln(3)

    # Dictionnaire Résidence -> Secteur
    secteur_map = {}
    if not df_clients.empty:
        for _, r in df_clients.iterrows():
            secteur_map[str(r.get("Résidence", "")).strip()] = str(r.get("Secteur", "")).strip()

    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(20, 60, 110)
    pdf.set_text_color(255, 255, 255)
    widths = [40, 30, 68, 68, 68]
    headers = ["Employé", "Jour", "Créneau 1 (Matin)", "Créneau 2 (Midi)", "Créneau 3 (Soir)"]
    for w, h_txt in zip(widths, headers):
        pdf.cell(w, 8, clean_pdf(h_txt), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 8)

    for _, row in df_planning.iterrows():
        emp = str(row.get("Employe", ""))
        jour = str(row.get("Jour", ""))
        slots_txt = []
        for s_col in ["Slot1", "Slot2", "Slot3"]:
            res = str(row.get(s_col, "")).strip()
            if res and res not in ["-", "Aucun", "nan"]:
                sec = secteur_map.get(res, "")
                slots_txt.append(f"{res}\n({sec})" if sec else res)
            else:
                slots_txt.append("-")

        # Calcul hauteur max de la ligne
        line_h = 12
        if pdf.get_y() + line_h > 185:
            pdf.add_page()

        y0 = pdf.get_y()
        x0 = pdf.get_x()
        pdf.cell(widths[0], line_h, clean_pdf(emp), border=1)
        pdf.cell(widths[1], line_h, clean_pdf(jour), border=1, align="C")
        for idx, stxt in enumerate(slots_txt):
            x_curr = x0 + widths[0] + widths[1] + idx * widths[2]
            pdf.set_xy(x_curr, y0)
            pdf.multi_cell(widths[idx + 2], 6, clean_pdf(stxt), border=1, align="C")
        pdf.set_y(y0 + line_h)

    return pdf.output(dest="S").encode("latin-1")

# ==========================================
# 5. CHARGEMENT INITIAL & AUTO-SYNC
# ==========================================
try:
    sh = get_spreadsheet()
except Exception as e:
    st.error(f"Impossible de se connecter à Google Sheets : {e}")
    st.stop()

df_clients = load_sheet(sh, "Clients", ["Résidence", "Secteur", "Responsable", "Téléphone", "Services", "Produits", "Prix (MAD)", "Jour de paiement"])
df_hist = load_sheet(sh, "Historique", ["Date", "Résidence", "Employé", "Tâches", "Statut"])
df_emp = load_sheet(sh, "Employes", ["Nom", "Téléphone", "Poste", "Photo"])
df_fin = load_sheet(sh, "Finances", ["Date", "Type", "Categorie", "Montant (MAD)", "Description"])
df_plan = load_sheet(sh, "Planning", ["Employe", "Jour", "Slot1", "Slot2", "Slot3"])

price_col = get_price_col(df_clients)

# Auto-synchronisation au lancement de la session (depuis le dernier jour enregistré ou début du mois)
if "auto_synced" not in st.session_state:
    try:
        date_debut_auto = date.today().replace(day=1)
        if not df_hist.empty and "Date" in df_hist.columns:
            valid_dates = pd.to_datetime(df_hist["Date"], errors="coerce").dropna()
            if not valid_dates.empty:
                last_dt = valid_dates.max().date()
                # On prend la date la plus ancienne entre le dernier enregistrement et il y a 7 jours
                date_debut_auto = min(last_dt, date.today() - timedelta(days=7))
        nb_ajoutes = sync_historique_auto(sh, df_plan, df_hist, date_debut_auto)
        st.session_state["auto_synced"] = True
        if nb_ajoutes > 0:
            st.toast(f"✅ {nb_ajoutes} séances enregistrées automatiquement !", icon="🤖")
            df_hist = load_sheet(sh, "Historique", ["Date", "Résidence", "Employé", "Tâches", "Statut"])
    except Exception as e:
        st.warning(f"Note Auto-Sync : {e}")

# ==========================================
# 6. MENU LATÉRAL
# ==========================================
st.sidebar.title("🧹 ImmoClean ERP")
st.sidebar.caption(f"{COMPANY_NAME} - {COMPANY_CITY}")

menu = st.sidebar.radio(
    "Navigation",
    [
        "📊 Tableau de bord",
        "✅ Pointage & Paiements",
        "➕ Nouveau Client",
        "🏢 Gérer les clients",
        "💰 Finances & Trésorerie",
        "🧾 Générer Reçu",
        "📄 Générer Devis",
        "📑 Générer Facture",
        "👷 Gestion d'Équipe",
        "📅 Planning"
    ]
)

# ==========================================
# PAGE 1 : TABLEAU DE BORD
# ==========================================
if menu == "📊 Tableau de bord":
    st.title("📊 Tableau de bord - ImmoClean FACILITY")

    total_clients = len(df_clients)
    ca_mensuel = df_clients[price_col].apply(to_float).sum() if not df_clients.empty else 0.0

    entrees = df_fin[df_fin["Type"] == "Entrée"]["Montant (MAD)"].apply(to_float).sum() if not df_fin.empty else 0.0
    sorties = df_fin[df_fin["Type"] == "Sortie"]["Montant (MAD)"].apply(to_float).sum() if not df_fin.empty else 0.0
    solde = entrees - sorties

    mois_actuel = date.today().strftime("%Y-%m")
    seances_mois = 0
    if not df_hist.empty:
        seances_mois = len(df_hist[
            (df_hist["Date"].astype(str).str.startswith(mois_actuel)) &
            (df_hist["Statut"].astype(str).str.strip() == "Effectuée")
        ])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏢 Résidences Actives", total_clients)
    c2.metric("💵 Abonnements Mensuels", f"{ca_mensuel:,.0f} MAD")
    c3.metric("🏦 Solde Trésorerie", f"{solde:,.0f} MAD")
    c4.metric("✅ Séances ce mois", seances_mois)

    st.divider()
    st.subheader("📋 Liste des Clients (Résidences)")

    # Tableau épuré SANS colonnes de TVA / HT selon demande
    colonnes_voulues = [
        "Résidence",
        "Responsable",
        "Téléphone",
        "Secteur",
        price_col,
        "Jour de paiement"
    ]
    cols_dispo = [c for c in colonnes_voulues if c in df_clients.columns]

    if not df_clients.empty:
        df_affichage = df_clients[cols_dispo].rename(columns={
            "Résidence": "Nom Résidence",
            "Responsable": "Syndic / Responsable",
            "Téléphone": "Téléphone Syndic",
            "Secteur": "Localisation",
            price_col: "Abonnement (MAD)",
            "Jour de paiement": "Jour d'abonnement"
        })
        st.dataframe(df_affichage, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun client enregistré pour le moment.")

# ==========================================
# PAGE 2 : POINTAGE & PAIEMENTS (LOGIQUE INVERSÉE + RATTRAPAGE)
# ==========================================
elif menu == "✅ Pointage & Paiements":
    st.title("✅ Suivi Automatique des Séances & Paiements")

    tab1, tab2, tab3 = st.tabs(["🤖 Suivi par Exception", "💳 Encaisser un Client", "📚 Archive & Rattrapage"])

    with tab1:
        st.info("💡 Toutes les séances du Planning sont enregistrées automatiquement comme **Effectuée**. Cliquez uniquement si une séance a été **Reportée** ou **Annulée**.")
        date_sel = st.date_input("Choisir une date à vérifier :", value=date.today())
        date_str = date_sel.strftime("%Y-%m-%d")

        # Bouton rapide pour forcer la synchro de cette date si besoin
        if st.button("🔄 Synchroniser cette date depuis le Planning"):
            n = sync_historique_auto(sh, df_plan, df_hist, date_sel)
            st.success(f"{n} séance(s) ajoutée(s) !")
            st.rerun()

        df_jour = df_hist[df_hist["Date"].astype(str).str.strip() == date_str]

        if df_jour.empty:
            st.warning(f"Aucune séance trouvée pour le {date_str}.")
        else:
            for idx, row in df_jour.iterrows():
                statut = str(row["Statut"]).strip()
                icone = "✅" if statut == "Effectuée" else ("⏳" if statut == "Reportée" else "❌")

                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([4, 2, 2])
                    col_a.markdown(f"**{icone} {row['Résidence']}** — 👷 {row['Employé']}  \nStatut actuel : **{statut}**")

                    if statut == "Effectuée":
                        if col_b.button("⏳ Reportée", key=f"rep_{idx}", use_container_width=True):
                            df_hist.at[idx, "Statut"] = "Reportée"
                            save_sheet(sh, "Historique", df_hist)
                            st.rerun()
                        if col_c.button("❌ Annulée", key=f"ann_{idx}", use_container_width=True):
                            df_hist.at[idx, "Statut"] = "Annulée"
                            save_sheet(sh, "Historique", df_hist)
                            st.rerun()
                    else:
                        if col_b.button("✅ Remettre Effectuée", key=f"eff_{idx}", use_container_width=True):
                            df_hist.at[idx, "Statut"] = "Effectuée"
                            save_sheet(sh, "Historique", df_hist)
                            st.rerun()

    with tab2:
        st.subheader("💳 Enregistrer le paiement d'un client")
        if df_clients.empty:
            st.warning("Ajoutez d'abord des clients.")
        else:
            with st.form("form_paiement_client"):
                res_p = st.selectbox("Résidence", df_clients["Résidence"].tolist())
                prix_defaut = to_float(df_clients[df_clients["Résidence"] == res_p][price_col].values[0])
                montant_p = st.number_input("Montant encaissé (MAD)", min_value=0.0, value=prix_defaut, step=50.0)
                date_p = st.date_input("Date d'encaissement", value=date.today())
                desc_p = st.text_input("Description", value=f"Abonnement mensuel - {res_p}")
                if st.form_submit_button("💾 Enregistrer dans Finances"):
                    ws_fin = sh.worksheet("Finances")
                    ws_fin.append_row([date_p.strftime("%Y-%m-%d"), "Entrée", "Abonnement Client", str(montant_p), desc_p])
                    st.success(f"Paiement de {montant_p:,.2f} MAD enregistré pour {res_p} !")
                    st.rerun()

    with tab3:
        st.subheader("🔄 Rattrapage automatique de l'archive (Séances passées)")
        st.write("Si vous n'avez pas ouvert l'application pendant plusieurs jours, choisissez la date de début pour remplir automatiquement tout l'historique manquant à partir du Planning.")
        c_r1, c_r2 = st.columns([2, 1])
        date_rattrapage = c_r1.date_input("Date de début du rattrapage :", value=date.today() - timedelta(days=30))
        if c_r2.button("🚀 Remplir l'archive jusqu'à aujourd'hui", use_container_width=True):
            with st.spinner("Synchronisation en cours..."):
                nb = sync_historique_auto(sh, df_plan, df_hist, date_rattrapage)
            st.success(f"Terminé ! {nb} séances passées ont été ajoutées à l'archive (sans doublons).")
            st.rerun()

        st.divider()
        st.subheader("📚 Historique complet")
        if not df_hist.empty:
            filtre_res = st.selectbox("Filtrer par Résidence", ["Toutes"] + sorted(df_hist["Résidence"].astype(str).unique().tolist()))
            df_h_view = df_hist if filtre_res == "Toutes" else df_hist[df_hist["Résidence"] == filtre_res]
            st.dataframe(df_h_view.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)

# ==========================================
# PAGE 3 : NOUVEAU CLIENT
# ==========================================
elif menu == "➕ Nouveau Client":
    st.title("➕ Ajouter une Nouvelle Résidence")
    with st.form("new_client_form"):
        c1, c2 = st.columns(2)
        res_name = c1.text_input("Nom de la Résidence *")
        secteur = c2.text_input("Secteur / Localisation *")
        resp = c1.text_input("Nom du Syndic / Responsable")
        tel = c2.text_input("Téléphone")
        services = c1.text_input("Services inclus", value="Nettoyage escaliers, hall, vitres")
        produits = c2.text_input("Produits fournis", value="Inclus")
        prix = c1.number_input("Prix Abonnement Mensuel (MAD)", min_value=0.0, step=100.0)
        jour_p = c2.text_input("Jour de paiement (ex: 1er du mois)", value="1er du mois")

        if st.form_submit_button("✅ Enregistrer le Client"):
            if not res_name.strip():
                st.error("Le nom de la résidence est obligatoire.")
            else:
                new_row = pd.DataFrame([{
                    "Résidence": res_name.strip(),
                    "Secteur": secteur.strip(),
                    "Responsable": resp.strip(),
                    "Téléphone": tel.strip(),
                    "Services": services.strip(),
                    "Produits": produits.strip(),
                    price_col: str(prix),
                    "Jour de paiement": jour_p.strip()
                }])
                df_updated = pd.concat([df_clients, new_row], ignore_index=True)
                save_sheet(sh, "Clients", df_updated)
                st.success(f"Résidence '{res_name}' ajoutée avec succès !")
                st.rerun()

# ==========================================
# PAGE 4 : GÉRER LES CLIENTS
# ==========================================
elif menu == "🏢 Gérer les clients":
    st.title("🏢 Modifier ou Supprimer un Client")
    if df_clients.empty:
        st.info("Aucun client à gérer.")
    else:
        client_sel = st.selectbox("Sélectionner une résidence", df_clients["Résidence"].tolist())
        idx = df_clients[df_clients["Résidence"] == client_sel].index[0]
        row = df_clients.loc[idx]

        with st.form("edit_client_form"):
            c1, c2 = st.columns(2)
            n_res = c1.text_input("Résidence", value=str(row["Résidence"]))
            n_sec = c2.text_input("Secteur", value=str(row["Secteur"]))
            n_resp = c1.text_input("Responsable", value=str(row["Responsable"]))
            n_tel = c2.text_input("Téléphone", value=str(row["Téléphone"]))
            n_srv = c1.text_input("Services", value=str(row["Services"]))
            n_prd = c2.text_input("Produits", value=str(row["Produits"]))
            n_prix = c1.number_input("Prix (MAD)", value=to_float(row[price_col]), step=50.0)
            n_jp = c2.text_input("Jour de paiement", value=str(row["Jour de paiement"]))

            b1, b2 = st.columns(2)
            if b1.form_submit_button("💾 Enregistrer les modifications"):
                df_clients.loc[idx, "Résidence"] = n_res
                df_clients.loc[idx, "Secteur"] = n_sec
                df_clients.loc[idx, "Responsable"] = n_resp
                df_clients.loc[idx, "Téléphone"] = n_tel
                df_clients.loc[idx, "Services"] = n_srv
                df_clients.loc[idx, "Produits"] = n_prd
                df_clients.loc[idx, price_col] = str(n_prix)
                df_clients.loc[idx, "Jour de paiement"] = n_jp
                save_sheet(sh, "Clients", df_clients)
                st.success("Modifications enregistrées !")
                st.rerun()

            if b2.form_submit_button("🗑️ Supprimer ce client"):
                df_clients = df_clients.drop(idx).reset_index(drop=True)
                save_sheet(sh, "Clients", df_clients)
                st.warning(f"Client '{client_sel}' supprimé.")
                st.rerun()

# ==========================================
# PAGE 5 : FINANCES & TRÉSORERIE
# ==========================================
elif menu == "💰 Finances & Trésorerie":
    st.title("💰 Finances & Trésorerie")

    entrees = df_fin[df_fin["Type"] == "Entrée"]["Montant (MAD)"].apply(to_float).sum() if not df_fin.empty else 0.0
    sorties = df_fin[df_fin["Type"] == "Sortie"]["Montant (MAD)"].apply(to_float).sum() if not df_fin.empty else 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("📈 Total Entrées", f"{entrees:,.2f} MAD")
    c2.metric("📉 Total Sorties", f"{sorties:,.2f} MAD")
    c3.metric("🏦 Solde Net", f"{entrees - sorties:,.2f} MAD")

    with st.form("add_finance"):
        st.subheader("Nouvelle opération")
        fc1, fc2, fc3 = st.columns(3)
        f_date = fc1.date_input("Date", value=date.today())
        f_type = fc2.selectbox("Type", ["Entrée", "Sortie"])
        f_cat = fc3.selectbox("Catégorie", ["Abonnement Client", "Fin de Chantier", "Salaires", "Produits & Matériel", "Transport", "Autre"])
        f_montant = st.number_input("Montant (MAD)", min_value=0.0, step=50.0)
        f_desc = st.text_input("Description")
        if st.form_submit_button("💾 Ajouter l'opération"):
            ws_fin = sh.worksheet("Finances")
            ws_fin.append_row([f_date.strftime("%Y-%m-%d"), f_type, f_cat, str(f_montant), f_desc])
            st.success("Opération enregistrée !")
            st.rerun()

    st.divider()
    if not df_fin.empty:
        st.dataframe(df_fin.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)

# ==========================================
# PAGE 6 : GÉNÉRER REÇU
# ==========================================
elif menu == "🧾 Générer Reçu":
    st.title("🧾 Générer un Reçu de Paiement (PDF)")
    clients_list = df_clients["Résidence"].tolist() if not df_clients.empty else []
    c_recu = st.selectbox("Client / Résidence", clients_list + ["Autre"])
    if c_recu == "Autre":
        c_recu = st.text_input("Nom du client")
    m_recu = st.text_input("Mois / Période", value=date.today().strftime("%B %Y"))
    default_m = to_float(df_clients[df_clients["Résidence"] == c_recu][price_col].values[0]) if c_recu in clients_list else 0.0
    montant_r = st.number_input("Montant (MAD)", value=default_m, step=50.0)
    mode_r = st.selectbox("Mode de paiement", ["Espèces", "Virement Bancaire", "Chèque"])
    date_r = st.date_input("Date du reçu", value=date.today())

    if st.button("📥 Générer le Reçu PDF"):
        pdf_bytes = generate_recu_pdf(c_recu, m_recu, montant_r, mode_r, date_r.strftime("%d/%m/%Y"))
        st.download_button("⬇️ Télécharger le Reçu PDF", data=pdf_bytes, file_name=f"Recu_{c_recu}.pdf", mime="application/pdf")

# ==========================================
# PAGE 7 : GÉNÉRER DEVIS
# ==========================================
elif menu == "📄 Générer Devis":
    st.title("📄 Générer un Devis (PDF)")
    c1, c2 = st.columns(2)
    num_d = c1.text_input("N° Devis", value=f"DEV-{date.today().strftime('%Y-%m')}-001")
    cli_d = c2.text_input("Nom du Client / Société")
    ice_d = c1.text_input("ICE Client (optionnel)")
    lieu_d = c2.text_input("Lieu du chantier", value="Kénitra")
    desc_d = st.text_area("Détail des prestations", value="Nettoyage complet de fin de chantier...")
    ttc_d = st.number_input("Montant Total TTC (MAD)", min_value=0.0, value=5000.0, step=100.0)
    val_d = st.number_input("Validité (jours)", min_value=1, value=30)

    if st.button("📥 Générer le Devis PDF"):
        pdf_bytes = generate_devis_pdf(num_d, cli_d, ice_d, lieu_d, desc_d, ttc_d, val_d)
        st.download_button("⬇️ Télécharger le Devis PDF", data=pdf_bytes, file_name=f"Devis_{num_d}.pdf", mime="application/pdf")

# ==========================================
# PAGE 8 : GÉNÉRER FACTURE (CGI 2026 + RAS TVA)
# ==========================================
elif menu == "📑 Générer Facture":
    st.title("📑 Générer une Facture Légale (CGI 2026)")
    c1, c2 = st.columns(2)
    num_f = c1.text_input("N° Facture", value=f"FAC-{date.today().year}-001")
    cli_f = c2.text_input("Client / Société")
    ice_f = c1.text_input("ICE Client (obligatoire B2B)")
    adr_f = c2.text_input("Adresse / Ville Client", value="Kénitra")
    desc_f = st.text_area("Désignation de la prestation", value="Nettoyage approfondi de fin de chantier")

    fc1, fc2, fc3 = st.columns(3)
    ttc_f = fc1.number_input("Montant Total TTC (MAD)", min_value=0.0, value=7000.0, step=100.0)
    acompte_f = fc2.number_input("Acompte déjà reçu (MAD)", min_value=0.0, value=0.0, step=100.0)
    ras_option = fc3.selectbox("Retenue à la source (RAS TVA)", ["Aucune (0%)", "75% (Avec Attestation)", "100% (Sans Attestation)"])
    mode_f = st.selectbox("Mode de paiement du solde", ["Virement Bancaire", "Chèque", "Espèces"])

    ras_taux = 75 if "75%" in ras_option else (100 if "100%" in ras_option else 0)
    ht_calc = round(ttc_f / 1.20, 2)
    tva_calc = round(ttc_f - ht_calc, 2)
    ras_calc = round(tva_calc * (ras_taux / 100.0), 2)
    reste_calc = round(ttc_f - ras_calc - acompte_f, 2)

    st.info(f"**Aperçu :** HT = {ht_calc:,.2f} MAD | TVA 20% = {tva_calc:,.2f} MAD | RAS TVA = {ras_calc:,.2f} MAD | **Reste à encaisser = {reste_calc:,.2f} MAD**")

    if st.button("📥 Générer la Facture PDF"):
        pdf_bytes = generate_facture_pdf(num_f, cli_f, ice_f, adr_f, desc_f, ttc_f, acompte_f, ras_taux, mode_f)
        st.download_button("⬇️ Télécharger la Facture PDF", data=pdf_bytes, file_name=f"Facture_{num_f}.pdf", mime="application/pdf")

# ==========================================
# PAGE 9 : GESTION D'ÉQUIPE
# ==========================================
elif menu == "👷 Gestion d'Équipe":
    st.title("👷 Gestion de l'Équipe")
    with st.form("add_emp"):
        c1, c2, c3 = st.columns(3)
        e_nom = c1.text_input("Nom complet *")
        e_tel = c2.text_input("Téléphone")
        e_poste = c3.text_input("Poste", value="Agent de nettoyage")
        if st.form_submit_button("➕ Ajouter l'employé"):
            if e_nom.strip():
                ws_emp = sh.worksheet("Employes")
                ws_emp.append_row([e_nom.strip(), e_tel.strip(), e_poste.strip(), ""])
                st.success(f"Employé {e_nom} ajouté !")
                st.rerun()

    if not df_emp.empty:
        st.dataframe(df_emp[["Nom", "Téléphone", "Poste"]], use_container_width=True, hide_index=True)

# ==========================================
# PAGE 10 : PLANNING
# ==========================================
elif menu == "📅 Planning":
    st.title("📅 Planning Hebdomadaire")

    emps_list = df_emp["Nom"].tolist() if not df_emp.empty else []
    res_list = ["-"] + (df_clients["Résidence"].tolist() if not df_clients.empty else [])

    with st.form("edit_planning"):
        st.subheader("Ajouter / Modifier une ligne du Planning")
        pc1, pc2 = st.columns(2)
        p_emp = pc1.selectbox("Employé", emps_list if emps_list else ["Employé 1"])
        p_jour = pc2.selectbox("Jour", JOURS_SEMAINE)
        ps1, ps2, ps3 = st.columns(3)
        s1 = ps1.selectbox("Créneau 1 (Matin)", res_list)
        s2 = ps2.selectbox("Créneau 2 (Midi)", res_list)
        s3 = ps3.selectbox("Créneau 3 (Soir)", res_list)

        if st.form_submit_button("💾 Enregistrer dans le Planning"):
            mask = (df_plan["Employe"] == p_emp) & (df_plan["Jour"] == p_jour)
            if mask.any():
                df_plan.loc[mask, ["Slot1", "Slot2", "Slot3"]] = [s1, s2, s3]
            else:
                new_p = pd.DataFrame([{"Employe": p_emp, "Jour": p_jour, "Slot1": s1, "Slot2": s2, "Slot3": s3}])
                df_plan = pd.concat([df_plan, new_p], ignore_index=True)
            save_sheet(sh, "Planning", df_plan)
            st.success("Planning mis à jour !")
            st.rerun()

    st.divider()
    if not df_plan.empty:
        st.dataframe(df_plan, use_container_width=True, hide_index=True)
        if st.button("📥 Exporter le Planning en PDF (avec Secteurs)"):
            pdf_p = generate_planning_pdf(df_plan, df_clients)
            st.download_button("⬇️ Télécharger Planning PDF", data=pdf_p, file_name="Planning_ImmoClean.pdf", mime="application/pdf")
