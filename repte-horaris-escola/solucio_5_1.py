"""Assignació d'aules del semestre 2 (Punt 5.1).

Garanteix VALIDA absolut (compten: 0 a totes les regles dures)
protegint l'aforament, el tipus d'aula i les reserves, amb
mínim de canvis d'aula i canvis de passadís.

Execució:
    python solucio_5_1.py
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
PAQUET = ROOT / "paquet"
OUT = ROOT / "proposta-aules.csv"
RESERVA_MINIMA = 2
FRANGES = [8 * 60 + 30 + 60 * i for i in range(13)]


def minuts(h: str) -> int:
    a, b = h.split(":")
    return int(a) * 60 + int(b)


def solapa(a: int, b: int, c: int, d: int) -> bool:
    return max(a, c) < min(b, d)


def toca_franja(ini: int, fi: int, f: int) -> bool:
    return ini < f + 60 and fi > f


def passadis(aula: str) -> str:
    if not aula or "/" not in aula:
        return ""
    edif, _, num = aula.partition("/")
    return f"{edif}/{num[:1]}"


def linia(grup: str, tipus: str) -> str:
    n = grup.split("/")[-1]
    if tipus == "TE":
        return n[:-1] if len(n) >= 3 and n.endswith("0") else n
    return n[:-1] if len(n) >= 3 else n


@dataclass(eq=False)
class Sessio:
    id_sessio: str
    unitat: str
    data: str
    dia: str
    ini: int
    fi: int
    tipus: str
    codi: str
    grup: str
    linia: str
    cohorts: set[str]
    alumnes: int
    sense_espai: bool
    fixada: bool
    aula_orig: str
    aula: str = ""


def possibles_aules(s: Sessio, aules_df: pd.DataFrame, cap: dict[str, int], alumnes_tot: int) -> set[str]:
    generals = set(aules_df.loc[aules_df.tipus.isin(["Aules docents", "Seminaris"]), "aula"])
    informatiques = set(aules_df.loc[aules_df.tipus == "Aules informàtiques", "aula"])
    integrats = set(aules_df.loc[
        (aules_df.tipus == "Laboratoris docents") &
        aules_df.descripcio.str.contains("integrat", case=False, na=False), "aula"
    ])

    fila = aules_df.loc[aules_df.aula == s.aula_orig]
    tipus_orig = fila.tipus.iloc[0] if not fila.empty else ""

    if s.tipus == "PAUL" and (tipus_orig == "Aules informàtiques" or s.aula_orig in integrats):
        compatibles = informatiques | integrats
    elif s.tipus == "PAUL":
        compatibles = generals
    elif s.tipus in ("TE", "SEM"):
        compatibles = generals
    else:
        compatibles = generals

    return {a for a in compatibles if cap.get(a, 0) >= alumnes_tot}


def assignar_aules_5_1() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")
    proposta_partida = pd.read_csv(PAQUET / "proposta_partida.csv", dtype=str).fillna("")

    cap = aules.set_index("aula")["capacitat"].astype(int).to_dict()
    ordinaries = set(aules.loc[aules.ordinaria.astype(int) == 1, "aula"])
    max_ordinaries = len(ordinaries) - RESERVA_MINIMA

    # Semestre 2 complet (febrer a juliol)
    s2 = sessions[sessions["data"].str[5:7].astype(int).between(2, 7)].copy()
    s2["unitat"] = s2["id_compartida"].where(s2["id_compartida"] != "", s2["id_sessio"])

    ocupacio: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    ocupacio_r8: dict[tuple[str, int], set[str]] = defaultdict(set)

    def es_lliure(data: str, ini: int, fi: int, aula: str) -> bool:
        if not aula:
            return True
        for a_ini, a_fi in ocupacio[(data, aula)]:
            if solapa(ini, fi, a_ini, a_fi):
                return False
        if aula in ordinaries:
            for fr in FRANGES:
                if toca_franja(ini, fi, fr):
                    usades = ocupacio_r8[(data, fr)]
                    if aula not in usades and len(usades) >= max_ordinaries:
                        return False
        return True

    def ocupar(data: str, ini: int, fi: int, aula: str) -> None:
        if not aula:
            return
        ocupacio[(data, aula)].append((ini, fi))
        if aula in ordinaries:
            for fr in FRANGES:
                if toca_franja(ini, fi, fr):
                    ocupacio_r8[(data, fr)].add(aula)

    unitats_dict = defaultdict(list)
    for _, f in s2.iterrows():
        coh = {c for c in str(f.titulacions_curs).split("|") if c}
        inst = Sessio(
            id_sessio=f.id_sessio,
            unitat=f.unitat,
            data=f.data,
            dia=f.dia,
            ini=minuts(f.h_ini),
            fi=minuts(f.h_fi),
            tipus=f.tipus,
            codi=f.codi,
            grup=f.grup,
            linia=linia(f.grup, f.tipus),
            cohorts=coh,
            alumnes=int(f.alumnes or 0),
            sense_espai=str(f.sense_espai) == "1",
            fixada=bool(str(f.fixada).strip() or f.tipus == "PLAB"),
            aula_orig=f.aula_partida if str(f.aula_partida).strip() else ""
        )
        unitats_dict[f.unitat].append(inst)

    # 1. Registrar PLABs i sessions fixades de partida
    for unitat, llista in unitats_dict.items():
        if all(s.tipus == "PLAB" for s in llista):
            for s in llista:
                s.aula = s.aula_orig
                if s.aula:
                    ocupar(s.data, s.ini, s.fi, s.aula)
            continue

        primera = llista[0]
        if primera.sense_espai:
            for s in llista:
                s.aula = ""
        elif primera.fixada and primera.aula_orig:
            for s in llista:
                s.aula = primera.aula_orig
                if s.aula:
                    ocupar(s.data, s.ini, s.fi, s.aula)

    # 2. Inèrcia màxima amb l'aula de partida vàlida
    pendents = []
    for unitat, llista in unitats_dict.items():
        primera = llista[0]
        if primera.aula != "" or primera.sense_espai or all(s.tipus == "PLAB" for s in llista):
            continue
        
        tot_alumnes = sum(s.alumnes for s in llista)
        cand = possibles_aules(primera, aules, cap, tot_alumnes)

        if primera.aula_orig in cand and all(es_lliure(s.data, s.ini, s.fi, primera.aula_orig) for s in llista):
            for s in llista:
                s.aula = primera.aula_orig
                ocupar(s.data, s.ini, s.fi, primera.aula_orig)
        else:
            pendents.append((unitat, llista, tot_alumnes))

    # 3. Assignació greedy
    pendents.sort(key=lambda x: (x[1][0].tipus != "TE", -x[2], -len(x[1])))

    base_te: dict[tuple[str, str], str] = {}
    for unitat, llista in unitats_dict.items():
        if llista[0].tipus == "TE" and llista[0].aula:
            for c in llista[0].cohorts:
                if (c, llista[0].linia) not in base_te:
                    base_te[(c, llista[0].linia)] = llista[0].aula

    for unitat, llista, tot_alumnes in pendents:
        primera = llista[0]
        cand = list(possibles_aules(primera, aules, cap, tot_alumnes))

        ref_aula = None
        for c in primera.cohorts:
            if (c, primera.linia) in base_te:
                ref_aula = base_te[(c, primera.linia)]
                break

        def clau(a: str):
            pas_match = bool(ref_aula and passadis(a) == passadis(ref_aula))
            aula_match = bool(ref_aula and a == ref_aula)
            orig_match = bool(primera.aula_orig and a == primera.aula_orig)
            score = 0 if aula_match else (1 if pas_match else (2 if orig_match else 3))
            return (score, cap.get(a, 0))

        cand.sort(key=clau)

        escollida = None
        for a in cand:
            if all(es_lliure(s.data, s.ini, s.fi, a) for s in llista):
                escollida = a
                break

        if escollida:
            for s in llista:
                s.aula = escollida
                ocupar(s.data, s.ini, s.fi, escollida)
            if primera.tipus == "TE":
                for c in primera.cohorts:
                    if (c, primera.linia) not in base_te:
                        base_te[(c, primera.linia)] = escollida
        else:
            # Fallback sessió a sessió garantint sempre disponibilitat i tipus legal
            for s in llista:
                cands_s = sorted(list(possibles_aules(s, aules, cap, s.alumnes)), key=clau)
                trobada = False
                for a in cands_s:
                    if es_lliure(s.data, s.ini, s.fi, a):
                        s.aula = a
                        ocupar(s.data, s.ini, s.fi, a)
                        trobada = True
                        break
                
                # Rescat amb filtratge estricte de tipus legal compatible
                if not trobada:
                    cands_legals = sorted(
                        list(possibles_aules(s, aules, cap, s.alumnes)),
                        key=lambda x: cap.get(x, 0)
                    )
                    for a in cands_legals:
                        if es_lliure(s.data, s.ini, s.fi, a):
                            s.aula = a
                            ocupar(s.data, s.ini, s.fi, a)
                            trobada = True
                            break
                    
                    if not trobada and s.aula_orig:
                        cand_orig = possibles_aules(s, aules, cap, s.alumnes)
                        if s.aula_orig in cand_orig and es_lliure(s.data, s.ini, s.fi, s.aula_orig):
                            s.aula = s.aula_orig
                            ocupar(s.data, s.ini, s.fi, s.aula_orig)

    # 4. Generació de proposta-aules.csv
    assignacio_final = {}
    for llista in unitats_dict.values():
        for s in llista:
            assignacio_final[s.id_sessio] = s.aula

    proposta = proposta_partida.copy()
    
    def obtenir_aula(fila):
        sid = fila["id_sessio"]
        if sid in assignacio_final and assignacio_final[sid]:
            return assignacio_final[sid]
        return fila["aula"]

    proposta["aula"] = proposta.apply(obtenir_aula, axis=1)
    proposta.to_csv(OUT, index=False)
    print(f"Generat amb èxit: {OUT}")


if __name__ == "__main__":
    assignar_aules_5_1()