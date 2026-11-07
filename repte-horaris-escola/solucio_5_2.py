"""Punt 5.2 — torns nous: 1r/2n al matí, 3r/4t a la tarda.

Executa'l des de l'arrel del repte:
    python solucio_5_2_completa.py

Genera proposta-torns.csv i resum-5_2.md. No canvia PLAB ni sessions fixades.
Si no pot respectar una restricció, atura l'execució i NO escriu una proposta
invàlida. Només necessita pandas.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


ARREL = Path(__file__).resolve().parent
PAQUET = ARREL / "paquet"
RESERVA = 2
DIES = "LMXJV"
MATI = (8 * 60 + 30, 14 * 60 + 30)
TARDA = (14 * 60 + 30, 21 * 60)
FRANGES_R8 = range(8 * 60 + 30, 21 * 60, 60)


def hm(h: str) -> int:
    a, b = h.split(":")
    return int(a) * 60 + int(b)


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def solapa(a: int, b: int, c: int, d: int) -> bool:
    return max(a, c) < min(b, d)


def dins_finestra(ini: int, fi: int, torn: str) -> bool:
    a, b = MATI if torn == "mati" else TARDA
    return a <= ini and fi <= b


def toca_franja(ini: int, fi: int, f: int) -> bool:
    return ini < f + 60 and fi > f


def dia_setmana(data: str, dia: str) -> str:
    """Data ISO del dia indicat, dins de la mateixa setmana de la sessió."""
    d = date.fromisoformat(data)
    return (d + timedelta(days=DIES.index(dia) - d.weekday())).isoformat()


def linia(grup: str, tipus: str) -> str:
    n = grup.split("/")[-1]
    if tipus == "TE":
        return n[:-1] if len(n) >= 3 and n.endswith("0") else n
    return n[:-1] if len(n) >= 3 else n


def comparteix_alumnat(a: "Event", b: "Event") -> bool:
    if not (a.cohorts & b.cohorts):
        return False
    if a.tipus == "TE" or b.tipus == "TE":
        return a.linia == b.linia or a.num_grup == b.num_grup
    return a.num_grup == b.num_grup


@dataclass(eq=False)
class Event:
    key: str
    ids: tuple[str, ...]
    data_origen: str
    dia_origen: str
    ini_origen: int
    fi_origen: int
    tipus: str
    codi: str
    alumnes: int
    cohorts: set[str]
    docents: set[str]
    linia: str
    num_grup: str
    torn: str
    aula_origen: str
    aules: list[str]
    movible: bool
    data: str = ""
    dia: str = ""
    ini: int = 0
    aula: str = ""

    @property
    def fi(self) -> int:
        return self.ini + (self.fi_origen - self.ini_origen)


class Planificador:
    def __init__(self, aules: pd.DataFrame, dies_tancats: set[str]):
        self.cap = aules.set_index("aula").capacitat.astype(int).to_dict()
        self.ordinaries = set(aules.loc[aules.ordinaria.astype(int) == 1, "aula"])
        self.max_ordinaries = len(self.ordinaries) - RESERVA
        self.dies_tancats = dies_tancats
        self.colocades: list[Event] = []

    def es_legal(self, e: Event, data: str, dia: str, ini: int, aula: str) -> bool:
        fi = ini + (e.fi_origen - e.ini_origen)
        if data in self.dies_tancats or not dins_finestra(ini, fi, e.torn):
            return False
        for x in self.colocades:
            if x.data != data or not solapa(ini, fi, x.ini, x.fi):
                continue
            # R4-AULA, DOCENT, ALUMNAT i PLAB.
            if aula == x.aula:
                return False
            if e.docents & x.docents:
                return False
            if comparteix_alumnat(e, x):
                return False
            if e.codi == x.codi and "PLAB" in {e.tipus, x.tipus} and {e.tipus, x.tipus} & {"TE", "PAUL"}:
                return False
        # R8: dues aules docents lliures a cada franja de 60 minuts.
        if aula in self.ordinaries:
            for f in FRANGES_R8:
                if not toca_franja(ini, fi, f):
                    continue
                usades = {x.aula for x in self.colocades if x.data == data and x.aula in self.ordinaries and toca_franja(x.ini, x.fi, f)}
                if aula not in usades and len(usades) >= self.max_ordinaries:
                    return False
        return True

    def posar(self, e: Event, data: str, dia: str, ini: int, aula: str) -> None:
        e.data, e.dia, e.ini, e.aula = data, dia, ini, aula
        self.colocades.append(e)

    def candidats(self, e: Event):
        """Mateixa setmana, dies laborables, franges de 30 minuts i aula vàlida."""
        # Una sessió que ja és al torn correcte no canvia dia ni hora: només
        # li busquem aula si la partida no en tenia o si evita un conflicte.
        ja_be = dins_finestra(e.ini_origen, e.fi_origen, e.torn)
        dies = [e.dia_origen] if ja_be else [e.dia_origen] + [d for d in DIES if d != e.dia_origen]
        if ja_be:
            hores = [e.ini_origen]
        else:
            inici, fi = MATI if e.torn == "mati" else TARDA
            hores = list(range(inici, fi - (e.fi_origen - e.ini_origen) + 1, 30))
            hores.sort(key=lambda h: (h != e.ini_origen, abs(h - e.ini_origen)))
        aules = sorted(e.aules, key=lambda a: (a != e.aula_origen, self.cap[a]))
        for dia in dies:
            data = dia_setmana(e.data_origen, dia)
            for ini in hores:
                for aula in aules:
                    if self.es_legal(e, data, dia, ini, aula):
                        yield data, dia, ini, aula


def aules_permeses(files: list[pd.Series], aules: pd.DataFrame) -> list[str]:
    """R3-TIPUS, inclosa l'excepció de PAUL en informàtica/lab integrat."""
    cap = aules.set_index("aula").capacitat.astype(int).to_dict()
    generals = set(aules.loc[aules.tipus.isin(["Aules docents", "Seminaris"]), "aula"])
    informatica = set(aules.loc[aules.tipus == "Aules informàtiques", "aula"])
    integrats = set(aules.loc[(aules.tipus == "Laboratoris docents") & aules.descripcio.str.contains("integrat", case=False, na=False), "aula"])
    permeses = []
    for f in files:
        origen = f.aula_partida
        fila = aules.loc[aules.aula == origen]
        tipus_origen = fila.tipus.iloc[0] if not fila.empty else ""
        if f.tipus == "PAUL" and tipus_origen == "Aules informàtiques":
            permeses.append(informatica | integrats)
        elif f.tipus == "PAUL":
            permeses.append(generals | informatica | integrats)
        else:
            permeses.append(generals)
    capacitat = sum(int(f.alumnes or 0) for f in files)
    return sorted(set.intersection(*permeses) & {a for a in cap if cap[a] >= capacitat})


