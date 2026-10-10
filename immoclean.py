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
            n_secteur = st.text_input("Secteur", value=str(client_info.get("Secteur", "")))
            n_resp = st.text_input("Responsable (Syndic)", value=str(client_info.get("Responsable", "")))
            n_tel = st.text_input("Téléphone", value=str(client_info.get("Téléphone", "")))
            
            services_list = [
                "Escalier 1 passage par semaine", 
                "Escalier 2 fois par semaine", 
                "Escalier 1 passage tous les 15 jours (2/mois)", 
                "Sous-sol (Parking)", 
                "Terrasse", 
                "Bureau"
            ]
            current_services_str = str(client_info.get("Services", ""))
            current_services = [s.strip() for s in current_services_str.split("+") if s.strip() in services_list]
            n_services = st.multiselect("Type de service", services_list, default=current_services)
            
            produits_options = ["À notre charge", "À la charge du client"]
            current_produit = str(client_info.get("Produits", "À la charge du client"))
            produit_idx = produits_options.index(current_produit) if current_produit in produits_options else 1
            n_produit = st.radio("Les produits de nettoyage :", produits_options, index=produit_idx)
            
            n_prix = st.number_input("Prix (MAD)", value=float(client_info.get("Prix (MAD)", 0.0)))
            
            jour_options = [f"Le {i}" for i in range(1, 32)]
            current_jour = str(client_info.get("Jour de paiement", "Le 1"))
            jour_idx = jour_options.index(current_jour) if current_jour in jour_options else 0
            n_jour = st.selectbox("Jour de paiement préféré:", jour_options, index=jour_idx)
            
            if st.form_submit_button("💾 Enregistrer"):
                df = df.astype(object)
                
                df.loc[df["Résidence"] == client_choisi, "Secteur"] = str(n_secteur)
                df.loc[df["Résidence"] == client_choisi, "Responsable"] = str(n_resp)
                df.loc[df["Résidence"] == client_choisi, "Téléphone"] = str(n_tel)
                df.loc[df["Résidence"] == client_choisi, "Services"] = " + ".join(n_services)
                df.loc[df["Résidence"] == client_choisi, "Produits"] = str(n_produit)
                df.loc[df["Résidence"] == client_choisi, "Prix (MAD)"] = float(n_prix)
                df.loc[df["Résidence"] == client_choisi, "Jour de paiement"] = str(n_jour)
                
                save_data("Clients", df)
                st.success("تم التعديل بنجاح في Google Sheets!")
                st.rerun()
                
        st.markdown("---")
        if st.button("❌ Supprimer le client"):
            df_new = df[df["Résidence"] != client_choisi]
            save_data("Clients", df_new)
            st.success("تم مسح الكليان من قاعدة البيانات!")
            st.rerun()

