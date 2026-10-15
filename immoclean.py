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

# --- دالة تنظيف أرقام الهاتف من + و = باش ما يطلعش #ERROR! فـ Google Sheets ---
def nettoyer_texte_gsheet(val):
    s = str(val).strip()
    if s.startswith("+") or s.startswith("="):
        return s.lstrip("+=").strip()
    return s

# --- دوال جلب وحفظ البيانات ---
def load_data(sheet_name, columns):
    ws = sh.worksheet(sheet_name)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    # تحويل عمود الهاتف دائماً إلى نص باش يتعدل بسهولة
    if "Téléphone" in df.columns:
        df["Téléphone"] = df["Téléphone"].astype(str)
    return df

def save_data(sheet_name, df):
    ws = sh.worksheet(sheet_name)
    df_clean = df.copy()
    if "Téléphone" in df_clean.columns:
        df_clean["Téléphone"] = df_clean["Téléphone"].apply(nettoyer_texte_gsheet)
    ws.clear()
    set_with_dataframe(ws, df_clean)

# --- دالة حساب عدد الحصص المستهدفة فالشهر لكل إقامة ---
def calculer_cible_passages(services_str):
    s = str(services_str).lower()
    if "30/mois" in s or "7j/7" in s:
        return 30
    elif "26/mois" in s or "6j/7" in s or "tous les jours" in s or "quotidien" in s:
        return 26
    elif "3 fois" in s or "12/mois" in s:
        return 12
    elif "2 fois" in s or "8/mois" in s:
        return 8
    elif "2/mois" in s or "15 jours" in s:
        return 2
    else:
        return 4

# --- أسماء الأعمدة في كل ورقة ---
COLS_CLIENTS = ["Résidence", "Secteur", "Responsable", "Téléphone", "Services", "Produits", "Prix (MAD)", "Jour de paiement"]
COLS_HIST = ["Date", "Résidence", "Employé", "Tâches", "Statut"]
COLS_EMP = ["Nom", "Téléphone", "Poste", "Photo"]
COLS_FIN = ["Date", "Type", "Categorie", "Montant (MAD)", "Description", "Paye_Par"]
COLS_PLAN = ["Employe", "Client", "Jour", "Heure_Debut", "Heure_Fin", "Date_Debut", "Frequence", "Couleur", "Statut"]

# --- 🚨 دوال رادار تداخل الأوقات (Détecteur de Conflits) 🚨 ---
def verifier_conflit_ajout(df_plan, emp, jour, h_deb, h_fin, d_deb, freq):
    if df_plan.empty:
        return False, ""
    
    emp_tasks = df_plan[df_plan["Employe"] == emp]
    for _, row in emp_tasks.iterrows():
        if str(row.get("Frequence", "")) == "Exception":
            continue
            
        r_jour = str(row.get("Jour", ""))
        match_jour = (
            r_jour == jour or 
            r_jour in ["Tous les jours", "Tous les jours (Sauf Dimanche)"] or 
            jour in ["Tous les jours", "Tous les jours (Sauf Dimanche)"]
        )
        if (r_jour == "Tous les jours (Sauf Dimanche)" and jour == "Dimanche") or (jour == "Tous les jours (Sauf Dimanche)" and r_jour == "Dimanche"):
            match_jour = False

        if match_jour:
            try:
                r_deb = datetime.datetime.strptime(str(row["Heure_Debut"]), "%H:%M").time()
                r_fin = datetime.datetime.strptime(str(row["Heure_Fin"]), "%H:%M").time()
                
                if (h_deb < r_fin) and (h_fin > r_deb):
                    r_freq = str(row.get("Frequence", "Chaque semaine"))
                    r_date_deb = datetime.datetime.strptime(str(row["Date_Debut"]), "%Y-%m-%d").date()
                    
                    conflit_semaine = True
                    if freq == "1 semaine sur 2" and r_freq == "1 semaine sur 2":
                        sem1 = d_deb.isocalendar()[1]
                        an1 = d_deb.isocalendar()[0]
                        sem2 = r_date_deb.isocalendar()[1]
                        an2 = r_date_deb.isocalendar()[0]
                        diff = abs((an1 - an2) * 52 + (sem1 - sem2))
                        if diff % 2 != 0:
                            conflit_semaine = False
                            
                    if conflit_semaine:
                        return True, f"⚠️ تداخل فالتوقيت! العاملة **{emp}** عندها ديجا **{row['Client']}** يوم **{r_jour}** من **{row['Heure_Debut']}** إلى **{row['Heure_Fin']}** ({r_freq})."
            except:
                pass
    return False, ""

