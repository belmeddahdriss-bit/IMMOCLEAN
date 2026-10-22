import streamlit as st
import pandas as pd
import os
import datetime
import re
import json
import html as _html
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

# --- دالة تنظيف وإصلاح أرقام الهاتف ---
def nettoyer_texte_gsheet(val):
    s = str(val).strip()
    if s.startswith("+") or s.startswith("=") or s.startswith("'"):
        s = s.lstrip("+='").strip()
    if s.endswith(".0"):
        s = s[:-2]
    if len(s) == 9 and s.isdigit() and s[0] in ["5", "6", "7"]:
        s = "0" + s
    return s

# --- دوال جلب وحفظ البيانات ---
def load_data(sheet_name, columns):
    try:
        ws = sh.worksheet(sheet_name)
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame(columns=columns)
        df = pd.DataFrame(records)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        first_col = columns[0]
        df = df[df[first_col].astype(str).str.strip().replace("nan", "") != ""].reset_index(drop=True)
        if "Téléphone" in df.columns:
            df["Téléphone"] = df["Téléphone"].apply(nettoyer_texte_gsheet)
        return df
    except Exception as e:
        st.warning(f"⚠️ تعذر تحميل ورقة '{sheet_name}' مؤقتاً: {e}")
        return pd.DataFrame(columns=columns)

def save_data(sheet_name, df):
    try:
        ws = sh.worksheet(sheet_name)
        df_clean = df.copy()
        if "Téléphone" in df_clean.columns:
            df_clean["Téléphone"] = df_clean["Téléphone"].apply(nettoyer_texte_gsheet)
        ws.clear()
        set_with_dataframe(ws, df_clean, string_escaping="full")
    except Exception as e:
        st.error(f"⚠️ خطأ أثناء الحفظ في '{sheet_name}': {e}")

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

# --- دالة تنظيف النصوص للـ PDF ---
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
        "الاثنين": "Lundi",
        "الثلاثاء": "Mardi",
        "الأربعاء": "Mercredi",
        "الخميس": "Jeudi",
        "الجمعة": "Vendredi",
        "السبت": "Samedi",
        "عائشة": "Aicha",
        "فاطمة الزهراء": "Fatima Zahra"
    }
    for ar, fr in remplacements.items():
        t = t.replace(ar, fr)
    return t.encode('latin-1', 'replace').decode('latin-1')

# --- أسماء الأعمدة في كل ورقة ---
COLS_CLIENTS = ["Résidence", "Secteur", "Responsable", "Téléphone", "Services", "Produits", "Prix (MAD)", "Jour de paiement"]
COLS_HIST = ["Date", "Résidence", "Employé", "Tâches", "Statut"]
COLS_EMP = ["Nom", "Téléphone", "Poste", "Photo"]
COLS_FIN = ["Date", "Type", "Categorie", "Montant (MAD)", "Description", "Paye_Par"]
COLS_PLAN = ["Employe", "Client", "Jour", "Heure_Debut", "Heure_Fin", "Date_Debut", "Frequence", "Couleur", "Statut"]

# ===============================================================
# 📅 كود الشبكة الأسبوعية + توليد PDF (Planning en grille)
# ===============================================================
PALETTE = [
    "#1E88E5", "#E91E63", "#43A047", "#FB8C00", "#8E24AA",
    "#00ACC1", "#F4511E", "#6D4C41", "#3949AB", "#7CB342",
]
JOURS_FR = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi",
    4: "Vendredi", 5: "Samedi", 6: "Dimanche",
}
JOURS_AR = {
    0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس",
    4: "الجمعة", 5: "السبت", 6: "الأحد",
}
FREQ_BADGE = {
    "Chaque semaine": "",
    "1 semaine sur 2": "↔️ أسبوع إيه وأسبوع لا",
    "1 fois par mois": "📆 مرة فالشهر",
}

CSS_PLANNING = """
<style>
.pg-wrap{overflow-x:auto;padding-bottom:6px}
.pg{display:grid;gap:8px;min-width:900px}
.pg-day{background:#fff;border-radius:12px;padding:8px;
  box-shadow:0 2px 8px rgba(0,0,0,.06);min-height:120px}
.pg-day.today{outline:2px solid #1E88E5}
.pg-head{text-align:center;font-weight:700;color:#0b3d91;
  border-bottom:1px solid #eee;padding-bottom:6px;margin-bottom:8px}
.pg-head small{display:block;color:#888;font-weight:400}
.pc{border-radius:8px;padding:6px 8px;margin-bottom:6px;font-size:13px;
  line-height:1.35;color:#222}
.pc .t{font-size:11px;color:#666;font-weight:700}
.pc .c{font-weight:700;font-size:14px}
.pc .e{font-size:12px;color:#444}
.pc .b{font-size:11px;color:#555;margin-top:2px}
.pc.rep{opacity:.45;text-decoration:line-through}
.pc.dup{outline:2px solid #d32f2f}
.pg-empty{color:#bbb;text-align:center;font-size:12px;padding-top:20px}
.leg{display:inline-block;padding:3px 10px;border-radius:12px;
  color:#fff;font-size:12px;margin:0 6px 6px 0}
</style>
"""

def _esc(x):
    return _html.escape(str(x))

def _couleur_employe(nom, noms_tries):
    try:
        return PALETTE[noms_tries.index(str(nom)) % len(PALETTE)]
    except ValueError:
        return "#607D8B"

def _couleur_carte(row, mode, noms_emp, noms_cli):
    if mode == "cli":
        return _couleur_employe(row.get("Client", ""), noms_cli)
    if mode == "row":
        c = str(row.get("Couleur", ""))
        if len(c) == 7 and c.startswith("#"):
            return c
    return _couleur_employe(row.get("Employe", ""), noms_emp)

def _jours_se_chevauchent(j1, j2):
    tous = ("Tous les jours", "Tous les jours (Sauf Dimanche)")
    if j1 == j2 or j1 == "Tous les jours" or j2 == "Tous les jours":
        return True
    if j1 == tous[1]:
        return j2 != "Dimanche"
    if j2 == tous[1]:
        return j1 != "Dimanche"
    return False

