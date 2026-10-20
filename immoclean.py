import datetime
import json
import os
import re
from fpdf import FPDF
import gspread
from gspread_dataframe import set_with_dataframe
import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

st.set_page_config(page_title="ImmoClean ERP", page_icon="🏢", layout="wide")

# --- كود الديزاين (CSS) النقي والمضيء ---
st.markdown(
    """
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetric"] { background-color: white; border-left: 5px solid #1E88E5; padding: 15px 20px; border-radius: 10px; box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.05); }
    h1, h2, h3 { color: #0b3d91 !important; font-family: 'Segoe UI', Tahoma, sans-serif; }
</style>
""",
    unsafe_allow_html=True,
)


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


# --- دالة تنظيف وإصلاح أرقام الهاتف (كتحيد + وكتحافظ على 0 فـ اللول) ---
def nettoyer_texte_gsheet(val):
  s = str(val).strip()
  if s.startswith("+") or s.startswith("=") or s.startswith("'"):
    s = s.lstrip("+='").strip()
  if s.endswith(".0"):
    s = s[:-2]
  if len(s) == 9 and s.isdigit() and s[0] in ["5", "6", "7"]:
    s = "0" + s
  return s


# --- دوال جلب وحفظ البيانات (مع تنظيف السطور الخاوية) ---
def load_data(sheet_name, columns):
  ws = sh.worksheet(sheet_name)
  records = ws.get_all_records()
  if not records:
    return pd.DataFrame(columns=columns)
  df = pd.DataFrame(records)
  for col in columns:
    if col not in df.columns:
      df[col] = ""
  first_col = columns[0]
  df = df[
      df[first_col].astype(str).str.strip().replace("nan", "") != ""
  ].reset_index(drop=True)
  if "Téléphone" in df.columns:
    df["Téléphone"] = df["Téléphone"].apply(nettoyer_texte_gsheet)
  return df


def save_data(sheet_name, df):
  ws = sh.worksheet(sheet_name)
  df_clean = df.copy()
  if "Téléphone" in df_clean.columns:
    df_clean["Téléphone"] = df_clean["Téléphone"].apply(nettoyer_texte_gsheet)
  ws.clear()
  set_with_dataframe(ws, df_clean, string_escaping="full")


# --- دالة حساب عدد الحصص المستهدفة فالشهر لكل إقامة ---
def calculer_cible_passages(services_str):
  s = str(services_str).lower()
  if "30/mois" in s or "7j/7" in s:
    return 30
  elif (
      "26/mois" in s or "6j/7" in s or "tous les jours" in s or "quotidien" in s
  ):
    return 26
  elif "3 fois" in s or "12/mois" in s:
    return 12
  elif "2 fois" in s or "8/mois" in s:
    return 8
  elif "2/mois" in s or "15 jours" in s:
    return 2
  else:
    return 4


# --- دالة تنظيف النصوص للـ PDF (باش ما يتبلوكاش مع العربية أو الرموز) ---
def txt_pdf(texte):
  t = str(texte)
  remplacements = {
      "الدروج": "Escaliers",
      "السطح": "Terrasse",
      "الباركينغ": "Parking",
      "المكتب": "Bureau",
      "تنظيف عادي": "Nettoyage standard",
      "حصة شاملة": "Grand nettoyage",
      "الأحد": "Dimanche",
      "الإثنين": "Lundi",
      "الثلاثاء": "Mardi",
      "الأربعاء": "Mercredi",
      "الخميس": "Jeudi",
      "الجمعة": "Vendredi",
      "السبت": "Samedi",
  }
  for ar, fr in remplacements.items():
    t = t.replace(ar, fr)
  return t.encode("latin-1", "replace").decode("latin-1")


# --- أسماء الأعمدة في كل ورقة ---
COLS_CLIENTS = [
    "Résidence",
    "Secteur",
    "Responsable",
    "Téléphone",
    "Services",
    "Produits",
    "Prix (MAD)",
    "Jour de paiement",
]
COLS_HIST = ["Date", "Résidence", "Employé", "Tâches", "Statut"]
COLS_EMP = ["Nom", "Téléphone", "Poste", "Photo"]
COLS_FIN = [
    "Date",
    "Type",
    "Categorie",
    "Montant (MAD)",
    "Description",
    "Paye_Par",
]
COLS_PLAN = [
    "Employe",
    "Client",
    "Jour",
    "Heure_Debut",
    "Heure_Fin",
    "Date_Debut",
    "Frequence",
    "Couleur",
    "Statut",
]


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
        r_jour == jour
        or r_jour in ["Tous les jours", "Tous les jours (Sauf Dimanche)"]
        or jour in ["Tous les jours", "Tous les jours (Sauf Dimanche)"]
    )
    if (r_jour == "Tous les jours (Sauf Dimanche)" and jour == "Dimanche") or (
        jour == "Tous les jours (Sauf Dimanche)" and r_jour == "Dimanche"
    ):
      match_jour = False

    if match_jour:
      try:
        r_deb = datetime.datetime.strptime(
            str(row["Heure_Debut"]), "%H:%M"
        ).time()
        r_fin = datetime.datetime.strptime(
            str(row["Heure_Fin"]), "%H:%M"
        ).time()

        if (h_deb < r_fin) and (h_fin > r_deb):
          r_freq = str(row.get("Frequence", "Chaque semaine"))
          r_date_deb = datetime.datetime.strptime(
              str(row["Date_Debut"]), "%Y-%m-%d"
          ).date()

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
            return (
                True,
                f"⚠️ تداخل فالتوقيت! العاملة **{emp}** عندها ديجا"
                f" **{row['Client']}** يوم **{r_jour}** من"
                f" **{row['Heure_Debut']}** إلى **{row['Heure_Fin']}**"
                f" ({r_freq}).",
            )
      except:
        pass
  return False, ""