def verifier_conflit_report(df_plan, emp, date_cible, h_deb, h_fin):
    if df_plan.empty:
        return False, ""
        
    jours_fr = {0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"}
    nom_jour = jours_fr[date_cible.weekday()]
    date_str = date_cible.strftime("%Y-%m-%d")
    sem_cible = date_cible.isocalendar()[1]
    an_cible = date_cible.isocalendar()[0]
    
    emp_tasks = df_plan[df_plan["Employe"] == emp]
    for _, row in emp_tasks.iterrows():
        try:
            r_freq = str(row.get("Frequence", "Chaque semaine"))
            r_deb = datetime.datetime.strptime(str(row["Heure_Debut"]), "%H:%M").time()
            r_fin = datetime.datetime.strptime(str(row["Heure_Fin"]), "%H:%M").time()
            
            if not ((h_deb < r_fin) and (h_fin > r_deb)):
                continue
                
            if r_freq == "Exception":
                if str(row.get("Date_Debut", "")) == date_str:
                    return True, f"⚠️ تداخل! **{emp}** عندها ديجا حصة مؤجلة ديال **{row['Client']}** فهاد التاريخ من **{row['Heure_Debut']}** لـ **{row['Heure_Fin']}**."
                continue
                
            r_jour = str(row.get("Jour", ""))
            jour_actif = (
                r_jour == nom_jour or 
                r_jour == "Tous les jours" or 
                (r_jour == "Tous les jours (Sauf Dimanche)" and nom_jour != "Dimanche")
            )
            if jour_actif:
                verif_rep = df_plan[(df_plan["Frequence"] == "Exception") & (df_plan["Client"] == row["Client"]) & (df_plan["Statut"] == f"Report:{date_str}")]
                if not verif_rep.empty:
                    continue
                    
                d_deb_row = datetime.datetime.strptime(str(row["Date_Debut"]), "%Y-%m-%d").date()
                diff_sem = (an_cible - d_deb_row.isocalendar()[0]) * 52 + (sem_cible - d_deb_row.isocalendar()[1])
                if diff_sem >= 0:
                    if r_freq == "Chaque semaine" or (r_freq == "1 semaine sur 2" and diff_sem % 2 == 0) or (r_freq == "1 fois par mois" and diff_sem % 4 == 0):
                        return True, f"⚠️ تداخل! **{emp}** عندها **{row['Client']}** يوم **{nom_jour} ({date_cible.strftime('%d/%m')})** من **{row['Heure_Debut']}** لـ **{row['Heure_Fin']}**."
        except:
            pass
    return False, ""

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

# ==========================================
# 1. Tableau de bord
# ==========================================
if menu == "Tableau de bord":
    st.header("📊 Tableau de bord (نظرة عامة)")
    
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_emp = load_data("Employes", COLS_EMP)
    df_hist = load_data("Historique", COLS_HIST)
    df_fin = load_data("Finances", COLS_FIN)
    
    secteurs_dict = {}
    if not df_clients.empty:
        for _, r_c in df_clients.iterrows():
            secteurs_dict[str(r_c["Résidence"])] = str(r_c.get("Secteur", "")).strip()
    
    total_clients = len(df_clients) if not df_clients.empty else 0
    total_employes = len(df_emp) if not df_emp.empty else 0
    
    # حساب مجموع الأموال في العقود الشهرية (Total Contrats)
    total_contrats_mad = 0
    if not df_clients.empty and "Prix (MAD)" in df_clients.columns:
        total_contrats_mad = pd.to_numeric(df_clients["Prix (MAD)"], errors='coerce').fillna(0).sum()
    
    residences_a_facturer = 0
    clients_en_retard = []
    
    if not df_clients.empty and not df_hist.empty:
        for _, row in df_clients.iterrows():
            client = str(row["Résidence"]).strip()
            cible = calculer_cible_passages(row.get("Services", ""))
            
            passages_non_payes = len(df_hist[(df_hist["Résidence"].astype(str).str.strip() == client) & (df_hist["Statut"] == "En attente")])
            if passages_non_payes >= cible:
                residences_a_facturer += 1
                clients_en_retard.append(client)

    total_revenus = pd.to_numeric(df_fin[df_fin["Type"] == "Entrée (Revenu)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    total_depenses = pd.to_numeric(df_fin[df_fin["Type"] == "Sortie (Dépense)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    solde_net = total_revenus - total_depenses
    
    # عرض البطاقات الخمسة الفوق
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric(label="🏢 إجمالي الإقامات", value=f"{total_clients}")
    with col2: st.metric(label="📜 قيمة العقود الشهرية", value=f"{total_contrats_mad:,.0f} MAD")
    with col3: st.metric(label="🚨 واجب استخلاصها", value=f"{residences_a_facturer}")
    with col4: st.metric(label="💰 المداخيل المستلمة", value=f"{total_revenus:,.0f} MAD")
    with col5: st.metric(label="💎 الصافي (Solde Net)", value=f"{solde_net:,.0f} MAD")
    
    # تنبيه أحمر بارز للإقامات اللي وصلات لوقت الخلاص
    if clients_en_retard:
        st.markdown(f"""
        <div style="background-color: #ffebee; border-left: 6px solid #d32f2f; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h4 style="color: #c62828 !important; margin: 0;">🚨 تنبيه الأداء: إقامات وصلت لوقت الخلاص!</h4>
            <p style="color: #b71c1c; font-size: 16px; font-weight: bold; margin: 5px 0 0 0;">🏢 {'  |  🏢 '.join(clients_en_retard)}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    # --- جدول الإقامات المتعاقد معها مع تلوين الإقامات اللي وصل خلاصها بالأحمر ---
    with st.expander("🏢 جدول جميع الإقامات المتعاقد معها (الإقامات باللون الأحمر وصل وقت خلاصها 🚨)", expanded=True):
        if not df_clients.empty:
            df_cl_display = df_clients.copy()
            df_cl_display["Prix (MAD)"] = pd.to_numeric(df_cl_display["Prix (MAD)"], errors='coerce').fillna(0)
            
            # إنشاء سطر المجموع في آخر الجدول
            total_row = pd.DataFrame({
                "Résidence": ["💰 المجموع الإجمالي للعقود (TOTAL)"],
                "Secteur": [f"{total_clients} إقامات"],
                "Responsable": ["—"],
                "Téléphone": ["—"],
                "Services": ["—"],
                "Produits": ["—"],
                "Prix (MAD)": [total_contrats_mad],
                "Jour de paiement": ["شهرياً (Par mois)"]
            })
            
            df_cl_avec_total = pd.concat([df_cl_display, total_row], ignore_index=True)
            
            # دالة تلوين السطور: الأحمر للإقامات اللي وصل خلاصها، والأخضر لسطر المجموع
            def colorer_lignes_clients(row):
                nom_r = str(row["Résidence"]).strip()
                if nom_r in clients_en_retard:
                    return ['background-color: #ffcdd2; color: #b71c1c; font-weight: bold;'] * len(row)
                elif "TOTAL" in nom_r:
                    return ['background-color: #e8f5e9; color: #1b5e20; font-weight: bold;'] * len(row)
                return [''] * len(row)

            styled_df = df_cl_avec_total.style.apply(colorer_lignes_clients, axis=1).format({"Prix (MAD)": "{:,.0f} MAD"})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            st.success(f"💵 **مجموع الأموال الشهرية الثابتة في العقود (MRR):** `{total_contrats_mad:,.2f} MAD / Mois`")
        else:
            st.info("لا توجد إقامات مسجلة حالياً.")

    st.markdown("---")
    st.subheader("📅 برنامج اليوم وغداً (مع الموقع، Pointage وتأجيل الحصص)")
    
    df_plan = load_data("Planning", COLS_PLAN)
    if not df_plan.empty:
        jours_fr = {0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"}
        
        dates_a_afficher = [
            ("اليوم", datetime.date.today()),
            ("غداً", datetime.date.today() + datetime.timedelta(days=1))
        ]
        
        for label, date_cible in dates_a_afficher:
            nom_jour_cible = jours_fr[date_cible.weekday()]
            semaine_cible = date_cible.isocalendar()[1]
            annee_cible = date_cible.isocalendar()[0]
            date_cible_str = str(date_cible)
            
            st.markdown(f"#### 🔹 {label} ({nom_jour_cible} {date_cible.strftime('%d/%m/%Y')})")
            
            taches_jour = []
            for _, row in df_plan.iterrows():
                freq = str(row.get("Frequence", "Chaque semaine"))
                statut_plan = str(row.get("Statut", "Actif"))
                
                if freq == "Exception":
                    if str(row.get("Date_Debut", "")) == date_cible_str:
                        taches_jour.append(row)
                    continue
                
                jour_row = str(row.get("Jour", ""))
                jour_correspond = (
                    jour_row == nom_jour_cible or 
                    jour_row == "Tous les jours" or 
                    (jour_row == "Tous les jours (Sauf Dimanche)" and nom_jour_cible != "Dimanche")
                )
                
                if jour_correspond:
                    try:
                        d_debut = datetime.datetime.strptime(str(row["Date_Debut"]), "%Y-%m-%d").date()
                        sem_debut = d_debut.isocalendar()[1]
                        an_debut = d_debut.isocalendar()[0]
                        diff_semaines = (annee_cible - an_debut) * 52 + (semaine_cible - sem_debut)
                        
                        if diff_semaines >= 0:
                            if freq == "Chaque semaine" or (freq == "1 semaine sur 2" and diff_semaines % 2 == 0) or (freq == "1 fois par mois" and diff_semaines % 4 == 0):
                                taches_jour.append(row)
                    except:
                        pass
                        
            df_jour = pd.DataFrame(taches_jour)
            
            if not df_jour.empty:
                df_jour = df_jour.sort_values(by="Heure_Debut").reset_index(drop=True)
                cols = st.columns(3)
                for index, tache in df_jour.iterrows():
                    couleur = tache.get("Couleur", "#1E88E5")
                    client_nom = tache["Client"]
                    emp_nom = tache["Employe"]
                    freq_tache = str(tache.get("Frequence", ""))
                    statut_tache = str(tache.get("Statut", "Actif"))
                    
                    secteur_client = secteurs_dict.get(str(client_nom), "")
                    secteur_html = f'<div style="font-size: 13px; color: #1E88E5; font-weight: 600; margin-bottom: 5px;">📍 المنطقـة: {secteur_client}</div>' if secteur_client else ""
                    
                    est_reportee = False
                    date_report_vers = ""
                    if freq_tache != "Exception":
                        verif_rep = df_plan[(df_plan["Frequence"] == "Exception") & (df_plan["Client"] == client_nom) & (df_plan["Statut"] == f"Report:{date_cible_str}")]
                        if not verif_rep.empty:
                            est_reportee = True
                            date_report_vers = verif_rep.iloc[0]["Date_Debut"]
                    
                    taches_str = "غير محدد"
                    taches_hist_list = []
                    badge = ""
                    badge_color = "#555"
                    
                    if not df_clients.empty:
                        client_data = df_clients[df_clients["Résidence"] == client_nom]
                        if not client_data.empty:
                            services = str(client_data.iloc[0].get("Services", "")).lower()
                            cible = calculer_cible_passages(services)
                            
                            if not df_hist.empty:
                                passages_non_payes = len(df_hist[(df_hist["Résidence"] == client_nom) & (df_hist["Statut"] == "En attente")])
                            else:
                                passages_non_payes = 0
                            
                            taches_a_faire = []
                            if "escalier" in services: 
                                taches_a_faire.append("الدروج")
                                taches_hist_list.append("Escaliers")
                            if "bureau" in services: 
                                taches_a_faire.append("المكتب")
                                taches_hist_list.append("Bureau")
                            
                            is_debut_cycle = (passages_non_payes % cible == 0)
                            
                            if is_debut_cycle:
                                if "terrasse" in services: 
                                    taches_a_faire.append("السطح")
                                    taches_hist_list.append("Terrasse")
                                if "sous-sol" in services or "parking" in services: 
                                    taches_a_faire.append("الباركينغ")
                                    taches_hist_list.append("Parking")
                                badge = "🌟 حصة شاملة (بداية الشهر)"
                                badge_color = "#E91E63"
                            else:
                                badge = "🧹 حصة عادية"
                                badge_color = "#388E3C"
                                
                            taches_str = " + ".join(taches_a_faire) if taches_a_faire else "تنظيف عادي"
                            taches_hist_str = " + ".join(taches_hist_list) if taches_hist_list else "Escaliers"
                        else:
                            taches_hist_str = "Escaliers"
                    else:
                        taches_hist_str = "Escaliers"
                    
                    if freq_tache == "Exception":
                        badge = "🔄 حصة مؤجلة مبرمجة اليوم"
                        badge_color = "#FF9800"
                    elif est_reportee:
                        badge = f"⏳ مؤجلة إلى يوم {date_report_vers}"
                        badge_color = "#9E9E9E"
                        couleur = "#9E9E9E"
                    
                    with cols[index % 3]:
                        st.markdown(f'''
                        <div style="background-color: white; border-left: 6px solid {couleur}; padding: 15px; border-radius: 8px; box-shadow: 0px 4px 6px rgba(0,0,0,0.05); margin-bottom: 8px; opacity: {'0.6' if est_reportee else '1.0'};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <span style="font-size: 14px; font-weight: bold; color: {couleur}; background-color: {couleur}20; padding: 3px 8px; border-radius: 12px;">🕒 {tache["Heure_Debut"]} - {tache["Heure_Fin"]}</span>
                                <span style="font-size: 14px; font-weight: bold; color: #555;">👩‍🔧 {emp_nom}</span>
                            </div>
                            <div style="font-size: 18px; font-weight: bold; color: #333; margin-bottom: 3px;">🏢 {client_nom}</div>
                            {secteur_html}
                            <div style="font-size: 13px; color: #444; margin-top: 8px; border-top: 1px solid #eee; padding-top: 8px;">
                                <b>المهام المطلوبة:</b> {taches_str} <br>
                                <div style="margin-top: 8px;"><span style="font-size: 11px; background-color: {badge_color}; color: white; padding: 3px 8px; border-radius: 12px;">{badge}</span></div>
                            </div>
                        </div>
                        ''', unsafe_allow_html=True)
                        
                        if not est_reportee:
                            if label == "اليوم":
                                deja_pointe = False
                                if not df_hist.empty:
                                    verif = df_hist[(df_hist["Date"] == date_cible_str) & (df_hist["Résidence"] == client_nom) & (df_hist["Employé"] == emp_nom)]
                                    if not verif.empty:
                                        deja_pointe = True
                                        
                                if deja_pointe:
                                    st.button("✔️ تم إنجاز الحصة اليوم", key=f"done_{label}_{index}_{client_nom}", disabled=True, use_container_width=True)
                                else:
                                    if st.button(f"✅ تأكيد الإنجاز ({client_nom})", key=f"btn_pt_{label}_{index}_{client_nom}", use_container_width=True):
                                        nv_passage = pd.DataFrame({
                                            "Date": [date_cible_str], 
                                            "Résidence": [client_nom], 
                                            "Employé": [emp_nom], 
                                            "Tâches": [taches_hist_str], 
                                            "Statut": ["En attente"]
                                        })
                                        df_hist = pd.concat([df_hist, nv_passage], ignore_index=True)
                                        save_data("Historique", df_hist)
                                        st.success(f"تم تسجيل مرور {client_nom} بنجاح!")
                                        st.rerun()

                            with st.expander("🔄 تأجيل هذه الحصة لليوم آخر"):
                                nv_date_rep = st.date_input("اختر التاريخ الجديد", date_cible + datetime.timedelta(days=1), key=f"d_rep_{label}_{index}")
                                nv_h_deb = st.time_input("وقت البداية", datetime.datetime.strptime(str(tache["Heure_Debut"]), "%H:%M").time(), key=f"hd_rep_{label}_{index}")
                                nv_h_fin = st.time_input("وقت النهاية", datetime.datetime.strptime(str(tache["Heure_Fin"]), "%H:%M").time(), key=f"hf_rep_{label}_{index}")
                                
                                if st.button("تأكيد التأجيل", key=f"btn_rep_{label}_{index}", use_container_width=True):
                                    conflit, msg_err = verifier_conflit_report(df_plan, emp_nom, nv_date_rep, nv_h_deb, nv_h_fin)
                                    if conflit:
                                        st.error(msg_err)
                                    else:
                                        jours_fr_map = {0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"}
                                        nv_excep = pd.DataFrame({
                                            "Employe": [emp_nom],
                                            "Client": [client_nom],
                                            "Jour": [jours_fr_map[nv_date_rep.weekday()]],
                                            "Heure_Debut": [nv_h_deb.strftime("%H:%M")],
                                            "Heure_Fin": [nv_h_fin.strftime("%H:%M")],
                                            "Date_Debut": [str(nv_date_rep)],
                                            "Frequence": ["Exception"],
                                            "Couleur": ["#FF9800"],
                                            "Statut": [f"Report:{date_cible_str}"]
                                        })
                                        df_plan = pd.concat([df_plan, nv_excep], ignore_index=True)
                                        save_data("Planning", df_plan)
                                        st.success(f"تم تأجيل حصة {client_nom} إلى {nv_date_rep}!")
                                        st.rerun()
            else:
                st.info(f"لا توجد حصص مبرمجة لـ {label}.")
    else:
        st.info("جدول Planning فارغ حالياً.")

# ==========================================
# 2. Nouveau Client
# ==========================================
elif menu == "Nouveau Client":
    st.header("🏢 إضافة إقامة جديدة (Nouveau Client)")
    df_clients = load_data("Clients", COLS_CLIENTS)
    
    with st.form("form_nv_client", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            res_nom = st.text_input("🏢 اسم الإقامة (Résidence)")
            secteur = st.text_input("📍 الحي / المنطقة (Secteur - مثال: المعمورة، ميموزا)")
            resp = st.text_input("👤 اسم السانديك (Responsable)")
            tel = st.text_input("📞 رقم الهاتف (مثال: 0661234567 أو 212661234567 بدون +)")
        with c2:
            freq_srv = st.selectbox("🔄 عدد المرات فـ الأسبوع (الوتيرة)", [
                "1 fois/semaine (4/mois)", 
                "2 fois/semaine (8/mois)", 
                "3 fois/semaine (12/mois)",
                "Tous les jours (6j/7 - 26/mois)",
                "Tous les jours (7j/7 - 30/mois)",
                "1 fois/15 jours (2/mois)"
            ])
            zones_srv = st.multiselect("🧹 المرافق المشمولة", ["Escaliers", "Terrasse", "Sous-sol / Parking", "Bureau"], default=["Escaliers"])
            produits = st.selectbox("🧴 مواد النظافة (Produits)", ["Inclus (على حساب الشركة)", "Non inclus (على حساب السانديك)"])
            prix = st.number_input("💰 الثمن الشهري (MAD)", min_value=0, step=50, value=500)
            jour_paie = st.text_input("📅 يوم الأداء أو تاريخ العقد (مثال: Le 5 du mois)")
            
        submit_cl = st.form_submit_button("✅ حفظ الإقامة", use_container_width=True)
        if submit_cl:
            if res_nom:
                srv_str = f"{freq_srv} | {', '.join(zones_srv)}"
                nv_cl = pd.DataFrame({
                    "Résidence": [res_nom],
                    "Secteur": [secteur],
                    "Responsable": [resp],
                    "Téléphone": [nettoyer_texte_gsheet(tel)],
                    "Services": [srv_str],
                    "Produits": [produits],
                    "Prix (MAD)": [prix],
                    "Jour de paiement": [jour_paie]
                })
                df_clients = pd.concat([df_clients, nv_cl], ignore_index=True)
                save_data("Clients", df_clients)
                st.success(f"🎉 تم تسجيل إقامة **{res_nom}** بنجاح!")
            else:
                st.warning("⚠️ المرجو إدخال اسم الإقامة على الأقل.")

# ==========================================
# 3. Gérer les clients
# ==========================================
elif menu == "Gérer les clients":
    st.header("✏️ إدارة وتعديل الزبناء (Gérer les clients)")
    df_clients = load_data("Clients", COLS_CLIENTS)
    
    if not df_clients.empty:
        # --- 1. أداة التعديل السريع والمضمون (ممتازة للهاتف) ---
        with st.expander("📱 تعديل سريع لزبون (سهل ومضمون من الهاتف)", expanded=True):
            liste_res = df_clients["Résidence"].tolist()
            res_a_modifier = st.selectbox("🎯 اختر الإقامة التي تريد تعديل معلوماتها:", liste_res)
            
            if res_a_modifier:
                idx_mod = df_clients[df_clients["Résidence"] == res_a_modifier].index[0]
                row_mod = df_clients.loc[idx_mod]
                
                with st.form("form_modif_rapide"):
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        nv_nom_r = st.text_input("🏢 اسم الإقامة", value=str(row_mod["Résidence"]))
                        nv_sec_r = st.text_input("📍 الحي / المنطقة", value=str(row_mod["Secteur"]))
                        nv_resp_r = st.text_input("👤 اسم السانديك", value=str(row_mod["Responsable"]))
                        nv_tel_r = st.text_input("📞 رقم الهاتف (بدون +)", value=str(row_mod["Téléphone"]))
                    with mc2:
                        nv_srv_r = st.text_input("🧹 الخدمات والوتيرة", value=str(row_mod["Services"]))
                        nv_prod_r = st.text_input("🧴 مواد النظافة", value=str(row_mod["Produits"]))
                        prix_actuel = int(pd.to_numeric(row_mod["Prix (MAD)"], errors='coerce') or 0)
                        nv_prix_r = st.number_input("💰 الثمن الشهري (MAD)", value=prix_actuel, step=50)
                        nv_jour_r = st.text_input("📅 يوم الأداء", value=str(row_mod["Jour de paiement"]))
                        
                    if st.form_submit_button("✅ حفظ تعديلات هذه الإقامة", use_container_width=True):
                        df_clients.at[idx_mod, "Résidence"] = nv_nom_r
                        df_clients.at[idx_mod, "Secteur"] = nv_sec_r
                        df_clients.at[idx_mod, "Responsable"] = nv_resp_r
                        df_clients.at[idx_mod, "Téléphone"] = nettoyer_texte_gsheet(nv_tel_r)
                        df_clients.at[idx_mod, "Services"] = nv_srv_r
                        df_clients.at[idx_mod, "Produits"] = nv_prod_r
                        df_clients.at[idx_mod, "Prix (MAD)"] = nv_prix_r
                        df_clients.at[idx_mod, "Jour de paiement"] = nv_jour_r
                        save_data("Clients", df_clients)
                        st.success(f"✔️ تم تحديث معلومات **{nv_nom_r}** بنجاح!")
                        st.rerun()

        st.markdown("---")
        # --- 2. الجدول الشامل (مع إصلاح عمود الهاتف باش يتعدل مباشرة) ---
        st.subheader("📋 الجدول الشامل لجميع الإقامات")
        st.info("💡 يمكنك أيضاً التعديل مباشرة في الجدول أو مسح سطر، ثم الضغط على **حفظ التعديلات**.")
        
        df_clients["Téléphone"] = df_clients["Téléphone"].astype(str)
        df_clients["Prix (MAD)"] = pd.to_numeric(df_clients["Prix (MAD)"], errors='coerce').fillna(0)
        
        edited_df = st.data_editor(
            df_clients, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Téléphone": st.column_config.TextColumn("📞 Téléphone"),
                "Résidence": st.column_config.TextColumn("🏢 Résidence"),
                "Responsable": st.column_config.TextColumn("👤 Responsable"),
                "Prix (MAD)": st.column_config.NumberColumn("💰 Prix (MAD)", min_value=0, step=50)
            }
        )
        
        total_c = pd.to_numeric(edited_df["Prix (MAD)"], errors='coerce').fillna(0).sum()
        st.markdown(f"#### 💰 المجموع الإجمالي للعقود في الجدول: **`{total_c:,.2f} MAD / Mois`**")
        
        if st.button("💾 حفظ تعديلات الجدول (Enregistrer)", use_container_width=True):
            save_data("Clients", edited_df)
            st.success("✔️ تم تحديث بيانات الزبناء بنجاح!")
            st.rerun()
    else:
        st.info("لا يوجد زبناء حالياً.")

# ==========================================
# 4. Pointage & Paiements
# ==========================================
elif menu == "Pointage & Paiements":
    st.header("💳 تتبع الحصص والخلاص (Pointage & Paiements)")
    
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_emp = load_data("Employes", COLS_EMP)
    df_hist = load_data("Historique", COLS_HIST)
    df_fin = load_data("Finances", COLS_FIN)
    
    tab1, tab2 = st.tabs(["💰 حالة الخلاص (Paiements Syndics)", "📝 تسجيل مرور يدوي (Pointage)"])
    
    with tab1:
        if not df_clients.empty:
            for idx, client_row in df_clients.iterrows():
                nom_res = str(client_row["Résidence"]).strip()
                prix_res = pd.to_numeric(client_row["Prix (MAD)"], errors='coerce') or 0
                cible = calculer_cible_passages(client_row.get("Services", ""))
                
                nb_attente = 0
                if not df_hist.empty:
                    nb_attente = len(df_hist[(df_hist["Résidence"].astype(str).str.strip() == nom_res) & (df_hist["Statut"] == "En attente")])
                
                est_en_retard = (nb_attente >= cible)
                
                # تلوين الخلفية بالأحمر الفاتح إذا وصل وقت الخلاص
                if est_en_retard:
                    st.markdown(f"""
                    <div style="background-color: #ffebee; border: 2px solid #ef5350; padding: 10px 15px; border-radius: 8px; margin-bottom: 5px;">
                        <span style="color: #c62828; font-weight: bold; font-size: 16px;">🚨 {nom_res} ({client_row.get('Secteur', '')}) — وصل وقت الأداء! ({prix_res} MAD)</span>
                    </div>
                    """, unsafe_allow_html=True)

                col_a, col_b, col_c = st.columns([3, 2, 2])
                with col_a:
                    if not est_en_retard:
                        st.markdown(f"**🏢 {nom_res}** ({client_row.get('Secteur', '')}) — *{prix_res} MAD/mois*")
                    pct_p = min(1.0, float(nb_attente / cible)) if cible > 0 else 0.0
                    st.progress(pct_p)
                with col_b:
                    st.write(f"الحصص المنجزة: **{nb_attente} / {cible}**")
                    if est_en_retard:
                        st.markdown("<span style='color:#d32f2f; font-weight:bold;'>🔴 واجب الأداء حالاً!</span>", unsafe_allow_html=True)
                with col_c:
                    if st.button(f"💵 تأكيد استلام {prix_res} DH", key=f"pay_{idx}_{nom_res}", use_container_width=True):
                        if not df_hist.empty:
                            df_hist.loc[(df_hist["Résidence"].astype(str).str.strip() == nom_res) & (df_hist["Statut"] == "En attente"), "Statut"] = "Payé"
                            save_data("Historique", df_hist)
                        
                        nv_rev = pd.DataFrame({
                            "Date": [str(datetime.date.today())],
                            "Type": ["Entrée (Revenu)"],
                            "Categorie": ["خلاص سانديك (Paiement Client)"],
                            "Montant (MAD)": [float(prix_res)],
                            "Description": [f"Règlement de résidence {nom_res} ({nb_attente} passages)"],
                            "Paye_Par": ["Caisse (صندوق الشركة)"]
                        })
                        df_fin = pd.concat([df_fin, nv_rev], ignore_index=True)
                        save_data("Finances", df_fin)
                        st.success(f"✅ تم تسجيل خلاص {nom_res} وإضافته لصندوق الشركة!")
                        st.rerun()
                st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)
        else:
            st.info("أضف إقامات أولاً.")

    with tab2:
        st.subheader("➕ إضافة حصة عمل يدوياً للسجل")
        with st.form("form_pt_manuel"):
            d_pt = st.date_input("📅 التاريخ", datetime.date.today())
            res_list = df_clients["Résidence"].tolist() if not df_clients.empty else []
            emp_list = df_emp["Nom"].tolist() if not df_emp.empty else ["خديجة"]
            
            res_pt = st.selectbox("🏢 الإقامة", res_list)
            emp_pt = st.selectbox("👩‍🔧 العاملة", emp_list)
            taches_pt = st.multiselect("🧹 المهام المنجزة", ["Escaliers", "Terrasse", "Parking", "Bureau"], default=["Escaliers"])
            
            if st.form_submit_button("✅ تسجيل المرور"):
                if res_pt:
                    nv_h = pd.DataFrame({
                        "Date": [str(d_pt)],
                        "Résidence": [res_pt],
                        "Employé": [emp_pt],
                        "Tâches": [" + ".join(taches_pt)],
                        "Statut": ["En attente"]
                    })
                    df_hist = pd.concat([df_hist, nv_h], ignore_index=True)
                    save_data("Historique", df_hist)
                    st.success("تم تسجيل المرور!")
                    st.rerun()
        
        if not df_hist.empty:
            st.dataframe(df_hist.tail(20), use_container_width=True)

# ==========================================
# 5. Finances & Trésorerie (مع ميزانية Driss & Younes)
# ==========================================
elif menu == "Finances & Trésorerie":
    st.header("💰 التسيير المالي وتتبع رأس المال (Finances & Capital)")
    
    df_fin = load_data("Finances", COLS_FIN)
    
    if not df_fin.empty:
        if "Paye_Par" not in df_fin.columns:
            df_fin["Paye_Par"] = "Caisse (صندوق الشركة)"
        df_fin["Paye_Par"] = df_fin["Paye_Par"].replace("", "Caisse (صندوق الشركة)").fillna("Caisse (صندوق الشركة)")
        df_fin["Montant (MAD)"] = pd.to_numeric(df_fin["Montant (MAD)"], errors='coerce').fillna(0)
    else:
        df_fin = pd.DataFrame(columns=COLS_FIN)

    # ----------------------------------------------------------
    # 🏦 1. ميزانية التأسيس المشتركة (10,000 DH : Driss & Younes)
    # ----------------------------------------------------------
    BUDGET_TOTAL = 10000.0
    BUDGET_DRISS_INIT = 5000.0
    BUDGET_YOUNES_INIT = 5000.0

    dep_driss = df_fin[(df_fin["Type"].isin(["Sortie (Dépense)", "Dépense"])) & (df_fin["Paye_Par"] == "Driss")]["Montant (MAD)"].sum()
    dep_younes = df_fin[(df_fin["Type"].isin(["Sortie (Dépense)", "Dépense"])) & (df_fin["Paye_Par"] == "Younes")]["Montant (MAD)"].sum()

    reste_driss = BUDGET_DRISS_INIT - dep_driss
    reste_younes = BUDGET_YOUNES_INIT - dep_younes
    reste_capital_global = reste_driss + reste_younes

    st.subheader("🏦 ميزانية التأسيس المشتركة (10,000 DH)")
    st.info(f"💡 **المتبقي الإجمالي من ميزانية التأسيس (10,000 DH):** `{reste_capital_global:,.2f} MAD`  |  *(مجموع ما تم صرفه من التأسيس: `{(dep_driss + dep_younes):,.2f} MAD`)*")

    col_driss, col_younes = st.columns(2)

    with col_driss:
        st.markdown(f"""
        <div style="background-color: white; padding: 18px; border-radius: 12px; border-top: 5px solid #1E88E5; box-shadow: 0px 4px 10px rgba(0,0,0,0.06);">
            <h3 style="margin-top:0; color: #1E88E5 !important;">👤 ميزانية Driss</h3>
            <div style="font-size: 16px; color: #555; margin-bottom: 6px;">🔹 <b>الرصيد الأولي:</b> <span style="font-weight:bold; color:#000;">5,000.00 MAD</span></div>
            <div style="font-size: 16px; color: #D32F2F; margin-bottom: 10px;">🔻 <b>مجموع ما صرف:</b> - {dep_driss:,.2f} MAD</div>
            <hr style="margin: 10px 0; border-top: 1px solid #eee;">
            <div style="font-size: 20px; font-weight: bold; color: #2E7D32;">✅ المتبقي: {reste_driss:,.2f} MAD</div>
        </div>
        """, unsafe_allow_html=True)
        pct_d = max(0.0, min(1.0, float(reste_driss / BUDGET_DRISS_INIT)))
        st.progress(pct_d)

    with col_younes:
        st.markdown(f"""
        <div style="background-color: white; padding: 18px; border-radius: 12px; border-top: 5px solid #FF8F00; box-shadow: 0px 4px 10px rgba(0,0,0,0.06);">
            <h3 style="margin-top:0; color: #FF8F00 !important;">👤 ميزانية Younes</h3>
            <div style="font-size: 16px; color: #555; margin-bottom: 6px;">🔹 <b>الرصيد الأولي:</b> <span style="font-weight:bold; color:#000;">5,000.00 MAD</span></div>
            <div style="font-size: 16px; color: #D32F2F; margin-bottom: 10px;">🔻 <b>مجموع ما صرف:</b> - {dep_younes:,.2f} MAD</div>
            <hr style="margin: 10px 0; border-top: 1px solid #eee;">
            <div style="font-size: 20px; font-weight: bold; color: #2E7D32;">✅ المتبقي: {reste_younes:,.2f} MAD</div>
        </div>
        """, unsafe_allow_html=True)
        pct_y = max(0.0, min(1.0, float(reste_younes / BUDGET_YOUNES_INIT)))
        st.progress(pct_y)

    st.markdown("---")

    # ----------------------------------------------------------
    # 📊 2. ملخص صندوق الشركة العام (Caisse & Opérations)
    # ----------------------------------------------------------
    total_entrees = df_fin[df_fin["Type"] == "Entrée (Revenu)"]["Montant (MAD)"].sum()
    total_sorties = df_fin[df_fin["Type"] == "Sortie (Dépense)"]["Montant (MAD)"].sum()
    solde_caisse = total_entrees - total_sorties

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("💵 إجمالي المداخيل (Entrées)", f"{total_entrees:,.2f} MAD")
    with c2: st.metric("💸 إجمالي المصاريف (Sorties)", f"{total_sorties:,.2f} MAD")
    with c3: st.metric("💎 الصافي العام (Solde Net)", f"{solde_caisse:,.2f} MAD")

    st.markdown("---")

    # ----------------------------------------------------------
    # ➕ 3. إضافة عملية مالية جديدة (مصروف أو مدخول)
    # ----------------------------------------------------------
    st.subheader("➕ تسجيل عملية مالية جديدة")
    with st.form("form_ajout_finance", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            date_f = st.date_input("📅 التاريخ", datetime.date.today())
            type_f = st.selectbox("🔄 نوع العملية", ["Sortie (Dépense)", "Entrée (Revenu)"])
            montant_f = st.number_input("💰 المبلغ (MAD)", min_value=0.0, step=50.0)
        with f_col2:
            cat_f = st.selectbox("📂 الفئة (Catégorie)", [
                "إعلانات وتسويق (Ads / Flyers)",
                "مواد ومعدات النظافة (Produits)",
                "أجور العاملات (Salaires)",
                "خلاص سانديك (Paiement Client)",
                "تنقل ومازوط (Transport)",
                "أوراق وإدارة (Administratif)",
                "أخرى (Autre)"
            ])
            paye_par_f = st.selectbox(
                "💳 شكون خلص؟ (المصدر)", 
                ["Driss", "Younes", "Caisse (صندوق الشركة)"],
                help="اختار Driss أو Younes باش يتنقص المبلغ مباشرة من 5000 درهم ديالو. إيلا كان مدخول أو تخلص من فلوس الكليان، اختار Caisse."
            )
            desc_f = st.text_input("📝 الوصف (مثال: إعلان فيسبوك / شراء سطولا وجافيل...)")

        submit_f = st.form_submit_button("✅ حفظ العملية", use_container_width=True)
        if submit_f:
            if montant_f > 0:
                source_finale = "Caisse (صندوق الشركة)" if type_f == "Entrée (Revenu)" else paye_par_f
                
                nv_fin = pd.DataFrame({
                    "Date": [str(date_f)],
                    "Type": [type_f],
                    "Categorie": [cat_f],
                    "Montant (MAD)": [float(montant_f)],
                    "Description": [desc_f],
                    "Paye_Par": [source_finale]
                })
                df_fin = pd.concat([df_fin, nv_fin], ignore_index=True)
                save_data("Finances", df_fin)
                st.success(f"✔️ تم تسجيل العملية بنجاح! ({montant_f} MAD)")
                st.rerun()
            else:
                st.warning("⚠️ عافاك دخل مبلغ أكبر من 0 درهم.")

    st.markdown("---")

    # ----------------------------------------------------------
    # 📋 4. جدول تتبع العمليات مع الفلتر
    # ----------------------------------------------------------
    st.subheader("📋 سجل الحسابات التفصيلي")
    if not df_fin.empty:
        filtre_p = st.radio("🔍 فلتر حسب المصدر:", ["الكل", "مصاريف Driss", "مصاريف Younes", "Caisse (صندوق الشركة)"], horizontal=True)
        
        df_view = df_fin.copy()
        if filtre_p == "مصاريف Driss":
            df_view = df_view[df_view["Paye_Par"] == "Driss"]
        elif filtre_p == "مصاريف Younes":
            df_view = df_view[df_view["Paye_Par"] == "Younes"]
        elif filtre_p == "Caisse (صندوق الشركة)":
            df_view = df_view[df_view["Paye_Par"] == "Caisse (صندوق الشركة)"]

        st.dataframe(df_view, use_container_width=True)
    else:
        st.info("لا توجد عمليات مسجلة حالياً.")

# ==========================================
# 6. Générer Reçu (PDF)
# ==========================================
elif menu == "Générer Reçu":
    st.header("🧾 استخراج وصل الأداء (Générer Reçu PDF)")
    df_clients = load_data("Clients", COLS_CLIENTS)
    
    res_list = df_clients["Résidence"].tolist() if not df_clients.empty else []
    
    c1, c2 = st.columns(2)
    with c1:
        client_recu = st.selectbox("🏢 اختر الإقامة", res_list) if res_list else st.text_input("🏢 اسم الإقامة")
        mois_recu = st.text_input("📅 شهر الأداء (مثال: Octobre 2026)", datetime.date.today().strftime("%B %Y"))
    with c2:
        default_prix = 500
        if not df_clients.empty and client_recu in df_clients["Résidence"].values:
            default_prix = int(pd.to_numeric(df_clients[df_clients["Résidence"] == client_recu]["Prix (MAD)"].iloc[0], errors='coerce') or 500)
        montant_recu = st.number_input("💰 المبلغ المؤدى (MAD)", value=default_prix, step=50)
        mode_paie = st.selectbox("💳 طريقة الدفع", ["Espèces (نقداً)", "Virement Bancaire (تحويل)", "Chèque (شيك)"])
        
    if st.button("📄 توليد وصل الأداء (PDF)", use_container_width=True):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 20)
        pdf.set_text_color(11, 61, 145)
        pdf.cell(0, 15, "IMMOCLEAN FACILITY", ln=True, align="C")
        
        pdf.set_font("Arial", "", 11)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 7, "Service Professionnel de Nettoyage et d'Entretien des Residences - Kenitra", ln=True, align="C")
        pdf.cell(0, 7, "Tel: 06 49 92 43 54", ln=True, align="C")
        pdf.ln(10)
        
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 12, "RECU DE PAIEMENT", ln=True, align="C", border=1)
        pdf.ln(10)
        
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Date : {datetime.date.today().strftime('%d/%m/%Y')}", ln=True)
        pdf.cell(0, 10, f"Residence : {client_recu.encode('latin-1', 'replace').decode('latin-1')}", ln=True)
        pdf.cell(0, 10, f"Periode : {mois_recu.encode('latin-1', 'replace').decode('latin-1')}", ln=True)
        pdf.cell(0, 10, f"Montant paye : {montant_recu} MAD", ln=True)
        pdf.cell(0, 10, f"Mode de reglement : {mode_paie.split(' ')[0]}", ln=True)
        pdf.ln(15)
        
        pdf.set_font("Arial", "I", 11)
        pdf.cell(0, 10, "Merci pour votre confiance. Direction ImmoClean FACILITY.", ln=True, align="R")
        
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        st.download_button(
            label="📥 تحميل الوصل (Télécharger PDF)",
            data=pdf_bytes,
            file_name=f"Recu_{client_recu}_{mois_recu}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# ==========================================
# 7. Générer Devis (PDF)
# ==========================================
elif menu == "Générer Devis":
    st.header("📑 إنشاء عرض ثمن (Générer Devis PDF)")
    
    c1, c2 = st.columns(2)
    with c1:
        nom_prospect = st.text_input("🏢 اسم الإقامة (Prospect)")
        secteur_prospect = st.text_input("📍 المنطقة / الحي (Kénitra)")
        freq_devis = st.selectbox("🔄 وتيرة النظافة المقترحة", [
            "1 passage par semaine (4/mois)", 
            "2 passages par semaine (8/mois)",
            "3 passages par semaine (12/mois)",
            "Passage quotidien 6j/7 (26/mois)",
            "Passage quotidien 7j/7 (30/mois)"
        ])
    with c2:
        prix_devis = st.number_input("💰 الثمن الشهري المقترح (MAD)", value=600, step=50)
        prod_devis = st.selectbox("🧴 مواد النظافة", ["Produits inclus (A la charge d'ImmoClean)", "Produits non inclus"])
        details_devis = st.text_area("📝 تفاصيل الخدمات", "Nettoyage complet des escaliers, hall d'entree, vitres, ascenseur, ainsi que le lavage du parking et de la terrasse.")
        
    if st.button("📄 توليد Devis (PDF)", use_container_width=True):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 20)
        pdf.set_text_color(11, 61, 145)
        pdf.cell(0, 15, "IMMOCLEAN FACILITY", ln=True, align="C")
        
        pdf.set_font("Arial", "", 11)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 7, "Nettoyage et Entretien des Coproprietes & Residences - Kenitra", ln=True, align="C")
        pdf.cell(0, 7, "Tel: 06 49 92 43 54", ln=True, align="C")
        pdf.ln(10)
        
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 12, "DEVIS / PROPOSITION COMMERCIALE", ln=True, align="C", border=1)
        pdf.ln(10)
        
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 9, f"Date : {datetime.date.today().strftime('%d/%m/%Y')}", ln=True)
        pdf.cell(0, 9, f"Client / Residence : {nom_prospect.encode('latin-1', 'replace').decode('latin-1')} ({secteur_prospect.encode('latin-1', 'replace').decode('latin-1')})", ln=True)
        pdf.cell(0, 9, f"Frequence : {freq_devis.encode('latin-1', 'replace').decode('latin-1')}", ln=True)
        pdf.cell(0, 9, f"Produits : {prod_devis.encode('latin-1', 'replace').decode('latin-1')}", ln=True)
        pdf.ln(5)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 9, "Prestations incluses :", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.multi_cell(0, 8, details_devis.encode('latin-1', 'replace').decode('latin-1'))
        pdf.ln(8)
        
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(11, 61, 145)
        pdf.cell(0, 12, f"Tarif Mensuel Forfaitaire : {prix_devis} MAD / Mois", ln=True, border=1, align="C")
        
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        st.download_button(
            label="📥 تحميل العرض (Télécharger Devis PDF)",
            data=pdf_bytes,
            file_name=f"Devis_ImmoClean_{nom_prospect}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# ==========================================
# 8. Gestion d'Équipe
# ==========================================
elif menu == "Gestion d'Équipe":
    st.header("👩‍🔧 إدارة فريق العمل (Gestion d'Équipe)")
    df_emp = load_data("Employes", COLS_EMP)
    
    with st.form("form_emp", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1: nom_e = st.text_input("👩‍🔧 اسم العاملة / الموظف")
        with c2: tel_e = st.text_input("📞 رقم الهاتف")
        with c3: poste_e = st.text_input("🛠️ المهمة (Poste)", value="Agent de nettoyage")
        
        if st.form_submit_button("➕ إضافة للفريق", use_container_width=True):
            if nom_e:
                nv_e = pd.DataFrame({"Nom": [nom_e], "Téléphone": [nettoyer_texte_gsheet(tel_e)], "Poste": [poste_e], "Photo": [""]})
                df_emp = pd.concat([df_emp, nv_e], ignore_index=True)
                save_data("Employes", df_emp)
                st.success(f"تمت إضافة {nom_e} بنجاح!")
                st.rerun()
                
    if not df_emp.empty:
        st.dataframe(df_emp, use_container_width=True)

# ==========================================
# 9. Planning
# ==========================================
elif menu == "Planning":
    st.header("📅 البرمجة الأسبوعية والرادار الذكي (Planning)")
    
    df_plan = load_data("Planning", COLS_PLAN)
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_emp = load_data("Employes", COLS_EMP)
    
    with st.form("form_plan"):
        st.subheader("➕ برمجة حصة جديدة")
        c1, c2, c3 = st.columns(3)
        with c1:
            emp_p = st.selectbox("👩‍🔧 العاملة", df_emp["Nom"].tolist() if not df_emp.empty else ["خديجة"])
            client_p = st.selectbox("🏢 الإقامة", df_clients["Résidence"].tolist() if not df_clients.empty else [""])
            jour_p = st.selectbox("📆 يوم العمل", [
                "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche", 
                "Tous les jours (Sauf Dimanche)", "Tous les jours"
            ])
        with c2:
            h_deb_p = st.time_input("🕒 وقت البداية", datetime.time(9, 0))
            h_fin_p = st.time_input("🕒 وقت النهاية", datetime.time(11, 0))
            date_deb_p = st.date_input("📅 تاريخ بداية العقد", datetime.date.today())
        with c3:
            freq_p = st.selectbox("🔄 التكرار", ["Chaque semaine", "1 semaine sur 2", "1 fois par mois"])
            couleur_p = st.color_picker("🎨 لون البطاقة", "#1E88E5")
            
        if st.form_submit_button("✅ إضافة للبرنامج (مع فحص التداخل)", use_container_width=True):
            if client_p:
                conflit, msg = verifier_conflit_ajout(df_plan, emp_p, jour_p, h_deb_p, h_fin_p, date_deb_p, freq_p)
                if conflit:
                    st.error(msg)
                else:
                    nv_p = pd.DataFrame({
                        "Employe": [emp_p],
                        "Client": [client_p],
                        "Jour": [jour_p],
                        "Heure_Debut": [h_deb_p.strftime("%H:%M")],
                        "Heure_Fin": [h_fin_p.strftime("%H:%M")],
                        "Date_Debut": [str(date_deb_p)],
                        "Frequence": [freq_p],
                        "Couleur": [couleur_p],
                        "Statut": ["Actif"]
                    })
                    df_plan = pd.concat([df_plan, nv_p], ignore_index=True)
                    save_data("Planning", df_plan)
                    st.success(f"✔️ تمت برمجة **{client_p}** يوم **{jour_p}** بنجاح!")
                    st.rerun()
            else:
                st.warning("المرجو اختيار إقامة.")

    st.markdown("---")
    st.subheader("📋 جدول الحصص المبرمجة (يمكنك التعديل أو الحذف مباشرة)")
    if not df_plan.empty:
        edited_plan = st.data_editor(df_plan, num_rows="dynamic", use_container_width=True)
        if st.button("💾 حفظ تعديلات البلانينغ", use_container_width=True):
            save_data("Planning", edited_plan)
            st.success("✔️ تم تحديث البلانينغ بنجاح!")
            st.rerun()
    else:
        st.info("لا توجد حصص مبرمجة حالياً.")