def verifier_doublon_client(df_plan, client, jour, d_deb, freq):
    if df_plan is None or df_plan.empty:
        return False, ""
    for _, row in df_plan[df_plan["Client"].astype(str) == str(client)].iterrows():
        r_freq = str(row.get("Frequence", ""))
        if r_freq == "Exception":
            continue
        r_jour = str(row.get("Jour", ""))
        if not _jours_se_chevauchent(r_jour, jour):
            continue
        if freq == "1 semaine sur 2" and r_freq == "1 semaine sur 2":
            try:
                d0 = datetime.datetime.strptime(str(row["Date_Debut"]), "%Y-%m-%d").date()
                a, b = d_deb.isocalendar(), d0.isocalendar()
                if abs((a[0] - b[0]) * 52 + (a[1] - b[1])) % 2 != 0:
                    continue
            except Exception:
                pass
        return True, (
            f"⚠️ الإقامة **{client}** مبرمجة ديجا نهار **{r_jour}** "
            f"(مع **{row.get('Employe','')}**، {r_freq}). "
            "ما يمكنش تنزل مرتين فنفس النهار."
        )
    return False, ""

def _tache_active(row, date):
    freq = str(row.get("Frequence", "Chaque semaine"))
    if freq == "Exception":
        return str(row.get("Date_Debut", "")) == str(date)

    jour_row = str(row.get("Jour", ""))
    nom_jour = JOURS_FR[date.weekday()]
    ok_jour = (
        jour_row == nom_jour
        or jour_row == "Tous les jours"
        or (jour_row == "Tous les jours (Sauf Dimanche)" and nom_jour != "Dimanche")
    )
    if not ok_jour:
        return False
    try:
        d0 = datetime.datetime.strptime(str(row["Date_Debut"]), "%Y-%m-%d").date()
    except Exception:
        return False
    iso, iso0 = date.isocalendar(), d0.isocalendar()
    diff = (iso[0] - iso0[0]) * 52 + (iso[1] - iso0[1])
    if diff < 0:
        return False
    return (
        freq == "Chaque semaine"
        or (freq == "1 semaine sur 2" and diff % 2 == 0)
        or (freq == "1 fois par mois" and diff % 4 == 0)
    )

def _taches_du_jour(df_plan, date):
    out = []
    reports = df_plan[df_plan["Frequence"] == "Exception"]
    for _, row in df_plan.iterrows():
        if not _tache_active(row, date):
            continue
        freq = str(row.get("Frequence", ""))
        reportee = False
        if freq != "Exception":
            reportee = not reports[
                (reports["Client"] == row["Client"])
                & (reports["Statut"] == f"Report:{date}")
            ].empty
        out.append({"row": row, "exception": freq == "Exception", "reportee": reportee})
    out.sort(key=lambda t: str(t["row"].get("Heure_Debut", "")))
    return out

def _carte_html(t, couleur, doublon):
    r = t["row"]
    cls = "pc" + (" rep" if t["reportee"] else "") + (" dup" if doublon else "")
    freq = str(r.get("Frequence", ""))
    badge = FREQ_BADGE.get(freq, "")
    if t["exception"]:
        badge = "🔄 حصة مؤجلة"
    if t["reportee"]:
        badge = "⏭️ تم تأجيلها"
    if doublon:
        badge = "⚠️ نفس الإقامة مرتين فنفس النهار"
    badge_html = f'<div class="b">{badge}</div>' if badge else ""
    return (
        f'<div class="{cls}" style="background:{couleur}1F;border-left:5px solid {couleur}">'
        f'<div class="t">⏰ {_esc(r.get("Heure_Debut",""))} - {_esc(r.get("Heure_Fin",""))}</div>'
        f'<div class="c">🏢 {_esc(r.get("Client",""))}</div>'
        f'<div class="e">👷‍♀️ {_esc(r.get("Employe",""))}</div>'
        f"{badge_html}</div>"
    )

# --- 📄 دالة توليد ملف PDF لاستعمال الزمن الأسبوعي (Landscape A4) ---
def generer_planning_pdf(df_f, dates, sel_emp):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(11, 61, 145)
    pdf.cell(0, 8, "IMMOCLEAN FACILITY - PLANNING HEBDOMADAIRE", ln=True, align="C")

    d_deb_str = dates[0].strftime('%d/%m/%Y')
    d_fin_str = dates[-1].strftime('%d/%m/%Y')
    emp_str = ", ".join(sel_emp) if len(sel_emp) <= 4 else f"{len(sel_emp)} Employes"

    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, txt_pdf(f"Semaine du {d_deb_str} au {d_fin_str}  |  Equipe : {emp_str}"), ln=True, align="C")
    pdf.ln(4)

    nb_cols = len(dates)
    largeur_totale = 277
    col_w = largeur_totale / nb_cols

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(30, 136, 229)
    pdf.set_text_color(255, 255, 255)
    for d in dates:
        titre_jour = f"{JOURS_FR[d.weekday()]} {d.strftime('%d/%m')}"
        pdf.cell(col_w, 9, txt_pdf(titre_jour), border=1, align="C", fill=True)
    pdf.ln()

    taches_par_jour = []
    max_taches = 0
    for d in dates:
        t_list = [t for t in _taches_du_jour(df_f, d) if not t["reportee"]]
        taches_par_jour.append(t_list)
        if len(t_list) > max_taches:
            max_taches = len(t_list)

    pdf.set_text_color(0, 0, 0)
    if max_taches == 0:
        pdf.set_font("Arial", "I", 11)
        pdf.cell(largeur_totale, 15, "Aucune seance programmee pour cette semaine.", border=1, ln=True, align="C")
    else:
        for i in range(max_taches):
            pdf.set_font("Arial", "B", 8)
            pdf.set_fill_color(240, 244, 248)
            for j in range(nb_cols):
                if i < len(taches_par_jour[j]):
                    r = taches_par_jour[j][i]["row"]
                    txt_h = f"{r.get('Heure_Debut','')} - {r.get('Heure_Fin','')}"
                    pdf.cell(col_w, 5, txt_pdf(txt_h), border="LTR", align="C", fill=True)
                else:
                    pdf.cell(col_w, 5, "", border="LTR", align="C")
            pdf.ln()

            pdf.set_font("Arial", "B", 9)
            for j in range(nb_cols):
                if i < len(taches_par_jour[j]):
                    r = taches_par_jour[j][i]["row"]
                    cli = txt_pdf(str(r.get("Client", "")))[:22]
                    pdf.cell(col_w, 6, cli, border="LR", align="C")
                else:
                    pdf.cell(col_w, 6, "", border="LR", align="C")
            pdf.ln()

            pdf.set_font("Arial", "", 8)
            pdf.set_text_color(60, 60, 60)
            for j in range(nb_cols):
                if i < len(taches_par_jour[j]):
                    r = taches_par_jour[j][i]["row"]
                    emp = txt_pdf(str(r.get("Employe", "")))[:22]
                    pdf.cell(col_w, 5, f"Agent: {emp}", border="LBR", align="C")
                else:
                    pdf.cell(col_w, 5, "", border="LBR", align="C")
            pdf.set_text_color(0, 0, 0)
            pdf.ln()

    pdf.ln(6)
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, f"Document genere le {datetime.date.today().strftime('%d/%m/%Y')} - ImmoClean FACILITY Kenitra", ln=True, align="R")

    return pdf.output(dest="S").encode("latin-1", "replace")


