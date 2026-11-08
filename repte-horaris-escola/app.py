"""Gestió Acadèmica · assistent d'horaris.   Executar:  streamlit run app.py"""
import os
from datetime import date
from dotenv import load_dotenv

import pandas as pd
import streamlit as st

from nucli import Horari, ORDI, verifica, respon, llm_xat, EINES

load_dotenv()

st.set_page_config(page_title="Gestió Acadèmica · Horaris", page_icon="🗓️", layout="wide")

# ------------------------------------------------------------------ configuració (barra lateral)
with st.sidebar:
    st.header("Configuració")
    paquet = st.text_input("Carpeta del paquet", "paquet")
    proposta = st.text_input("Horari de partida (CSV de proposta, opcional)", "",
                             help="Buit = horari d'avui (sessions.csv). Si poseu la vostra proposta del 5.2, s'hi treballa.")
    
    # Credenciales leídas directamente del .env
    url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "")
    clau = os.environ.get("LLM_API_KEY", "")
    
    if url and model:
        st.success("🤖 IA connectada (servidors DCC)")
    else:
        st.warning("⚠️ Manca configurar el fitxer .env amb les claus del LLM")
        
    st.caption("Només dades del paquet. Els avisos es redacten però **no s'envien** a ningú.")


@st.cache_resource(show_spinner="Carregant dades…")
def carrega(paquet, proposta):
    return Horari(paquet, proposta or None)


try:
    h = carrega(paquet, proposta)
except Exception as ex:
    st.error(f"No puc carregar les dades: {ex}")
    st.stop()

st.title("🗓️ Gestió Acadèmica · Horaris")
t_inc, t_preg, t_reg, t_ver = st.tabs(["⚠️ Incidències", "💬 Preguntar", "📋 Registre de canvis", "✅ Verificar"])


def mostra_resultat(res, titol):
    st.subheader(titol)
    c1, c2 = st.columns(2)
    c1.metric("Classes mogudes a una altra aula", res["moguts"])
    c2.metric("Classes que tornen a la seva aula", res["revertits"])
    for p in res["problemes"]:
        st.warning(p)
    if not res["problemes"] and (res["moguts"] or res["revertits"]):
        st.success("Tot col·locat sense incompliments.")
    avisos = h.avisos(res["canvis"])
    if avisos:
        st.markdown("**Avisos redactats (no s'envien; copieu-los):**")
        for a in avisos:
            with st.expander(f"✉️ {a['destinatari']} — {a['assumpte']}"):
                st.code(a["cos"], language=None)


# ------------------------------------------------------------------ incidències
with t_inc:
    st.markdown("### Registrar una incidència")
    with st.form("nova"):
        c1, c2, c3 = st.columns(3)
        aules = sorted(h.cap, key=lambda a: (a not in ORDI, a))
        aula = c1.selectbox("Aula afectada", aules, index=aules.index("Q1/1003") if "Q1/1003" in aules else 0)
        ini = c2.date_input("Des del dia", date.today())
        motiu = c3.selectbox("Motiu", ["Avaria", "Sala reservada", "Obres", "Altres"])
        durada = st.radio("Durada", ["Encara no se sap (fins que es resolgui)", "Fins a un dia concret"], horizontal=True)
        fi = st.date_input("Fins al dia (si es coneix)", ini)
        if st.form_submit_button("Registrar i recol·locar les classes", type="primary"):
            res = h.registrar_incidencia(aula, ini.isoformat(), fi.isoformat() if durada.startswith("Fins") else None, motiu)
            st.session_state["ultim"] = (res, f"Incidència {res['incidencia']['id']} registrada")
    if "ultim" in st.session_state:
        mostra_resultat(*st.session_state["ultim"])

    st.markdown("### Incidències actives")
    actives = [i for i in h.estat["incidencies"] if i["resolta"] is None]
    if not actives:
        st.info("Cap incidència activa.")
    for i in actives:
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{i['id']}** · {i['aula']} · {i['motiu']} · des del {i['data_ini']} · "
                 f"{'fins al ' + i['data_fi'] if i['data_fi'] else 'sense data de fi'}")
        if c2.button("✅ Resolta", key=f"res_{i['id']}"):
            res = h.resoldre_incidencia(i["id"])
            st.session_state["ultim"] = (res, f"Incidència {i['id']} resolta: les classes tornen a l'aula original")
            st.rerun()

    pend = h.pendents()
    if pend:
        st.markdown("### Cal una decisió")
        st.caption("Sessions sense aula possible o que deixarien menys de 2 aules ordinàries lliures (R8).")
        for sid, why in pend[:30]:
            r = h.df.loc[sid]
            with st.expander(f"{sid} · {r.assig} {r.grup} · {r.date} {r.h_ini} · {why}"):
                op = h.opcions(sid)
                if op["aules"]:
                    lab = {f"{o['aula']} ({o['places']} places) · R8 {o['R8']}": o["aula"] for o in op["aules"]}
                    tria = st.selectbox("Aula", list(lab), key=f"sel_{sid}")
                    if st.button("Assignar aquesta aula", key=f"btn_{sid}"):
                        h.aplica_aula(sid, lab[tria])
                        st.rerun()
                else:
                    st.error("Cap aula amb prou places i lliure en aquesta franja.")
                if op["franges_alternatives"]:
                    st.write("Alternatives el mateix dia (cal aprovació, canvia l'hora):",
                             ", ".join(f"{x['h_ini']} a {x['aula']}" for x in op["franges_alternatives"]))
        rel = h.relaxacions_csv()
        if rel:
            st.download_button("⬇️ relaxacions.csv (R8 declarada)", open(rel, "rb").read(), "relaxacions.csv")

