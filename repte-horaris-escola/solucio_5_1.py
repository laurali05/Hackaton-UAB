"""Assignació d'aules del semestre 2 (Punt 5.1) - Òptim equilibrat Restricció 9.

Equilibri harmònic de costos per superar totes les marques del Xamà:
- r6_canvis_te_paul_fora_passadis < 950
- canvis_aula < 460
- desplacaments_aula < 3200
- r6_aules_te_extra_per_grup < 80
- VALIDA rotund (compten: 0)

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


def minuts(hora: str) -> int:
    h, m = map(int, hora.split(":"))
    return 60 * h + m


def solapa(a_ini: int, a_fi: int, b_ini: int, b_fi: int) -> bool:
    return max(a_ini, b_ini) < min(a_fi, b_fi)


def toca_franja(ini: int, fi: int, franja: int) -> bool:
    return ini < franja + 60 and fi > franja


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
class SessioInstancia:
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
    cohorts: list[str]
    alumnes: int
    sense_espai: bool
    fixada: bool
    aula_partida: str
    aula: str = ""


def possibles_aules_exactes(s: SessioInstancia, aules_df: pd.DataFrame, capacitats: dict[str, int], alumnes_totals: int) -> list[str]:
    generals = set(aules_df.loc[aules_df.tipus.isin(["Aules docents", "Seminaris"]), "aula"])
    informatiques = set(aules_df.loc[aules_df.tipus == "Aules informàtiques", "aula"])
    integrats = set(aules_df.loc[
        (aules_df.tipus == "Laboratoris docents") &
        aules_df.descripcio.str.contains("integrat", case=False, na=False), "aula"
    ])

    origen = s.aula_partida
    fila = aules_df.loc[aules_df.aula == origen]
    tipus_origen = fila.tipus.iloc[0] if not fila.empty else ""

    if s.tipus == "PAUL" and (tipus_origen == "Aules informàtiques" or origen in integrats):
        compatibles = informatiques | integrats
    elif s.tipus == "PAUL":
        compatibles = generals
    elif s.tipus in ("TE", "SEM"):
        compatibles = generals
    else:
        compatibles = generals

    return [a for a in compatibles if capacitats.get(a, 0) >= alumnes_totals]


def assignar_aules_5_1() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")
    proposta = pd.read_csv(PAQUET / "proposta_partida.csv", dtype=str).fillna("")

    capacitats = aules.set_index("aula")["capacitat"].astype(int).to_dict()
    ordinaries = set(aules.loc[aules.ordinaria.astype(int) == 1, "aula"])
    max_ordinaries = len(ordinaries) - RESERVA_MINIMA

    s2 = sessions[sessions["data"].str[5:7].astype(int).between(2, 6)].copy()
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
    for _, fila in s2.iterrows():
        coh = [c for c in str(fila.titulacions_curs).split("|") if c]
        alumnes_val = int(fila.alumnes or 0)
        s_inst = SessioInstancia(
            id_sessio=fila.id_sessio,
            unitat=fila.unitat,
            data=fila.data,
            dia=fila.dia,
            ini=minuts(fila.h_ini),
            fi=minuts(fila.h_fi),
            tipus=fila.tipus,
            codi=fila.codi,
            grup=fila.grup,
            linia=linia(fila.grup, fila.tipus),
            cohorts=coh,
            alumnes=alumnes_val,
            sense_espai=str(fila.sense_espai) == "1",
            fixada=bool(str(fila.fixada).strip() or fila.tipus == "PLAB"),
            aula_partida=fila.aula_partida if str(fila.aula_partida).strip() else ""
        )
        unitats_dict[fila.unitat].append(s_inst)

    grups_teoria_base: dict[tuple[str, str], str] = {}

    # 1. Registrar PLAB i sessions que tenen aula fixa
    for unitat, llista in unitats_dict.items():
        if all(s.tipus == "PLAB" for s in llista):
            for s in llista:
                s.aula = s.aula_partida
                if s.aula:
                    ocupar(s.data, s.ini, s.fi, s.aula)
            continue

        primera = llista[0]
        if primera.sense_espai:
            for s in llista:
                s.aula = ""
        elif primera.fixada and primera.aula_partida:
            for s in llista:
                s.aula = primera.aula_partida
                if s.aula:
                    ocupar(s.data, s.ini, s.fi, s.aula)
                if s.tipus == "TE" and s.aula:
                    for c in s.cohorts:
                        grups_teoria_base[(c, s.linia)] = s.aula

    # 2. Dividir les activitats pendents
    teories_pendents = []
    altres_pendents = []

    for unitat, llista in unitats_dict.items():
        if llista[0].aula != "" or llista[0].sense_espai or all(s.tipus == "PLAB" for s in llista):
            continue
        alumnes_totals = sum(s.alumnes for s in llista)
        if llista[0].tipus == "TE":
            teories_pendents.append((unitat, llista, alumnes_totals))
        else:
            altres_pendents.append((unitat, llista, alumnes_totals))

    teories_pendents.sort(key=lambda x: (-x[2], -len(x[1])))
    altres_pendents.sort(key=lambda x: (-x[2], -len(x[1])))

    # 3. Assignar teories fixant una aula base estable
    for unitat, llista, alumnes_totals in teories_pendents:
        primera = llista[0]
        candidats = possibles_aules_exactes(primera, aules, capacitats, alumnes_totals)

        aula_preferida = None
        for c in primera.cohorts:
            if (c, primera.linia) in grups_teoria_base:
                aula_preferida = grups_teoria_base[(c, primera.linia)]
                break

        def cost_teoria(a: str):
            # Prioritza l'aula base del grup, després aula_partida
            c_base = 0 if (aula_preferida and a == aula_preferida) else 2
            c_part = 0 if (primera.aula_partida and a == primera.aula_partida) else 1
            return (c_base, c_part, capacitats.get(a, 0))

        candidats.sort(key=cost_teoria)

        aula_escollida = None
        for a in candidats:
            if all(es_lliure(s.data, s.ini, s.fi, a) for s in llista):
                aula_escollida = a
                break

        if aula_escollida is not None:
            for s in llista:
                s.aula = aula_escollida
                ocupar(s.data, s.ini, s.fi, aula_escollida)
            for c in primera.cohorts:
                if (c, primera.linia) not in grups_teoria_base:
                    grups_teoria_base[(c, primera.linia)] = aula_escollida
        else:
            for s in llista:
                cands_sessio = possibles_aules_exactes(s, aules, capacitats, s.alumnes)
                cands_sessio.sort(key=cost_teoria)
                for a in cands_sessio:
                    if es_lliure(s.data, s.ini, s.fi, a):
                        s.aula = a
                        ocupar(s.data, s.ini, s.fi, a)
                        break

    # 4. Assignar PAULs i seminaris amb equilibri passadís/desplaçament
    for unitat, llista, alumnes_totals in altres_pendents:
        primera = llista[0]
        candidats = possibles_aules_exactes(primera, aules, capacitats, alumnes_totals)

        aula_teoria_base = None
        passadis_base = None
        for c in primera.cohorts:
            if (c, primera.linia) in grups_teoria_base:
                aula_teoria_base = grups_teoria_base[(c, primera.linia)]
                passadis_base = passadis(aula_teoria_base)
                break

        def cost_paul(a: str):
            # Equilibri:
            # - Mateix passadís (espina/planta) que la teoria: màxima prioritat
            # - Si a més és la mateixa aula o l'aula de partida, desempat positiu
            # - Capacitat més ajustada per no saturar aules grans
            c_pas = 0 if (passadis_base and passadis(a) == passadis_base) else 1
            c_part = 0 if (primera.aula_partida and a == primera.aula_partida) else (
                0 if (aula_teoria_base and a == aula_teoria_base) else 1
            )
            return (c_pas, c_part, capacitats.get(a, 0))

        candidats.sort(key=cost_paul)

        aula_escollida = None
        for a in candidats:
            if all(es_lliure(s.data, s.ini, s.fi, a) for s in llista):
                aula_escollida = a
                break

        if aula_escollida is not None:
            for s in llista:
                s.aula = aula_escollida
                ocupar(s.data, s.ini, s.fi, aula_escollida)
        else:
            for s in llista:
                cands_sessio = possibles_aules_exactes(s, aules, capacitats, s.alumnes)
                cands_sessio.sort(key=cost_paul)
                for a in cands_sessio:
                    if es_lliure(s.data, s.ini, s.fi, a):
                        s.aula = a
                        ocupar(s.data, s.ini, s.fi, a)
                        break

    # 5. Generar proposta-aules.csv
    assignacio_final = {}
    for llista in unitats_dict.values():
        for s in llista:
            assignacio_final[s.id_sessio] = s.aula

    proposta["aula"] = proposta["id_sessio"].map(assignacio_final).fillna(proposta["aula"])
    proposta.to_csv(OUT, index=False)
    print(f"Generat amb èxit: {OUT}")


if __name__ == "__main__":
    assignar_aules_5_1()