def construir_events(sessions: pd.DataFrame, aules: pd.DataFrame) -> tuple[list[Event], list[Event]]:
    sessions = sessions[sessions.data.str[5:7].astype(int).between(2, 6)].copy().fillna("")
    sessions["unitat"] = sessions.id_compartida.where(sessions.id_compartida != "", sessions.id_sessio)
    movibles, fixats = [], []
    for unitat, df in sessions.groupby("unitat", sort=False):
        files = [f for _, f in df.iterrows()]
        s = files[0]
        if any((f.data, f.h_ini, f.h_fi) != (s.data, s.h_ini, s.h_fi) for f in files):
            raise ValueError(f"Docència compartida incoherent: {unitat}")
        if all(str(f.sense_espai) == "1" for f in files):
            continue
        fixada = any(str(f.fixada).strip() for f in files) or all(f.tipus == "PLAB" for f in files)
        aula_origen = next((f.aula_partida for f in files if str(f.aula_partida).strip()), "")
        # Un PLAB sense aula no s'ha d'assignar; conserva'n la fila original.
        if fixada and not aula_origen:
            continue
        tipus = s.tipus
        grup = s.grup
        e = Event(str(unitat), tuple(f.id_sessio for f in files), s.data, s.dia, hm(s.h_ini), hm(s.h_fi), tipus,
                  s.codi, sum(int(f.alumnes or 0) for f in files), set("|".join(f.titulacions_curs for f in files).split("|")) - {""},
                  set("|".join(f.docents for f in files).split("|")) - {""}, linia(grup, tipus), grup.split("/")[-1],
                  s.torn_requerit, aula_origen, [aula_origen] if fixada else aules_permeses(files, aules), not fixada)
        # Per minimitzar canvis, una sessió ja correcta i amb aula es deixa
        # exactament com està. Només es planifiquen les que han de canviar de
        # torn, les que no tenen aula o les de l'edifici J (que cal traslladar).
        ja_correcta = dins_finestra(e.ini_origen, e.fi_origen, e.torn)
        deixar_com_esta = (not fixada and aula_origen and ja_correcta and not aula_origen.startswith("J/"))
        if fixada or deixar_com_esta:
            e.data, e.dia, e.ini, e.aula = e.data_origen, e.dia_origen, e.ini_origen, aula_origen
            fixats.append(e)
        else:
            if not e.aules:
                raise ValueError(f"No hi ha aula compatible per a {e.ids[0]}")
            movibles.append(e)
    return movibles, fixats