# --- 4. Pointage & Paiements ---
elif menu == "Pointage & Paiements":
    st.header("🔄 Pointage et Cycle de Paiement الذكي")
    
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_emp = load_data("Employes", COLS_EMP)
    df_hist = load_data("Historique", COLS_HIST)
    
    if df_clients.empty or df_emp.empty:
        st.warning("⚠️ خصك ضروري تدخل الكليان والعمال باش تقدر تسجل الحصص.")
    else:
        st.subheader("1️⃣ تسجيل حصة عمل جديدة (Pointage اليومي)")
        with st.form("form_pointage"):
            col1, col2, col3 = st.columns(3)
            with col1: date_passage = st.date_input("تاريخ الحصة", datetime.date.today())
            with col2: client_choisi = st.selectbox("الإقامة (Résidence)", df_clients["Résidence"].tolist())
            with col3: emp_choisi = st.selectbox("العامل(ة) المكلف(ة)", df_emp["Nom"].tolist())
            
            taches_dict = {
                "Escaliers": "الدروج (Escaliers)",
                "Terrasse": "الترّاس (Terrasse)",
                "Sous-sol": "السوسول (Sous-sol)",
                "Parking": "الباركينغ (Parking)",
                "Bureau": "البيرو (Bureau)",
                "Lavage": "الغسيل / التسييق (Lavage)"
            }
            taches_effectuees = st.multiselect(
                "شنو تنظف فهاد الحصة؟ (Tâches effectuées)",
                options=list(taches_dict.keys()),
                format_func=lambda x: taches_dict[x]
            )
            
            if st.form_submit_button("✅ تأكيد إنجاز الحصة"):
                taches_str = " + ".join(taches_effectuees) if taches_effectuees else "Non specifie"
                nv_passage = pd.DataFrame({
                    "Date": [str(date_passage)], "Résidence": [client_choisi], 
                    "Employé": [emp_choisi], "Tâches": [taches_str], "Statut": ["En attente"]
                })
                df_hist = pd.concat([df_hist, nv_passage], ignore_index=True)
                save_data("Historique", df_hist)
                st.success("تم تسجيل الحصة بنجاح!")
                st.rerun()

        st.markdown("---")
        st.subheader("2️⃣ العداد الذكي وتتبع الخلاص (Compteurs)")
        
        for index, row in df_clients.iterrows():
            client = row["Résidence"]
            services = str(row.get("Services", "")).lower()
            prix_client = float(row.get("Prix (MAD)", 0))
            
            if "2 fois" in services: cible = 8
            elif "2/mois" in services or "15 jours" in services: cible = 2
            else: cible = 4
            
            passages_non_payes = df_hist[(df_hist["Résidence"] == client) & (df_hist["Statut"] == "En attente")]
            nb = len(passages_non_payes)
            
            with st.expander(f"🏢 {client} - العداد: {nb} / {cible} حصص", expanded=(nb >= cible)):
                st.progress(min(nb / cible, 1.0))
                if nb > 0:
                    st.write("**تفاصيل الحصص المنجزة حالياً:**")
                    st.dataframe(passages_non_payes[["Date", "Employé", "Tâches"]], hide_index=True, use_container_width=True)
                else:
                    st.info("العداد مصفر (0 حصص).")
                    
                if nb >= cible:
                    st.error(f"⚠️ الإقامة كملات {nb} حصص. حان وقت استخلاص الفاتورة!")
                    if st.button(f"💰 تأكيد الخلاص وتصفير العداد لـ {client}", key=f"pay_{client}"):
                        df_hist.loc[(df_hist["Résidence"] == client) & (df_hist["Statut"] == "En attente"), "Statut"] = "Payé"
                        save_data("Historique", df_hist)
                        
                        df_fin_ex = load_data("Finances", COLS_FIN)
                        nv_recette = pd.DataFrame({
                            "Date": [str(datetime.date.today())],
                            "Type": ["Entrée (Revenu)"],
                            "Categorie": ["Paiement Client (Abonnement)"],
                            "Montant (MAD)": [prix_client],
                            "Description": [f"Reglement de {client} ({nb} passages)"]
                        })
                        df_fin_final = pd.concat([df_fin_ex, nv_recette], ignore_index=True)
                        save_data("Finances", df_fin_final)
                        
                        st.success(f"تم تسجيل الخلاص وإضافة المبلغ للمداخيل بنجاح!")
                        st.rerun()

