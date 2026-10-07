import streamlit as st
import pandas as pd
import os
import datetime
import re
from fpdf import FPDF

st.set_page_config(page_title="ImmoClean", page_icon="🏢", layout="wide")

os.makedirs("photos_employes", exist_ok=True)
FICHIER_DONNEES = "clients.csv"
FICHIER_EMPLOYES = "employes.csv"
FICHIER_PLANNING = "planning.csv"
FICHIER_HISTORIQUE = "historique_passages.csv"

# التحقق من الملفات وتحديثها إذا لزم الأمر
if not os.path.exists(FICHIER_DONNEES):
    pd.DataFrame(columns=["Résidence", "Secteur", "Responsable", "Téléphone", "Services", "Produits", "Prix (MAD)", "Jour de paiement"]).to_csv(FICHIER_DONNEES, index=False)
if not os.path.exists(FICHIER_HISTORIQUE):
    pd.DataFrame(columns=["Date", "Résidence", "Employé", "Tâches", "Statut"]).to_csv(FICHIER_HISTORIQUE, index=False)
else:
    df_hist_verif = pd.read_csv(FICHIER_HISTORIQUE)
    if "Tâches" not in df_hist_verif.columns:
        df_hist_verif.insert(3, "Tâches", "Non spécifié")
        df_hist_verif.to_csv(FICHIER_HISTORIQUE, index=False)

if not os.path.exists(FICHIER_EMPLOYES):
    pd.DataFrame(columns=["Nom", "Téléphone", "Poste", "Photo"]).to_csv(FICHIER_EMPLOYES, index=False)

# --- القائمة الجانبية ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    elif os.path.exists("logo.jpg"): st.image("logo.jpg", use_container_width=True)
    elif os.path.exists("logo.jpeg"): st.image("logo.jpeg", use_container_width=True)
    st.markdown("---")
    
    menu = st.radio("Menu principal", [
        "🏢 Accueil (Liste des clients)", 
        "➕ Ajouter un nouveau client",
        "✏️ Modifier / Supprimer un client",
        "🔄 Pointage & Paiements (الحصص والخلاص)", 
        "📄 Générer Reçu (Facture)",
        "👥 Gestion de l'Équipe",
        "📅 Planning Hebdomadaire"
    ])

st.title("ImmoClean FACILITY 🏢")

if menu == "🏢 Accueil (Liste des clients)":
    st.header("Gestion des Clients - Accueil")
    df = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
    if not df.empty: 
        df_affiche = df.copy()
        df_affiche.index = range(1, len(df_affiche) + 1)
        st.dataframe(df_affiche, use_container_width=True)
    else: st.info("الطابلو خاوي حالياً.")

elif menu == "➕ Ajouter un nouveau client":
    st.header("➕ Ajouter un nouveau client")
    with st.form("form_client"):
        residence = st.text_input("Nom de la résidence / Client")
        secteur = st.text_input("Secteur Géographique (ex: Centre Ville, Maamora...)")
        responsable = st.text_input("Nom du responsable (Syndic)")
        telephone = st.text_input("Téléphone")
        services_choisis = st.multiselect("Type de service", ["Escalier 1 passage par semaine", "Escalier 2 fois par semaine", "Sous-sol (Parking)", "Terrasse", "Bureau"])
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
                df_existant = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
                df_final = pd.concat([df_existant, nouveau], ignore_index=True)
                df_final.to_csv(FICHIER_DONNEES, index=False)
                st.success(f"Le client {residence} a été ajouté avec succès !")

elif menu == "✏️ Modifier / Supprimer un client":
    st.header("✏️ Modifier ou Supprimer un client")
    df = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
    if not df.empty:
        client_choisi = st.selectbox("اختار الكليان اللي بغيتي تعدل أو تمسح:", df["Résidence"].tolist())
        client_info = df[df["Résidence"] == client_choisi].iloc[0]
        with st.form("form_modifier"):
            n_secteur = st.text_input("Secteur", value=str(client_info.get("Secteur", "")))
            n_resp = st.text_input("Responsable (Syndic)", value=str(client_info["Responsable"]))
            n_tel = st.text_input("Téléphone", value=str(client_info["Téléphone"]))
            n_prix = st.number_input("Prix (MAD)", value=float(client_info["Prix (MAD)"]))
            if st.form_submit_button("💾 Enregistrer"):
                df.loc[df["Résidence"] == client_choisi, "Secteur"] = str(n_secteur)
                df.loc[df["Résidence"] == client_choisi, "Responsable"] = str(n_resp)
                df.loc[df["Résidence"] == client_choisi, "Téléphone"] = str(n_tel)
                df.loc[df["Résidence"] == client_choisi, "Prix (MAD)"] = float(n_prix)
                df.to_csv(FICHIER_DONNEES, index=False)
                st.success("تم التعديل بنجاح!")
                st.rerun()
        st.markdown("---")
        if st.button("❌ Supprimer le client"):
            df[df["Résidence"] != client_choisi].to_csv(FICHIER_DONNEES, index=False)
            st.success("تم مسح الكليان!")
            st.rerun()