def verifier_conflit_report(df_plan, emp, date_cible, h_deb, h_fin):
  if df_plan.empty:
    return False, ""

  jours_fr = {
      0: "Lundi",
      1: "Mardi",
      2: "Mercredi",
      3: "Jeudi",
      4: "Vendredi",
      5: "Samedi",
      6: "Dimanche",
  }
  nom_jour = jours_fr[date_cible.weekday()]
  date_str = date_cible.strftime("%Y-%m-%d")
  sem_cible = date_cible.isocalendar()[1]
  an_cible = date_cible.isocalendar()[0]

  emp_tasks = df_plan[df_plan["Employe"] == emp]
  for _, row in emp_tasks.iterrows():
    try:
      r_freq = str(row.get("Frequence", "Chaque semaine"))
      r_deb = datetime.datetime.strptime(
          str(row["Heure_Debut"]), "%H:%M"
      ).time()
      r_fin = datetime.datetime.strptime(str(row["Heure_Fin"]), "%H:%M").time()

      if not ((h_deb < r_fin) and (h_fin > r_deb)):
        continue

      if r_freq == "Exception":
        if str(row.get("Date_Debut", "")) == date_str:
          return (
              True,
              f"⚠️ تداخل! **{emp}** عندها ديجا حصة مؤجلة ديال"
              f" **{row['Client']}** فهاد التاريخ من **{row['Heure_Debut']}**"
              f" لـ **{row['Heure_Fin']}**.",
          )
        continue

      r_jour = str(row.get("Jour", ""))
      jour_actif = (
          r_jour == nom_jour
          or r_jour == "Tous les jours"
          or (
              r_jour == "Tous les jours (Sauf Dimanche)"
              and nom_jour != "Dimanche"
          )
      )
      if jour_actif:
        verif_rep = df_plan[
            (df_plan["Frequence"] == "Exception")
            & (df_plan["Client"] == row["Client"])
            & (df_plan["Statut"] == f"Report:{date_str}")
        ]
        if not verif_rep.empty:
          continue

        d_deb_row = datetime.datetime.strptime(
            str(row["Date_Debut"]), "%Y-%m-%d"
        ).date()
        diff_sem = (an_cible - d_deb_row.isocalendar()[0]) * 52 + (
            sem_cible - d_deb_row.isocalendar()[1]
        )
        if diff_sem >= 0:
          if (
              r_freq == "Chaque semaine"
              or (r_freq == "1 semaine sur 2" and diff_sem % 2 == 0)
              or (r_freq == "1 fois par mois" and diff_sem % 4 == 0)
          ):
            return (
                True,
                f"⚠️ تداخل! **{emp}** عندها **{row['Client']}** يوم"
                f" **{nom_jour} ({date_cible.strftime('%d/%m')})** من"
                f" **{row['Heure_Debut']}** لـ **{row['Heure_Fin']}**.",
            )
    except:
      pass
  return False, ""


