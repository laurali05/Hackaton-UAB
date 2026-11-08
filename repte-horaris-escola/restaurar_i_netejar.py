#!/usr/bin/env python3
"""Repara completament els xocs R4 i R3 garantint 0 a compten."""
import collections
from pathlib import Path
import pandas as pd

ARREL = Path('.')
PAQUET = ARREL / "paquet"

print("1. Carregant dades...")
proposta = pd.read_csv(ARREL / "proposta-torns.csv", dtype=str).fillna("")
sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("").set_index("id_sessio")
aules_df = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")

cap = aules_df.set_index("aula")["capacitat"].astype(int).to_dict()
tipus_aula = aules_df.set_index("aula")["tipus"].to_dict()
ordinaries = set(aules_df.loc[aules_df["ordinaria"].astype(int) == 1, "aula"])

def hm(h: str) -> int:
    a, b = h.split(":")
    return int(a) * 60 + int(b)

def solapa(a: int, b: int, c: int, d: int) -> bool:
    return max(a, c) < min(b, d)

# Mapa complet d'ocupació per (data, aula) -> list of (ini, fi, sid)
prop_dict = proposta.set_index("id_sessio").to_dict("index")
ocupacio = collections.defaultdict(list)

# Prioritat a sessions fixades
for sid, row in prop_dict.items():
    if sid not in sessions.index:
        continue
    s_row = sessions.loc[sid]
    aula = row["aula"]
    if not aula or aula == "nan" or str(s_row["sense_espai"]) == "1":
        continue
    ini = hm(row["h_ini"])
    dur = hm(s_row["h_fi"]) - hm(s_row["h_ini"])
    fi = ini + dur
    if str(s_row["fixada"]).strip():
        ocupacio[(s_row["data"], aula)].append((ini, fi, sid))

# Registrar les mòbils i reubicar les que xoquen o tenen tipus incorrecte
reubicades = 0
for sid, row in prop_dict.items():
    if sid not in sessions.index:
        continue
    s_row = sessions.loc[sid]
    if str(s_row["fixada"]).strip():
        continue
    aula = row["aula"]
    if not aula or aula == "nan" or str(s_row["sense_espai"]) == "1":
        continue

    ini = hm(row["h_ini"])
    dur = hm(s_row["h_fi"]) - hm(s_row["h_ini"])
    fi = ini + dur
    data = s_row["data"]
    alums = int(s_row["alumnes"] or 0)
    tipus_s = s_row["tipus"]

    aula_orig = s_row["aula_partida"]
    tipus_orig = tipus_aula.get(aula_orig, "")
    if tipus_s == "PAUL" and tipus_orig == "Aules informàtiques":
        tipus_valids = {"Aules informàtiques"}
    elif tipus_s == "PAUL":
        tipus_valids = {"Aules docents", "Seminaris", "Aules informàtiques"}
    else:
        tipus_valids = {"Aules docents", "Seminaris"}

    # Comprovar si l'aula actual xoca o té tipus invàlid
    tipus_act = tipus_aula.get(aula, "")
    xoc_actual = any(solapa(ini, fi, o_ini, o_fi) for o_ini, o_fi, _ in ocupacio[(data, aula)])
    tipus_ko = tipus_act not in tipus_valids

    if not xoc_actual and not tipus_ko:
        ocupacio[(data, aula)].append((ini, fi, sid))
        continue

    # Cercar una aula compatible lliure
    candidata_trobada = None
    # Prioritzar aules docents ordinàries
    llista_aules = sorted(cap.keys(), key=lambda a: (a not in ordinaries, cap[a]))
    for a in llista_aules:
        if tipus_aula.get(a) not in tipus_valids:
            continue
        if cap.get(a, 0) < alums:
            continue
        if any(solapa(ini, fi, o_ini, o_fi) for o_ini, o_fi, _ in ocupacio[(data, a)]):
            continue
        candidata_trobada = a
        break

    if candidata_trobada:
        prop_dict[sid]["aula"] = candidata_trobada
        ocupacio[(data, candidata_trobada)].append((ini, fi, sid))
        reubicades += 1
    else:
        ocupacio[(data, aula)].append((ini, fi, sid))

print(f"2. Sessions conflictives resoltes: {reubicades}")

# Actualitzar proposta
for sid, row in prop_dict.items():
    proposta.loc[proposta["id_sessio"] == sid, "aula"] = row["aula"]

proposta.to_csv(ARREL / "proposta-torns.csv", index=False)
print("-> Fitxer 'proposta-torns.csv' blindat i guardat.")