def afficher_planning_grille(df_plan):
    if df_plan is None or df_plan.empty:
        st.info("الجدول الزمني فارغ حالياً.")
        return

    st.markdown(CSS_PLANNING, unsafe_allow_html=True)

    noms = sorted(df_plan["Employe"].astype(str).unique())
    clients = sorted(df_plan["Client"].astype(str).unique())

    if "plan_offset" not in st.session_state:
        st.session_state.plan_offset = 0
    n1, n2, n3 = st.columns([1, 1, 1])
    if n1.button("◀ الأسبوع السابق", use_container_width=True):
        st.session_state.plan_offset -= 1
    if n2.button("📍 هذا الأسبوع", use_container_width=True):
        st.session_state.plan_offset = 0
    if n3.button("الأسبوع التالي ▶", use_container_width=True):
        st.session_state.plan_offset += 1

    aujourdhui = datetime.date.today()
    lundi = aujourdhui - datetime.timedelta(days=aujourdhui.weekday())
    lundi += datetime.timedelta(weeks=st.session_state.plan_offset)
    st.markdown(
        f"**🗓️ من {lundi.strftime('%d/%m')} إلى "
        f"{(lundi + datetime.timedelta(days=5)).strftime('%d/%m/%Y')}**"
    )

    f1, f2 = st.columns(2)
    sel_emp = f1.multiselect("👷‍♀️ تصفية العاملات", noms, default=noms)
    sel_cli = f2.multiselect("🏢 تصفية الإقامات", clients, default=clients)
    
    c_opt1, c_opt2, c_opt3 = st.columns([2, 2, 1])
    with c_opt1:
        vue = st.radio("طريقة العرض", ["📅 حسب الأيام", "👷‍♀️ حسب العاملة"], horizontal=True)
    with c_opt2:
        cm = st.radio("🎨 التلوين حسب", ["العاملة", "الإقامة", "اللون المختار"], horizontal=True)
    with c_opt3:
        st.write("")
        avec_dimanche = st.checkbox("إظهار الأحد", value=False)

    mode = {"العاملة": "emp", "الإقامة": "cli", "اللون المختار": "row"}[cm]

    df_f = df_plan[
        df_plan["Employe"].astype(str).isin(sel_emp)
        & df_plan["Client"].astype(str).isin(sel_cli)
    ]

    if mode in ("emp", "cli"):
        items = noms if mode == "emp" else clients
        leg = "".join(
            f'<span class="leg" style="background:{_couleur_employe(n, items)}">{_esc(n)}</span>'
            for n in items
        )
        st.markdown(leg, unsafe_allow_html=True)

    nb_jours = 7 if avec_dimanche else 6
    dates = [lundi + datetime.timedelta(days=i) for i in range(nb_jours)]

    if vue.startswith("📅"):
        colonnes = []
        for d in dates:
            taches = _taches_du_jour(df_f, d)
            vus = {}
            for t in taches:
                if not t["reportee"]:
                    c = str(t["row"]["Client"])
                    vus[c] = vus.get(c, 0) + 1
            cartes = "".join(
                _carte_html(
                    t,
                    _couleur_carte(t["row"], mode, noms, clients),
                    vus.get(str(t["row"]["Client"]), 0) > 1 and not t["reportee"],
                )
                for t in taches
            ) or '<div class="pg-empty">—</div>'
            today = " today" if d == aujourdhui else ""
            colonnes.append(
                f'<div class="pg-day{today}"><div class="pg-head">'
                f"{JOURS_AR[d.weekday()]}<small>{JOURS_FR[d.weekday()]} "
                f"{d.strftime('%d/%m')}</small></div>{cartes}</div>"
            )
        st.markdown(
            f'<div class="pg-wrap"><div class="pg" style="grid-template-columns:'
            f'repeat({nb_jours},1fr)">{"".join(colonnes)}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        for emp in sel_emp:
            couleur = _couleur_employe(emp, noms)
            df_e = df_f[df_f["Employe"].astype(str) == emp]
            lignes = ""
            total = 0
            for d in dates:
                taches = [
                    t for t in _taches_du_jour(df_e, d) if not t["reportee"]
                ]
                if not taches:
                    continue
                total += len(taches)
                cartes = "".join(
                    _carte_html(t, _couleur_carte(t["row"], mode, noms, clients), False)
                    for t in taches
                )
                lignes += (
                    f'<div class="pg-head" style="text-align:right">'
                    f"{JOURS_AR[d.weekday()]} {d.strftime('%d/%m')}</div>{cartes}"
                )
            st.markdown(
                f'<div class="pg-day" style="border-top:5px solid {couleur};'
                f'margin-bottom:12px"><h4 style="margin:0 0 8px 0;color:{couleur}'
                f' !important">👷‍♀️ {_esc(emp)} — {total} حصة</h4>'
                f'{lignes or "<div class=pg-empty>لا توجد حصص</div>"}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    pdf_planning_bytes = generer_planning_pdf(df_f, dates, sel_emp)
    nom_fichier_plan = f"Planning_ImmoClean_{dates[0].strftime('%d-%m-%Y')}.pdf"
    st.download_button(
        label="📥 تحميل استعمال الزمن الأسبوعي (Télécharger Planning PDF)",
        data=pdf_planning_bytes,
        file_name=nom_fichier_plan,
        mime="application/pdf",
        use_container_width=True,
    )

# --- 🚨 دوال رادار تداخل الأوقات ---
def verifier_conflit_ajout(df_plan, emp, jour, h_deb, h_fin, d_deb, freq):
    if df_plan.empty:
        return False, ""
    
    emp_tasks = df_plan[df_plan["Employe"] == emp]
    for _, row in emp_tasks.iterrows():
        if str(row.get("Frequence", "")) == "Exception":
            continue
            
        r_jour = str(row.get("Jour", ""))
        match_jour = _jours_se_chevauchent(r_jour, jour)

        if match_jour:
            try:
                r_deb = datetime.datetime.strptime(str(row["Heure_Debut"]), "%H:%M").time()
                r_fin = datetime.datetime.strptime(str(row["Heure_Fin"]), "%H:%M").time()
                
                if (h_deb < r_fin) and (h_fin > r_deb):
                    r_freq = str(row.get("Frequence", "Chaque semaine"))
                    r_date_deb = datetime.datetime.strptime(str(row["Date_Debut"]), "%Y-%m-%d").date()
                    
                    conflit_semaine = True
                    if freq == "1 semaine sur 2" and r_freq == "1 semaine sur 2":
                        sem1, an1 = d_deb.isocalendar()[1], d_deb.isocalendar()[0]
                        sem2, an2 = r_date_deb.isocalendar()[1], r_date_deb.isocalendar()[0]
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
        
    nom_jour = JOURS_FR[date_cible.weekday()]
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
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric(label="🏢 إجمالي الإقامات", value=f"{total_clients}")
    with col2: st.metric(label="📜 قيمة العقود الشهرية", value=f"{total_contrats_mad:,.0f} MAD")
    with col3: st.metric(label="🚨 واجب استخلاصها", value=f"{residences_a_facturer}")
    with col4: st.metric(label="💰 المداخيل المستلمة", value=f"{total_revenus:,.0f} MAD")
    with col5: st.metric(label="💎 الصافي (Solde Net)", value=f"{solde_net:,.0f} MAD")
    
    if clients_en_retard:
        st.markdown(f"""
        <div style="background-color: #ffebee; border-left: 6px solid #d32f2f; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h4 style="color: #c62828 !important; margin: 0;">🚨 تنبيه الأداء: إقامات وصلت لوقت الخلاص!</h4>
            <p style="color: #b71c1c; font-size: 16px; font-weight: bold; margin: 5px 0 0 0;">🏢 {'  |  🏢 '.join(clients_en_retard)}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    with st.expander("🏢 جدول جميع الإقامات المتعاقد معها (الإقامات باللون الأحمر وصل وقت خلاصها 🚨)", expanded=True):
        if not df_clients.empty:
            df_cl_display = df_clients.copy()
            df_cl_display["Prix (MAD)"] = pd.to_numeric(df_cl_display["Prix (MAD)"], errors='coerce').fillna(0)
            
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
        dates_a_afficher = [
            ("اليوم", datetime.date.today()),
            ("غداً", datetime.date.today() + datetime.timedelta(days=1))
        ]
        
        for label, date_cible in dates_a_afficher:
            nom_jour_cible = JOURS_FR[date_cible.weekday()]
            date_cible_str = str(date_cible)
            
            st.markdown(f"#### 🔹 {label} ({nom_jour_cible} {date_cible.strftime('%d/%m/%Y')})")
            
            taches_jour = [ row for _, row in df_plan.iterrows() if _tache_active(row, date_cible) ]
            df_jour = pd.DataFrame(taches_jour)
            
            if not df_jour.empty:
                df_jour = df_jour.sort_values(by="Heure_Debut").reset_index(drop=True)
                cols = st.columns(3)
                for index, tache in df_jour.iterrows():
                    couleur = tache.get("Couleur", "#1E88E5")
                    client_nom = tache["Client"]
                    emp_nom = tache["Employe"]
                    freq_tache = str(tache.get("Frequence", ""))
                    
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
                    
                    deja_pointe = False
                    if not df_hist.empty:
                        verif_p = df_hist[(df_hist["Date"].astype(str) == date_cible_str) & (df_hist["Résidence"] == client_nom)]
                        if not verif_p.empty:
                            deja_pointe = True
                    
                    with cols[index % 3]:
                        st.markdown(f"""
                        <div style="background: white; border-top: 5px solid {couleur}; padding: 15px; border-radius: 10px; box-shadow: 0 3px 8px rgba(0,0,0,0.08); margin-bottom: 10px;">
                            <div style="font-size: 13px; color: #777; font-weight: bold;">⏰ {tache['Heure_Debut']} - {tache['Heure_Fin']}</div>
                            <div style="font-size: 18px; font-weight: bold; color: #222; margin: 4px 0;">🏢 {client_nom}</div>
                            {secteur_html}
                            <div style="font-size: 14px; color: #444; margin-bottom: 8px;">👷‍♀️ العاملة: <b>{emp_nom}</b></div>
                            <span style="background-color: {badge_color}; color: white; padding: 3px 8px; border-radius: 5px; font-size: 12px;">{badge}</span>
                            <div style="margin-top: 8px; font-size: 13px; color: #333;">🛠️ <b>المهام:</b> {taches_str}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if est_reportee:
                            st.warning(f"🔄 مؤجلة إلى: {date_report_vers}")
                        elif deja_pointe:
                            st.success("✅ تم تسجيل الحضور (Pointé)")
                        else:
                            c_btn1, c_btn2 = st.columns(2)
                            with c_btn1:
                                if st.button("✅ Pointage", key=f"pt_{label}_{index}", use_container_width=True):
                                    tache_save = " + ".join(taches_hist_list) if taches_hist_list else "Nettoyage"
                                    new_hist = pd.DataFrame([{
                                        "Date": date_cible_str,
                                        "Résidence": client_nom,
                                        "Employé": emp_nom,
                                        "Tâches": tache_save,
                                        "Statut": "En attente"
                                    }])
                                    df_hist = pd.concat([df_hist, new_hist], ignore_index=True)
                                    save_data("Historique", df_hist)
                                    st.rerun()
                            with c_btn2:
                                with st.popover("🔄 تأجيل"):
                                    new_d = st.date_input("تاريخ جديد", value=date_cible + datetime.timedelta(days=1), key=f"nd_{label}_{index}")
                                    new_hd = st.time_input("وقت البدء", value=datetime.time(9, 0), key=f"nhd_{label}_{index}")
                                    new_hf = st.time_input("وقت الانتهاء", value=datetime.time(12, 0), key=f"nhf_{label}_{index}")
                                    if st.button("تأكيد التأجيل", key=f"ok_rep_{label}_{index}"):
                                        conflit, msg_c = verifier_conflit_report(df_plan, emp_nom, new_d, new_hd, new_hf)
                                        if conflit:
                                            st.error(msg_c)
                                        else:
                                            new_ex = pd.DataFrame([{
                                                "Employe": emp_nom,
                                                "Client": client_nom,
                                                "Jour": JOURS_FR[new_d.weekday()],
                                                "Heure_Debut": new_hd.strftime("%H:%M"),
                                                "Heure_Fin": new_hf.strftime("%H:%M"),
                                                "Date_Debut": new_d.strftime("%Y-%m-%d"),
                                                "Frequence": "Exception",
                                                "Couleur": "#FF9800",
                                                "Statut": f"Report:{date_cible_str}"
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
            secteur = st.text_input("📍 الحي / المنطقة (Secteur - ex: Maamora, Ville Haute)")
            responsable = st.text_input("👤 اسم المسؤول / السانديك (Responsable)")
            telephone = st.text_input("📞 رقم الهاتف (Téléphone)")
        with c2:
            freq_passage = st.selectbox("🔄 وتيرة العمل (Fréquence)", [
                "1 fois/semaine (4/mois)", 
                "2 fois/semaine (8/mois)", 
                "3 fois/semaine (12/mois)", 
                "Tous les jours sauf Dimanche (26/mois)",
                "1 fois / 15 jours (2/mois)"
            ])
            zones_clean = st.multiselect("🧹 الأماكن المشمولة بالتنظيف", ["Escaliers", "Terrasse", "Sous-sol / Parking", "Bureau", "Jardin"], default=["Escaliers", "Terrasse"])
            produits = st.selectbox("🧴 مواد النظافة (Produits)", ["Inclus (ImmoClean)", "Fournis par le Syndic"])
            prix = st.number_input("💰 السعر الشهري (Prix en MAD)", min_value=0, value=600, step=50)
            jour_paie = st.text_input("📅 يوم الأداء (Jour de paiement)", value="Le 1er du mois")
            
        submitted = st.form_submit_button("💾 حفظ الإقامة الجديدة", use_container_width=True)
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
                    "Jour de paiement": jour_paie
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
        edited_df = st.data_editor(df_clients, num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 حفظ التعديلات (Enregistrer)", type="primary"):
            edited_df = edited_df[edited_df["Résidence"].astype(str).str.strip().replace("nan", "") != ""].reset_index(drop=True)
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
    
    tab1, tab2, tab3 = st.tabs(["📝 تسجيل حصة عمل (Pointage)", "💰 استخلاص شهر مكتمل (Paiement)", "📜 سجل جميع الحصص (Historique)"])
    
    with tab1:
        st.subheader("تسجيل مرور عاملة في إقامة")
        with st.form("form_pointage_manuel"):
            c1, c2 = st.columns(2)
            with c1:
                d_pt = st.date_input("📅 التاريخ", value=datetime.date.today())
                res_pt = st.selectbox("🏢 الإقامة", df_clients["Résidence"].tolist() if not df_clients.empty else [])
            with c2:
                emp_pt = st.selectbox("👷‍♀️ العاملة", df_emp["Nom"].tolist() if not df_emp.empty else ["عائشة"])
                taches_pt = st.multiselect("🧹 المهام المنجزة", ["Escaliers", "Terrasse", "Parking", "Bureau"], default=["Escaliers"])
            
            if st.form_submit_button("✅ تأكيد وتسجيل الحصة", use_container_width=True):
                new_h = pd.DataFrame([{
                    "Date": str(d_pt),
                    "Résidence": res_pt,
                    "Employé": emp_pt,
                    "Tâches": " + ".join(taches_pt),
                    "Statut": "En attente"
                }])
                df_hist = pd.concat([df_hist, new_h], ignore_index=True)
                save_data("Historique", df_hist)
                st.success(f"✅ تم تسجيل الحصة لـ {res_pt} بنجاح!")
                st.rerun()
                
    with tab2:
        st.subheader("💰 تأكيد خلاص إقامة وتحويلها للمداخيل")
        if not df_clients.empty:
            res_pay = st.selectbox("🏢 اختر الإقامة لتأكيد خلاصها", df_clients["Résidence"].tolist())
            info_c = df_clients[df_clients["Résidence"] == res_pay].iloc[0]
            cible_c = calculer_cible_passages(info_c.get("Services", ""))
            prix_c = pd.to_numeric(info_c.get("Prix (MAD)", 0), errors='coerce')
            
            en_attente_df = df_hist[(df_hist["Résidence"] == res_pay) & (df_hist["Statut"] == "En attente")]
            nb_att = len(en_attente_df)
            
            st.info(f"📊 عدد الحصص غير المؤداة حالياً لـ **{res_pay}** هو: **`{nb_att}`** من أصل **`{cible_c}`** حصص فالشهر.")
            montant_encaisse = st.number_input("💵 المبلغ المستلم (MAD)", value=int(prix_c) if pd.notna(prix_c) else 500, step=50)
            encaisse_par = st.selectbox("👤 شكون تسلم الفلوس / فين دخلات", ["Caisse (صندوق الشركة)", "Driss", "Younnes"])
            
            if st.button("💰 تأكيد استلام المبلغ وتصفية الحصص", type="primary"):
                df_hist.loc[(df_hist["Résidence"] == res_pay) & (df_hist["Statut"] == "En attente"), "Statut"] = "Payé"
                save_data("Historique", df_hist)
                
                new_fin = pd.DataFrame([{
                    "Date": str(datetime.date.today()),
                    "Type": "Entrée (Revenu)",
                    "Categorie": "Abonnement Résidence",
                    "Montant (MAD)": montant_encaisse,
                    "Description": f"Paiement mensuel - {res_pay}",
                    "Paye_Par": encaisse_par
                }])
                df_fin = pd.concat([df_fin, new_fin], ignore_index=True)
                save_data("Finances", df_fin)
                st.success(f"🎉 تم تسجيل خلاص **{res_pay}** ({montant_encaisse} MAD) وتحديث الحصص إلى 'Payé'!")
                st.rerun()
                
    with tab3:
        if not df_hist.empty:
            edited_hist = st.data_editor(df_hist, num_rows="dynamic", use_container_width=True)
            if st.button("💾 حفظ تعديلات السجل"):
                save_data("Historique", edited_hist)
                st.success("تم الحفظ!")
                st.rerun()
        else:
            st.info("لا توجد حصص مسجلة بعد.")

# ==========================================
# 5. Finances & Trésorerie
# ==========================================
elif menu == "Finances & Trésorerie":
    st.header("💼 المالية والمحاسبة (Finances & Trésorerie)")
    df_fin = load_data("Finances", COLS_FIN)
    
    if not df_fin.empty:
        df_dep = df_fin[df_fin["Type"] == "Sortie (Dépense)"].copy()
        df_dep["Montant (MAD)"] = pd.to_numeric(df_dep["Montant (MAD)"], errors='coerce').fillna(0)
        
        dep_driss = df_dep[df_dep["Paye_Par"].astype(str).str.contains("Driss", case=False, na=False)]["Montant (MAD)"].sum()
        dep_younnes = df_dep[df_dep["Paye_Par"].astype(str).str.contains("Younnes|Younes", case=False, na=False)]["Montant (MAD)"].sum()
        dep_caisse = df_dep[df_dep["Paye_Par"].astype(str).str.contains("Caisse|صندوق", case=False, na=False)]["Montant (MAD)"].sum()
        
        st.markdown("#### 💳 تفصيل المصاريف حسب الدافع (شكون خسر الفلوس):")
        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            st.metric(label="👤 مصاريف خلصها Driss", value=f"{dep_driss:,.0f} MAD")
        with c_p2:
            st.metric(label="👤 مصاريف خلصها Younnes", value=f"{dep_younnes:,.0f} MAD")
        with c_p3:
            st.metric(label="🏦 مصاريف من صندوق الشركة (Caisse)", value=f"{dep_caisse:,.0f} MAD")
        st.markdown("---")
    
    with st.expander("➕ تسجيل عملية مالية جديدة (مدخول أو مصروف)", expanded=True):
        with st.form("form_finance"):
            c1, c2, c3 = st.columns(3)
            with c1:
                d_fin = st.date_input("📅 التاريخ", value=datetime.date.today())
                type_fin = st.selectbox("🔄 نوع العملية", ["Sortie (Dépense)", "Entrée (Revenu)"])
            with c2:
                cat_fin = st.selectbox("📂 التصنيف", ["Produits & Matériel", "Salaires", "Transport", "Publicité (Ads)", "Abonnement Résidence", "Autre"])
                mnt_fin = st.number_input("💰 المبلغ (MAD)", min_value=0, step=10)
            with c3:
                desc_fin = st.text_input("📝 الوصف / البيان")
                paye_par_fin = st.selectbox("👤 شكون خلصها / صندوق الأداء (Payé par)", ["Driss", "Younnes", "Caisse (صندوق الشركة)"])
                
            if st.form_submit_button("💾 تسجيل العملية المالية", use_container_width=True):
                new_f = pd.DataFrame([{
                    "Date": str(d_fin),
                    "Type": type_fin,
                    "Categorie": cat_fin,
                    "Montant (MAD)": mnt_fin,
                    "Description": desc_fin,
                    "Paye_Par": paye_par_fin
                }])
                df_fin = pd.concat([df_fin, new_f], ignore_index=True)
                save_data("Finances", df_fin)
                st.success("✅ تمت إضافة العملية المالية بنجاح!")
                st.rerun()
                
    if not df_fin.empty:
        st.markdown("---")
        st.subheader("📊 سجل المعاملات المالية (Historique Financier)")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtre_personne = st.selectbox(
                "🔍 فلتر حسب الشخص / الصندوق (شكون خلص أو تسلم):",
                ["الكل (Tous)", "Driss", "Younnes", "Caisse (صندوق الشركة)"]
            )
        with col_f2:
            filtre_type = st.selectbox(
                "🔄 فلتر حسب نوع العملية:",
                ["الكل (مداخيل + مصاريف)", "Sortie (Dépense) - المصاريف فقط", "Entrée (Revenu) - المداخيل فقط"]
            )
            
        df_fin_affiche = df_fin.copy()
        
        if filtre_personne == "Driss":
            df_fin_affiche = df_fin_affiche[df_fin_affiche["Paye_Par"].astype(str).str.contains("Driss", case=False, na=False)]
        elif filtre_personne == "Younnes":
            df_fin_affiche = df_fin_affiche[df_fin_affiche["Paye_Par"].astype(str).str.contains("Younnes|Younes", case=False, na=False)]
        elif filtre_personne == "Caisse (صندوق الشركة)":
            df_fin_affiche = df_fin_affiche[df_fin_affiche["Paye_Par"].astype(str).str.contains("Caisse|صندوق", case=False, na=False)]
            
        if "Sortie" in filtre_type:
            df_fin_affiche = df_fin_affiche[df_fin_affiche["Type"] == "Sortie (Dépense)"]
        elif "Entrée" in filtre_type:
            df_fin_affiche = df_fin_affiche[df_fin_affiche["Type"] == "Entrée (Revenu)"]
            
        total_filtre = pd.to_numeric(df_fin_affiche["Montant (MAD)"], errors='coerce').fillna(0).sum()
        st.info(f"📌 **عدد العمليات المعروضة:** `{len(df_fin_affiche)}`  |  💰 **مجموع المبالغ فـ هاد الفلتر:** `{total_filtre:,.2f} MAD`")
        
        is_tout = (filtre_personne == "الكل (Tous)" and filtre_type == "الكل (مداخيل + مصاريف)")
        
        edited_fin = st.data_editor(
            df_fin_affiche,
            num_rows="dynamic" if is_tout else "fixed",
            use_container_width=True,
            key="editor_finances"
        )
        
        if st.button("💾 حفظ تعديلات المالية"):
            if is_tout:
                save_data("Finances", edited_fin)
            else:
                df_fin.update(edited_fin)
                save_data("Finances", df_fin)
            st.success("✅ تم حفظ التعديلات بنجاح!")
            st.rerun()

# ==========================================
# 6. Générer Reçu
# ==========================================
elif menu == "Générer Reçu":
    st.header("🧾 مولد التوصيلات (Reçu de Paiement avec Historique des Séances)")
    
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_hist = load_data("Historique", COLS_HIST)
    
    if df_clients.empty:
        st.warning("⚠️ لا توجد إقامات مسجلة حالياً فـ قاعدة البيانات.")
    else:
        liste_res = [str(r).strip() for r in df_clients["Résidence"].dropna().unique() if str(r).strip() != ""]
        
        col1, col2 = st.columns(2)
        with col1:
            res_choisie = st.selectbox("🏢 اختر الإقامة (Résidence)", liste_res)
            
            client_info = df_clients[df_clients["Résidence"].astype(str).str.strip() == res_choisie]
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
            montant = st.number_input("💰 المبلغ المؤدى (Montant en MAD)", value=prix_defaut, step=50)
            
        with col2:
            mode_reglement = st.selectbox("💳 طريقة الأداء (Mode de règlement)", ["Espèces", "Virement", "Chèque"])
            st.info(f"📋 **تفاصيل العقد:** `{services_client}`  \n🎯 **عدد الحصص الشهري في العقد:** `{cible_auto} حصص`")
            
            nb_seances = st.number_input("🔢 عدد الحصص الأخيرة التي ستُطبع في الوصل:", min_value=1, max_value=35, value=int(cible_auto))
            statut_filtre = st.radio(
                "🔍 تصفية الحصص المسحوبة من Historique:",
                ["آخر الحصص المنجزة (الكل)", "فقط الحصص المؤداة (Payé)", "فقط الحصص في الانتظار (En attente)"],
                horizontal=True
            )
            
        df_seances_recu = pd.DataFrame()
        if not df_hist.empty and "Résidence" in df_hist.columns:
            df_sub = df_hist[df_hist["Résidence"].astype(str).str.strip() == res_choisie].copy()
            
            if statut_filtre == "فقط الحصص المؤداة (Payé)":
                df_sub = df_sub[df_sub["Statut"].astype(str).str.strip() == "Payé"]
            elif statut_filtre == "فقط الحصص في الانتظار (En attente)":
                df_sub = df_sub[df_sub["Statut"].astype(str).str.strip() == "En attente"]
                
            df_seances_recu = df_sub.tail(int(nb_seances)).reset_index(drop=True)
            
        st.markdown("---")
        st.subheader(f"📋 معاينة الـ {len(df_seances_recu)} حصص الأخيرة التي ستظهر في الـ Reçu لـ ({res_choisie}):")
        if not df_seances_recu.empty:
            st.dataframe(df_seances_recu, use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ لا توجد حصص مسجلة لهذه الإقامة في جدول Historique حالياً! سيخرج الوصل بدون جدول الحصص.")

        def generer_recu_complet_pdf(res_nom, per_str, mnt_val, mode_str, srv_str, df_s):
            pdf = FPDF()
            pdf.add_page()
            
            pdf.set_font("Arial", "B", 16)
            pdf.set_text_color(11, 61, 145)
            pdf.cell(0, 10, "IMMOCLEAN FACILITY", ln=True, align="C")
            
            pdf.set_font("Arial", "", 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, "Service Professionnel de Nettoyage et d'Entretien des Residences - Kenitra", ln=True, align="C")
            pdf.cell(0, 6, "Tel: 06 49 92 43 54", ln=True, align="C")
            pdf.ln(6)
            
            pdf.set_font("Arial", "B", 13)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 10, "RECU DE PAIEMENT", border=1, ln=True, align="C")
            pdf.ln(6)
            
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
            
            if not df_s.empty:
                pdf.set_font("Arial", "B", 11)
                pdf.set_text_color(11, 61, 145)
                pdf.cell(0, 8, txt_pdf(f"Detail des {len(df_s)} dernieres seances de nettoyage effectuees :"), ln=True)
                pdf.ln(2)
                
                pdf.set_font("Arial", "B", 9)
                pdf.set_fill_color(230, 238, 250)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(12, 8, "N", border=1, align="C", fill=True)
                pdf.cell(32, 8, "Date", border=1, align="C", fill=True)
                pdf.cell(45, 8, "Agent / Employe", border=1, align="C", fill=True)
                pdf.cell(73, 8, "Prestations realisees", border=1, align="C", fill=True)
                pdf.cell(28, 8, "Statut", border=1, ln=True, align="C", fill=True)
                
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
            pdf.set_font("Arial", "I", 10)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 8, "Merci pour votre confiance. Direction ImmoClean FACILITY.", ln=True, align="R")
            
            return pdf.output(dest='S').encode('latin-1', 'replace')

        pdf_data = generer_recu_complet_pdf(res_choisie, periode, montant, mode_reglement, services_client, df_seances_recu)
        nom_pdf = f"Recu_{res_choisie}_{periode}.pdf".replace(" ", "_")
        
        st.download_button(
            label="📥 تحميل الوصل بالحصص (Télécharger le Reçu PDF)",
            data=pdf_data,
            file_name=nom_pdf,
            mime="application/pdf",
            use_container_width=True
        )

# ==========================================
# 7. Générer Devis (مطور مع السطح والباركينغ والعدد)
# ==========================================
elif menu == "Générer Devis":
    st.header("📄 مولد عروض الأثمان المطور (Générateur de Devis PDF)")
    
    col1, col2 = st.columns(2)
    with col1:
        nom_client_devis = st.text_input("🏢 اسم الإقامة أو الشركة", "Résidence Al Amal")
        ville_devis = st.text_input("📍 المدينة / الحي", "Kénitra")
        freq_devis = st.selectbox("🔄 عدد زيارات التنظيف الأساسي", [
            "1 passage par semaine (4 séances / mois)",
            "2 passages par semaine (8 séances / mois)",
            "3 passages par semaine (12 séances / mois)",
            "Quotidien 6j/7 (26 séances / mois)"
        ])
        prix_visites = st.number_input("💰 ثمن الزيارات الأساسية (الدرج والمهد) (MAD)", min_value=0, value=600, step=50)
        
    with col2:
        st.markdown("### 🏢 خدمات إضافية (السطح والباركينغ)")
        inclure_terrasse = st.checkbox("➕ إضافة تنظيف السطح (Terrasse)", value=True)
        nb_terrasses = 1
        prix_terrasse = 0
        if inclure_terrasse:
            nb_terrasses = st.number_input("عدد السطوح", min_value=1, max_value=5, value=1, step=1)
            prix_terrasse = st.number_input("ثمن تنظيف السطح (MAD)", min_value=0, value=100, step=25)
            
        inclure_parking = st.checkbox("➕ إضافة تنظيف الباركينغ (Parking)", value=True)
        nb_parkings = 1
        prix_parking = 0
        if inclure_parking:
            nb_parkings = st.number_input("عدد الباركينغات / المرآب", min_value=1, max_value=5, value=1, step=1)
            prix_parking = st.number_input("ثمن تنظيف الباركينغ (MAD)", min_value=0, value=100, step=25)

    st.markdown("---")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        produits_devis = st.selectbox("🧴 مواد ومعدات النظافة", ["Inclus (Fournis par ImmoClean FACILITY)", "A la charge de la Résidence"])
    with col_d2:
        prix_total_devis = prix_visites + (prix_terrasse if inclure_terrasse else 0) + (prix_parking if inclure_parking else 0)
        st.metric(label="💎 المجموع الإجمالي المقترح للشهر", value=f"{prix_total_devis:,.0f} MAD")

    details_devis = st.text_area("🧹 تفاصيل الخدمات الإضافية المشمولة", "Nettoyage complet des cages d'escaliers, hall d'entree, vitres et ascenseur.")

    def creer_devis_pdf(client_n, ville_n, freq_n, prod_n, det_n, p_visites, inc_ter, nb_ter, p_ter, inc_par, nb_par, p_par, p_tot):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(11, 61, 145)
        pdf.cell(0, 10, "IMMOCLEAN FACILITY", ln=True, align="C")
        
        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, "Service Professionnel de Nettoyage et d'Entretien des Residences - Kenitra", ln=True, align="C")
        pdf.cell(0, 6, "Tel: 06 49 92 43 54", ln=True, align="C")
        pdf.ln(8)
        
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, "DEVIS / PROPOSITION COMMERCIALE", border=1, ln=True, align="C")
        pdf.ln(8)
        
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, txt_pdf(f"Date : {datetime.date.today().strftime('%d/%m/%Y')}"), ln=True)
        pdf.cell(0, 8, txt_pdf(f"Client / Residence : {client_n} ({ville_n})"), ln=True)
        pdf.ln(4)
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "1. Frequence d'intervention de base :", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, txt_pdf(f"   - {freq_n}"), ln=True)
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "2. Prestations incluses et options :", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 7, txt_pdf(f"   - Nettoyage parties communes (Cages d'escaliers, hall) : {p_visites} MAD"), ln=True)
        if inc_ter:
            pdf.cell(0, 7, txt_pdf(f"   - Nettoyage Terrasse(s) (Quantite: {nb_ter}) : {p_ter} MAD"), ln=True)
        if inc_par:
            pdf.cell(0, 7, txt_pdf(f"   - Nettoyage Parking(s) / Garage(s) (Quantite: {nb_par}) : {p_par} MAD"), ln=True)
        
        if det_n:
            pdf.multi_cell(0, 7, txt_pdf(f"   - Autres details : {det_n}"))
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "3. Produits et Materiel :", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, txt_pdf(f"   - {prod_n}"), ln=True)
        pdf.ln(6)
        
        pdf.set_font("Arial", "B", 13)
        pdf.set_fill_color(230, 238, 250)
        pdf.cell(0, 12, txt_pdf(f"TARIF MENSUEL FORFAITAIRE TOTAL : {p_tot} MAD / Mois"), border=1, ln=True, align="C", fill=True)
        pdf.ln(12)
        
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 8, "Ce devis est valable pour une duree de 30 jours. Direction ImmoClean FACILITY.", ln=True, align="R")
        return pdf.output(dest='S').encode('latin-1', 'replace')

    devis_bytes = creer_devis_pdf(
        nom_client_devis, ville_devis, freq_devis, produits_devis, details_devis,
        prix_visites, inclure_terrasse, nb_terrasses, prix_terrasse,
        inclure_parking, nb_parkings, prix_parking, prix_total_devis
    )
    st.download_button("📥 تحميل عرض الثمن المطور (Télécharger Devis PDF)", data=devis_bytes, file_name=f"Devis_{nom_client_devis}.pdf".replace(" ", "_"), mime="application/pdf", use_container_width=True)