# --- 5. Finances & Trésorerie ---
elif menu == "Finances & Trésorerie":
    st.header("💰 Gestion Financière & Trésorerie (المالية والنفقات)")
    
    df_fin = load_data("Finances", COLS_FIN)
    total_rev = pd.to_numeric(df_fin[df_fin["Type"] == "Entrée (Revenu)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    total_dep = pd.to_numeric(df_fin[df_fin["Type"] == "Sortie (Dépense)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    net_solde = total_rev - total_dep
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric(label="📥 Total Entrées (المداخيل)", value=f"{total_rev} MAD")
    with col2: st.metric(label="📤 Total Dépenses (النفقات)", value=f"{total_dep} MAD")
    with col3: st.metric(label="💎 Trésorerie Nette (الصافي في الصندوق)", value=f"{net_solde} MAD", delta=f"{net_solde} MAD")
    
    st.markdown("---")
    st.subheader("➕ إضافة معاملة مالية جديدة")
    with st.form("form_finance"):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: type_mouvement = st.selectbox("نوع المعاملة", ["Entrée (Revenu)", "Sortie (Dépense)"])
        with col_f2: categorie = st.selectbox("الفئة / السبب", ["Paiement Client", "Achat Produits Nettoyage", "Carburant / Transport", "Salaires Employés", "Publicité (Meta Ads)", "Charges / Loyer", "Autre"])
        with col_f3: montant = st.number_input("المبلغ (MAD)", min_value=0.0, step=10.0)
        
        date_operation = st.date_input("تاريخ المعاملة", datetime.date.today())
        description = st.text_input("ملاحظة أو وصف إضافي")
        
        if st.form_submit_button("💾 تسجيل العملية المالية"):
            if montant <= 0:
                st.warning("عافاك دخل مبلغ أكبر من الصفر.")
            else:
                nv_op = pd.DataFrame({"Date": [str(date_operation)], "Type": [type_mouvement], "Categorie": [categorie], "Montant (MAD)": [montant], "Description": [description if description else "-"]})
                df_fin = pd.concat([df_fin, nv_op], ignore_index=True)
                save_data("Finances", df_fin)
                st.success("تم تسجيل العملية المالية في Google Sheets!")
                st.rerun()
                
    st.markdown("---")
    st.subheader("📜 السجل المالي الكامل")
    if not df_fin.empty:
        df_fin_affiche = df_fin.copy()
        df_fin_affiche.index = range(1, len(df_fin_affiche) + 1)
        st.dataframe(df_fin_affiche, use_container_width=True)
        if st.button("🗑️ مسح السجل المالي"):
            save_data("Finances", pd.DataFrame(columns=COLS_FIN))
            st.success("تم مسح السجل المالي بنجاح!")
            st.rerun()
    else:
        st.info("لا توجد أي معاملات مالية مسجلة حالياً.")

# --- 6. Générer Reçu ---
elif menu == "Générer Reçu":
    st.header("📄 Générer un Reçu de Paiement (PDF)")
    df = load_data("Clients", COLS_CLIENTS)
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1: client_choisi = st.selectbox("اختار الكليان (Résidence):", df["Résidence"].tolist())
        with col2: motif_paiement = st.text_input("سبب الأداء:", f"Reglement mensuel / Passages")
        client_info = df[df["Résidence"] == client_choisi].iloc[0]
        
        if st.button("🛠️ Créer le Reçu (توليد PDF)"):
            pdf = FPDF()
            pdf.add_page()
            if os.path.exists("logo.png"): pdf.image("logo.png", 10, 8, 40)
            elif os.path.exists("logo.jpg"): pdf.image("logo.jpg", 10, 8, 40)
            elif os.path.exists("logo.jpeg"): pdf.image("logo.jpeg", 10, 8, 40)
            elif os.path.exists("logo.webp"): pdf.image("logo.webp", 10, 8, 40)
            
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(80)
            pdf.cell(30, 20, 'RECU DE PAIEMENT', 0, 1, 'C')
            
            # مسافة تحت اللوگو
            pdf.ln(25) 
            
            # --- المعلومات القانونية للشركة (Reçu) بدون ICE و RC ---
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 6, "IMMOCLEAN FACILITY S.A.R.L", 0, 1)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 5, "Adresse : JMM 7 RUE MOULAY RACHID APPT 10, 4 EME ETAGE HASSAN, RABAT", 0, 1)
            pdf.cell(0, 5, "Telephone : +212 649 924 354", 0, 1)
            pdf.cell(0, 5, "Email : contact@immoclean.ma", 0, 1)
            
            date_actuelle = datetime.datetime.now().strftime('%Y-%m-%d')
            pdf.cell(0, 5, f"Date de generation : {date_actuelle}", 0, 1)
            pdf.ln(10)
            
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(225, 245, 254)
            pdf.cell(0, 8, " INFORMATIONS DU CLIENT", 0, 1, 'L', 1)
            pdf.set_font("Arial", '', 11)
            pdf.cell(0, 8, f"Residence : {str(client_info['Résidence'])}", 0, 1)
            pdf.cell(0, 8, f"Responsable (Syndic) : {str(client_info['Responsable'])}", 0, 1)
            pdf.cell(0, 8, f"Motif : {motif_paiement}", 0, 1)
            pdf.ln(5)
            
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, " DETAILS DES INTERVENTIONS (HISTORIQUE)", 0, 1, 'L', 1)
            
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(30, 7, "Date", 1, 0, 'C')
            pdf.cell(45, 7, "Employe", 1, 0, 'C')
            pdf.cell(115, 7, "Taches effectuees", 1, 1, 'C')
            
            df_hist = load_data("Historique", COLS_HIST)
            passages_client = df_hist[df_hist["Résidence"] == client_choisi]
            passages_en_attente = passages_client[passages_client["Statut"] == "En attente"]
            
            services_client = str(client_info.get("Services", "")).lower()
            if "2 fois" in services_client: cible = 8
            elif "2/mois" in services_client or "15 jours" in services_client: cible = 2
            else: cible = 4
            
            if passages_en_attente.empty:
                passages_a_afficher = passages_client.tail(cible)
            else:
                passages_a_afficher = passages_en_attente
                
            pdf.set_font("Arial", '', 9)
            if not passages_a_afficher.empty:
                for _, p_row in passages_a_afficher.iterrows():
                    date_p = str(p_row['Date'])
                    emp_p = str(p_row['Employé'])[:20]
                    tach_cleaned = re.sub(r'[^\x00-\x7F]+', '', str(p_row['Tâches']))
                    tach_cleaned = tach_cleaned.replace('()', '').replace('( )', '').strip(' +')
                    if tach_cleaned == "": tach_cleaned = "Non specifie"
                    pdf.cell(30, 7, date_p, 1, 0, 'C')
                    pdf.cell(45, 7, emp_p, 1, 0, 'C')
                    pdf.cell(115, 7, tach_cleaned[:65], 1, 1, 'L')
            else:
                pdf.cell(190, 7, "Aucun passage recemment enregistre.", 1, 1, 'C')
                
            pdf.ln(10)
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 12, f"MONTANT PAYE : {client_info['Prix (MAD)']} MAD", 1, 1, 'C')
            pdf.ln(20)
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, "L'equipe ImmoClean Facility vous remercie pour votre confiance.", 0, 1, 'C')
            nom_fichier_pdf = f"Recu_{client_choisi.replace(' ', '_')}.pdf"
            pdf.output(nom_fichier_pdf)
            with open(nom_fichier_pdf, "rb") as pdf_file:
                st.success("✅ تم تجهيز التوصيل بنجاح!")
                st.download_button(label="📥 Télécharger le Reçu", data=pdf_file, file_name=nom_fichier_pdf, mime="application/pdf")