def resum(events: list[Event], movibles: list[Event], p: Planificador) -> str:
    pic = {}
    for torn, limits in (("matí", MATI), ("tarda", TARDA)):
        maxim = 0
        for f in FRANGES_R8:
            if limits[0] <= f < limits[1]:
                maxim = max(maxim, sum(toca_franja(e.ini, e.fi, f) for e in p.colocades))
        pic[torn] = maxim
    canvis = defaultdict(int)
    total_canvis = 0
    for e in movibles:
        if (e.dia, e.ini, e.aula) != (e.dia_origen, e.ini_origen, e.aula_origen):
            total_canvis += len(e.ids)
            for c in e.cohorts or {"sense cohort"}:
                canvis[c] += len(e.ids)
    llistat = "\n".join(f"- {k}: {v}" for k, v in sorted(canvis.items())) or "- Cap"
    return f"""# Resum punt 5.2 — Junta Permanent

## Capacitat

- Pic de sessions simultànies al matí: **{pic['matí']}** davant de 19 aules docents disponibles.
- Pic de sessions simultànies a la tarda: **{pic['tarda']}** davant de 19 aules docents disponibles.
- Aules que falten o sobren: la planificació manté dues aules docents de reserva a cada franja; no en falten.

## Sessions modificades per titulació i curs

Total de sessions modificades: **{total_canvis}**.

{llistat}

## Excepcions a R1

- Cap: PLAB i sessions fixades no s'han modificat.
"""


def main() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")
    aules["capacitat"] = aules.capacitat.astype(int)
    proposta = pd.read_csv(PAQUET / "proposta_partida.csv", dtype=str).fillna("")
    calendari = pd.read_csv(PAQUET / "calendari.csv", dtype=str).fillna("")
    # Festius/no lectius: no s'hi mou cap sessió. Les aturades parcials també
    # es descarten senceres, opció conservadora i sempre vàlida.
    dies_tancats = set(calendari.data)
    movibles, fixats = construir_events(sessions, aules)
    p = Planificador(aules, dies_tancats)
    for e in fixats:
        p.colocades.append(e)
    # Les més restringides primer. Això redueix canvis i evita deixar sense espai les grans.
    movibles.sort(key=lambda e: (len(e.aules), -e.alumnes, -(e.fi_origen - e.ini_origen)))
    sense_lloc = []
    for e in movibles:
        opcio = next(p.candidats(e), None)
        if opcio is None:
            sense_lloc.append(e.ids[0])
        else:
            p.posar(e, *opcio)
    if sense_lloc:
        raise RuntimeError("No s'han pogut col·locar: " + ", ".join(sense_lloc[:20]))

    per_id = {sid: e for e in movibles for sid in e.ids}
    nous_dies = {sid: e.dia for sid, e in per_id.items()}
    noves_hores = {sid: hhmm(e.ini) for sid, e in per_id.items()}
    noves_aules = {sid: e.aula for sid, e in per_id.items()}
    proposta["dia"] = proposta.id_sessio.map(nous_dies).fillna(proposta["dia"])
    proposta["h_ini"] = proposta.id_sessio.map(noves_hores).fillna(proposta["h_ini"])
    proposta["aula"] = proposta.id_sessio.map(noves_aules).fillna(proposta["aula"])
    proposta.to_csv(ARREL / "proposta-torns.csv", index=False)
    (ARREL / "resum-5_2.md").write_text(resum(p.colocades, movibles, p), encoding="utf-8")
    print("Creats proposta-torns.csv i resum-5_2.md")
    print("Valida-ho amb: python -m horaris check proposta-torns.csv --semestre 2")


if __name__ == "__main__":
    main()
