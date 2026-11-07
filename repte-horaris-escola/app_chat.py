import os
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------------- CONFIGURACIÓ
st.set_page_config(
    page_title="Gestió Acadèmica · Escola d'Enginyeria UAB",
    page_icon="🏛️",
    layout="wide"
)

UAB_BASE_URL = os.environ.get("UAB_BASE_URL", "https://dcc-llm-gw.uab.cat/uabthehack/v1")
MODEL_NAME = os.environ.get("UAB_MODEL_NAME", "ornith")
client = OpenAI(base_url=UAB_BASE_URL, api_key=os.environ.get("UAB_API_KEY", "none"))

DIES = ["L", "M", "X", "J", "V", "S", "D"]
DIES_CA = {"L": "dilluns", "M": "dimarts", "X": "dimecres", "J": "dijous", "V": "divendres", "S": "dissabte", "D": "diumenge"}
NOMS_DIA = {
    "dilluns": 0, "dimarts": 1, "dimecres": 2, "dijous": 3, "divendres": 4,
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4
}

# ---------------------------------------------------------------- UTILITATS
def norm(t):
    if t is None or pd.isna(t):
        return ""
    t = unicodedata.normalize("NFD", str(t))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()

def minuts(h):
    if not h or pd.isna(h):
        return None
    m = re.search(r"(\d{1,2})[:.hH](\d{2})", str(h))
    if m:
        return int(m[1]) * 60 + int(m[2])
    m_h = re.search(r"(\d{1,2})h", str(h), re.IGNORECASE)
    if m_h:
        return int(m_h[1]) * 60
    return None

def hhmm(m):
    if m is None:
        return "--:--"
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"

def fd(d):
    return d.strftime("%d/%m/%Y") if isinstance(d, (date, pd.Timestamp)) else str(d)

def espina_planta(aula):
    p = str(aula).split("/")
    return (p[0], p[1][0]) if len(p) == 2 and p[1] else ("", "")