elif menu == "🔄 Pointage & Paiements (الحصص والخلاص)":
    st.header("🔄 Pointage et Cycle de Paiement الذكي")
    
    df_clients = pd.read_csv(FICHIER_DONNEES)
    df_emp = pd.read_csv(FICHIER_EMPLOYES)
    df_hist = pd.read_csv(FICHIER_HISTORIQUE)
    
    if df_clients.empty or df_emp.empty:
        st.warning("⚠️ خصك ضروري تدخل الكليان والعمال باش تقدر تسجل الحصص.")
    else:
        st.subheader("1️⃣ تسجيل حصة عمل جديدة (Pointage اليومي)")
        with st.form("form_pointage"):
            col1, col2, col3 = st.columns(3)
            with col1:
                date_passage = st.date_input("تاريخ الحصة", datetime.date.today())
            with col2:
                client_choisi = st.selectbox("الإقامة (Résidence)", df_clients["Résidence"].tolist())
            with col3:
                emp_choisi = st.selectbox("العامل(ة) المكلف(ة)", df_emp["Nom"].tolist())
            
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
                    "Date": [str(date_passage)],
                    "Résidence": [client_choisi],
                    "Employé": [emp_choisi],
                    "Tâches": [taches_str],
                    "Statut": ["En attente"]
                })
                df_hist = pd.concat([df_hist, nv_passage], ignore_index=True)
                df_hist.to_csv(FICHIER_HISTORIQUE, index=False)
                st.success("تم تسجيل الحصة بنجاح! العداد تزاد فيه نقطة.")
                st.rerun()

        st.markdown("---")
        
        st.subheader("2️⃣ العداد الذكي وتتبع الخلاص (Compteurs)")
        st.write("هنا كيبان ليك شحال من حصة تدارت لكل إقامة. غير يوصل العداد للحد، غيخرج ليك تنبيه باش تتخلص وتصفر العداد.")
        
        for index, row in df_clients.iterrows():
            client = row["Résidence"]
            services = str(row.get("Services", ""))
            
            cible = 8 if "2 fois" in services.lower() else 4
            
            passages_non_payes = df_hist[(df_hist["Résidence"] == client) & (df_hist["Statut"] == "En attente")]
            nb = len(passages_non_payes)
            
            with st.expander(f"🏢 {client} - العداد: {nb} / {cible} حصص", expanded=(nb >= cible)):
                st.progress(min(nb / cible, 1.0))
                
                if nb > 0:
                    st.write("**تفاصيل الحصص المنجزة حالياً:**")
                    df_show = passages_non_payes[["Date", "Employé", "Tâches"]].copy()
                    st.dataframe(df_show, hide_index=True, use_container_width=True)
                else:
                    st.info("العداد مصفر (0 حصص). إما عاد بداو الدورة الجديدة أو كلشي مخلص.")
                    
                if nb >= cible:
                    st.error(f"⚠️ الإقامة كملات {nb} حصص. حان وقت استخلاص الفاتورة!")
                    if st.button(f"💰 لقد استلمت الدفعة! (تأكيد الخلاص وتصفير العداد لـ {client})", key=f"pay_{client}"):
                        df_hist.loc[(df_hist["Résidence"] == client) & (df_hist["Statut"] == "En attente"), "Statut"] = "Payé"
                        df_hist.to_csv(FICHIER_HISTORIQUE, index=False)
                        st.success(f"تم تسجيل الخلاص بنجاح! العداد رجع للزيرو بالنسبة لـ {client}.")
                        st.rerun()

