"""Assignació d'aules del semestre 2 sense canviar dia ni hora.

Executa'l des de l'arrel del repte:
    python solucio_aules_valida.py

Genera proposta-aules-validada.csv. Necessita pandas.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parent
if not (ROOT / "paquet").exists():
    # Permet guardar l'script dins d'una carpeta de lliurables.
    ROOT = Path.cwd()
PAQUET = ROOT / "paquet"
OUT = ROOT / "proposta-aules-validada.csv"
RESERVA_MINIMA = 2
FRANGES = range(8 * 60 + 30, 21 * 60, 60)


def minuts(hora: str) -> int:
    h, m = map(int, hora.split(":"))
    return 60 * h + m


def solapa(a_ini: int, a_fi: int, b_ini: int, b_fi: int) -> bool:
    return max(a_ini, b_ini) < min(a_fi, b_fi)


def toca_franja(ini: int, fi: int, franja: int) -> bool:
    # Exactament la mateixa definició horària que R8 al verificador.
    return ini < franja + 60 and fi > franja


@dataclass(eq=False)
class Esdeveniment:
    clau: str
    data: str
    ini: int
    fi: int
    files: list[pd.Series]
    capacitat: int
    candidates: list[str]
    partida: str
    fixat: bool = False


class Planificador:
    """Planificador per dia amb backtracking curt i reserva R8 integrada."""

    def __init__(self, aules: pd.DataFrame, ordinaries: set[str]):
        self.capacitat = aules.set_index("aula")["capacitat"].astype(int).to_dict()
        self.ordinaries = ordinaries
        self.max_ordinaries = len(ordinaries) - RESERVA_MINIMA
        self.ocupacio: dict[str, list[Esdeveniment]] = defaultdict(list)
        self.aula_de: dict[str, str] = {}

    def afegir(self, e: Esdeveniment, aula: str) -> None:
        self.ocupacio[aula].append(e)
        self.aula_de[e.clau] = aula

    def treure(self, e: Esdeveniment) -> None:
        aula = self.aula_de.pop(e.clau, None)
        if aula is not None:
            self.ocupacio[aula].remove(e)

    def bloquejadors(self, e: Esdeveniment, aula: str) -> list[Esdeveniment] | None:
        """Retorna què cal moure. None significa que hi ha un fixat."""
        bloquegen = [x for x in self.ocupacio[aula] if solapa(e.ini, e.fi, x.ini, x.fi)]
        if any(x.fixat for x in bloquegen):
            return None

        if aula in self.ordinaries:
            for franja in FRANGES:
                if not toca_franja(e.ini, e.fi, franja):
                    continue
                ocupades = {
                    self.aula_de[x.clau]
                    for x in self.aula_de_event_franja(franja)
                }
                if aula not in ocupades and len(ocupades) >= self.max_ordinaries:
                    # Per alliberar reserva, cal desplaçar una activitat ordinària.
                    extres = [
                        x for x in self.aula_de_event_franja(franja)
                        if x not in bloquegen
                    ]
                    if any(x.fixat for x in extres):
                        return None
                    bloquegen.extend(extres)
        return list(dict.fromkeys(bloquegen))

    def aula_de_event_franja(self, franja: int) -> Iterable[Esdeveniment]:
        for aula in self.ordinaries:
            for e in self.ocupacio[aula]:
                if toca_franja(e.ini, e.fi, franja):
                    yield e

    def col_locar(self, e: Esdeveniment, profunditat: int = 5,
                  vistos: set[str] | None = None) -> bool:
        vistos = set() if vistos is None else vistos
        # Conserva una aula inicial vàlida si no complica l'assignació.
        candidates = sorted(
            e.candidates,
            key=lambda aula: (
                aula != e.partida,
                len(self.ocupacio[aula]),
            ),
        )
        for aula in candidates:
            bloquegen = self.bloquejadors(e, aula)
            if bloquegen is None:
                continue
            if not bloquegen:
                self.afegir(e, aula)
                return True
            if profunditat == 0 or any(x.clau in vistos for x in bloquegen):
                continue

            antic = [(x, self.aula_de[x.clau]) for x in bloquegen]
            for x, _ in antic:
                self.treure(x)
            correcte = True
            for x, _ in antic:
                if not self.col_locar(x, profunditat - 1, vistos | {e.clau, x.clau}):
                    correcte = False
                    break
            if correcte and self.bloquejadors(e, aula) == []:
                self.afegir(e, aula)
                return True

            # Reverteix l'intent complet abans de provar una altra aula.
            for x, _ in antic:
                self.treure(x)
            for x, aula_antiga in antic:
                self.afegir(x, aula_antiga)
        return False


def es_semestre_2(data: str) -> bool:
    # El verificador classifica el semestre per data, no pel camp semestre de Sigma.
    return 2 <= int(data[5:7]) <= 6


def possibles_per_sessio(s: pd.Series, aules: pd.DataFrame) -> set[str]:
    """Replica R3-TIPUS per a sessions que es poden reubicar."""
    generals = set(aules.loc[aules.tipus.isin(["Aules docents", "Seminaris"]), "aula"])
    informatiques = set(aules.loc[aules.tipus == "Aules informàtiques", "aula"])
    integrats = set(aules.loc[
        (aules.tipus == "Laboratoris docents")
        & aules.descripcio.str.contains("integrat", case=False, na=False), "aula"
    ])
    origen = s.aula_partida
    tipus_origen = aules.loc[aules.aula == origen, "tipus"]
    tipus_origen = tipus_origen.iloc[0] if not tipus_origen.empty else None

    # Un PAUL pot usar informàtica o laboratori integrat. Si parteix de
    # l'aula informàtica, R3 exigeix continuar en un d'aquests espais.
    if s.tipus == "PAUL" and tipus_origen == "Aules informàtiques":
        return informatiques | integrats
    if s.tipus == "PAUL":
        return generals | informatiques | integrats
    # TE i SEM, i PAUL procedent d'un laboratori no integrat, es poden posar
    # en aula docent o seminari; els laboratoris no integrats queden exclosos.
    return generals


def construir_esdeveniments(sessions: pd.DataFrame, aules: pd.DataFrame) -> tuple[list[Esdeveniment], list[Esdeveniment]]:
    sessions = sessions[sessions.data.map(es_semestre_2)].copy()
    sessions["clau_fisica"] = sessions.apply(
        lambda s: f"{s.id_compartida or s.id_sessio}|{s.data}", axis=1
    )
    movibles: list[Esdeveniment] = []
    fixats: list[Esdeveniment] = []
    capacitats = aules.set_index("aula")["capacitat"].astype(int).to_dict()

    for clau, df in sessions.groupby("clau_fisica", sort=False):
        files = [fila for _, fila in df.iterrows()]
        primera = files[0]
        if any((f.data, f.h_ini, f.h_fi) != (primera.data, primera.h_ini, primera.h_fi) for f in files):
            raise ValueError(f"Compartida incoherent: {clau}")
        if all(str(f.sense_espai) == "1" for f in files):
            continue
        # PLAB no es toca i no necessita aula si la partida no en tenia.
        pin = next((f for f in files if str(f.fixada).strip() and str(f.aula_partida).strip()), None)
        if pin is None:
            pin = next((f for f in files if f.tipus == "PLAB" and str(f.aula_partida).strip()), None)
        if pin is not None:
            fixats.append(Esdeveniment(clau, primera.data, minuts(primera.h_ini), minuts(primera.h_fi),
                                       files, sum(int(f.alumnes or 0) for f in files), [pin.aula_partida],
                                       pin.aula_partida, True))
            continue
        if all(f.tipus == "PLAB" for f in files):
            continue

        permeses = set.intersection(*(possibles_per_sessio(f, aules) for f in files))
        capacitat = sum(int(f.alumnes or 0) for f in files)  # R3-AFORAMENT suma compartides
        candidates = [a for a in permeses if capacitats[a] >= capacitat]
        if not candidates:
            raise ValueError(f"Cap aula compatible per a {clau} ({capacitat} alumnes)")
        movibles.append(Esdeveniment(clau, primera.data, minuts(primera.h_ini), minuts(primera.h_fi),
                                     files, capacitat, candidates,
                                     primera.aula_partida if pd.notna(primera.aula_partida) else ""))
    return movibles, fixats


def main() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv").fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv").fillna("")
    proposta = pd.read_csv(PAQUET / "proposta_partida.csv").fillna("")
    ordinaries = set(aules.loc[aules.ordinaria.astype(int) == 1, "aula"])
    movibles, fixats = construir_esdeveniments(sessions, aules)

    per_dia: dict[str, list[Esdeveniment]] = defaultdict(list)
    for e in movibles:
        per_dia[e.data].append(e)
    assignacions: dict[str, str] = {}

    for data, esdeveniments in per_dia.items():
        p = Planificador(aules, ordinaries)
        for e in (x for x in fixats if x.data == data):
            p.afegir(e, e.candidates[0])
        # Primer les activitats amb menys alternatives, després les més grans.
        esdeveniments.sort(key=lambda e: (len(e.candidates), -e.capacitat, -(e.fi - e.ini)))
        no_col_locats = [e for e in esdeveniments if not p.col_locar(e)]
        if no_col_locats:
            ids = ", ".join(e.files[0].id_sessio for e in no_col_locats[:8])
            raise RuntimeError(f"No s'han pogut assignar {len(no_col_locats)} sessions del {data}: {ids}")
        assignacions.update(p.aula_de)

    # Propaga una única aula a totes les files d'una sessió compartida.
    per_id: dict[str, str] = {}
    for e in movibles:
        aula = assignacions[e.clau]
        per_id.update({f.id_sessio: aula for f in e.files})
    proposta["aula"] = proposta.id_sessio.map(per_id).fillna(proposta.aula)
    proposta.to_csv(OUT, index=False)
    print(f"Creat: {OUT} ({len(per_id)} sessions amb aula calculada)")


if __name__ == "__main__":
    main()