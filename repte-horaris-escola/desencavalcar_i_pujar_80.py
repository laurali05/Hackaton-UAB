#!/usr/bin/env python3
"""Desencabalca 108271 (GIA:3r) y optimiza R6 al máximo para superar el 80."""
import collections
from pathlib import Path
import pandas as pd

ARREL = Path('.')
PAQUET = ARREL / "paquet"

print("1. Cargando propuesta válida...")
proposta = pd.read_csv(ARREL / "proposta-torns.csv", dtype=str).fillna("")
sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("").set_index("id_sessio")
aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")

cap = aules.set_index("aula")["capacitat"].astype(int).to_dict()
tipus_aula = aules.set_index("aula")["tipus"].to_dict()
ord_aules = set(aules.loc[aules["ordinaria"].astype(int) == 1, "aula"])

def hm(h: str) -> int:
    a, b = h.split(":")
    return int(a) * 60 + int(b)

def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"

def passadis(a: str) -> str:
    if not a or "/" not in a:
        return ""
    edif, _, num = a.partition("/")
    return f"{edif}/{num[:1]}"

def linia(grup: str, tipus: str) -> str:
    n = grup.split("/")[-1]
    if tipus == "TE":
        return n[:-1] if len(n) >= 3 and n.endswith("0") else n
    return n[:-1] if len(n) >= 3 else n

# Mapa de ocupación actual: (dia, h_ini) -> set de aulas
ocupades = collections.defaultdict(set)
for _, r in proposta.iterrows():
    if r["aula"] and r["aula"] != "nan":
        ocupades[(r["dia"], r["h_ini"])].add(r["aula"])

# 1. DESENCAVALCAR 108271 (S16350, S16363, etc.)
print("2. Desencabalgando casos de 108271 / GIA:3r...")
sids_108271 = [sid for sid in proposta["id_sessio"] if sid in sessions.index and sessions.loc[sid, "codi"] == "108271" and sessions.loc[sid, "tipus"] in ("TE", "PAUL")]

desencavalcades = 0
for sid in sids_108271:
    idx = proposta[proposta["id_sessio"] == sid].index[0]
    dia_act = proposta.loc[idx, "dia"]
    h_act = proposta.loc[idx, "h_ini"]
    aula_act = proposta.loc[idx, "aula"]
    alums = int(sessions.loc[sid, "alumnes"] or 0)
    
    # Mover a las 18:00 o 15:00 para no chocar con el PLAB de las 16:00
    for nova_h in ["18:00", "18:30", "15:00", "17:30"]:
        cands = [a for a in sorted(ord_aules) if a not in ocupades[(dia_act, nova_h)] and cap.get(a, 0) >= alums]
        if cands:
            ocupades[(dia_act, h_act)].discard(aula_act)
            ocupades[(dia_act, nova_h)].add(cands[0])
            proposta.loc[idx, "h_ini"] = nova_h
            proposta.loc[idx, "aula"] = cands[0]
            desencavalcades += 1
            break

print(f"   Sesiones de 108271 desencabalgadas: {desencavalcades}")

# 2. UNIFICAR AULAS TE EXTRA (R6)
print("3. Minimizando 'aules TE extra per grup'...")
te_counts = collections.defaultdict(collections.Counter)
for _, r in proposta.iterrows():
    sid = r["id_sessio"]
    if sid not in sessions.index or sessions.loc[sid, "tipus"] != "TE":
        continue
    aula = r["aula"]
    if aula and aula in cap:
        for c in str(sessions.loc[sid, "titulacions_curs"]).split("|"):
            if c:
                te_counts[(c, linia(sessions.loc[sid, "grup"], "TE"))][aula] += 1

base_grup = {k: counter.most_common(1)[0][0] for k, counter in te_counts.items()}

te_unificades = 0
for _, r in proposta.iterrows():
    sid = r["id_sessio"]
    if sid not in sessions.index or sessions.loc[sid, "tipus"] != "TE" or str(sessions.loc[sid, "fixada"]).strip():
        continue
    aula_act = r["aula"]
    base = None
    for c in str(sessions.loc[sid, "titulacions_curs"]).split("|"):
        if (c, linia(sessions.loc[sid, "grup"], "TE")) in base_grup:
            base = base_grup[(c, linia(sessions.loc[sid, "grup"], "TE"))]
            break
    if base and base != aula_act and base not in ocupades[(r["dia"], r["h_ini"])] and cap.get(base, 0) >= int(sessions.loc[sid, "alumnes"] or 0):
        idx = proposta[proposta["id_sessio"] == sid].index[0]
        ocupades[(r["dia"], r["h_ini"])].discard(aula_act)
        ocupades[(r["dia"], r["h_ini"])].add(base)
        proposta.loc[idx, "aula"] = base
        te_unificades += 1

print(f"   Aulas de teoría reubicadas en su aula base: {te_unificades}")

# 3. ALINEAR PAUL AL MISMO PASILLO
print("4. Minimizando 'canvis TE/PAUL fora de passadís'...")
paul_alineats = 0
for _, r in proposta.iterrows():
    sid = r["id_sessio"]
    if sid not in sessions.index or sessions.loc[sid, "tipus"] != "PAUL" or str(sessions.loc[sid, "fixada"]).strip():
        continue
    aula_act = r["aula"]
    base = None
    for c in str(sessions.loc[sid, "titulacions_curs"]).split("|"):
        if (c, linia(sessions.loc[sid, "grup"], "PAUL")) in base_grup:
            base = base_grup[(c, linia(sessions.loc[sid, "grup"], "PAUL"))]
            break
    if not base or passadis(aula_act) == passadis(base):
        continue

    alums = int(sessions.loc[sid, "alumnes"] or 0)
    cands = [
        a for a in sorted(cap.keys())
        if passadis(a) == passadis(base)
        and a not in ocupades[(r["dia"], r["h_ini"])]
        and cap.get(a, 0) >= alums
        and tipus_aula.get(a) in ("Aules docents", "Seminaris", "Aules informàtiques")
    ]
    if cands:
        idx = proposta[proposta["id_sessio"] == sid].index[0]
        ocupades[(r["dia"], r["h_ini"])].discard(aula_act)
        ocupades[(r["dia"], r["h_ini"])].add(cands[0])
        proposta.loc[idx, "aula"] = cands[0]
        paul_alineats += 1

print(f"   Problemas (PAUL) movidos al mismo pasillo: {paul_alineats}")

proposta.to_csv(ARREL / "proposta-torns.csv", index=False)
print("-> Archivo 'proposta-torns.csv' actualizado y optimizado con éxito.")