elif menu == "📄 Générer Reçu (Facture)":
    st.header("📄 Générer un Reçu de Paiement (PDF)")
    df = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1: client_choisi = st.selectbox("اختار الكليان (Résidence):", df["Résidence"].tolist())
        with col2: motif_paiement = st.text_input("سبب الأداء أو الشهر (مثلا: Octobre 2026):", f"Reglement mensuel / Passages")
        client_info = df[df["Résidence"] == client_choisi].iloc[0]
        
        if st.button("🛠️ Créer le Reçu (توليد PDF)"):
            pdf = FPDF()
            pdf.add_page()
            if os.path.exists("logo.png"): pdf.image("logo.png", 10, 8, 40)
            elif os.path.exists("logo.jpg"): pdf.image("logo.jpg", 10, 8, 40)
            elif os.path.exists("logo.jpeg"): pdf.image("logo.jpeg", 10, 8, 40)
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(80)
            pdf.cell(30, 20, 'RECU DE PAIEMENT', 0, 1, 'C')
            pdf.ln(15)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, "IMMOCLEAN FACILITY S.A.R.L", 0, 1)
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 5, "Telephone : +212 649 924 354", 0, 1)
            date_actuelle = datetime.datetime.now().strftime('%Y-%m-%d')
            pdf.cell(0, 5, f"Date de generation : {date_actuelle}", 0, 1)
            pdf.ln(10)
            
            # 1. معلومات الكليان
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(225, 245, 254)
            pdf.cell(0, 8, " INFORMATIONS DU CLIENT", 0, 1, 'L', 1)
            pdf.set_font("Arial", '', 11)
            residence_str = str(client_info['Résidence']).encode('latin-1', 'replace').decode('latin-1')
            responsable_str = str(client_info['Responsable']).encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 8, f"Residence : {residence_str}", 0, 1)
            pdf.cell(0, 8, f"Responsable (Syndic) : {responsable_str}", 0, 1)
            motif_str = motif_paiement.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 8, f"Motif du reglement : {motif_str}", 0, 1)
            pdf.ln(5)
            
            # 2. طابلو الحصص (Detail des passages)
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, " DETAILS DES INTERVENTIONS (HISTORIQUE)", 0, 1, 'L', 1)
            
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(30, 7, "Date", 1, 0, 'C')
            pdf.cell(45, 7, "Employe", 1, 0, 'C')
            pdf.cell(115, 7, "Taches effectuees", 1, 1, 'C')
            
            df_hist = pd.read_csv(FICHIER_HISTORIQUE)
            passages_client = df_hist[df_hist["Résidence"] == client_choisi]
            passages_en_attente = passages_client[passages_client["Statut"] == "En attente"]
            
            if passages_en_attente.empty:
                cible = 8 if "2 fois" in str(client_info.get("Services", "")).lower() else 4
                passages_a_afficher = passages_client.tail(cible)
            else:
                passages_a_afficher = passages_en_attente
                
            pdf.set_font("Arial", '', 9)
            if not passages_a_afficher.empty:
                for _, p_row in passages_a_afficher.iterrows():
                    date_p = str(p_row['Date'])
                    emp_p = str(p_row['Employé']).encode('latin-1', 'replace').decode('latin-1')[:20]
                    
                    # الحل النهائي: تنظيف أي حرف عربي لضمان عدم ظهور علامات الاستفهام ????
                    tach_cleaned = re.sub(r'[^\x00-\x7F]+', '', str(p_row['Tâches']))
                    tach_cleaned = tach_cleaned.replace('()', '').replace('( )', '').strip(' +')
                    if tach_cleaned == "":
                        tach_cleaned = "Non specifie"
                    tach_p = tach_cleaned.encode('latin-1', 'replace').decode('latin-1')[:65]
                    
                    pdf.cell(30, 7, date_p, 1, 0, 'C')
                    pdf.cell(45, 7, emp_p, 1, 0, 'C')
                    pdf.cell(115, 7, tach_p, 1, 1, 'L')
            else:
                pdf.cell(190, 7, "Aucun passage recemment enregistre.", 1, 1, 'C')
                
            pdf.ln(10)
            
            # 3. المبلغ الإجمالي
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 12, f"MONTANT PAYE : {client_info['Prix (MAD)']} MAD", 1, 1, 'C')
            pdf.ln(20)
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, "L'equipe ImmoClean Facility vous remercie pour votre confiance.", 0, 1, 'C')
            nom_fichier_pdf = f"Recu_{client_choisi.replace(' ', '_')}.pdf"
            pdf.output(nom_fichier_pdf)
            with open(nom_fichier_pdf, "rb") as pdf_file:
                st.success("✅ تم تجهيز التوصيل بنجاح! طابلو الحصص تضاف للفاكتورة.")
                st.download_button(label="📥 Télécharger le Reçu", data=pdf_file, file_name=nom_fichier_pdf, mime="application/pdf")