def split_docents(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or not str(v).strip():
        return ["(docent sense assignar)"]
    return [x.strip() for x in re.split(r"[;,|]", str(v)) if x.strip()]

# ---------------------------------------------------------------- CARREGA DE DADES
@st.cache_data
def carregar_csv():
    df_s = pd.read_csv("paquet/sessions.csv")
    df_a = pd.read_csv("paquet/aules.csv")
    return df_s, df_a

@st.cache_data
def proposta_defecte():
    try:
        return pd.read_csv("paquet/proposta_partida.csv")
    except Exception:
        return None

@st.cache_data
def construir_horari(s, proposta):
    s = s.copy()
    s["dia_orig"] = s["dia"]
    s["dur"] = s["h_fi"].map(minuts) - s["h_ini"].map(minuts)
    s["dur"] = s["dur"].fillna(120)
    s["data0"] = pd.to_datetime(s["data"], errors="coerce")
    
    if proposta is not None:
        s = s.drop(columns=["dia", "h_ini", "aula_partida"], errors="ignore").merge(
            proposta[["id_sessio", "dia", "h_ini", "aula"]], on="id_sessio", how="left"
        )
        s["dia"] = s["dia"].fillna(s["dia_orig"])
    else:
        if "aula_partida" in s:
            s["aula"] = s["aula_partida"]
            
    desp = s["dia"].map(lambda x: DIES.index(x) if x in DIES else 0) - s["dia_orig"].map(lambda x: DIES.index(x) if x in DIES else 0)
    s["data_eff"] = (s["data0"] + pd.to_timedelta(desp.fillna(0), unit="D")).dt.date
    s["ini"] = s["h_ini"].map(minuts)
    s["fi"] = s["ini"] + s["dur"]
    s["sense_espai"] = s["sense_espai"].fillna(0) if "sense_espai" in s else 0
    if "cohort" not in s:
        s["cohort"] = s["titulacions_curs"] if "titulacions_curs" in s else "—"
    s["aula"] = s["aula"].where(s["aula"].notna() & (s["aula"] != "Sense assignar"))
    s["alumnes"] = pd.to_numeric(s["alumnes"], errors="coerce").fillna(0).astype(int)
    return s

def ocupacio(df):
    d = df[df["aula"].notna() & (df["sense_espai"] != 1) & df["ini"].notna()]
    occ = defaultdict(list)
    for dt, a, i, f in zip(d["data_eff"], d["aula"], d["ini"], d["fi"]):
        occ[dt].append((int(i), int(f), a))
    return occ

def mapa_bloqueig(incs, data_max):
    bloq, motiu_de = defaultdict(set), {}
    for inc in incs:
        d, fi = inc["ini"], inc["fi"] or data_max
        while d <= fi:
            bloq[d].add(inc["aula"])
            motiu_de[(d, inc["aula"])] = (inc["id"], inc["motiu"])
            d += timedelta(days=1)
    return bloq, motiu_de

# ---------------------------------------------------------------- REUBICACIÓ (NIVELL 5.3)
COLS_MOVES = [
    "id_sessio", "data", "dia", "hora", "assignatura", "grup", "tipus", "cohort",
    "docents", "alumnes", "aula_origen", "aula_desti", "estat", "motiu", "incidencia"
]

def calcular_reubicacions(df, incs, aules, prev, mode, data_max):
    cap = aules.set_index("aula")["capacitat"].to_dict()
    tip = aules.set_index("aula")["tipus"].to_dict()
    ordin = set(aules.loc[aules["ordinaria"] == 1, "aula"])
    semin = {a for a, t in tip.items() if "semin" in norm(t)}
    bloq, motiu_de = mapa_bloqueig(incs, data_max)
    
    if not bloq:
        return pd.DataFrame(columns=COLS_MOVES), df.iloc[0:0]

    occ = ocupacio(df)
    mask = pd.Series([a in bloq.get(d, ()) for a, d in zip(df["aula"], df["data_eff"])], index=df.index)
    plab = df[mask & (df["tipus"] == "PLAB")]
    af = df[mask & (df["tipus"] != "PLAB") & (df["sense_espai"] != 1) & df["ini"].notna()]
    af = af.sort_values(["data_eff", "ini", "alumnes"], ascending=[True, True, False])

    pref, files = {}, []
    for s in af.to_dict("records"):
        d, ini, fi, orig = s["data_eff"], int(s["ini"]), int(s["fi"]), s["aula"]
        bl = bloq[d]
        ocup_ara = {a for i, f, a in occ[d] if i < fi and ini < f}
        
        free_ts = [
            len(ordin - {a for i, f, a in occ[d] if i <= t < f} - bl)
            for t in range(ini, fi, 30)
        ]
        reserva_ok = all(x - 1 >= 2 for x in free_ts)
        tip_o = tip.get(orig, "Aula")

        cands = []
        for a in cap:
            if a in ocup_ara or a in bl or a == orig or cap[a] < s["alumnes"]:
                continue
            if a.startswith(("Q5/", "Q6/", "J/")):
                continue
            if not (a in ordin or a in semin or (s["tipus"] == "PAUL" and tip[a] == tip_o)):
                continue
            cands.append(a)

        def puntuacio(a):
            e, p = espina_planta(a)
            e0, p0 = espina_planta(orig)
            prox = 0 if (e, p) == (e0, p0) else 1 if e == e0 else 2
            bonus = (-2 if prev.get(s["id_sessio"]) == a else 0) + (-1 if pref.get((s["assignatura"], s["grup"])) == a else 0)
            return (prox + bonus, cap[a] - s["alumnes"])

        valides = sorted([a for a in cands if a not in ordin or reserva_ok], key=puntuacio)
        estat = "OK"
        if valides:
            nova = valides[0]
        elif cands and mode == "auto":
            nova, estat = sorted(cands, key=puntuacio)[0], "Reserva R8 relaxada"
        else:
            nova, estat = None, "SENSE AULA"

        if nova:
            occ[d].append((ini, fi, nova))
            pref[(s["assignatura"], s["grup"])] = nova
            
        inc_id, motiu = motiu_de[(d, orig)]
        files.append({
            "id_sessio": s["id_sessio"], "data": d, "dia": s["dia"],
            "hora": f"{hhmm(ini)}-{hhmm(fi)}", "assignatura": s["assignatura"], "grup": s["grup"],
            "tipus": s["tipus"], "cohort": s["cohort"], "docents": s["docents"],
            "alumnes": s["alumnes"], "aula_origen": orig, "aula_desti": nova or "—",
            "estat": estat, "motiu": motiu, "incidencia": inc_id
        })
    return pd.DataFrame(files, columns=COLS_MOVES), plab

def aula_efectiva(df, moves):
    m = dict(zip(moves["id_sessio"], moves["aula_desti"])) if len(moves) else {}
    out = df.copy()
    out["aula_eff"] = [None if m.get(i, a) == "—" else m.get(i, a) for i, a in zip(out["id_sessio"], out["aula"])]
    return out

def diff_moviments(old, new):
    o = dict(zip(old["id_sessio"], old["aula_desti"])) if len(old) else {}
    n = dict(zip(new["id_sessio"], new["aula_desti"])) if len(new) else {}
    m_nou = pd.Series([(i not in o) or o[i] != n[i] for i in new["id_sessio"]], index=new.index, dtype=bool)
    m_tor = pd.Series([i not in n for i in old["id_sessio"]], index=old.index, dtype=bool)
    return new[m_nou], old[m_tor]

# ---------------------------------------------------------------- AVISOS I REGISTRE
def agrupar_per_avis(rows):
    if rows.empty:
        return []
    grp_cols = ["assignatura", "grup", "tipus", "cohort", "dia", "hora", "aula_origen", "aula_desti", "docents", "motiu", "estat"]
    out = []
    for k, g in rows.groupby(grp_cols, dropna=False, sort=False):
        r = dict(zip(grp_cols, k))
        r["dates"], r["ids"] = sorted(g["data"]), list(g["id_sessio"])
        out.append(r)
    return sorted(out, key=lambda a: (a["dates"][0], a["hora"]))

def format_linia_avis(a, torna):
    ds = a["dates"]
    quan = fd(ds[0]) if len(ds) == 1 else f"{len(ds)} sessions, del {fd(ds[0])} al {fd(ds[-1])}"
    canvi = f"{a['aula_desti']} → {a['aula_origen']} (habitual)" if torna else (
        f"{a['aula_origen']} → SENSE AULA" if a["aula_desti"] == "—" else f"{a['aula_origen']} → {a['aula_desti']}"
    )
    return f"• {a['assignatura']} · {a['tipus']} {a['grup']} · {DIES_CA.get(a['dia'], a['dia'])} {a['hora']} · {canvi} · {quan} [ref. {a['ids'][0]}]"

def generar_avisos(rows, torna):
    if rows.empty:
        return []
    acts = agrupar_per_avis(rows)
    avui = fd(date.today())
    motius = "; ".join(sorted({str(a["motiu"]) for a in acts}))
    assumpte = "Restabliment de l'aula habitual" if torna else "Canvi d'aula provisional"
    intro = (
        "La incidència ha quedat resolta. Les classes següents tornen a la seva aula habitual:"
        if torna else
        f"Per una incidència d'aula ({motius}), les següents classes es traslladen provisionalment:"
    )
    tanc = "Cordialment,\nGestió Acadèmica · Escola d'Enginyeria UAB"
    capcalera = lambda dest: f"Assumpte: {assumpte}\nData de l'avís: {avui}\nPer a: {dest}\n\nBon dia,\n\n{intro}\n\n"

    per_doc, per_coh = defaultdict(list), defaultdict(list)
    for a in acts:
        for dct in split_docents(a["docents"]):
            per_doc[dct].append(a)
        per_coh[a["cohort"]].append(a)

    avisos = [{
        "tipus": "Gestió Acadèmica", "dest": "Gestió Acadèmica", "assumpte": assumpte,
        "text": f"Assumpte: {assumpte} (resum intern)\nData: {avui}\nSessions afectades: {len(rows)}\n\n" +
                "\n".join(format_linia_avis(a, torna) for a in acts) + f"\n\n{tanc}"
    }]
    for doc, l in sorted(per_doc.items()):
        avisos.append({"tipus": "Docent", "dest": doc, "assumpte": assumpte, "text": capcalera(f"docent {doc}") + "\n".join(format_linia_avis(a, torna) for a in l) + f"\n\n{tanc}"})
    for coh, l in sorted(per_coh.items()):
        avisos.append({"tipus": "Alumnat", "dest": coh, "assumpte": assumpte, "text": capcalera(f"alumnat de {coh}") + "\n".join(format_linia_avis(a, torna) for a in l) + f"\n\n{tanc}"})
    return avisos

def files_registre(rows, torna):
    out = []
    for r in rows.itertuples():
        a, b = (r.aula_desti, r.aula_origen) if torna else (r.aula_origen, r.aula_desti)
        out.append({
            "id_sessio": r.id_sessio, "data": r.data, "canvi": f"{a} → {b}",
            "motiu": ("Resolució: " if torna else "") + str(r.motiu),
            "afecta": f"docent(s) {r.docents}; {r.cohort}; grup {r.grup}",
            "data_avis": date.today().isoformat(), "tipus": "restabliment" if torna else "canvi"
        })
    return out

def millorar_amb_ia(text):
    try:
        r = client.chat.completions.create(
            model=MODEL_NAME, temperature=0.1,
            messages=[
                {"role": "system", "content": "Reescriu aquest avís acadèmic en català, formal i clar. Mantén TOTES les aules, dates, hores i codis id_sessio exactament iguals. No afegeixis fets nous."},
                {"role": "user", "content": text}
            ]
        )
        nou = r.choices[0].message.content
        cod = lambda t: set(re.findall(r"[A-Z]\w*/\d+", t))
        return nou if cod(text) <= cod(nou) else text
    except Exception:
        return text

# ---------------------------------------------------------------- MOTOR DE CONSULTES (CHAT VERIFICABLE)
def cercar_context_horari(pregunta, df_base, df_a, ss_moves, ss_incs, data_max):
    p = norm(pregunta)
    eff = aula_efectiva(df_base, ss_moves)
    eff["aula"] = eff["aula_eff"]
    
    # 1. Resolució de data
    dt = None
    if "dema" in p or "manana" in p:
        dt = date.today() + timedelta(days=1)
    elif "avui" in p or "hoy" in p:
        dt = date.today()
    else:
        for n, w in NOMS_DIA.items():
            if n in p:
                d = date.today()
                while d.weekday() != w:
                    d += timedelta(days=1)
                dt = d
                break
        if dt is None:
            m_dt = re.search(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{4}))?", p)
            if m_dt:
                any_d = int(m_dt[3]) if m_dt[3] else date.today().year
                try:
                    dt = date(any_d, int(m_dt[2]), int(m_dt[1]))
                except ValueError:
                    dt = None

    # 2. Resolució d'hora
    m_h = re.search(r"\b(\d{1,2})(?:[:.](\d{2})|h)\b", p)
    ini = (int(m_h[1]) * 60 + int(m_h[2] or 0)) if m_h else None

    # Context d'incidències actives
    notes = []
    if ss_incs:
        notes.append("Incidències registrades: " + "; ".join(f"{i['aula']} ({fd(i['ini'])}→{fd(i['fi']) if i['fi'] else 'obert'}, {i['motiu']})" for i in ss_incs))

    # A. Consulta d'aules lliures
    if any(k in p for k in ["lliure", "lliures", "libre", "libres", "disponible", "disponibles"]) and (dt or ini is not None):
        if dt is None:
            dt = date.today()
        if ini is None:
            ini = 9 * 60  # per defecte 9:00 si no s'especifica
            
        occ = ocupacio(eff)
        bloq, _ = mapa_bloqueig(ss_incs, data_max)
        ocup = {a for i, f, a in occ[dt] if i <= ini < f} | bloq.get(dt, set())
        
        m_cap = re.findall(r"\b(\d{2,3})\s*(?:places|plazas|alumnes|estudiants)?", p)
        cap_min = int(m_cap[0]) if m_cap else 0
        
        q = df_a[(df_a["ordinaria"] == 1) & (df_a["capacitat"] >= cap_min) & ~df_a["aula"].isin(ocup)]
        res_aules = q[["aula", "capacitat", "tipus"]].sort_values("capacitat").head(15)
        return "\n".join(notes + [
            f"Consulta: Aules ordinàries lliures el {fd(dt)} a les {hhmm(ini)} (mínim {cap_min} places):",
            res_aules.to_string(index=False) if not res_aules.empty else "No hi ha cap aula que compleixi els requisits."
        ])

    # B. Cerca de sessions específiques (per assignatura, docent, aula, id_sessio, grup)
    tokens = [w for w in re.findall(r"[a-z0-9/_]+", p) if len(w) >= 2 and not w.isdigit()]
    mask = pd.Series(False, index=eff.index)
    
    # Comprovar si hi ha cerca per id directe (ex: s11527 o 11527)
    id_match = re.search(r"\b([sS]?\d{4,6})\b", pregunta)
    if id_match:
        val_id = id_match.group(1).upper()
        mask |= eff["id_sessio"].astype(str).str.upper().str.contains(val_id)

    # Comprovar aula exacta (ex: Q4/0011)
    aula_match = re.search(r"\b([A-Z]\w*/\d+)\b", pregunta, re.IGNORECASE)
    if aula_match:
        val_a = aula_match.group(1).upper()
        mask |= eff["aula"].astype(str).str.upper().eq(val_a)

    for w in tokens:
        pat = rf"\b{re.escape(w)}"
        mask |= (
            eff["assignatura"].map(norm).str.contains(pat, na=False) |
            eff["docents"].astype(str).str.lower().str.contains(pat, na=False) |
            eff["grup"].astype(str).str.lower().eq(w) |
            eff["cohort"].astype(str).str.lower().contains(pat, na=False)
        )

    r = eff[mask]
    if dt is not None:
        r = r[r["data_eff"] == dt]
    if ini is not None and not r.empty:
        r = r[(r["ini"] <= ini) & (r["fi"] > ini)]

    if r.empty:
        return "\n".join(notes + ["No s'ha trobat cap sessió a la base de dades amb aquests criteris."])

    cols = ["id_sessio", "assignatura", "grup", "tipus", "cohort", "docents", "data_eff", "h_ini", "h_fi", "aula", "alumnes"]
    r_cols = [c for c in cols if c in r.columns]
    return "\n".join(notes + [
        f"Sessions trobades ({len(r)} registres, mostrant fins a 12):",
        r[r_cols].head(12).to_string(index=False)
    ])