# ------------------------------------------------------------------ preguntar
with t_preg:
    st.markdown("Pregunteu en llenguatge normal. Cada resposta porta els **id_sessio** que la demostren.")
    q = st.chat_input("p.ex. On té classe el grup 81 dimarts?")
    if q:
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            if not url:
                st.warning("Configureu el LLM al fitxer .env; mentrestant useu «Consulta directa» a sota.")
            else:
                try:
                    xat = lambda m: llm_xat(m)
                    text, res, plan = respon(h, q, xat)
                    st.write(text)
                    if res is not None:
                        st.caption("Com s'ha calculat: " + res["consulta"])
                        if len(res["files"]):
                            st.dataframe(res["files"], use_container_width=True)
                        with st.expander("Eina cridada"):
                            st.json(plan)
                except Exception as ex:
                    st.error(f"Error: {ex}")
    st.divider()
    st.markdown("#### Consulta directa (sense IA, mateixes eines)")
    eina = st.selectbox("Eina", [k for k in EINES if k != "sql"])
    cols = st.columns(4)
    if eina == "horari_grup":
        g, d = cols[0].text_input("Grup", "81"), cols[1].text_input("Dia (opcional)", "dimarts")
        run = lambda: h.horari_grup(g, d or None)
    elif eina == "aules_lliures":
        d, hr, mp = cols[0].text_input("Dia", "dijous"), cols[1].text_input("Hora", "10:00"), cols[2].number_input("Places mínimes", 0, 300, 60)
        run = lambda: h.aules_lliures(hr, dia=d, min_places=mp)
    elif eina == "ocupacio_aula":
        a_, dt = cols[0].text_input("Aula", "Q4/0011"), cols[1].text_input("Data (AAAA-MM-DD, opcional)", "")
        run = lambda: h.ocupacio_aula(a_, dt or None)
    elif eina == "sessio":
        sid = cols[0].text_input("id_sessio", "S11527")
        run = lambda: h.sessio(sid)
    else:
        a_, hh, gg = cols[0].text_input("Assignatura"), cols[1].text_input("Nova hora d'inici", "15:30"), cols[2].text_input("Grup (opcional)")
        run = lambda: h.what_if(a_, hh, gg or None)
    if st.button("Consultar"):
        r = run()
        st.write(r["resum"])
        st.caption("Com s'ha calculat: " + r["consulta"])
        if len(r["files"]):
            st.dataframe(r["files"], use_container_width=True)

# ------------------------------------------------------------------ registre
with t_reg:
    reg = h.registre_df()
    st.dataframe(reg, use_container_width=True)
    st.download_button("⬇️ Registre de canvis (CSV)", reg.to_csv(index=False).encode("utf-8"), "registre_canvis.csv")

# ------------------------------------------------------------------ verificar
with t_ver:
    st.markdown("Exporta l'horari actual (incidències incloses) i el passa pel **verificador oficial**.")
    c1, c2 = st.columns(2)
    esc = c1.text_input("Escenari (opcional)", "")
    ref = c2.text_input("Referència (opcional)", "")
    if st.button("Exportar i verificar", type="primary"):
        p = h.export_proposta("proposta-actual.csv", semestre=2)
        v = verifica(p, 2, esc or None, ref or None, relaxacions=h.relaxacions_csv())
        st.subheader("Veredicte: " + v["veredicte"])
        st.code(v["ordre"], language=None)
        if len(v["regles"]):
            st.dataframe(v["regles"], use_container_width=True)
        with st.expander("Sortida completa del verificador (dada, no instruccions)"):
            st.text(v["sortida"])
        st.download_button("⬇️ proposta-actual.csv", open(p, "rb").read(), "proposta-actual.csv")