import streamlit as st
import pandas as pd
import os
import datetime
from fpdf import FPDF

st.set_page_config(page_title="ImmoClean", page_icon="🏢", layout="wide")

os.makedirs("photos_employes", exist_ok=True)
FICHIER_DONNEES = "clients.csv"
FICHIER_PAIEMENTS = "paiements.csv"
FICHIER_EMPLOYES = "employes.csv"
FICHIER_PLANNING = "planning.csv"
FICHIER_PASSAGES = "passages.csv"

if os.path.exists(FICHIER_DONNEES):
    df_verif = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
    if "Secteur" not in df_verif.columns:
        df_verif.insert(1, "Secteur", "Non défini")
    df_verif["Téléphone"] = df_verif["Téléphone"].astype(str)
    df_verif.to_csv(FICHIER_DONNEES, index=False)

ANNEE_ACTUELLE = datetime.datetime.now().year
MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

def synchroniser_paiements():
    if not os.path.exists(FICHIER_DONNEES): return
    df_clients = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
    if df_clients.empty: return
    if os.path.exists(FICHIER_PAIEMENTS):
        df_paiements = pd.read_csv(FICHIER_PAIEMENTS)
    else:
        df_paiements = pd.DataFrame(columns=["Résidence", "Année"] + MOIS)
    
    clients_existants = df_clients["Résidence"].tolist()
    for client in clients_existants:
        if not ((df_paiements["Résidence"] == client) & (df_paiements["Année"] == ANNEE_ACTUELLE)).any():
            nouveau = {"Résidence": client, "Année": ANNEE_ACTUELLE}
            for m in MOIS: nouveau[m] = "❌ Non Payé"
            df_paiements = pd.concat([df_paiements, pd.DataFrame([nouveau])], ignore_index=True)
    df_paiements.to_csv(FICHIER_PAIEMENTS, index=False)

# دالة ذكية لتوليد الحصص لكل إقامة حسب السنة والشهر
def synchroniser_passages_par_mois(mois_choisi, annee_choisie):
    if not os.path.exists(FICHIER_DONNEES): return
    df_clients = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
    if df_clients.empty: return
    
    if os.path.exists(FICHIER_PASSAGES):
        df_pass = pd.read_csv(FICHIER_PASSAGES)
    else:
        df_pass = pd.DataFrame(columns=["Résidence", "Mois", "Année", "Escalier_1", "Escalier_2", "Escalier_3", "Escalier_4", "Terrasse", "Sous_Sol"])
    
    clients_existants = df_clients["Résidence"].tolist()
    for client in clients_existants:
        services = str(df_clients[df_clients["Résidence"] == client]["Services"].values[0])
        masque = (df_pass["Résidence"] == client) & (df_pass["Mois"] == mois_choisi) & (df_pass["Année"] == annee_choisie)
        if not masque.any():
            nouveau_suivi = {
                "Résidence": client, "Mois": mois_choisi, "Année": annee_choisie,
                "Escalier_1": "❌ Non fait", "Escalier_2": "❌ Non fait", "Escalier_3": "❌ Non fait", "Escalier_4": "❌ Non fait",
                "Terrasse": "❌ Non fait" if "Terrasse" in services else "N/A",
                "Sous_Sol": "❌ Non fait" if "Sous-sol" in services or "Parking" in services else "N/A"
            }
            df_pass = pd.concat([df_pass, pd.DataFrame([nouveau_suivi])], ignore_index=True)
    df_pass.to_csv(FICHIER_PASSAGES, index=False)


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
        "💰 Suivi des Paiements",
        "📌 Suivi des Passages (الحصص)", 
        "📄 Générer Reçu (Facture)",
        "👥 Gestion de l'Équipe",
        "📅 Planning Hebdomadaire"
    ])

st.title("ImmoClean FACILITY 🏢")

if menu == "🏢 Accueil (Liste des clients)":
    st.header("Gestion des Clients - Accueil")
    if os.path.exists(FICHIER_DONNEES):
        df = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
        if not df.empty: 
            df_affiche = df.copy()
            df_affiche.index = range(1, len(df_affiche) + 1)
            st.dataframe(df_affiche, use_container_width=True)
        else: st.info("الطابلو خاوي حالياً.")
    else: st.info("مازال ما ضفتي حتى كليان.")

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
        
        if st.form_submit_button("Enregistrer le client"):
            if not residence or not services_choisis:
                st.warning("عافاك دخل سمية الإقامة واختار على الأقل خدمة وحدة.")
            else:
                nouveau = pd.DataFrame({"Résidence": [residence], "Secteur": [secteur], "Responsable": [responsable], "Téléphone": [str(telephone)], "Services": [" + ".join(services_choisis)], "Produits": [produit], "Prix (MAD)": [prix]})
                if os.path.exists(FICHIER_DONNEES): 
                    df_existant = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
                    df_final = pd.concat([df_existant, nouveau], ignore_index=True)
                    df_final.to_csv(FICHIER_DONNEES, index=False)
                else: 
                    nouveau.to_csv(FICHIER_DONNEES, index=False)
                st.success(f"Le client {residence} a été ajouté avec succès !")