# ---------------------------------------------------------------- INICIALITZACIÓ D'ESTAT
df_s, df_a = carregar_csv()
with st.sidebar:
    st.caption("Configuració de l'entorn")
    up = st.file_uploader("Carrega proposta alternativa (id_sessio,dia,h_ini,aula)", type="csv")
prop = pd.read_csv(up) if up is not None else proposta_defecte()
df_base = construir_horari(df_s, prop)
DATA_MAX = df_base["data_eff"].dropna().max()

ss = st.session_state
for k, v in {
    "incs": [], "seq": 1, "moves": pd.DataFrame(columns=COLS_MOVES), "plab": pd.DataFrame(),
    "events": [], "registre": [], "flash": [], "ia": {}, "chat": [], "mode": "auto"
}.items():
    ss.setdefault(k, v)

def refrescar_sistema():
    old = ss.moves
    prev = dict(zip(old["id_sessio"], old["aula_desti"])) if len(old) else {}
    ss.moves, ss.plab = calcular_reubicacions(df_base, ss.incs, df_a, prev, ss.mode, DATA_MAX)
    return diff_moviments(old, ss.moves)

def afegir_event(titol, nous, torna):
    avisos = generar_avisos(nous, False) + generar_avisos(torna, True)
    if avisos:
        ss.events.insert(0, {
            "id": len(ss.events) + 1, "titol": titol,
            "hora": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M"), "avisos": avisos
        })
        ss.registre += files_registre(nous, False) + files_registre(torna, True)
    return len(avisos)