elif menu == "👥 Gestion de l'Équipe":
    st.header("👥 Gestion de l'Équipe")
    with st.expander("➕ Ajouter un employé"):
        with st.form("form_employe"):
            nom_emp = st.text_input("Nom complet")
            tel_emp = st.text_input("Téléphone")
            poste_emp = st.selectbox("Poste", ["Femme de ménage", "Superviseur", "Chauffeur", "Autre"])
            photo_emp = st.file_uploader("Photo", type=["jpg", "jpeg", "png"])
            if st.form_submit_button("Ajouter l'employé"):
                if nom_emp:
                    chemin_photo = ""
                    if photo_emp is not None:
                        chemin_photo = f"photos_employes/{nom_emp.replace(' ', '_')}.png"
                        with open(chemin_photo, "wb") as f: f.write(photo_emp.getbuffer())
                    nv_employe = pd.DataFrame({"Nom": [nom_emp], "Téléphone": [str(tel_emp)], "Poste": [poste_emp], "Photo": [chemin_photo]})
                    df_emp_ex = pd.read_csv(FICHIER_EMPLOYES, dtype={"Téléphone": str})
                    df_emp_final = pd.concat([df_emp_ex, nv_employe], ignore_index=True)
                    df_emp_final.to_csv(FICHIER_EMPLOYES, index=False)
                    st.success("تمت إضافة العامل بنجاح!")
                    st.rerun()
                else: st.warning("الاسم ضروري.")
    st.markdown("### 📋 Liste de l'équipe")
    df_emp = pd.read_csv(FICHIER_EMPLOYES, dtype={"Téléphone": str})
    cols = st.columns(4)
    for index, row in df_emp.iterrows():
        with cols[index % 4]:
            st.markdown(f"**{row['Nom']}**")
            st.caption(f"{row['Poste']}")
            photo_path = str(row['Photo'])
            if pd.notna(photo_path) and photo_path != "" and os.path.exists(photo_path):
                st.image(photo_path, width=100)
            else:
                st.info("Pas de photo")
            st.write(f"📞 {row['Téléphone']}")
            st.markdown("---")

