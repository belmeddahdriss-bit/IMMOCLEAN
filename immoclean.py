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
COLS_PLAN = ["Employe", "Client", "Jour", "Heure_Debut", "Heure_Fin", "Date_Debut", "Frequence", "Couleur", "Statut"]

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
    clients_en_retard = []
    
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
                clients_en_retard.append(client)

    total_revenus = pd.to_numeric(df_fin[df_fin["Type"] == "Entrée (Revenu)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    total_depenses = pd.to_numeric(df_fin[df_fin["Type"] == "Sortie (Dépense)"]["Montant (MAD)"], errors='coerce').sum() if not df_fin.empty else 0
    solde_net = total_revenus - total_depenses
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric(label="🏢 Total Clients", value=f"{total_clients}")
    with col2: st.metric(label="🚨 Résidences à Facturer", value=f"{residences_a_facturer}")
    with col3: st.metric(label="💰 Total Entrées", value=f"{total_revenus} MAD")
    with col4: st.metric(label="💎 Solde Net (الصافي)", value=f"{solde_net} MAD", delta=f"{solde_net} MAD")
    
    st.markdown("---")
    
    st.subheader("📅 برنامج اليوم وغداً (مع Pointage وتأجيل الحصص)")
    
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
                
                # 1. واش كاينة حصة استثنائية (مؤجلة) مبرمجة لهاد التاريخ بالضبط؟
                if freq == "Exception":
                    if str(row.get("Date_Debut", "")) == date_cible_str:
                        taches_jour.append(row)
                    continue
                
                # 2. الحصص العادية الدورية
                if row["Jour"] == nom_jour_cible or row["Jour"] == "Tous les jours":
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
                    
                    # التحقق واش هاد الحصة تأجلات لشي نهار آخر فهاد السيمانة
                    est_reportee = False
                    date_report_vers = ""
                    if freq_tache != "Exception":
                        verif_rep = df_plan[(df_plan["Frequence"] == "Exception") & (df_plan["Client"] == client_nom) & (df_plan["Statut"] == f"Report:{date_cible_str}")]
                        if not verif_rep.empty:
                            est_reportee = True
                            date_report_vers = verif_rep.iloc[0]["Date_Debut"]
                    
                    # --- الذكاء ديال تحديد المهام (دروج، سطح، باركينغ) ---
                    taches_str = "غير محدد"
                    taches_hist_list = []
                    badge = ""
                    badge_color = "#555"
                    
                    if not df_clients.empty:
                        client_data = df_clients[df_clients["Résidence"] == client_nom]
                        if not client_data.empty:
                            services = str(client_data.iloc[0].get("Services", "")).lower()
                            
                            if "2 fois" in services: cible = 8
                            elif "2/mois" in services or "15 jours" in services: cible = 2
                            else: cible = 4
                            
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
                    # ----------------------------------------------------
                    
                    with cols[index % 3]:
                        st.markdown(f'''
                        <div style="background-color: white; border-left: 6px solid {couleur}; padding: 15px; border-radius: 8px; box-shadow: 0px 4px 6px rgba(0,0,0,0.05); margin-bottom: 8px; opacity: {'0.6' if est_reportee else '1.0'};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <span style="font-size: 14px; font-weight: bold; color: {couleur}; background-color: {couleur}20; padding: 3px 8px; border-radius: 12px;">🕒 {tache["Heure_Debut"]} - {tache["Heure_Fin"]}</span>
                                <span style="font-size: 14px; font-weight: bold; color: #555;">👩‍🔧 {emp_nom}</span>
                            </div>
                            <div style="font-size: 18px; font-weight: bold; color: #333; margin-bottom: 5px;">🏢 {client_nom}</div>
                            <div style="font-size: 13px; color: #444; margin-top: 10px; border-top: 1px solid #eee; padding-top: 8px;">
                                <b>المهام المطلوبة:</b> {taches_str} <br>
                                <div style="margin-top: 8px;"><span style="font-size: 11px; background-color: {badge_color}; color: white; padding: 3px 8px; border-radius: 12px;">{badge}</span></div>
                            </div>
                        </div>
                        ''', unsafe_allow_html=True)
                        
                        # --- أزرار التحكم (لليوم وغدا) ---
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
                                        df_hist_updated = pd.concat([df_hist, nv_passage], ignore_index=True)
                                        save_data("Historique", df_hist_updated)
                                        st.success(f"تم تسجيل الحصة لـ {client_nom} بنجاح!")
                                        st.rerun()
                                    
                                    # خيار تأجيل الحصة لليوم آخر
                                    with st.expander("⏳ تأجيل هاد الحصة ليوم آخر"):
                                        nv_date_rep = st.date_input("اختار التاريخ الجديد:", date_cible + datetime.timedelta(days=2), key=f"d_rep_{label}_{index}")
                                        nv_h_deb = st.time_input("وقت البدء:", value=datetime.datetime.strptime(str(tache["Heure_Debut"]), "%H:%M").time(), key=f"hd_rep_{label}_{index}")
                                        nv_h_fin = st.time_input("وقت الانتهاء:", value=datetime.datetime.strptime(str(tache["Heure_Fin"]), "%H:%M").time(), key=f"hf_rep_{label}_{index}")
                                        
                                        if st.button("💾 تأكيد التأجيل", key=f"btn_rep_{label}_{index}"):
                                            nom_nv_jour = jours_fr[nv_date_rep.weekday()]
                                            nv_exception = pd.DataFrame({
                                                "Employe": [emp_nom],
                                                "Client": [client_nom],
                                                "Jour": [nom_nv_jour],
                                                "Heure_Debut": [nv_h_deb.strftime("%H:%M")],
                                                "Heure_Fin": [nv_h_fin.strftime("%H:%M")],
                                                "Date_Debut": [nv_date_rep.strftime("%Y-%m-%d")],
                                                "Frequence": ["Exception"],
                                                "Couleur": ["#FF9800"],
                                                "Statut": [f"Report:{date_cible_str}"]
                                            })
                                            df_plan_up = pd.concat([df_plan, nv_exception], ignore_index=True)
                                            save_data("Planning", df_plan_up)
                                            st.success(f"تم تأجيل حصة {client_nom} إلى يوم {nom_nv_jour} ({nv_date_rep.strftime('%d/%m')})!")
                                            st.rerun()
                        else:
                            if st.button("↩️ إلغاء التأجيل وإرجاعها لليوم", key=f"cancel_rep_{label}_{index}_{client_nom}", use_container_width=True):
                                df_plan_clean = df_plan[~((df_plan["Frequence"] == "Exception") & (df_plan["Client"] == client_nom) & (df_plan["Statut"] == f"Report:{date_cible_str}"))]
                                save_data("Planning", df_plan_clean)
                                st.success("تم إلغاء التأجيل!")
                                st.rerun()
                        
                        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
            else:
                st.info(f"🎉 ماكاين حتى خدمة مبرمجة لـ {label} ({nom_jour_cible}).")
            
            st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.info("البلانينغ باقي خاوي.")
        
    st.markdown("---")
    st.subheader("📋 Liste des Clients Actifs")
    if not df_clients.empty:
        def color_alerte(row):
            if row['Résidence'] in clients_en_retard:
                return ['background-color: #ffcdd2; color: #b71c1c; font-weight: bold'] * len(row)
            return [''] * len(row)
            
        st.dataframe(df_clients.style.apply(color_alerte, axis=1), use_container_width=True, hide_index=True)
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