# ==========================================
# 8. Gestion d'Équipe
# ==========================================
elif menu == "Gestion d'Équipe":
    st.header("👷‍♀️ إدارة فريق العمل (Gestion d'Équipe)")
    df_emp = load_data("Employes", COLS_EMP)
    
    with st.form("form_employe"):
        c1, c2, c3 = st.columns(3)
        with c1: nom_e = st.text_input("👩‍💼 اسم العاملة / العامل")
        with c2: tel_e = st.text_input("📞 رقم الهاتف")
        with c3: poste_e = st.selectbox("🛠️ المنصب", ["Agent de nettoyage", "Superviseur", "Technicien Monobrosse"])
        
        if st.form_submit_button("➕ إضافة للفريق", use_container_width=True):
            if nom_e.strip():
                new_e = pd.DataFrame([{"Nom": nom_e.strip(), "Téléphone": nettoyer_texte_gsheet(tel_e), "Poste": poste_e, "Photo": ""}])
                df_emp = pd.concat([df_emp, new_e], ignore_index=True)
                save_data("Employes", df_emp)
                st.success(f"✅ تمت إضافة {nom_e} بنجاح!")
                st.rerun()
                
    if not df_emp.empty:
        edited_emp = st.data_editor(df_emp, num_rows="dynamic", use_container_width=True)
        if st.button("💾 حفظ تعديلات الفريق"):
            save_data("Employes", edited_emp)
            st.success("تم الحفظ!")
            st.rerun()

