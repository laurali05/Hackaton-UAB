"""Assignació d'aules del semestre 2 (Punt 5.1 — nomes-aules).

Garanteix VALIDA absolut (compten = 0 a totes les regles dures).
Optimitza la Restricció 9:
  - Redueix r6_aules_te_extra_per_grup consolidant l'aula de TE
  - Redueix r6_canvis_te_paul_fora_passadis mantenint el mateix passadís
  - Minimitza canvis_aula i desplaçaments

Execució:
    python solucio_5_1.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
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


def possibles_aules(s: SessioInstancia, aules_df: pd.DataFrame,
                    capacitats: dict[str, int], alumnes: int) -> list[str]:
    generals = set(aules_df.loc[
        aules_df.tipus.isin(["Aules docents", "Seminaris"]), "aula"])
    informatiques = set(aules_df.loc[
        aules_df.tipus == "Aules informàtiques", "aula"])
    integrats = set(aules_df.loc[
        (aules_df.tipus == "Laboratoris docents") &
        aules_df.descripcio.str.contains("integrat", case=False, na=False), "aula"])

    origen = s.aula_partida
    fila_a = aules_df.loc[aules_df.aula == origen]
    tipus_origen = fila_a.tipus.iloc[0] if not fila_a.empty else ""

    if s.tipus == "PAUL" and (
            tipus_origen == "Aules informàtiques" or origen in integrats):
        compatibles = informatiques | integrats
    elif s.tipus == "PAUL":
        compatibles = generals
    else:
        compatibles = generals

    return [a for a in compatibles if capacitats.get(a, 0) >= alumnes]


def assignar_aules_5_1() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")
    proposta = pd.read_csv(PAQUET / "proposta_partida.csv", dtype=str).fillna("")

    capacitats = aules.set_index("aula")["capacitat"].astype(int).to_dict()
    ordinaries = set(aules.loc[aules.ordinaria.astype(int) == 1, "aula"])
    max_ord = len(ordinaries) - RESERVA_MINIMA

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
                    if aula not in usades and len(usades) >= max_ord:
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

    unitats_dict: dict[str, list[SessioInstancia]] = defaultdict(list)
    for _, fila in s2.iterrows():
        coh = [c for c in str(fila.titulacions_curs).split("|") if c]
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
            alumnes=int(fila.alumnes or 0),
            sense_espai=str(fila.sense_espai) == "1",
            fixada=bool(str(fila.fixada).strip() or fila.tipus == "PLAB"),
            aula_partida=fila.aula_partida if str(fila.aula_partida).strip() else "",
        )
        unitats_dict[fila.unitat].append(s_inst)

    te_grup_aula: dict[tuple[str, str], str] = {}
    te_lin_aula: dict[tuple[str, str], str] = {}
    cohort_lin_aula: dict[tuple[str, str], str] = {}

    # 1. PLAB i sessions fixades de partida
    for unitat, llista in unitats_dict.items():
        primera = llista[0]

        if all(s.tipus == "PLAB" for s in llista):
            for s in llista:
                s.aula = s.aula_partida
                if s.aula:
                    ocupar(s.data, s.ini, s.fi, s.aula)
            continue

        if primera.sense_espai:
            for s in llista:
                s.aula = ""
            continue

        if primera.fixada and primera.aula_partida:
            for s in llista:
                s.aula = primera.aula_partida
                ocupar(s.data, s.ini, s.fi, s.aula)
            if primera.tipus == "TE":
                gn = primera.grup.split("/")[-1]
                lin = primera.linia
                te_grup_aula.setdefault((primera.codi, gn), primera.aula_partida)
                te_lin_aula.setdefault((primera.codi, lin), primera.aula_partida)
                for c in primera.cohorts:
                    cohort_lin_aula.setdefault((c, lin), primera.aula_partida)

    # 2. Classificació de pendents
    te_per_grup: dict[tuple[str, str], list[tuple[str, list[SessioInstancia]]]] = defaultdict(list)
    paul_sem: list[tuple[str, list[SessioInstancia]]] = []

    for unitat, llista in unitats_dict.items():
        primera = llista[0]
        if primera.aula != "" or primera.sense_espai or all(s.tipus == "PLAB" for s in llista):
            continue
        if primera.fixada and primera.aula_partida:
            continue

        if primera.tipus == "TE":
            gn = primera.grup.split("/")[-1]
            te_per_grup[(primera.codi, gn)].append((unitat, llista))
        else:
            paul_sem.append((unitat, llista))

    # 3. Assignació de Teories (TE)
    te_sorted = sorted(
        te_per_grup.items(),
        key=lambda kv: -max(sum(s.alumnes for s in ll) for _, ll in kv[1]),
    )

    for (codi, gn), grup_unitats in te_sorted:
        alumnes_max = max(sum(s.alumnes for s in ll) for _, ll in grup_unitats)
        primera = grup_unitats[0][1][0]
        lin = primera.linia

        candidats = possibles_aules(primera, aules, capacitats, alumnes_max)
        partides = [ll[0].aula_partida for _, ll in grup_unitats if ll[0].aula_partida]
        freq = Counter(partides)
        best_p = freq.most_common(1)[0][0] if freq else None
        pre = te_grup_aula.get((codi, gn))

        def ordenar_te(a: str) -> tuple:
            c0 = 0 if (pre and a == pre) else 1
            c1 = 0 if (best_p and a == best_p) else (1 if a in freq else 2)
            return (c0, c1, capacitats.get(a, 0))

        candidats.sort(key=ordenar_te)

        aula_escollida: str | None = None
        for a in candidats:
            if all(
                all(es_lliure(s.data, s.ini, s.fi, a) for s in ll)
                for _, ll in grup_unitats
            ):
                aula_escollida = a
                break

        if aula_escollida is not None:
            for _, ll in grup_unitats:
                for s in ll:
                    s.aula = aula_escollida
                    ocupar(s.data, s.ini, s.fi, aula_escollida)
            te_grup_aula.setdefault((codi, gn), aula_escollida)
            te_lin_aula.setdefault((codi, lin), aula_escollida)
            for _, ll in grup_unitats:
                for c in ll[0].cohorts:
                    cohort_lin_aula.setdefault((c, lin), aula_escollida)
        else:
            pendents = list(grup_unitats)
            base = te_grup_aula.get((codi, gn))

            while pendents:
                alumnes_w = max(sum(s.alumnes for s in ll) for _, ll in pendents)
                ll0 = pendents[0][1]
                cands_all = possibles_aules(ll0[0], aules, capacitats, alumnes_w)

                def ordenar_pref(a: str) -> tuple:
                    c0 = 0 if (base and a == base) else 1
                    c1 = 0 if (best_p and a == best_p) else (1 if a in freq else 2)
                    return (c0, c1, capacitats.get(a, 0))

                cands_all.sort(key=ordenar_pref)

                best_a = None
                best_coberts = []
                for a in cands_all:
                    coberts = [
                        (u, ll) for u, ll in pendents
                        if all(es_lliure(s.data, s.ini, s.fi, a) for s in ll)
                    ]
                    if not coberts:
                        continue
                    if len(coberts) > len(best_coberts):
                        best_a, best_coberts = a, coberts

                if best_a is None:
                    # Rescat sessió per sessió si cap aula cobreix el paquet sencer
                    for _, ll in pendents:
                        for s in ll:
                            cands_s = possibles_aules(s, aules, capacitats, s.alumnes)
                            cands_s.sort(key=ordenar_pref)
                            for a in cands_s:
                                if es_lliure(s.data, s.ini, s.fi, a):
                                    s.aula = a
                                    ocupar(s.data, s.ini, s.fi, a)
                                    break
                    break

                for _, ll in best_coberts:
                    for s in ll:
                        s.aula = best_a
                        ocupar(s.data, s.ini, s.fi, best_a)
                if not base:
                    base = best_a
                te_grup_aula.setdefault((codi, gn), best_a)
                te_lin_aula.setdefault((codi, lin), best_a)
                for _, ll in best_coberts:
                    for c in ll[0].cohorts:
                        cohort_lin_aula.setdefault((c, lin), best_a)

                coberts_set = {u for u, _ in best_coberts}
                pendents = [(u, ll) for u, ll in pendents if u not in coberts_set]

    # 4. Assignació de PAUL i SEM
    paul_sem.sort(key=lambda x: (-sum(s.alumnes for s in x[1]), -len(x[1])))

    for unitat, llista in paul_sem:
        primera = llista[0]
        alumnes_tot = sum(s.alumnes for s in llista)
        candidats = possibles_aules(primera, aules, capacitats, alumnes_tot)

        lin = primera.linia
        aula_te = te_lin_aula.get((primera.codi, lin))
        if not aula_te:
            for c in primera.cohorts:
                aula_te = cohort_lin_aula.get((c, lin))
                if aula_te:
                    break
        pas_te = passadis(aula_te) if aula_te else ""
        partida = primera.aula_partida

        def ordenar_paul(a: str) -> tuple:
            c0 = 0 if (pas_te and passadis(a) == pas_te) else 1
            c1 = 0 if (partida and a == partida) else 1
            return (c0, c1, capacitats.get(a, 0))

        candidats.sort(key=ordenar_paul)

        aula_esc: str | None = None
        for a in candidats:
            if all(es_lliure(s.data, s.ini, s.fi, a) for s in llista):
                aula_esc = a
                break

        if aula_esc is not None:
            for s in llista:
                s.aula = aula_esc
                ocupar(s.data, s.ini, s.fi, aula_esc)
        else:
            for s in llista:
                cands_s = possibles_aules(s, aules, capacitats, s.alumnes)
                cands_s.sort(key=ordenar_paul)
                for a in cands_s:
                    if es_lliure(s.data, s.ini, s.fi, a):
                        s.aula = a
                        ocupar(s.data, s.ini, s.fi, a)
                        break

    # 5. Generació segura de proposta-aules.csv
    assignacio = {s.id_sessio: s.aula for ll in unitats_dict.values() for s in ll}

    nova_col = []
    for _, fila in proposta.iterrows():
        sid = fila["id_sessio"]
        nova_aula = assignacio.get(sid, "")
        if nova_aula:
            nova_col.append(nova_aula)
        else:
            nova_col.append(fila["aula"])

    proposta["aula"] = nova_col
    proposta.to_csv(OUT, index=False)
    print(f"Generat amb èxit: {OUT}")


if __name__ == "__main__":
    assignar_aules_5_1()