elif menu == "📅 Planning Hebdomadaire":
    st.header("📅 Planning de la semaine (برنامج الأسبوع)")
    df_emp = pd.read_csv(FICHIER_EMPLOYES)
    df_clients = pd.read_csv(FICHIER_DONNEES)
    if df_emp.empty or df_clients.empty:
        st.warning("خاصك تدخل الكليان والعمال.")
    else:
        femmes_menage = df_emp[df_emp["Poste"] == "Femme de ménage"]["Nom"].tolist()
        if not femmes_menage:
            st.info("ما كاينا حتى 'Femme de ménage'.")
        else:
            employe_choisie = st.selectbox("👩‍🔧 اختار العاملة:", femmes_menage)
            tous_clients = df_clients["Résidence"].tolist()
            if not os.path.exists(FICHIER_PLANNING):
                pd.DataFrame(columns=["Employe", "Jour", "Slot1", "Slot2", "Slot3"]).to_csv(FICHIER_PLANNING, index=False)
            df_plan = pd.read_csv(FICHIER_PLANNING)
            clients_deja_assignes = []
            if not df_plan.empty:
                clients_deja_assignes = pd.concat([df_plan["Slot1"], df_plan["Slot2"], df_plan["Slot3"]]).dropna().tolist()
            
            st.markdown(f"#### برنامج العمل ديال: **<span style='color:#1E88E5;'>{employe_choisie}</span>**", unsafe_allow_html=True)
            jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
            with st.form("form_planning"):
                selections = {}
                cols1 = st.columns(4)
                for i, jour in enumerate(jours[:4]):
                    with cols1[i]:
                        st.markdown(f"<div style='background-color:#e1f5fe; padding:8px; border-radius:5px; text-align:center; margin-bottom:10px;'><b>🗓️ {jour}</b></div>", unsafe_allow_html=True)
                        v1, v2, v3 = "", "", ""
                        if not df_plan.empty:
                            row_actuel = df_plan[(df_plan["Employe"] == employe_choisie) & (df_plan["Jour"] == jour)]
                            if not row_actuel.empty:
                                v1 = row_actuel["Slot1"].values[0] if pd.notna(row_actuel["Slot1"].values[0]) else ""
                                v2 = row_actuel["Slot2"].values[0] if pd.notna(row_actuel["Slot2"].values[0]) else ""
                                v3 = row_actuel["Slot3"].values[0] if pd.notna(row_actuel["Slot3"].values[0]) else ""
                        dispo_v1 = [""] + [c for c in tous_clients if c not in clients_deja_assignes or c == v1]
                        dispo_v2 = [""] + [c for c in tous_clients if c not in clients_deja_assignes or c == v2]
                        dispo_v3 = [""] + [c for c in tous_clients if c not in clients_deja_assignes or c == v3]
                        s1 = st.selectbox("1️⃣", options=dispo_v1, index=dispo_v1.index(v1) if v1 in dispo_v1 else 0, key=f"{jour}_1")
                        s2 = st.selectbox("2️⃣", options=dispo_v2, index=dispo_v2.index(v2) if v2 in dispo_v2 else 0, key=f"{jour}_2")
                        s3 = st.selectbox("3️⃣", options=dispo_v3, index=dispo_v3.index(v3) if v3 in dispo_v3 else 0, key=f"{jour}_3")
                        selections[jour] = [s1, s2, s3]
                st.write("") 
                cols2 = st.columns(4)
                for i, jour in enumerate(jours[4:]):
                    with cols2[i]:
                        st.markdown(f"<div style='background-color:#e1f5fe; padding:8px; border-radius:5px; text-align:center; margin-bottom:10px;'><b>🗓️ {jour}</b></div>", unsafe_allow_html=True)
                        v1, v2, v3 = "", "", ""
                        if not df_plan.empty:
                            row_actuel = df_plan[(df_plan["Employe"] == employe_choisie) & (df_plan["Jour"] == jour)]
                            if not row_actuel.empty:
                                v1 = row_actuel["Slot1"].values[0] if pd.notna(row_actuel["Slot1"].values[0]) else ""
                                v2 = row_actuel["Slot2"].values[0] if pd.notna(row_actuel["Slot2"].values[0]) else ""
                                v3 = row_actuel["Slot3"].values[0] if pd.notna(row_actuel["Slot3"].values[0]) else ""
                        dispo_v1 = [""] + [c for c in tous_clients if c not in clients_deja_assignes or c == v1]
                        dispo_v2 = [""] + [c for c in tous_clients if c not in clients_deja_assignes or c == v2]
                        dispo_v3 = [""] + [c for c in tous_clients if c not in clients_deja_assignes or c == v3]
                        s1 = st.selectbox("1️⃣", options=dispo_v1, index=dispo_v1.index(v1) if v1 in dispo_v1 else 0, key=f"{jour}_1_b")
                        s2 = st.selectbox("2️⃣", options=dispo_v2, index=dispo_v2.index(v2) if v2 in dispo_v2 else 0, key=f"{jour}_2_b")
                        s3 = st.selectbox("3️⃣", options=dispo_v3, index=dispo_v3.index(v3) if v3 in dispo_v3 else 0, key=f"{jour}_3_b")
                        selections[jour] = [s1, s2, s3]
                st.write("")
                if st.form_submit_button("💾 Sauvegarder le Planning (حفظ)"):
                    df_plan = df_plan[df_plan["Employe"] != employe_choisie]
                    nouvelles_lignes = []
                    for jour in jours:
                        nouvelles_lignes.append({
                            "Employe": employe_choisie, "Jour": jour,
                            "Slot1": selections[jour][0], "Slot2": selections[jour][1], "Slot3": selections[jour][2]
                        })
                    df_plan = pd.concat([df_plan, pd.DataFrame(nouvelles_lignes)], ignore_index=True)
                    df_plan.to_csv(FICHIER_PLANNING, index=False)
                    st.success("تم تسجيل البرنامج الأسبوعي بنجاح!")
                    st.rerun()