# --- القائمة الجانبية (Menu Moderne) ---
with st.sidebar:
  if os.path.exists("logo.png"):
    st.image("logo.png", use_container_width=True)
  elif os.path.exists("logo.jpg"):
    st.image("logo.jpg", use_container_width=True)
  elif os.path.exists("logo.jpeg"):
    st.image("logo.jpeg", use_container_width=True)
  elif os.path.exists("logo.webp"):
    st.image("logo.webp", use_container_width=True)
  else:
    st.markdown(
        "<h2 style='text-align: center; color: #1E88E5;'>🏢 ImmoClean</h2>",
        unsafe_allow_html=True,
    )

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
          "Planning",
      ],
      icons=[
          "graph-up-arrow",
          "building-add",
          "pencil-square",
          "currency-dollar",
          "wallet2",
          "receipt",
          "file-earmark-ruled",
          "people",
          "calendar-week",
      ],
      menu_icon="cast",
      default_index=0,
      styles={
          "container": {
              "padding": "5!important",
              "background-color": "white",
              "border-radius": "10px",
              "border": "1px solid #e0e0e0",
          },
          "icon": {"color": "#1E88E5", "font-size": "18px"},
          "nav-link": {
              "font-size": "15px",
              "text-align": "left",
              "margin": "5px 0px",
              "color": "#333",
              "--hover-color": "#f0f2f6",
          },
          "nav-link-selected": {
              "background-color": "#1E88E5",
              "color": "white",
              "font-weight": "bold",
              "border-radius": "8px",
          },
      },
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

  total_contrats_mad = 0
  if not df_clients.empty and "Prix (MAD)" in df_clients.columns:
    total_contrats_mad = (
        pd.to_numeric(df_clients["Prix (MAD)"], errors="coerce").fillna(0).sum()
    )

  residences_a_facturer = 0
  clients_en_retard = []

  if not df_clients.empty and not df_hist.empty:
    for _, row in df_clients.iterrows():
      client = str(row["Résidence"]).strip()
      cible = calculer_cible_passages(row.get("Services", ""))

      passages_non_payes = len(
          df_hist[
              (df_hist["Résidence"].astype(str).str.strip() == client)
              & (df_hist["Statut"] == "En attente")
          ]
      )
      if passages_non_payes >= cible:
        residences_a_facturer += 1
        clients_en_retard.append(client)

  total_revenus = (
      pd.to_numeric(
          df_fin[df_fin["Type"] == "Entrée (Revenu)"]["Montant (MAD)"],
          errors="coerce",
      ).sum()
      if not df_fin.empty
      else 0
  )
  total_depenses = (
      pd.to_numeric(
          df_fin[df_fin["Type"] == "Sortie (Dépense)"]["Montant (MAD)"],
          errors="coerce",
      ).sum()
      if not df_fin.empty
      else 0
  )
  solde_net = total_revenus - total_depenses

  col1, col2, col3, col4, col5 = st.columns(5)
  with col1:
    st.metric(label="🏢 إجمالي الإقامات", value=f"{total_clients}")
  with col2:
    st.metric(
        label="📜 قيمة العقود الشهرية", value=f"{total_contrats_mad:,.0f} MAD"
    )
  with col3:
    st.metric(label="🚨 واجب استخلاصها", value=f"{residences_a_facturer}")
  with col4:
    st.metric(label="💰 المداخيل المستلمة", value=f"{total_revenus:,.0f} MAD")
  with col5:
    st.metric(label="💎 الصافي (Solde Net)", value=f"{solde_net:,.0f} MAD")

  if clients_en_retard:
    st.markdown(
        f"""
        <div style="background-color: #ffebee; border-left: 6px solid #d32f2f; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h4 style="color: #c62828 !important; margin: 0;">🚨 تنبيه الأداء: إقامات وصلت لوقت الخلاص!</h4>
            <p style="color: #b71c1c; font-size: 16px; font-weight: bold; margin: 5px 0 0 0;">🏢 {'  |  🏢 '.join(clients_en_retard)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

  st.markdown("---")

  with st.expander(
      "🏢 جدول جميع الإقامات المتعاقد معها (الإقامات باللون الأحمر وصل وقت"
      " خلاصها 🚨)",
      expanded=True,
  ):
    if not df_clients.empty:
      df_cl_display = df_clients.copy()
      df_cl_display["Prix (MAD)"] = pd.to_numeric(
          df_cl_display["Prix (MAD)"], errors="coerce"
      ).fillna(0)

      total_row = pd.DataFrame({
          "Résidence": ["💰 المجموع الإجمالي للعقود (TOTAL)"],
          "Secteur": [f"{total_clients} إقامات"],
          "Responsable": ["—"],
          "Téléphone": ["—"],
          "Services": ["—"],
          "Produits": ["—"],
          "Prix (MAD)": [total_contrats_mad],
          "Jour de paiement": ["شهرياً (Par mois)"],
      })

      df_cl_avec_total = pd.concat(
          [df_cl_display, total_row], ignore_index=True
      )

      def colorer_lignes_clients(row):
        nom_r = str(row["Résidence"]).strip()
        if nom_r in clients_en_retard:
          return [
              "background-color: #ffcdd2; color: #b71c1c; font-weight: bold;"
          ] * len(row)
        elif "TOTAL" in nom_r:
          return [
              "background-color: #e8f5e9; color: #1b5e20; font-weight: bold;"
          ] * len(row)
        return [""] * len(row)

      styled_df = df_cl_avec_total.style.apply(
          colorer_lignes_clients, axis=1
      ).format({"Prix (MAD)": "{:,.0f} MAD"})
      st.dataframe(styled_df, use_container_width=True, hide_index=True)
      st.success(
          "💵 **مجموع الأموال الشهرية الثابتة في العقود (MRR):**"
          f" `{total_contrats_mad:,.2f} MAD / Mois`"
      )
    else:
      st.info("لا توجد إقامات مسجلة حالياً.")

  st.markdown("---")
  st.subheader("📅 برنامج اليوم وغداً (مع الموقع، Pointage وتأجيل الحصص)")

  df_plan = load_data("Planning", COLS_PLAN)
  if not df_plan.empty:
    jours_fr = {
        0: "Lundi",
        1: "Mardi",
        2: "Mercredi",
        3: "Jeudi",
        4: "Vendredi",
        5: "Samedi",
        6: "Dimanche",
    }

    dates_a_afficher = [
        ("اليوم", datetime.date.today()),
        ("غداً", datetime.date.today() + datetime.timedelta(days=1)),
    ]

    for label, date_cible in dates_a_afficher:
      nom_jour_cible = jours_fr[date_cible.weekday()]
      semaine_cible = date_cible.isocalendar()[1]
      annee_cible = date_cible.isocalendar()[0]
      date_cible_str = str(date_cible)

      st.markdown(
          f"#### 🔹 {label} ({nom_jour_cible}"
          f" {date_cible.strftime('%d/%m/%Y')})"
      )

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
            jour_row == nom_jour_cible
            or jour_row == "Tous les jours"
            or (
                jour_row == "Tous les jours (Sauf Dimanche)"
                and nom_jour_cible != "Dimanche"
            )
        )

        if jour_correspond:
          try:
            d_debut = datetime.datetime.strptime(
                str(row["Date_Debut"]), "%Y-%m-%d"
            ).date()
            sem_debut = d_debut.isocalendar()[1]
            an_debut = d_debut.isocalendar()[0]
            diff_semaines = (annee_cible - an_debut) * 52 + (
                semaine_cible - sem_debut
            )

            if diff_semaines >= 0:
              if (
                  freq == "Chaque semaine"
                  or (freq == "1 semaine sur 2" and diff_semaines % 2 == 0)
                  or (freq == "1 fois par mois" and diff_semaines % 4 == 0)
              ):
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
          secteur_html = (
              '<div style="font-size: 13px; color: #1E88E5; font-weight: 600;'
              f' margin-bottom: 5px;">📍 المنطقـة: {secteur_client}</div>'
              if secteur_client
              else ""
          )

          est_reportee = False
          date_report_vers = ""
          if freq_tache != "Exception":
            verif_rep = df_plan[
                (df_plan["Frequence"] == "Exception")
                & (df_plan["Client"] == client_nom)
                & (df_plan["Statut"] == f"Report:{date_cible_str}")
            ]
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
                passages_non_payes = len(
                    df_hist[
                        (df_hist["Résidence"] == client_nom)
                        & (df_hist["Statut"] == "En attente")
                    ]
                )
              else:
                passages_non_payes = 0

              taches_a_faire = []
              if "escalier" in services:
                taches_a_faire.append("الدروج")
                taches_hist_list.append("Escaliers")
              if "bureau" in services:
                taches_a_faire.append("المكتب")
                taches_hist_list.append("Bureau")

              is_debut_cycle = passages_non_payes % cible == 0

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

              taches_str = (
                  " + ".join(taches_a_faire) if taches_a_faire else "تنظيف عادي"
              )

          deja_pointe = False
          if not df_hist.empty:
            verif_p = df_hist[
                (df_hist["Date"].astype(str) == date_cible_str)
                & (df_hist["Résidence"] == client_nom)
            ]
            if not verif_p.empty:
              deja_pointe = True

          with cols[index % 3]:
            st.markdown(
                f"""
                        <div style="background: white; border-top: 5px solid {couleur}; padding: 15px; border-radius: 10px; box-shadow: 0 3px 8px rgba(0,0,0,0.08); margin-bottom: 10px;">
                            <div style="font-size: 13px; color: #777; font-weight: bold;">⏰ {tache['Heure_Debut']} - {tache['Heure_Fin']}</div>
                            <div style="font-size: 18px; font-weight: bold; color: #222; margin: 4px 0;">🏢 {client_nom}</div>
                            {secteur_html}
                            <div style="font-size: 14px; color: #444; margin-bottom: 8px;">👷‍♀️ العاملة: <b>{emp_nom}</b></div>
                            <span style="background-color: {badge_color}; color: white; padding: 3px 8px; border-radius: 5px; font-size: 12px;">{badge}</span>
                            <div style="margin-top: 8px; font-size: 13px; color: #333;">🛠️ <b>المهام:</b> {taches_str}</div>
                        </div>
                        """,
                unsafe_allow_html=True,
            )

            if est_reportee:
              st.warning(f"🔄 مؤجلة إلى: {date_report_vers}")
            elif deja_pointe:
              st.success("✅ تم تسجيل الحضور (Pointé)")
            else:
              c_btn1, c_btn2 = st.columns(2)
              with c_btn1:
                if st.button(
                    "✅ Pointage",
                    key=f"pt_{label}_{index}",
                    use_container_width=True,
                ):
                  tache_save = (
                      " + ".join(taches_hist_list)
                      if taches_hist_list
                      else "Nettoyage"
                  )
                  new_hist = pd.DataFrame([{
                      "Date": date_cible_str,
                      "Résidence": client_nom,
                      "Employé": emp_nom,
                      "Tâches": tache_save,
                      "Statut": "En attente",
                  }])
                  df_hist = pd.concat([df_hist, new_hist], ignore_index=True)
                  save_data("Historique", df_hist)
                  st.rerun()
              with c_btn2:
                with st.popover("🔄 تأجيل"):
                  new_d = st.date_input(
                      "تاريخ جديد",
                      value=date_cible + datetime.timedelta(days=1),
                      key=f"nd_{label}_{index}",
                  )
                  new_hd = st.time_input(
                      "وقت البدء",
                      value=datetime.time(9, 0),
                      key=f"nhd_{label}_{index}",
                  )
                  new_hf = st.time_input(
                      "وقت الانتهاء",
                      value=datetime.time(12, 0),
                      key=f"nhf_{label}_{index}",
                  )
                  if st.button("تأكيد التأجيل", key=f"ok_rep_{label}_{index}"):
                    conflit, msg_c = verifier_conflit_report(
                        df_plan, emp_nom, new_d, new_hd, new_hf
                    )
                    if conflit:
                      st.error(msg_c)
                    else:
                      jours_map = {
                          0: "Lundi",
                          1: "Mardi",
                          2: "Mercredi",
                          3: "Jeudi",
                          4: "Vendredi",
                          5: "Samedi",
                          6: "Dimanche",
                      }
                      new_ex = pd.DataFrame([{
                          "Employe": emp_nom,
                          "Client": client_nom,
                          "Jour": jours_map[new_d.weekday()],
                          "Heure_Debut": new_hd.strftime("%H:%M"),
                          "Heure_Fin": new_hf.strftime("%H:%M"),
                          "Date_Debut": new_d.strftime("%Y-%m-%d"),
                          "Frequence": "Exception",
                          "Couleur": "#FF9800",
                          "Statut": f"Report:{date_cible_str}",
                      }])
                      df_plan = pd.concat([df_plan, new_ex], ignore_index=True)
                      save_data("Planning", df_plan)
                      st.success("تم التأجيل!")
                      st.rerun()
      else:
        st.info(f"لا توجد مهام مبرمجة لـ {label}.")
  else:
    st.info("الجدول الزمني (Planning) فارغ حالياً.")

# ==========================================
# 2. Nouveau Client
# ==========================================
elif menu == "Nouveau Client":
  st.header("🏢 إضافة إقامة جديدة (Nouveau Client)")
  df_clients = load_data("Clients", COLS_CLIENTS)

  with st.form("form_nouveau_client"):
    c1, c2 = st.columns(2)
    with c1:
      nom_res = st.text_input("🏢 اسم الإقامة (Résidence)")
      secteur = st.text_input(
          "📍 الحي / المنطقة (Secteur - ex: Maamora, Ville Haute)"
      )
      responsable = st.text_input("👤 اسم المسؤول / السانديك (Responsable)")
      telephone = st.text_input("📞 رقم الهاتف (Téléphone)")
    with c2:
      freq_passage = st.selectbox(
          "🔄 وتيرة العمل (Fréquence)",
          [
              "1 fois/semaine (4/mois)",
              "2 fois/semaine (8/mois)",
              "3 fois/semaine (12/mois)",
              "Tous les jours sauf Dimanche (26/mois)",
              "1 fois / 15 jours (2/mois)",
          ],
      )
      zones_clean = st.multiselect(
          "🧹 الأماكن المشمولة بالتنظيف",
          ["Escaliers", "Terrasse", "Sous-sol / Parking", "Bureau", "Jardin"],
          default=["Escaliers", "Terrasse"],
      )
      produits = st.selectbox(
          "🧴 مواد النظافة (Produits)",
          ["Inclus (ImmoClean)", "Fournis par le Syndic"],
      )
      prix = st.number_input(
          "💰 السعر الشهري (Prix en MAD)", min_value=0, value=600, step=50
      )
      jour_paie = st.text_input(
          "📅 يوم الأداء (Jour de paiement)", value="Le 1er du mois"
      )

    submitted = st.form_submit_button(
        "💾 حفظ الإقامة الجديدة", use_container_width=True
    )
    if submitted:
      if not nom_res.strip():
        st.error("⚠️ يرجى إدخال اسم الإقامة!")
      else:
        services_complet = f"{freq_passage} - {' + '.join(zones_clean)}"
        new_row = pd.DataFrame([{
            "Résidence": nom_res.strip(),
            "Secteur": secteur.strip(),
            "Responsable": responsable.strip(),
            "Téléphone": nettoyer_texte_gsheet(telephone),
            "Services": services_complet,
            "Produits": produits,
            "Prix (MAD)": prix,
            "Jour de paiement": jour_paie,
        }])
        df_clients = pd.concat([df_clients, new_row], ignore_index=True)
        save_data("Clients", df_clients)
        st.success(f"✅ تم تسجيل إقامة **{nom_res}** بنجاح!")

# ==========================================
# 3. Gérer les clients
# ==========================================
elif menu == "Gérer les clients":
  st.header("✏️ تعديل أو حذف الإقامات (Gérer les clients)")
  df_clients = load_data("Clients", COLS_CLIENTS)

  if df_clients.empty:
    st.info("لا توجد إقامات مسجلة حالياً.")
  else:
    st.info("💡 يمكنك التعديل مباشرة في الجدول أسفله، ثم الضغط على زر الحفظ.")
    edited_df = st.data_editor(
        df_clients, num_rows="dynamic", use_container_width=True
    )

    if st.button("💾 حفظ التعديلات (Enregistrer)", type="primary"):
      edited_df = edited_df[
          edited_df["Résidence"].astype(str).str.strip().replace("nan", "")
          != ""
      ].reset_index(drop=True)
      save_data("Clients", edited_df)
      st.success("✅ تم تحديث قاعدة بيانات الزبناء بنجاح!")
      st.rerun()

# ==========================================
# 4. Pointage & Paiements
# ==========================================
elif menu == "Pointage & Paiements":
  st.header("✅ تسجيل الحصص واستخلاص الأداءات (Pointage & Paiements)")

  df_clients = load_data("Clients", COLS_CLIENTS)
  df_emp = load_data("Employes", COLS_EMP)
  df_hist = load_data("Historique", COLS_HIST)
  df_fin = load_data("Finances", COLS_FIN)

  tab1, tab2, tab3 = st.tabs([
      "📝 تسجيل حصة عمل (Pointage)",
      "💰 استخلاص شهر مكتمل (Paiement)",
      "📜 سجل جميع الحصص (Historique)",
  ])

  with tab1:
    st.subheader("تسجيل مرور عاملة في إقامة")
    with st.form("form_pointage_manuel"):
      c1, c2 = st.columns(2)
      with c1:
        d_pt = st.date_input("📅 التاريخ", value=datetime.date.today())
        res_pt = st.selectbox(
            "🏢 الإقامة",
            df_clients["Résidence"].tolist() if not df_clients.empty else [],
        )
      with c2:
        emp_pt = st.selectbox(
            "👷‍♀️ العاملة",
            df_emp["Nom"].tolist() if not df_emp.empty else ["عائشة"],
        )
        taches_pt = st.multiselect(
            "🧹 المهام المنجزة",
            ["Escaliers", "Terrasse", "Parking", "Bureau"],
            default=["Escaliers"],
        )

      if st.form_submit_button("✅ تأكيد وتسجيل الحصة", use_container_width=True):
        new_h = pd.DataFrame([{
            "Date": str(d_pt),
            "Résidence": res_pt,
            "Employé": emp_pt,
            "Tâches": " + ".join(taches_pt),
            "Statut": "En attente",
        }])
        df_hist = pd.concat([df_hist, new_h], ignore_index=True)
        save_data("Historique", df_hist)
        st.success(f"✅ تم تسجيل الحصة لـ {res_pt} بنجاح!")
        st.rerun()

  with tab2:
    st.subheader("💰 تأكيد خلاص إقامة وتحويلها للمداخيل")
    if not df_clients.empty:
      res_pay = st.selectbox(
          "🏢 اختر الإقامة لتأكيد خلاصها", df_clients["Résidence"].tolist()
      )
      info_c = df_clients[df_clients["Résidence"] == res_pay].iloc[0]
      cible_c = calculer_cible_passages(info_c.get("Services", ""))
      prix_c = pd.to_numeric(info_c.get("Prix (MAD)", 0), errors="coerce")

      en_attente_df = df_hist[
          (df_hist["Résidence"] == res_pay)
          & (df_hist["Statut"] == "En attente")
      ]
      nb_att = len(en_attente_df)

      st.info(
          f"📊 عدد الحصص غير المؤداة حالياً لـ **{res_pay}** هو: **`{nb_att}`**"
          f" من أصل **`{cible_c}`** حصص فالشهر."
      )
      montant_encaisse = st.number_input(
          "💵 المبلغ المستلم (MAD)",
          value=int(prix_c) if pd.notna(prix_c) else 500,
          step=50,
      )
      encaisse_par = st.selectbox(
          "👤 شكون تسلم الفلوس / فين دخلات",
          ["Caisse (صندوق الشركة)", "Driss", "Younnes"],
      )

      if st.button("💰 تأكيد استلام المبلغ وتصفية الحصص", type="primary"):
        df_hist.loc[
            (df_hist["Résidence"] == res_pay)
            & (df_hist["Statut"] == "En attente"),
            "Statut",
        ] = "Payé"
        save_data("Historique", df_hist)

        new_fin = pd.DataFrame([{
            "Date": str(datetime.date.today()),
            "Type": "Entrée (Revenu)",
            "Categorie": "Abonnement Résidence",
            "Montant (MAD)": montant_encaisse,
            "Description": f"Paiement mensuel - {res_pay}",
            "Paye_Par": encaisse_par,
        }])
        df_fin = pd.concat([df_fin, new_fin], ignore_index=True)
        save_data("Finances", df_fin)
        st.success(
            f"🎉 تم تسجيل خلاص **{res_pay}** ({montant_encaisse} MAD) وتحديث"
            " الحصص إلى 'Payé'!"
        )
        st.rerun()

  with tab3:
    if not df_hist.empty:
      edited_hist = st.data_editor(
          df_hist, num_rows="dynamic", use_container_width=True
      )
      if st.button("💾 حفظ تعديلات السجل"):
        save_data("Historique", edited_hist)
        st.success("تم الحفظ!")
        st.rerun()
    else:
      st.info("لا توجد حصص مسجلة بعد.")

# ==========================================
# 5. Finances & Trésorerie (مع فلتر شكون خلص والعمليات)
# ==========================================
elif menu == "Finances & Trésorerie":
  st.header("💼 المالية والمحاسبة (Finances & Trésorerie)")
  df_fin = load_data("Finances", COLS_FIN)

  # --- حساب وعرض شحال خسر كل واحد الفوق ---
  if not df_fin.empty:
    df_dep = df_fin[df_fin["Type"] == "Sortie (Dépense)"].copy()
    df_dep["Montant (MAD)"] = pd.to_numeric(
        df_dep["Montant (MAD)"], errors="coerce"
    ).fillna(0)

    dep_driss = df_dep[
        df_dep["Paye_Par"].astype(str).str.contains("Driss", case=False, na=False)
    ]["Montant (MAD)"].sum()
    dep_younnes = df_dep[
        df_dep["Paye_Par"]
        .astype(str)
        .str.contains("Younnes|Younes", case=False, na=False)
    ]["Montant (MAD)"].sum()
    dep_caisse = df_dep[
        df_dep["Paye_Par"]
        .astype(str)
        .str.contains("Caisse|صندوق", case=False, na=False)
    ]["Montant (MAD)"].sum()

    st.markdown("#### 💳 تفصيل المصاريف حسب الدافع (شكون خسر الفلوس):")
    c_p1, c_p2, c_p3 = st.columns(3)
    with c_p1:
      st.metric(label="👤 مصاريف خلصها Driss", value=f"{dep_driss:,.0f} MAD")
    with c_p2:
      st.metric(
          label="👤 مصاريف خلصها Younnes", value=f"{dep_younnes:,.0f} MAD"
      )
    with c_p3:
      st.metric(
          label="🏦 مصاريف من صندوق الشركة (Caisse)",
          value=f"{dep_caisse:,.0f} MAD",
      )
    st.markdown("---")

  with st.expander("➕ تسجيل عملية مالية جديدة (مدخول أو مصروف)", expanded=True):
    with st.form("form_finance"):
      c1, c2, c3 = st.columns(3)
      with c1:
        d_fin = st.date_input("📅 التاريخ", value=datetime.date.today())
        type_fin = st.selectbox(
            "🔄 نوع العملية", ["Sortie (Dépense)", "Entrée (Revenu)"]
        )
      with c2:
        cat_fin = st.selectbox(
            "📂 التصنيف",
            [
                "Produits & Matériel",
                "Salaires",
                "Transport",
                "Publicité (Ads)",
                "Abonnement Résidence",
                "Autre",
            ],
        )
        mnt_fin = st.number_input("💰 المبلغ (MAD)", min_value=0, step=10)
      with c3:
        desc_fin = st.text_input("📝 الوصف / البيان")
        paye_par_fin = st.selectbox(
            "👤 شكون خلصها / صندوق الأداء (Payé par)",
            ["Driss", "Younnes", "Caisse (صندوق الشركة)"],
        )

      if st.form_submit_button(
          "💾 تسجيل العملية المالية", use_container_width=True
      ):
        new_f = pd.DataFrame([{
            "Date": str(d_fin),
            "Type": type_fin,
            "Categorie": cat_fin,
            "Montant (MAD)": mnt_fin,
            "Description": desc_fin,
            "Paye_Par": paye_par_fin,
        }])
        df_fin = pd.concat([df_fin, new_f], ignore_index=True)
        save_data("Finances", df_fin)
        st.success("✅ تمت إضافة العملية المالية بنجاح!")
        st.rerun()

  if not df_fin.empty:
    st.markdown("---")
    st.subheader("📊 سجل المعاملات المالية (Historique Financier)")

    # --- فلاتر البحث في سجل المعاملات المالية ---
    col_f1, col_f2 = st.columns(2)
    with col_f1:
      filtre_personne = st.selectbox(
          "🔍 فلتر حسب الشخص / الصندوق (شكون خلص أو تسلم):",
          [
              "الكل (Tous)",
              "Driss",
              "Younnes",
              "Caisse (صندوق الشركة)",
          ],
      )
    with col_f2:
      filtre_type = st.selectbox(
          "🔄 فلتر حسب نوع العملية:",
          [
              "الكل (مداخيل + مصاريف)",
              "Sortie (Dépense) - المصاريف فقط",
              "Entrée (Revenu) - المداخيل فقط",
          ],
      )

    # تطبيق الفلتر على الجدول مع الاحتفاظ بالـ Index الأصلي للحفظ الصحيح
    df_fin_affiche = df_fin.copy()

    if filtre_personne == "Driss":
      df_fin_affiche = df_fin_affiche[
          df_fin_affiche["Paye_Par"]
          .astype(str)
          .str.contains("Driss", case=False, na=False)
      ]
    elif filtre_personne == "Younnes":
      df_fin_affiche = df_fin_affiche[
          df_fin_affiche["Paye_Par"]
          .astype(str)
          .str.contains("Younnes|Younes", case=False, na=False)
      ]
    elif filtre_personne == "Caisse (صندوق الشركة)":
      df_fin_affiche = df_fin_affiche[
          df_fin_affiche["Paye_Par"]
          .astype(str)
          .str.contains("Caisse|صندوق", case=False, na=False)
      ]

    if "Sortie" in filtre_type:
      df_fin_affiche = df_fin_affiche[
          df_fin_affiche["Type"] == "Sortie (Dépense)"
      ]
    elif "Entrée" in filtre_type:
      df_fin_affiche = df_fin_affiche[
          df_fin_affiche["Type"] == "Entrée (Revenu)"
      ]

    # حساب مجموع العمليات المعروضة فـ الفلتر
    total_filtre = (
        pd.to_numeric(df_fin_affiche["Montant (MAD)"], errors="coerce")
        .fillna(0)
        .sum()
    )
    st.info(
        f"📌 **عدد العمليات المعروضة:** `{len(df_fin_affiche)}`  |  💰 **مجموع"
        f" المبالغ فـ هاد الفلتر:** `{total_filtre:,.2f} MAD`"
    )

    # إذا كان الفلتر على "الكل" كنسمحو بإضافة وحذف السطور، وإذا كان مفلتر كنعدلو السطور المعروضة بأمان
     is_tout = (
        filtre_personne == "الكل (Tous)"
        and filtre_type == "الكل (مداخيل + مصاريف)"
    )

    edited_fin = st.data_editor(
        df_fin_affiche,
        num_rows="dynamic" if is_tout else "fixed",
        use_container_width=True,
        key="editor_finances",
    )

    if st.button("💾 حفظ تعديلات المالية"):
      if is_tout:
        save_data("Finances", edited_fin)
      else:
        # تحديث السطور المعدلة فـ الجدول الأصلي بلا ما يضيعو السطور المخفيين بالفلتر
        df_fin.update(edited_fin)
        save_data("Finances", df_fin)
      st.success("✅ تم حفظ التعديلات بنجاح!")
      st.rerun()

# ==========================================
# 6. Générer Reçu (يجلب آخر الحصص أوتوماتيكياً حسب العقد)
# ==========================================
elif menu == "Générer Reçu":
  st.header("🧾 مولد التوصيلات (Reçu de Paiement avec Historique des Séances)")

  df_clients = load_data("Clients", COLS_CLIENTS)
  df_hist = load_data("Historique", COLS_HIST)

  if df_clients.empty:
    st.warning("⚠️ لا توجد إقامات مسجلة حالياً فـ قاعدة البيانات.")
  else:
    liste_res = [
        str(r).strip()
        for r in df_clients["Résidence"].dropna().unique()
        if str(r).strip() != ""
    ]

    col1, col2 = st.columns(2)
    with col1:
      res_choisie = st.selectbox("🏢 اختر الإقامة (Résidence)", liste_res)

      client_info = df_clients[
          df_clients["Résidence"].astype(str).str.strip() == res_choisie
      ]
      prix_defaut = 500
      services_client = ""
      cible_auto = 4

      if not client_info.empty:
        services_client = str(client_info.iloc[0].get("Services", ""))
        cible_auto = calculer_cible_passages(services_client)
        try:
          prix_defaut = int(float(client_info.iloc[0].get("Prix (MAD)", 500)))
        except:
          prix_defaut = 500

      mois_actuel = datetime.date.today().strftime("%B %Y")
      periode = st.text_input("📅 الشهر / الفترة (Période)", value=mois_actuel)
      montant = st.number_input(
          "💰 المبلغ المؤدى (Montant en MAD)", value=prix_defaut, step=50
      )

    with col2:
      mode_reglement = st.selectbox(
          "💳 طريقة الأداء (Mode de règlement)",
          ["Espèces", "Virement", "Chèque"],
      )
      st.info(
          f"📋 **تفاصيل العقد:** `{services_client}`  \n🎯 **عدد الحصص الشهري"
          f" في العقد:** `{cible_auto} حصص`"
      )

      nb_seances = st.number_input(
          "🔢 عدد الحصص الأخيرة التي ستُطبع في الوصل:",
          min_value=1,
          max_value=35,
          value=int(cible_auto),
      )
      statut_filtre = st.radio(
          "🔍 تصفية الحصص المسحوبة من Historique:",
          [
              "آخر الحصص المنجزة (الكل)",
              "فقط الحصص المؤداة (Payé)",
              "فقط الحصص في الانتظار (En attente)",
          ],
          horizontal=True,
      )

    df_seances_recu = pd.DataFrame()
    if not df_hist.empty and "Résidence" in df_hist.columns:
      df_sub = df_hist[
          df_hist["Résidence"].astype(str).str.strip() == res_choisie
      ].copy()

      if statut_filtre == "فقط الحصص المؤداة (Payé)":
        df_sub = df_sub[df_sub["Statut"].astype(str).str.strip() == "Payé"]
      elif statut_filtre == "فقط الحصص في الانتظار (En attente)":
        df_sub = df_sub[
            df_sub["Statut"].astype(str).str.strip() == "En attente"
        ]

      df_seances_recu = df_sub.tail(int(nb_seances)).reset_index(drop=True)

    st.markdown("---")
    st.subheader(
        f"📋 معاينة الـ {len(df_seances_recu)} حصص الأخيرة التي ستظهر في"
        f" الـ Reçu لـ ({res_choisie}):"
    )
    if not df_seances_recu.empty:
      st.dataframe(df_seances_recu, use_container_width=True, hide_index=True)
    else:
      st.warning(
          "⚠️ لا توجد حصص مسجلة لهذه الإقامة في جدول Historique حالياً! سيخرج"
          " الوصل بدون جدول الحصص."
      )

    def generer_recu_complet_pdf(
        res_nom, per_str, mnt_val, mode_str, srv_str, df_s
    ):
      pdf = FPDF()
      pdf.add_page()

      # 1. الهيدر (Header)
      pdf.set_font("Arial", "B", 16)
      pdf.set_text_color(11, 61, 145)
      pdf.cell(0, 10, "IMMOCLEAN FACILITY", ln=True, align="C")

      pdf.set_font("Arial", "", 10)
      pdf.set_text_color(100, 100, 100)
      pdf.cell(
          0,
          6,
          "Service Professionnel de Nettoyage et d'Entretien des Residences -"
          " Kenitra",
          ln=True,
          align="C",
      )
      pdf.cell(0, 6, "Tel: 06 49 92 43 54", ln=True, align="C")
      pdf.ln(6)

      # 2. عنوان الوصل
      pdf.set_font("Arial", "B", 13)
      pdf.set_text_color(0, 0, 0)
      pdf.cell(0, 10, "RECU DE PAIEMENT", border=1, ln=True, align="C")
      pdf.ln(6)

      # 3. تفاصيل الأداء والعقد
      pdf.set_font("Arial", "", 11)
      date_impression = datetime.date.today().strftime("%d/%m/%Y")
      pdf.cell(0, 7, txt_pdf(f"Date : {date_impression}"), ln=True)
      pdf.cell(0, 7, txt_pdf(f"Residence : {res_nom}"), ln=True)
      pdf.cell(0, 7, txt_pdf(f"Periode : {per_str}"), ln=True)
      if srv_str:
        pdf.cell(0, 7, txt_pdf(f"Formule Contrat : {srv_str}"), ln=True)
      pdf.set_font("Arial", "B", 11)
      pdf.cell(0, 7, txt_pdf(f"Montant paye : {mnt_val} MAD"), ln=True)
      pdf.set_font("Arial", "", 11)
      pdf.cell(0, 7, txt_pdf(f"Mode de reglement : {mode_str}"), ln=True)
      pdf.ln(6)

      # 4. جدول الحصص الأخيرة المنجزة
      if not df_s.empty:
        pdf.set_font("Arial", "B", 11)
        pdf.set_text_color(11, 61, 145)
        pdf.cell(
            0,
            8,
            txt_pdf(
                f"Detail des {len(df_s)} dernieres seances de nettoyage"
                " effectuees :"
            ),
            ln=True,
        )
        pdf.ln(2)

        # رؤوس الجدول
        pdf.set_font("Arial", "B", 9)
        pdf.set_fill_color(230, 238, 250)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(12, 8, "N", border=1, align="C", fill=True)
        pdf.cell(32, 8, "Date", border=1, align="C", fill=True)
        pdf.cell(45, 8, "Agent / Employe", border=1, align="C", fill=True)
        pdf.cell(73, 8, "Prestations realisees", border=1, align="C", fill=True)
        pdf.cell(28, 8, "Statut", border=1, ln=True, align="C", fill=True)

        # سطور الجدول
        pdf.set_font("Arial", "", 9)
        for i, row in df_s.iterrows():
          num = str(i + 1)
          d_seance = txt_pdf(row.get("Date", "-"))
          emp_seance = txt_pdf(row.get("Employé", "-"))[:22]
          tache_seance = txt_pdf(row.get("Tâches", "Nettoyage"))[:40]

          pdf.cell(12, 7, num, border=1, align="C")
          pdf.cell(32, 7, d_seance, border=1, align="C")
          pdf.cell(45, 7, emp_seance, border=1, align="L")
          pdf.cell(73, 7, tache_seance, border=1, align="L")
          pdf.cell(28, 7, "Realise", border=1, ln=True, align="C")

      pdf.ln(10)
      # 5. التوقيع فـ الأسفل
      pdf.set_font("Arial", "I", 10)
      pdf.set_text_color(80, 80, 80)
      pdf.cell(
          0,
          8,
          "Merci pour votre confiance. Direction ImmoClean FACILITY.",
          ln=True,
          align="R",
      )

      return pdf.output(dest="S").encode("latin-1", "replace")

    pdf_data = generer_recu_complet_pdf(
        res_choisie,
        periode,
        montant,
        mode_reglement,
        services_client,
        df_seances_recu,
    )
    nom_pdf = f"Recu_{res_choisie}_{periode}.pdf".replace(" ", "_")

    st.download_button(
        label="📥 تحميل الوصل بالحصص (Télécharger le Reçu PDF)",
        data=pdf_data,
        file_name=nom_pdf,
        mime="application/pdf",
        use_container_width=True,
    )

# ==========================================
# 7. Générer Devis
# ==========================================
elif menu == "Générer Devis":
  st.header("📄 مولد عروض الأثمان (Générateur de Devis PDF)")

  col1, col2 = st.columns(2)
  with col1:
    nom_client_devis = st.text_input(
        "🏢 اسم الإقامة أو الشركة", "Résidence Al Amal"
    )
    ville_devis = st.text_input("📍 المدينة / الحي", "Kénitra")
    freq_devis = st.selectbox(
        "🔄 عدد الزيارات",
        [
            "1 passage par semaine (4 séances / mois)",
            "2 passages par semaine (8 séances / mois)",
            "3 passages par semaine (12 séances / mois)",
            "Quotidien 6j/7 (26 séances / mois)",
        ],
    )
  with col2:
    prix_devis = st.number_input(
        "💰 السعر الشهري المقترح (MAD HT/TTC)", value=800, step=50
    )
    produits_devis = st.selectbox(
        "🧴 مواد ومعدات النظافة",
        [
            "Inclus (Fournis par ImmoClean FACILITY)",
            "A la charge de la Résidence",
        ],
    )
    details_devis = st.text_area(
        "🧹 تفاصيل الخدمات المشمولة",
        "Nettoyage complet des cages d'escaliers, hall d'entree, vitres,"
        " ascenseur, terrasse et parking.",
    )

  def creer_devis_pdf(client_n, ville_n, freq_n, prod_n, det_n, prix_n):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(11, 61, 145)
    pdf.cell(0, 10, "IMMOCLEAN FACILITY", ln=True, align="C")

    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        0,
        6,
        "Service Professionnel de Nettoyage et d'Entretien des Residences -"
        " Kenitra",
        ln=True,
        align="C",
    )
    pdf.cell(0, 6, "Tel: 06 49 92 43 54", ln=True, align="C")
    pdf.ln(8)

    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(
        0, 10, "DEVIS / PROPOSITION COMMERCIALE", border=1, ln=True, align="C"
    )
    pdf.ln(8)

    pdf.set_font("Arial", "", 11)
    pdf.cell(
        0,
        8,
        txt_pdf(f"Date : {datetime.date.today().strftime('%d/%m/%Y')}"),
        ln=True,
    )
    pdf.cell(
        0, 8, txt_pdf(f"Client / Residence : {client_n} ({ville_n})"), ln=True
    )
    pdf.ln(4)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "1. Frequence d'intervention :", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, txt_pdf(f"   - {freq_n}"), ln=True)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "2. Prestations incluses :", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 7, txt_pdf(f"   {det_n}"))

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "3. Produits et Materiel :", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, txt_pdf(f"   - {prod_n}"), ln=True)
    pdf.ln(6)

    pdf.set_font("Arial", "B", 13)
    pdf.set_fill_color(230, 238, 250)
    pdf.cell(
        0,
        12,
        txt_pdf(f"TARIF MENSUEL FORFAITAIRE : {prix_n} MAD / Mois"),
        border=1,
        ln=True,
        align="C",
        fill=True,
    )
    pdf.ln(12)

    pdf.set_font("Arial", "I", 10)
    pdf.cell(
        0,
        8,
        "Ce devis est valable pour une duree de 30 jours. Direction ImmoClean"
        " FACILITY.",
        ln=True,
        align="R",
    )
    return pdf.output(dest="S").encode("latin-1", "replace")

  devis_bytes = creer_devis_pdf(
      nom_client_devis,
      ville_devis,
      freq_devis,
      produits_devis,
      details_devis,
      prix_devis,
  )
  st.download_button(
      "📥 تحميل عرض الثمن (Télécharger Devis PDF)",
      data=devis_bytes,
      file_name=f"Devis_{nom_client_devis}.pdf".replace(" ", "_"),
      mime="application/pdf",
      use_container_width=True,
  )

# ==========================================
# 8. Gestion d'Équipe
# ==========================================
elif menu == "Gestion d'Équipe":
  st.header("👷‍♀️ إدارة فريق العمل (Gestion d'Équipe)")
  df_emp = load_data("Employes", COLS_EMP)

  with st.form("form_employe"):
    c1, c2, c3 = st.columns(3)
    with c1:
      nom_e = st.text_input("👩‍💼 اسم العاملة / العامل")
    with c2:
      tel_e = st.text_input("📞 رقم الهاتف")
    with c3:
      poste_e = st.selectbox(
          "🛠️ المنصب",
          ["Agent de nettoyage", "Superviseur", "Technicien Monobrosse"],
      )

    if st.form_submit_button("➕ إضافة للفريق", use_container_width=True):
      if nom_e.strip():
        new_e = pd.DataFrame([{
            "Nom": nom_e.strip(),
            "Téléphone": nettoyer_texte_gsheet(tel_e),
            "Poste": poste_e,
            "Photo": "",
        }])
        df_emp = pd.concat([df_emp, new_e], ignore_index=True)
        save_data("Employes", df_emp)
        st.success(f"✅ تمت إضافة {nom_e} بنجاح!")
        st.rerun()

  if not df_emp.empty:
    edited_emp = st.data_editor(
        df_emp, num_rows="dynamic", use_container_width=True
    )
    if st.button("💾 حفظ تعديلات الفريق"):
      save_data("Employes", edited_emp)
      st.success("تم الحفظ!")
      st.rerun()

# ==========================================
# 9. Planning
# ==========================================
elif menu == "Planning":
  st.header("📅 التخطيط والبرمجة الزمنية (Planning & Radar Anti-Conflits)")
  df_plan = load_data("Planning", COLS_PLAN)
  df_clients = load_data("Clients", COLS_CLIENTS)
  df_emp = load_data("Employes", COLS_EMP)

  with st.expander("➕ برمجة حصة جديدة في الجدول الزمني", expanded=True):
    with st.form("form_planning"):
      c1, c2, c3 = st.columns(3)
      with c1:
        emp_p = st.selectbox(
            "👷‍♀️ العاملة",
            df_emp["Nom"].tolist() if not df_emp.empty else ["عائشة"],
        )
        cli_p = st.selectbox(
            "🏢 الإقامة",
            df_clients["Résidence"].tolist() if not df_clients.empty else [],
        )
        jour_p = st.selectbox(
            "📆 اليوم",
            [
                "Lundi",
                "Mardi",
                "Mercredi",
                "Jeudi",
                "Vendredi",
                "Samedi",
                "Dimanche",
                "Tous les jours (Sauf Dimanche)",
                "Tous les jours",
            ],
        )
      with c2:
        h_deb_p = st.time_input("⏰ وقت البدء", value=datetime.time(9, 0))
        h_fin_p = st.time_input("⏰ وقت الانتهاء", value=datetime.time(13, 0))
        d_deb_p = st.date_input("📅 تاريخ البداية", value=datetime.date.today())
      with c3:
        freq_p = st.selectbox(
            "🔄 التكرار",
            ["Chaque semaine", "1 semaine sur 2", "1 fois par mois"],
        )
        coul_p = st.color_picker("🎨 لون البطاقة", "#1E88E5")

      if st.form_submit_button(
          "💾 إضافة للبرنامج الزمني", use_container_width=True
      ):
        conflit, msg_err = verifier_conflit_ajout(
            df_plan, emp_p, jour_p, h_deb_p, h_fin_p, d_deb_p, freq_p
        )
        if conflit:
          st.error(msg_err)
        else:
          new_p = pd.DataFrame([{
              "Employe": emp_p,
              "Client": cli_p,
              "Jour": jour_p,
              "Heure_Debut": h_deb_p.strftime("%H:%M"),
              "Heure_Fin": h_fin_p.strftime("%H:%M"),
              "Date_Debut": d_deb_p.strftime("%Y-%m-%d"),
              "Frequence": freq_p,
              "Couleur": coul_p,
              "Statut": "Actif",
          }])
          df_plan = pd.concat([df_plan, new_p], ignore_index=True)
          save_data("Planning", df_plan)
          st.success("✅ تمت إضافة الحصة للبرنامج بدون أي تداخل!")
          st.rerun()

  if not df_plan.empty:
    st.subheader("📋 جدول البرمجة الكامل")
    edited_plan = st.data_editor(
        df_plan, num_rows="dynamic", use_container_width=True
    )
    if st.button("💾 حفظ تعديلات الجدول الزمني"):
      save_data("Planning", edited_plan)
      st.success("✅ تم تحديث البرمجة الزمنية!")
      st.rerun()