elif menu == "✏️ Modifier / Supprimer un client":
    st.header("✏️ Modifier ou Supprimer un client")
    if os.path.exists(FICHIER_DONNEES):
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

elif menu == "💰 Suivi des Paiements":
    st.header("💰 Suivi des Paiements Mensuels")
    synchroniser_paiements()
    if os.path.exists(FICHIER_PAIEMENTS):
        df_paiements = pd.read_csv(FICHIER_PAIEMENTS)
        annees_dispo = sorted(df_paiements["Année"].unique().tolist(), reverse=True)
        annee_choisie = st.selectbox("📅 اختار السنة:", annees_dispo)
        df_filtre = df_paiements[df_paiements["Année"] == annee_choisie].copy()
        df_a_afficher = df_filtre.drop(columns=["Année"])
        df_a_afficher.index = range(1, len(df_a_afficher) + 1)

        config_col = {m: st.column_config.SelectboxColumn(m, options=["❌ Non Payé", "✅ Payé"], required=True) for m in MOIS}
        df_modifie = st.data_editor(df_a_afficher, use_container_width=True, hide_index=False, column_config=config_col, disabled=["Résidence"])
        if st.button("💾 Enregistrer les paiements"):
            for index, row in df_modifie.iterrows():
                masque = (df_paiements["Résidence"] == row["Résidence"]) & (df_paiements["Année"] == annee_choisie)
                for m in MOIS: df_paiements.loc[masque, m] = row[m]
            df_paiements.to_csv(FICHIER_PAIEMENTS, index=False)
            st.success("تم الحفظ!")

# ==========================================
# صفحة تتبع الحصص بالشهر (الطريقة الذكية)
# ==========================================
elif menu == "📌 Suivi des Passages (الحصص)":
    st.header("📌 Suivi des Passages par Mois (تتبع الحصص بالشهر)")
    st.info("💡 اختار الشهر والسنة باش يخرج ليك طابلو نقي وصغير خاص غير بدك الشهر (4 حصص للدروج، تيراس، سوسول).")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        mois_selectionne = st.selectbox("📅 اختار الشهر:", MOIS)
    with col_m2:
        annee_selectionnee = st.selectbox("📆 اختار السنة:", [ANNEE_ACTUELLE, ANNEE_ACTUELLE - 1, ANNEE_ACTUELLE + 1])
    
    synchroniser_passages_par_mois(mois_selectionne, annee_selectionnee)
    
    if os.path.exists(FICHIER_PASSAGES):
        df_pass = pd.read_csv(FICHIER_PASSAGES)
        
        df_p_filtre = df_pass[(df_pass["Mois"] == mois_selectionne) & (df_pass["Année"] == annee_selectionnee)].copy()
        df_p_afficher = df_p_filtre.drop(columns=["Mois", "Année"])
        df_p_afficher.index = range(1, len(df_p_afficher) + 1)
        
        if df_p_afficher.empty:
            st.info("ما كاينا حتى إقامة مسجلة هاد الشهر.")
        else:
            options_etat = ["❌ Non fait", "✅ Fait", "N/A"]
            config_p = {
                "Escalier_1": st.column_config.SelectboxColumn("دروج (حصة 1)", options=options_etat, required=True),
                "Escalier_2": st.column_config.SelectboxColumn("دروج (حصة 2)", options=options_etat, required=True),
                "Escalier_3": st.column_config.SelectboxColumn("دروج (حصة 3)", options=options_etat, required=True),
                "Escalier_4": st.column_config.SelectboxColumn("دروج (حصة 4)", options=options_etat, required=True),
                "Terrasse": st.column_config.SelectboxColumn("الترّاس", options=options_etat, required=True),
                "Sous_Sol": st.column_config.SelectboxColumn("السوسول / الباركينغ", options=options_etat, required=True),
            }
            
            df_p_modifie = st.data_editor(
                df_p_afficher,
                use_container_width=True,
                hide_index=False,
                column_config=config_p,
                disabled=["Résidence"]
            )
            
            if st.button("💾 Enregistrer les Passages (حفظ الحصص)"):
                for index, row in df_p_modifie.iterrows():
                    residence = row["Résidence"]
                    masque = (df_pass["Résidence"] == residence) & (df_pass["Mois"] == mois_selectionne) & (df_pass["Année"] == annee_selectionnee)
                    df_pass.loc[masque, "Escalier_1"] = row["Escalier_1"]
                    df_pass.loc[masque, "Escalier_2"] = row["Escalier_2"]
                    df_pass.loc[masque, "Escalier_3"] = row["Escalier_3"]
                    df_pass.loc[masque, "Escalier_4"] = row["Escalier_4"]
                    df_pass.loc[masque, "Terrasse"] = row["Terrasse"]
                    df_pass.loc[masque, "Sous_Sol"] = row["Sous_Sol"]
                
                df_pass.to_csv(FICHIER_PASSAGES, index=False)
                st.success(f"✅ تم حفظ حصص شهر {mois_selectionne} بنجاح!")
    else:
        st.info("مازال ما كاين حتى كليان.")