# --- 6.5. Générer Devis ---
elif menu == "Générer Devis":
    st.header("📝 Générer un Devis (PDF)")
    st.write("صاوب عرض سعر (Devis) احترافي للكليان الجداد أو الحاليين.")
    
    col1, col2 = st.columns(2)
    with col1:
        client_nom = st.text_input("Nom du Client / Résidence (سمية الكليان أو الإقامة)")
        client_adresse = st.text_input("Adresse / Secteur (العنوان)")
    with col2:
        date_devis = st.date_input("Date du devis (تاريخ الدوفي)", datetime.date.today())
        validite = st.selectbox("Durée de validité (مدة الصلاحية)", ["15 jours", "1 mois", "3 mois"])
        
    st.markdown("**Détails de l'offre (تفاصيل الخدمات والأثمنة) :**")
    service_desc = st.text_area("Description des services (مثال: تنظيف الدروج 2 مرات فالسيمانة + الباركينغ)")
    
    col3, col4 = st.columns(2)
    with col3:
        prix_ht = st.number_input("Prix Total HT (MAD) - الثمن بدون ضريبة", min_value=0.0, step=50.0)
    with col4:
        tva = st.selectbox("TVA (الضريبة)", ["0% (Auto-entrepreneur)", "20% (Société)"])
        
    if st.button("🛠️ Générer le Devis (توليد PDF)"):
        if not client_nom or not service_desc:
            st.warning("عافاك دخل سمية الكليان والخدمات المطلوبة باش يتصاوب الدوفي.")
        else:
            def clean_text(text):
                return str(text).encode('latin-1', 'ignore').decode('latin-1')

            c_nom = clean_text(client_nom)
            c_adr = clean_text(client_adresse)
            desc_cleaned = clean_text(service_desc)
            
            taux_tva = 0.20 if "20%" in tva else 0.0
            montant_tva = prix_ht * taux_tva
            prix_ttc = prix_ht + montant_tva
            
            pdf = FPDF()
            pdf.add_page()
            
            # Logo
            if os.path.exists("logo.png"): pdf.image("logo.png", 10, 8, 40)
            elif os.path.exists("logo.jpg"): pdf.image("logo.jpg", 10, 8, 40)
            elif os.path.exists("logo.jpeg"): pdf.image("logo.jpeg", 10, 8, 40)
            elif os.path.exists("logo.webp"): pdf.image("logo.webp", 10, 8, 40)
            
            pdf.set_font("Arial", 'B', 20)
            pdf.cell(80)
            pdf.cell(30, 20, 'DEVIS', 0, 1, 'C')
            
            # مسافة تحت اللوگو
            pdf.ln(25) 
            
            # --- المعلومات القانونية للشركة (Devis) بدون ICE و RC ---
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 6, "IMMOCLEAN FACILITY S.A.R.L", 0, 1)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 5, "Adresse : JMM 7 RUE MOULAY RACHID APPT 10, 4 EME ETAGE HASSAN, RABAT", 0, 1)
            pdf.cell(0, 5, "Telephone : +212 649 924 354", 0, 1)
            pdf.cell(0, 5, "Email : contact@immoclean.ma", 0, 1)
            
            # Devis & Client Info
            pdf.ln(10)
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(95, 8, " INFORMATIONS DU DEVIS", 1, 0, 'L', 1)
            pdf.cell(95, 8, " ADRESSE AU CLIENT", 1, 1, 'L', 1)
            
            pdf.set_font("Arial", '', 10)
            numero_devis = f"DEV-{date_devis.strftime('%Y%m%d')}-{str(abs(hash(c_nom)))[:4]}"
            pdf.cell(95, 7, f" Numero : {numero_devis}", 'L', 0)
            pdf.cell(95, 7, f" Client : {c_nom}", 'L|R', 1)
            
            pdf.cell(95, 7, f" Date : {date_devis.strftime('%Y-%m-%d')}", 'L', 0)
            pdf.cell(95, 7, f" Adresse : {c_adr}", 'L|R', 1)
            
            pdf.cell(95, 7, f" Validite : {validite}", 'L|B', 0)
            pdf.cell(95, 7, "", 'L|R|B', 1)
            
            pdf.ln(10)
            
            # Table Header
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(225, 245, 254)
            pdf.cell(190, 8, " Description des prestations (Details)", 1, 1, 'L', 1)
            
            # Services Description
            pdf.set_font("Arial", '', 10)
            if desc_cleaned.strip() == "": desc_cleaned = "Voir details avec le client"
            pdf.multi_cell(190, 8, desc_cleaned, 1)
            
            pdf.ln(5)
            
            # Totals
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(140, 8, "Total HT", 1, 0, 'R')
            pdf.cell(50, 8, f"{prix_ht:.2f} MAD", 1, 1, 'C')
            
            pdf.cell(140, 8, f"TVA ({tva})", 1, 0, 'R')
            pdf.cell(50, 8, f"{montant_tva:.2f} MAD", 1, 1, 'C')
            
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(140, 10, "TOTAL TTC", 1, 0, 'R', 1)
            pdf.cell(50, 10, f"{prix_ttc:.2f} MAD", 1, 1, 'C', 1)
            
            # Footer
            pdf.ln(20)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 5, "Conditions de paiement : A la signature du contrat ou selon accord.", 0, 1)
            pdf.cell(0, 5, "Bon pour accord (Date et Signature du client) :", 0, 1)
            
            nom_fichier_pdf = f"Devis_{c_nom.replace(' ', '_')}.pdf"
            pdf.output(nom_fichier_pdf)
            with open(nom_fichier_pdf, "rb") as pdf_file:
                st.success("✅ تم تجهيز الـ Devis بنجاح! تقدر تيليشارجيه دابا.")
                st.download_button(label="📥 Télécharger le Devis (PDF)", data=pdf_file, file_name=nom_fichier_pdf, mime="application/pdf")