# ---------------------------------------------------------------- VISTA I INTERFÍCIE
st.title("🏛️ Assistent de Gestió Acadèmica · Escola d'Enginyeria UAB")

for kind, msg in ss.flash:
    getattr(st, kind)(msg)
ss.flash = []

tabs = st.tabs(["💬 Consultes i Xatbot", f"🚨 Incidències ({sum(i['fi'] is None or i['fi'] >= date.today() for i in ss.incs)})", f"📨 Avisos ({len(ss.events)})"])

# ============ TAB 1: XATBOT I ASSISTENT ============
with tabs[0]:
    st.subheader("Assistent de Consultes Acadèmiques")
    st.caption("Respon de forma contrastada utilitzant la base de dades oficial. Cita sempre `id_sessio`, horari i aula.")
    
    for m in ss.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            
    if q := st.chat_input("Fes una consulta (Ex.: On té classe el grup 81 dimarts? Quina aula de 60 places està lliure dijous a les 10?)"):
        ss.chat.append({"role": "user", "content": q})
        ctx = cercar_context_horari(q, df_base, df_a, ss.moves, ss.incs, DATA_MAX)
        
        prompt_system = (
            "Ets l'assistent oficial de Gestió Acadèmica de l'Escola d'Enginyeria de la UAB. "
            "Respon SEMPRE en la mateixa llengua de l'usuari amb to professional i concís. "
            "IMPORTANTÍSSIM PER A L'AVALUACIÓ: Basa't ÚNICAMENT en el bloc DADES proporcionat. "
            "Està prohibit inventar aules, hores o disponibilitats. "
            "Cita SEMPRE l'id_sessio, assignatura, grup, hora i aula quan parlis d'una classe. "
            "Si demanen aules lliures, llista només les que apareixen expressament a la taula. "
            "Si a DADES diu que no es troba la informació, respon clarament que no consta cap registre."
        )
        
        try:
            r = client.chat.completions.create(
                model=MODEL_NAME, temperature=0.0,
                messages=[
                    {"role": "system", "content": prompt_system},
                    *ss.chat[-4:-1],
                    {"role": "user", "content": f"DADES COMPROVADES DE LA BASE DE DADES:\n{ctx}\n\nPREGUNTA DE L'USUARI:\n{q}"}
                ]
            )
            resp = r.choices[0].message.content
        except Exception:
            resp = f"*(Error de connexió amb el model DCC. Dades oficials recuperades:)*\n\n```\n{ctx}\n```"
            
        ss.chat.append({"role": "assistant", "content": resp})
        st.rerun()