# ==========================================
# 9. Planning (مدموج مع الشبكة الأسبوعية + PDF)
# ==========================================
elif menu == "Planning":
    st.header("📅 التخطيط والبرمجة الزمنية (Planning & Radar Anti-Conflits)")
    df_plan = load_data("Planning", COLS_PLAN)
    df_clients = load_data("Clients", COLS_CLIENTS)
    df_emp = load_data("Employes", COLS_EMP)
    
    with st.expander("➕ برمجة حصة جديدة في الجدول الزمني", expanded=False):
        with st.form("form_planning"):
            c1, c2, c3 = st.columns(3)
            with c1:
                emp_p = st.selectbox("👷‍♀️ العاملة", df_emp["Nom"].tolist() if not df_emp.empty else ["عائشة"])
                cli_p = st.selectbox("🏢 الإقامة", df_clients["Résidence"].tolist() if not df_clients.empty else [])
                jour_p = st.selectbox("📆 اليوم", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche", "Tous les jours (Sauf Dimanche)", "Tous les jours"])
            with c2:
                h_deb_p = st.time_input("⏰ وقت البدء", value=datetime.time(9, 0))
                h_fin_p = st.time_input("⏰ وقت الانتهاء", value=datetime.time(13, 0))
                d_deb_p = st.date_input("📅 تاريخ البداية", value=datetime.date.today())
            with c3:
                freq_p = st.selectbox("🔄 التكرار", ["Chaque semaine", "1 semaine sur 2", "1 fois par mois"])
                coul_p = st.color_picker("🎨 لون البطاقة", "#1E88E5")
                
            if st.form_submit_button("💾 إضافة للبرنامج الزمني", use_container_width=True):
                conflit_emp, msg_err_emp = verifier_conflit_ajout(df_plan, emp_p, jour_p, h_deb_p, h_fin_p, d_deb_p, freq_p)
                doublon_cli, msg_err_cli = verifier_doublon_client(df_plan, cli_p, jour_p, d_deb_p, freq_p)
                
                if conflit_emp:
                    st.error(msg_err_emp)
                elif doublon_cli:
                    st.error(msg_err_cli)
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
                        "Statut": "Actif"
                    }])
                    df_plan = pd.concat([df_plan, new_p], ignore_index=True)
                    save_data("Planning", df_plan)
                    st.success("✅ تمت إضافة الحصة للبرنامج بدون أي تداخل!")
                    st.rerun()

    # --- 1. عرض الشبكة الأسبوعية العصرية + زر تحميل PDF ---
    st.subheader("🗓️ استعمال الزمن الأسبوعي (Grille Interactive)")
    afficher_planning_grille(df_plan)
    
    # --- 2. جدول التعديل والحذف السريع ---
    if not df_plan.empty:
        st.markdown("---")
        with st.expander("✏️ تعديل أو حذف حصص من جدول البرمجة الكامل", expanded=False):
            edited_plan = st.data_editor(df_plan, num_rows="dynamic", use_container_width=True)
            if st.button("💾 حفظ تعديلات الجدول الزمني", type="primary"):
                save_data("Planning", edited_plan)
                st.success("✅ تم تحديث البرمجة الزمنية!")
                st.rerun()