# --- 7. Gestion d'Équipe ---
elif menu == "Gestion d'Équipe":
    st.header("👥 Gestion de l'Équipe")
    
    with st.expander("➕ Ajouter un employé"):
        with st.form("form_employe"):
            nom_emp = st.text_input("Nom complet")
            tel_emp = st.text_input("Téléphone")
            poste_emp = st.selectbox("Poste", ["Femme de ménage", "Superviseur", "Chauffeur", "Autre"])
            photo_emp = st.file_uploader("Photo", type=["jpg", "jpeg", "png"])
            
            if st.form_submit_button("Ajouter l'employé"):
                if nom_emp:
                    photo_b64 = ""
                    if photo_emp is not None:
                        try:
                            from PIL import Image
                            import io
                            import base64
                            img = Image.open(photo_emp)
                            img.thumbnail((150, 150))
                            img = img.convert("RGB")
                            buffered = io.BytesIO()
                            img.save(buffered, format="JPEG")
                            photo_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        except Exception as e:
                            st.warning("⚠️ وقع مشكل فرفع الصورة، غيتسجل العامل بلا بيها.")
                            
                    nv_employe = pd.DataFrame({"Nom": [nom_emp], "Téléphone": [str(tel_emp)], "Poste": [poste_emp], "Photo": [photo_b64]})
                    df_emp_ex = load_data("Employes", COLS_EMP)
                    df_emp_final = pd.concat([df_emp_ex, nv_employe], ignore_index=True)
                    save_data("Employes", df_emp_final)
                    st.success("تمت إضافة العامل بنجاح في قاعدة البيانات!")
                    st.rerun()
                else: 
                    st.warning("الاسم ضروري.")
    
    df_emp = load_data("Employes", COLS_EMP)
    
    if not df_emp.empty:
        with st.expander("✏️ Modifier ou Supprimer un employé"):
            emp_choisi = st.selectbox("اختار العامل اللي بغيتي تعدل أو تمسح:", df_emp["Nom"].tolist())
            emp_info = df_emp[df_emp["Nom"] == emp_choisi].iloc[0]
            
            with st.form("form_mod_emp"):
                n_nom = st.text_input("Nom complet", value=str(emp_info["Nom"]))
                n_tel = st.text_input("Téléphone", value=str(emp_info.get("Téléphone", "")))
                
                postes = ["Femme de ménage", "Superviseur", "Chauffeur", "Autre"]
                current_poste = str(emp_info.get("Poste", "Autre"))
                poste_idx = postes.index(current_poste) if current_poste in postes else 0
                n_poste = st.selectbox("Poste", postes, index=poste_idx)
                
                n_photo = st.file_uploader("Photo (خليه خاوي إيلا مابغيتيش تبدل التصويرة القديمة)", type=["jpg", "jpeg", "png"])
                
                if st.form_submit_button("💾 Enregistrer les modifications"):
                    df_emp = df_emp.astype(object)
                    
                    df_emp.loc[df_emp["Nom"] == emp_choisi, "Nom"] = str(n_nom)
                    df_emp.loc[df_emp["Nom"] == emp_choisi, "Téléphone"] = str(n_tel)
                    df_emp.loc[df_emp["Nom"] == emp_choisi, "Poste"] = str(n_poste)
                    
                    if n_photo is not None:
                        try:
                            from PIL import Image
                            import io
                            import base64
                            img = Image.open(n_photo)
                            img.thumbnail((150, 150))
                            img = img.convert("RGB")
                            buffered = io.BytesIO()
                            img.save(buffered, format="JPEG")
                            n_photo_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                            df_emp.loc[df_emp["Nom"] == emp_choisi, "Photo"] = n_photo_b64
                        except Exception as e:
                            st.warning("⚠️ وقع مشكل فرفع الصورة الجديدة.")
                            
                    save_data("Employes", df_emp)
                    st.success("تم تعديل معلومات العامل بنجاح!")
                    st.rerun()
            
            st.markdown("---")
            if st.button("❌ Supprimer l'employé"):
                df_emp_new = df_emp[df_emp["Nom"] != emp_choisi]
                save_data("Employes", df_emp_new)
                st.success("تم مسح العامل من قاعدة البيانات!")
                st.rerun()
    
    st.markdown("---")
    st.markdown("### 📋 Liste de l'équipe")
    if not df_emp.empty:
        cols = st.columns(4)
        for index, row in df_emp.iterrows():
            with cols[index % 4]:
                st.markdown("<div style='background-color:white; padding:15px; border-radius:10px; border:1px solid #e0e0e0; text-align:center;'>", unsafe_allow_html=True)
                
                if pd.notna(row.get('Photo')) and str(row['Photo']).strip() != "":
                    try:
                        import base64
                        img_bytes = base64.b64decode(str(row['Photo']))
                        st.image(img_bytes, width=100)
                    except:
                        st.markdown("<h1>👤</h1>", unsafe_allow_html=True)
                else:
                    st.markdown("<h1>👤</h1>", unsafe_allow_html=True)
                    
                st.markdown(f"**{row['Nom']}**")
                st.caption(f"{row['Poste']}")
                st.write(f"📞 {row.get('Téléphone', '')}")
                st.markdown("</div><br>", unsafe_allow_html=True)
    else:
        st.info("Aucun employé enregistré.")