# ============ TAB 2: INCIDÈNCIES I REUBICACIÓ ============
with tabs[1]:
    st.subheader("➕ Declarar incidència d'aula")
    c1, c2, c3 = st.columns([1.5, 1.2, 2])
    aula_inc = c1.selectbox("Aula afectada", sorted(df_a["aula"].dropna().unique()))
    ini_inc = c2.date_input("Data d'inici", date.today())
    motiu_opcio = c3.selectbox("Motiu de la incidència", [
        "Avaria de projector o equip informàtic",
        "Avaria del sistema de climatització",
        "Aula reservada per acte acadèmic / institucional",
        "Obres, pintura o manteniment",
        "Altre"
    ])
    motiu_final = st.text_input("Descripció detallada del motiu") if motiu_opcio == "Altre" else motiu_opcio
    
    col_d1, col_d2 = st.columns(2)
    durada = col_d1.radio("Previsió de resolució", ["Fins que es resolgui", "Fins a una data límit"], horizontal=True)
    fi_inc = col_d2.date_input("Data de fi prevista", ini_inc) if durada == "Fins a una data límit" else None

    if st.button("Registrar incidència i recalcular", type="primary", use_container_width=True):
        if fi_inc and fi_inc < ini_inc:
            st.error("La data final no pot ser anterior a la d'inici.")
        else:
            ss.incs.append({"id": ss.seq, "aula": aula_inc, "ini": ini_inc, "fi": fi_inc, "motiu": motiu_final})
            ss.seq += 1
            nous, torna = refrescar_sistema()
            n = afegir_event(f"Incidència a {aula_inc}: {motiu_final}", nous, torna)
            ss.flash.append(("success", f"Incidència guardada. Reubicacions generades: {len(nous)}, avisos preparats: {n}."))
            st.rerun()

    st.divider()
    st.subheader("Estat d'aules i descàrrega d'informes")
    
    if len(ss.moves):
        r8_rel = int((ss.moves["estat"] == "Reserva R8 relaxada").sum())
        sense_a = int((ss.moves["estat"] == "SENSE AULA").sum())
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Sessions mogudes", len(ss.moves))
        m2.metric("R8 relaxades", r8_rel)
        m3.metric("Sense aula", sense_a)
        
        st.dataframe(ss.moves[["id_sessio", "data", "hora", "assignatura", "grup", "aula_origen", "aula_desti", "estat"]], hide_index=True, use_container_width=True)
        
        d1, d2, d3 = st.columns(3)
        d1.download_button("Descàrrega registre_canvis.csv", pd.DataFrame(ss.registre).to_csv(index=False).encode(), "registre_canvis.csv", "text/csv")
        eff = aula_efectiva(df_base, ss.moves)
        out = eff[["id_sessio", "dia", "h_ini", "aula_eff"]].rename(columns={"aula_eff": "aula"})
        d2.download_button("Descàrrega proposta-imprevist.csv", out.to_csv(index=False).encode(), "proposta-imprevist.csv", "text/csv")
        if r8_rel:
            rel = pd.DataFrame([{"restriccio": "R8-RESERVA", "sessions": "*", "justificacio": "Incidència d'aula: reubicació sense 2 aules ordinàries lliures en franja."}])
            d3.download_button("Descàrrega relaxacions.csv", rel.to_csv(index=False).encode(), "relaxacions.csv", "text/csv")

# ============ TAB 3: AVISOS I ESBORRANYS ============
with tabs[2]:
    st.subheader("Historial d'avisos generats")
    if not ss.events:
        st.info("No hi ha cap avís registrat.")
    for ev in ss.events:
        st.markdown(f"#### {ev['titol']} · *{ev['hora']}*")
        for i, a in enumerate(ev["avisos"]):
            clau = f"ev_{ev['id']}_{i}"
            txt = ss.ia.get(clau, a["text"])
            with st.expander(f"Avís per a {a['tipus']}: {a['dest']}"):
                st.code(txt, language=None)
                if st.button("Reescriure formalment amb IA", key="btn_" + clau):
                    ss.ia[clau] = millorar_amb_ia(a["text"])
                    st.rerun()