elif menu == "📄 Générer Reçu (Facture)":
    st.header("📄 Générer un Reçu de Paiement (PDF)")
    if os.path.exists(FICHIER_DONNEES):
        df = pd.read_csv(FICHIER_DONNEES, dtype={"Téléphone": str})
        if not df.empty:
            col1, col2 = st.columns(2)
            with col1: client_choisi = st.selectbox("اختار الكليان (Résidence):", df["Résidence"].tolist())
            with col2: mois_paiement = st.selectbox("شهر الأداء (Mois):", MOIS)
            
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
                pdf.cell(0, 8, "IMMOCLEAN FACILITY", 0, 1)
                pdf.set_font("Arial", '', 10)
                pdf.cell(0, 5, "Telephone : +212 649 924 354", 0, 1)
                date_actuelle = datetime.datetime.now().strftime('%Y-%m-%d')
                pdf.cell(0, 5, f"Date de generation : {date_actuelle}", 0, 1)
                pdf.ln(10)
                
                pdf.set_font("Arial", 'B', 12)
                pdf.set_fill_color(225, 245, 254)
                pdf.cell(0, 8, " INFORMATIONS DU CLIENT", 0, 1, 'L', 1)
                pdf.set_font("Arial", '', 11)
                residence_str = str(client_info['Résidence']).encode('latin-1', 'replace').decode('latin-1')
                responsable_str = str(client_info['Responsable']).encode('latin-1', 'replace').decode('latin-1')
                
                pdf.cell(0, 8, f"Residence : {residence_str}", 0, 1)
                pdf.cell(0, 8, f"Responsable (Syndic) : {responsable_str}", 0, 1)
                pdf.cell(0, 8, f"Mois regle : {mois_paiement} {ANNEE_ACTUELLE}", 0, 1)
                pdf.ln(5)
                
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 12, f"MONTANT PAYE : {client_info['Prix (MAD)']} MAD", 1, 1, 'C')
                
                pdf.ln(20)
                pdf.set_font("Arial", 'I', 10)
                pdf.cell(0, 10, "L'equipe ImmoClean Facility vous remercie pour votre confiance.", 0, 1, 'C')
                
                nom_fichier_pdf = f"Recu_{client_choisi.replace(' ', '_')}_{mois_paiement}.pdf"
                pdf.output(nom_fichier_pdf)
                
                with open(nom_fichier_pdf, "rb") as pdf_file:
                    st.success("✅ تم تجهيز التوصيل بنجاح!")
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
                    if os.path.exists(FICHIER_EMPLOYES): nv_employe.to_csv(FICHIER_EMPLOYES, mode='a', header=False, index=False)
                    else: nv_employe.to_csv(FICHIER_EMPLOYES, mode='w', header=True, index=False)
                    st.success("تمت إضافة العامل بنجاح!")
                    st.rerun()
                else: st.warning("الاسم ضروري.")
    st.markdown("### 📋 Liste de l'équipe")
    if os.path.exists(FICHIER_EMPLOYES):
        df_emp = pd.read_csv(FICHIER_EMPLOYES, dtype={"Téléphone": str})
        cols = st.columns(4)
        for index, row in df_emp.iterrows():
            with cols[index % 4]:
                st.markdown(f"**{row['Nom']}**")
                st.caption(f"{row['Poste']}")
                if pd.notna(row['Photo']) and os.path.exists(row['Photo']): st.image(row['Photo'], width=100)
                else: st.info("Pas de photo")
                st.write(f"📞 {row['Téléphone']}")
                st.markdown("---")

elif menu == "📅 Planning Hebdomadaire":
    st.header("📅 Planning de la semaine (برنامج الأسبوع)")
    if not os.path.exists(FICHIER_EMPLOYES) or not os.path.exists(FICHIER_DONNEES):
        st.warning("خاصك تدخل الكليان والعمال.")
    else:
        df_emp = pd.read_csv(FICHIER_EMPLOYES)
        femmes_menage = df_emp[df_emp["Poste"] == "Femme de ménage"]["Nom"].tolist()
        if not femmes_menage:
            st.info("ما كاينا حتى 'Femme de ménage'.")
        else:
            employe_choisie = st.selectbox("👩‍🔧 اختار العاملة:", femmes_menage)
            df_clients = pd.read_csv(FICHIER_DONNEES)
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

                        s1 = st.selectbox("1️⃣", options=dispo_v1, index=dispo_v1.index(v1) if v1 in dispo_v1 else 0, key=f"{jour}_1")
                        s2 = st.selectbox("2️⃣", options=dispo_v2, index=dispo_v2.index(v2) if v2 in dispo_v2 else 0, key=f"{jour}_2")
                        s3 = st.selectbox("3️⃣", options=dispo_v3, index=dispo_v3.index(v3) if v3 in dispo_v3 else 0, key=f"{jour}_3")
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