# --- 8. Planning ---
elif menu == "Planning":
    st.header("📅 Planning de la semaine (برنامج الأسبوع)")
    df_emp = load_data("Employes", COLS_EMP)
    df_clients = load_data("Clients", COLS_CLIENTS)
    if df_emp.empty or df_clients.empty:
        st.warning("خاصك تدخل الكليان والعمال أولاً.")
    else:
        femmes_menage = df_emp[df_emp["Poste"] == "Femme de ménage"]["Nom"].tolist()
        if not femmes_menage:
            st.info("ما كاينا حتى 'Femme de ménage' مسجلة.")
        else:
            employe_choisie = st.selectbox("👩‍🔧 اختار العاملة:", femmes_menage)
            tous_clients = df_clients["Résidence"].tolist()
            
            df_plan = load_data("Planning", COLS_PLAN)
            
            st.markdown(f"#### برنامج العمل ديال: **<span style='color:#1E88E5;'>{employe_choisie}</span>**", unsafe_allow_html=True)
            jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
            
            with st.form("form_planning"):
                selections = {}
                activer_slot_3 = st.checkbox("➕ تفعيل خانة حصة ثالثة (Slot 3) في الجدول أسبوعياً")
                
                cols1 = st.columns(4)
                for i, jour in enumerate(jours[:4]):
                    with cols1[i]:
                        st.markdown(f"<div style='background-color:#e1f5fe; padding:8px; border-radius:5px; text-align:center; margin-bottom:10px; color:#0b3d91;'><b>🗓️ {jour}</b></div>", unsafe_allow_html=True)
                        v1, v2, v3 = "", "", ""
                        if not df_plan.empty:
                            row_actuel = df_plan[(df_plan["Employe"] == employe_choisie) & (df_plan["Jour"] == jour)]
                            if not row_actuel.empty:
                                v1 = str(row_actuel["Slot1"].values[0]) if pd.notna(row_actuel["Slot1"].values[0]) else ""
                                v2 = str(row_actuel["Slot2"].values[0]) if pd.notna(row_actuel["Slot2"].values[0]) else ""
                                v3 = str(row_actuel["Slot3"].values[0]) if pd.notna(row_actuel["Slot3"].values[0]) else ""
                                if v1 == "nan": v1 = ""
                                if v2 == "nan": v2 = ""
                                if v3 == "nan": v3 = ""
                                
                        dispo_v1 = [""] + tous_clients
                        dispo_v2 = [""] + tous_clients
                        dispo_v3 = [""] + tous_clients
                        
                        s1 = st.selectbox("حصة 1️⃣", options=dispo_v1, index=dispo_v1.index(v1) if v1 in dispo_v1 else 0, key=f"{jour}_1")
                        s2 = st.selectbox("حصة 2️⃣", options=dispo_v2, index=dispo_v2.index(v2) if v2 in dispo_v2 else 0, key=f"{jour}_2")
                        s3 = ""
                        if activer_slot_3 or v3 != "":
                            s3 = st.selectbox("حصة 3️⃣ (إضافية)", options=dispo_v3, index=dispo_v3.index(v3) if v3 in dispo_v3 else 0, key=f"{jour}_3")
                            
                        selections[jour] = [s1, s2, s3]
                        
                st.write("") 
                cols2 = st.columns(4)
                for i, jour in enumerate(jours[4:]):
                    with cols2[i]:
                        st.markdown(f"<div style='background-color:#e1f5fe; padding:8px; border-radius:5px; text-align:center; margin-bottom:10px; color:#0b3d91;'><b>🗓️ {jour}</b></div>", unsafe_allow_html=True)
                        v1, v2, v3 = "", "", ""
                        if not df_plan.empty:
                            row_actuel = df_plan[(df_plan["Employe"] == employe_choisie) & (df_plan["Jour"] == jour)]
                            if not row_actuel.empty:
                                v1 = str(row_actuel["Slot1"].values[0]) if pd.notna(row_actuel["Slot1"].values[0]) else ""
                                v2 = str(row_actuel["Slot2"].values[0]) if pd.notna(row_actuel["Slot2"].values[0]) else ""
                                v3 = str(row_actuel["Slot3"].values[0]) if pd.notna(row_actuel["Slot3"].values[0]) else ""
                                if v1 == "nan": v1 = ""
                                if v2 == "nan": v2 = ""
                                if v3 == "nan": v3 = ""
                                
                        dispo_v1 = [""] + tous_clients
                        dispo_v2 = [""] + tous_clients
                        dispo_v3 = [""] + tous_clients
                        
                        s1 = st.selectbox("حصة 1️⃣", options=dispo_v1, index=dispo_v1.index(v1) if v1 in dispo_v1 else 0, key=f"{jour}_1_b")
                        s2 = st.selectbox("حصة 2️⃣", options=dispo_v2, index=dispo_v2.index(v2) if v2 in dispo_v2 else 0, key=f"{jour}_2_b")
                        s3 = ""
                        if activer_slot_3 or v3 != "":
                            s3 = st.selectbox("حصة 3️⃣ (إضافية)", options=dispo_v3, index=dispo_v3.index(v3) if v3 in dispo_v3 else 0, key=f"{jour}_3_b")
                            
                        selections[jour] = [s1, s2, s3]
                        
                st.write("")
                if st.form_submit_button("💾 Sauvegarder le Planning (حفظ البرنامج)"):
                    df_plan = df_plan[df_plan["Employe"] != employe_choisie]
                    nouvelles_lignes = []
                    for jour in jours:
                        nouvelles_lignes.append({
                            "Employe": employe_choisie, "Jour": jour,
                            "Slot1": selections[jour][0], "Slot2": selections[jour][1], "Slot3": selections[jour][2]
                        })
                    df_plan = pd.concat([df_plan, pd.DataFrame(nouvelles_lignes)], ignore_index=True)
                    save_data("Planning", df_plan)
                    st.success("تم تسجيل البرنامج الأسبوعي بنجاح في Google Sheets!")
                    st.rerun()
