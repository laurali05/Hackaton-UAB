"""Punt 5.2 — torns nous: 1r/2n al matí, 3r/4t a la tarda.

Executa'l des de l'arrel del repte:
    python solucio_5_3.py

Genera:
    proposta-torns.csv          proposta final (la millor que passa el verificador)
    _candidates/                fitxers de treball: base i candidates (es poden esborrar)
    relaxacions-5_2.csv         excepcions declarades
    resum-5_2.md                resum per a la Junta Permanent
    graella-setmanal-aules.csv  graella setmanal per aula (regla 10)

Millores respecte de la versió anterior:
  1. Reintents adaptatius: les sessions sense lloc passen al davant a l'intent
     següent, i es conserva el millor intent (no l'últim).
  2. Aula base per activitat i grup (TE/PAUL al mateix passadís, sense canviar
     l'aula d'avui si no cal): menys canvis d'aula, desplaçaments i r6.
  3. Optimitzador de franges amb les definicions EXACTES dels objectius del verificador
     (hores mortes, desplaçaments, canvis de franja): mou sessions dins la seva setmana.
  4. Neteja de conflictes d'aula (R4-AULA) i reserva d'aula lliure per a les pendents.
  5. Guarda: cada candidata es passa pel verificador (python -m horaris check) i
     es tria per (veredicte, incompliments que compten, declarats, objectius).
     Si no es pot llegir l'informe, es conserva la base.
Només necessita pandas.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
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
INTENTS = 8
OPT_SEGONS = int(os.environ.get("OPT_SEGONS", "240"))  # temps màxim de l'optimitzador per candidata
SORTIDA = ARREL / "proposta-torns.csv"
CANDIDATES = ARREL / "_candidates"   # fitxers de treball (es poden esborrar)
BASE_CSV = CANDIDATES / "base.csv"
EXCEPCIONS = ARREL / "relaxacions-5_2.csv"


def hm(h: str) -> int:
    a, b = h.split(":")
    return int(a) * 60 + int(b)


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def solapa(a: int, b: int, c: int, d: int) -> bool:
    return max(a, c) < min(b, d)


def dins_finestra(ini: int, fi: int, torn: str) -> bool:
    if torn == "mati":
        a, b = MATI
    elif torn == "tarda":
        a, b = TARDA
    else:
        raise ValueError(f"Torn no reconegut: {torn!r} (s'esperava 'mati' o 'tarda')")
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
    for cohort in a.cohorts & b.cohorts:
        grups_a = a.grups_per_cohort.get(
            cohort, {(a.tipus, a.linia, a.num_grup)}
        )
        grups_b = b.grups_per_cohort.get(
            cohort, {(b.tipus, b.linia, b.num_grup)}
        )
        for tipus_a, linia_a, num_a in grups_a:
            for tipus_b, linia_b, num_b in grups_b:
                if tipus_a == "TE" or tipus_b == "TE":
                    if linia_a == linia_b or num_a == num_b:
                        return True
                elif num_a == num_b:
                    return True
    return False


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
    grups_per_cohort: dict[str, set[tuple[str, str, str]]]
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
    def __init__(self, aules: pd.DataFrame, dies_tancats: set[str],
                 dies_avaluacio: set[str], aturades: dict[str, list[tuple[int, int]]]):
        self.cap = aules.set_index("aula").capacitat.astype(int).to_dict()
        self.ordinaries = set(aules.loc[aules.ordinaria.astype(int) == 1, "aula"])
        self.max_ordinaries = len(self.ordinaries) - RESERVA
        self.dies_tancats = dies_tancats
        self.dies_avaluacio = dies_avaluacio
        self.aturades = aturades
        self.colocades: list[Event] = []
        # Index per dia: evitam escanejar tot el semestre per a cada aula candidata.
        self.per_data: dict[str, list[Event]] = defaultdict(list)
        self.ocupacio_r8: dict[tuple[str, int], set[str]] = defaultdict(set)

    def registrar(self, e: Event) -> None:
        self.colocades.append(e)
        self.per_data[e.data].append(e)
        if e.aula in self.ordinaries:
            for f in FRANGES_R8:
                if toca_franja(e.ini, e.fi, f):
                    self.ocupacio_r8[(e.data, f)].add(e.aula)

    def es_legal(self, e: Event, data: str, dia: str, ini: int, aula: str) -> bool:
        fi = ini + (e.fi_origen - e.ini_origen)
        if not self.horari_legal(e, data, ini, fi):
            return False
        for x in self.per_data[data]:
            if not solapa(ini, fi, x.ini, x.fi):
                continue
            # R4-AULA, DOCENT, ALUMNAT i PLAB.
            if aula and aula == x.aula:
                return False
            heretat = (
                data == e.data_origen
                and ini == e.ini_origen
                and x.data_origen == e.data_origen
                and x.ini == x.ini_origen
                and x.data == x.data_origen
                and solapa(
                    e.ini_origen, e.fi_origen,
                    x.ini_origen, x.fi_origen,
                )
            )
            if e.docents & x.docents and not heretat:
                return False
            if comparteix_alumnat(e, x) and not heretat:
                return False
            xoc_plab = (
                e.codi == x.codi
                and "PLAB" in {e.tipus, x.tipus}
                and bool({e.tipus, x.tipus} & {"TE", "PAUL"})
            )
            if xoc_plab and not heretat:
                return False
        # R8: dues aules docents lliures a cada franja de 60 minuts.
        if aula in self.ordinaries:
            for f in FRANGES_R8:
                if not toca_franja(ini, fi, f):
                    continue
                usades = self.ocupacio_r8[(data, f)]
                if aula not in usades and len(usades) >= self.max_ordinaries:
                    return False
        return True

    def horari_legal(self, e: Event, data: str, ini: int, fi: int) -> bool:
        mateix_slot = data == e.data_origen and ini == e.ini_origen
        if data in self.dies_tancats:
            return False
        torn_ok = dins_finestra(ini, fi, e.torn)
        # Una sessió R1 fixada sense aula no es pot moure de franja. Es permet
        # assignar-li aula al seu horari original si capta dins l'horari lectiu;
        # la discrepància de torn es declararà explícitament com a relaxació.
        fixada_al_origen = not e.movible and mateix_slot
        dins_horari_docent = (
            dins_finestra(ini, fi, "mati") or dins_finestra(ini, fi, "tarda")
        )
        if not torn_ok and not (fixada_al_origen and dins_horari_docent):
            return False
        if data in self.dies_avaluacio and data != e.data_origen:
            return False
        for aturada_ini, aturada_fi in self.aturades.get(data, []):
            if solapa(ini, fi, aturada_ini, aturada_fi) and not (
                    data == e.data_origen
                    and solapa(e.ini_origen, e.fi_origen, aturada_ini, aturada_fi)):
                return False
        return True

    def posar(self, e: Event, data: str, dia: str, ini: int, aula: str) -> None:
        e.data, e.dia, e.ini, e.aula = data, dia, ini, aula
        self.registrar(e)

    def treure(self, e: Event) -> None:
        self.colocades.remove(e)
        self.per_data[e.data].remove(e)
        if e.aula in self.ordinaries:
            for f in FRANGES_R8:
                if toca_franja(e.ini, e.fi, f) and not any(
                        x.aula == e.aula and toca_franja(x.ini, x.fi, f)
                        for x in self.per_data[e.data]):
                    self.ocupacio_r8[(e.data, f)].discard(e.aula)

    def candidats(self, e: Event, ignorar_conflictes: bool = False):
        """Mateixa setmana, dies laborables, franges de 30 minuts i aula vàlida.

        Es prova primer la posició original. Les sessions no fixades que ja
        compleixen el torn només es mouen si la posició original bloqueja una
        altra sessió o no compleix una altra restricció.
        """
        ja_be = dins_finestra(e.ini_origen, e.fi_origen, e.torn)
        inici, fi = MATI if e.torn == "mati" else TARDA
        hores_possibles = list(range(inici, fi - (e.fi_origen - e.ini_origen) + 1, 30))
        if ja_be and e.ini_origen not in hores_possibles:
            hores_possibles.append(e.ini_origen)
        hores = sorted(hores_possibles, key=lambda h: (h != e.ini_origen, abs(h - e.ini_origen)))
        dies = [e.dia_origen] + [d for d in DIES if d != e.dia_origen]
        # Les sessions fixades sense aula poden rebre'n una, però mantenen
        # estrictament el dia i l'hora d'origen.
        if not e.movible:
            dies = [e.dia_origen]
            hores = [e.ini_origen]
        aules = sorted(e.aules, key=lambda a: (a != e.aula_origen, self.cap.get(a, 0)))
        for dia in dies:
            data = dia_setmana(e.data_origen, dia)
            for ini in hores:
                for aula in aules:
                    fi_sessio = ini + (e.fi_origen - e.ini_origen)
                    if (self.horari_legal(e, data, ini, fi_sessio)
                            and (ignorar_conflictes or self.es_legal(e, data, dia, ini, aula))):
                        yield data, dia, ini, aula

    def bloquejadors(self, e: Event, data: str, ini: int, aula: str) -> list[Event]:
        fi = ini + (e.fi_origen - e.ini_origen)
        blocked = set()
        for x in self.per_data[data]:
            if not solapa(ini, fi, x.ini, x.fi):
                continue
            if ((aula and aula == x.aula) or e.docents & x.docents or comparteix_alumnat(e, x)
                    or (e.codi == x.codi and "PLAB" in {e.tipus, x.tipus}
                        and {e.tipus, x.tipus} & {"TE", "PAUL"})):
                blocked.add(x)
        if aula in self.ordinaries:
            for f in FRANGES_R8:
                if (toca_franja(ini, fi, f) and aula not in self.ocupacio_r8[(data, f)]
                        and len(self.ocupacio_r8[(data, f)]) >= self.max_ordinaries):
                    blocked.update(x for x in self.per_data[data]
                                   if x.aula in self.ordinaries and toca_franja(x.ini, x.fi, f))
        return list(blocked)


def reparar_una_sessio(p: Planificador, event: Event) -> bool:
    """Mou un màxim de tres bloquejadores flexibles per salvar una sessió pendent."""
    fallback = None
    if event in p.colocades:
        fallback = (event.data, event.dia, event.ini, event.aula)
        p.treure(event)
    for opcio in p.candidats(event, ignorar_conflictes=True):
        data, dia, ini, aula = opcio
        blockers = p.bloquejadors(event, data, ini, aula)
        if len(blockers) > 6 or any(not x.movible for x in blockers):
            continue
        previous = {x: (x.data, x.dia, x.ini, x.aula) for x in blockers}
        for x in blockers:
            p.treure(x)
        if not p.es_legal(event, data, dia, ini, aula):
            for x in blockers:
                p.posar(x, *previous[x])
            continue
        p.posar(event, *opcio)
        relocated = []
        success = True
        for x in sorted(blockers, key=lambda z: (len(z.aules), -z.alumnes)):
            alternative = next(p.candidats(x), None)
            if alternative is None:
                success = False
                break
            p.posar(x, *alternative)
            relocated.append(x)
        if success:
            return True
        for x in relocated:
            p.treure(x)
        p.treure(event)
        for x in blockers:
            p.posar(x, *previous[x])
    if fallback is not None:
        p.posar(event, *fallback)
    return False


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
    # Una activitat compartida entre plans és una sola classe física: no se
    # sumen dues vegades els mateixos estudiants.
    capacitat = max(int(f.alumnes or 0) for f in files)
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
        sense_espai = all(str(f.sense_espai) == "1" for f in files)
        fixada = any(str(f.fixada).strip() for f in files) or all(
            f.tipus == "PLAB" for f in files
        )
        aula_origen = next(
            (f.aula_partida for f in files if str(f.aula_partida).strip()), ""
        )

        # No necessiten aula, però sí que s'han de planificar perquè
        # compleixin el torn i no provoquin solapaments d'alumnat/docència.
        if sense_espai:
            aula_origen = ""
            aules_event = [""]
        # Els PLAB fixats sense aula es mantenen a l'horari d'origen,
        # però han de continuar bloquejant docent, alumnat i assignatura.
        elif fixada and not aula_origen and all(
            f.tipus == "PLAB" for f in files
        ):
            aules_event = [""]
        elif fixada and aula_origen:
            aules_event = [aula_origen]
        else:
            aules_event = aules_permeses(files, aules)
        tipus = s.tipus
        grup = s.grup
        grups_per_cohort: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        for f in files:
            num = f.grup.split("/")[-1]
            grup_fila = (f.tipus, linia(f.grup, f.tipus), num)
            for cohort in str(f.titulacions_curs).split("|"):
                if cohort:
                    grups_per_cohort[cohort].add(grup_fila)
        e = Event(str(unitat), tuple(f.id_sessio for f in files), s.data, s.dia, hm(s.h_ini), hm(s.h_fi), tipus,
                  s.codi, max(int(f.alumnes or 0) for f in files), set("|".join(f.titulacions_curs for f in files).split("|")) - {""},
                  set("|".join(f.docents for f in files).split("|")) - {""}, linia(grup, tipus), grup.split("/")[-1],
                  dict(grups_per_cohort),
                    s.torn_requerit, aula_origen, aules_event, not fixada)        # Les sessions fixades es mantenen; la resta poden canviar si cal.
        # Es prova primer la ubicació original per minimitzar moviments.
        if sense_espai and fixada:
            e.data, e.dia, e.ini, e.aula = (
                e.data_origen, e.dia_origen, e.ini_origen, ""
            )
            fixats.append(e)
            continue
        if fixada and aula_origen:
            e.data, e.dia, e.ini, e.aula = (
                e.data_origen, e.dia_origen, e.ini_origen, aula_origen
            )
            fixats.append(e)
        elif fixada:
            # Puede recibir aula, pero conserva su día y hora.
            movibles.append(e)
        else:
            if not e.aules:
                raise ValueError(f"No hi ha aula compatible per a {e.ids[0]}")
            movibles.append(e)
    return movibles, fixats


def resum(events: list[Event], movibles: list[Event], p: Planificador,
          sense_lloc: list[str] | None = None,
          relaxacions_r1: list[str] | None = None,
          relaxacions_r2: list[str] | None = None) -> str:
    pic = {}
    for torn, limits in (("matí", MATI), ("tarda", TARDA)):
        maxim = 0
        dates = {e.data for e in p.colocades}
        for data in dates:
            for f in FRANGES_R8:
                if limits[0] <= f < limits[1]:
                    maxim = max(maxim, len(p.ocupacio_r8[(data, f)]))
        pic[torn] = maxim
    canvis = defaultdict(int)
    total_canvis = 0
    for e in movibles:
        if (e.dia, e.ini, e.aula) != (e.dia_origen, e.ini_origen, e.aula_origen):
            total_canvis += len(e.ids)
            for c in e.cohorts or {"sense cohort"}:
                canvis[c] += len(e.ids)
    llistat = "\n".join(f"- {k}: {v}" for k, v in sorted(canvis.items())) or "- Cap"
    pendents = sense_lloc or []
    relaxacions = relaxacions_r1 or []
    relaxacions_calendari = relaxacions_r2 or []
    estat = (
        "INCOMPLETA" if pendents
        else "COMPLETA AMB RELAXACIONS" if relaxacions or relaxacions_calendari
        else "COMPLETA"
    )
    pendents_md = "\n".join(f"- {sid}" for sid in pendents) or "- Cap"
    relaxacions_md = (
        f"- R1-TORN: {len(relaxacions)} sessions fixades sense aula; "
        "justificació i IDs a relaxacions-5_2.csv."
        if relaxacions else "- Cap"
    )
    relaxacions_calendari_md = (
        f"- R2-CALENDARI: {len(relaxacions_calendari)} sessions; "
        "no hi havia franja del torn lliure a la setmana original."
        if relaxacions_calendari else "- Cap"
    )
    return f"""# Resum punt 5.2 — Junta Permanent

Estat de la planificació: **{estat}**.

## Capacitat

- Pic d'aules ordinàries ocupades al matí: **{pic['matí']}** de 21 (19 com a màxim per reservar-ne dues).
- Pic d'aules ordinàries ocupades a la tarda: **{pic['tarda']}** de 21 (19 com a màxim per reservar-ne dues).
- Aules que falten o sobren: la planificació manté dues aules docents de reserva a cada franja; no en falten.

## Sessions modificades per titulació i curs

Total de sessions modificades: **{total_canvis}**.

{llistat}

## Excepcions a R1

{relaxacions_md}

## Excepcions a R2

{relaxacions_calendari_md}

## Sessions pendents d'assignació

{pendents_md}
"""


# ---------------------------------------------------------------------------
# Estat, millores locals i escriptura
# ---------------------------------------------------------------------------
def instantania(movibles: list[Event]) -> dict[Event, tuple[str, str, int, str]]:
    return {e: (e.data, e.dia, e.ini, e.aula) for e in movibles}


def reconstruir(aules, dies_tancats, dies_avaluacio, aturades,
                fixats: list[Event], movibles: list[Event], estat) -> Planificador:
    p = Planificador(aules, dies_tancats, dies_avaluacio, aturades)
    for e in fixats:
        p.registrar(e)
    for e in movibles:
        p.posar(e, *estat[e])
    return p


def passadis(aula: str) -> tuple[str, str]:
    """Mateixa espina i planta (Q4/0011 -> ('Q4', '0'))."""
    if "/" not in aula:
        return (aula, "")
    esp, num = aula.split("/", 1)
    return (esp, num[:1])


def aula_lliure(p: Planificador, e: Event, data: str, ini: int, aula: str) -> bool:
    """Només comprova solapament d'aula i reserva R8 (no docent/alumnat)."""
    if not aula:
        return True
    fi = ini + (e.fi_origen - e.ini_origen)
    for x in p.per_data[data]:
        if x is not e and x.aula == aula and solapa(ini, fi, x.ini, x.fi):
            return False
    if aula in p.ordinaries:
        for f in FRANGES_R8:
            if toca_franja(ini, fi, f):
                usades = p.ocupacio_r8[(data, f)]
                if aula not in usades and len(usades) >= p.max_ordinaries:
                    return False
    return True


def conflictes_aula(p: Planificador) -> list[tuple[Event, Event]]:
    out = []
    for data, evs in list(p.per_data.items()):
        ev = sorted((x for x in evs if x.aula), key=lambda x: x.ini)
        for i, a in enumerate(ev):
            for b in ev[i + 1:]:
                if b.ini >= a.fi:
                    break
                if a.aula == b.aula:
                    out.append((a, b))
    return out


def _en_conflicte(p: Planificador, e: Event) -> bool:
    return bool(e.aula) and any(
        x is not e and x.aula == e.aula and solapa(e.ini, e.fi, x.ini, x.fi)
        for x in p.per_data[e.data])


def netejar_conflictes_aula(p: Planificador, movibles: list[Event]) -> int:
    """Desfà solapaments d'aula (R4-AULA) on intervé alguna sessió flexible."""
    mov = set(movibles)
    arreglats = 0
    for _ in range(3):
        parelles = [(a, b) for a, b in conflictes_aula(p) if a in mov or b in mov]
        if not parelles:
            break
        for a, b in parelles:
            for e in sorted((x for x in (a, b) if x in mov),
                            key=lambda x: not p.horari_legal(x, x.data, x.ini, x.fi)):
                if not _en_conflicte(p, e):
                    break
                antic = (e.data, e.dia, e.ini, e.aula)
                p.treure(e)
                aules = sorted(e.aules, key=lambda r: (r != e.aula_origen, p.cap.get(r, 0)))
                nova = next((r for r in aules
                             if r and r != antic[3] and aula_lliure(p, e, antic[0], antic[2], r)), None)
                if nova is not None:
                    p.posar(e, antic[0], antic[1], antic[2], nova)
                    arreglats += 1
                    break
                opcio = next(p.candidats(e), None)
                if opcio is not None:
                    p.posar(e, *opcio)
                    arreglats += 1
                    break
                p.posar(e, *antic)
    return arreglats


def assignar_aules_base(p: Planificador, movibles: list[Event]) -> int:
    """Una sola aula per activitat (mateix dia/hora cada setmana) i per grup."""
    grups: dict[tuple, list[Event]] = defaultdict(list)
    for e in movibles:
        if e.aula and e.aules != [""]:
            grups[(e.codi, e.tipus, e.num_grup, e.dia, e.ini)].append(e)
    ordre = sorted(grups, key=lambda k: ({"TE": 0, "PAUL": 1}.get(k[1], 2), k))
    base_linia: dict[tuple[str, str], str] = {}
    canvis = 0
    for k in ordre:
        evs = grups[k]
        lk = (k[0], evs[0].linia)
        b = base_linia.get(lk)
        permeses = set(evs[0].aules)
        for e in evs[1:]:
            permeses &= set(e.aules)
        if not permeses:
            continue
        origen = evs[0].aula_origen
        actual = evs[0].aula

        def clau(a: str, b=b, origen=origen, actual=actual):
            return (bool(origen) and a != origen,                  # no canviar l'aula d'avui
                    b is not None and a != b,                      # aula base del grup
                    b is not None and passadis(a) != passadis(b),  # mateix passadís
                    a != actual,                                   # estabilitat
                    p.cap.get(a, 0), a)

        candidates = sorted(permeses, key=clau)
        anteriors = [(e, e.data, e.dia, e.ini, e.aula) for e in evs]
        for e in evs:
            p.treure(e)
        comuna = next((a for a in candidates
                       if all(p.es_legal(e, e.data, e.dia, e.ini, a) for e in evs)), None)
        if comuna is not None:
            triades = [comuna] * len(evs)
        else:  # cap aula val per a totes les setmanes: la millor per a cada una
            triades = [next((a for a in candidates if p.es_legal(e, e.data, e.dia, e.ini, a)), a_ant)
                       for e, _, _, _, a_ant in anteriors]
        for (e, d, di, i, a_ant), a in zip(anteriors, triades):
            p.posar(e, d, di, i, a)
            canvis += a != a_ant
        base_linia.setdefault(lk, triades[0])
    return canvis


def objectiu_data(events: list[Event]) -> tuple[int, int, int]:
    """Hores mortes, desplaçaments d'aula i d'edifici d'un dia (mateixa lògica que check._objectius)."""
    agenda: dict[tuple, list[Event]] = defaultdict(list)
    for c in events:
        sg = "*" if c.tipus == "TE" else c.num_grup
        for coh in c.cohorts:
            agenda[(coh, c.linia, sg)].append(c)
    linies: dict[tuple, set] = defaultdict(set)
    for (coh, lin, sg) in agenda:
        linies[(coh, lin)].add(sg)
    mortes = desp = edif = 0
    for (coh, lin), sgs in linies.items():
        teoria = agenda.get((coh, lin, "*"), [])
        reals = [x for x in sgs if x != "*"] or ["*"]
        for sg in reals:
            cs = teoria + (agenda.get((coh, lin, sg), []) if sg != "*" else [])
            if len(cs) < 2:
                continue
            cs = sorted({id(c): c for c in cs}.values(), key=lambda c: c.ini)
            for a, b in zip(cs, cs[1:]):
                gap = b.ini - a.fi
                if gap > 0 and (a.fi <= MATI[1]) == (b.ini < MATI[1]):
                    mortes += gap
                if a.aula and b.aula and a.aula != b.aula:
                    desp += 1
                    if a.aula.split("/")[0] != b.aula.split("/")[0]:
                        edif += 1
    return mortes, desp, edif


def optimitzar_slots(p: Planificador, movibles: list[Event], segons: float) -> int:
    """Mou sessions dins la seva setmana si millora (hores mortes + desplaçaments + canvis de franja),
    amb pesos normalitzats pel valor actual de cada objectiu. Cada moviment passa per es_legal()."""
    t0 = time.time()
    tot_m = tot_d = 0
    for data in list(p.per_data):
        m, d, _ = objectiu_data(p.per_data[data])
        tot_m += m
        tot_d += d
    franja = sum(len(e.ids) for e in movibles if (e.dia, e.ini) != (e.dia_origen, e.ini_origen))
    wm, wd, wf = 1 / max(tot_m, 1), 1 / max(tot_d, 1), 1 / max(franja, 1)
    pes = lambda t: wm * t[0] + wd * t[1] + 1000 * wd * t[2]
    fets = 0
    moguts = [e for e in movibles if e.movible and (e.dia, e.ini) != (e.dia_origen, e.ini_origen)]
    resta = [e for e in movibles if e.movible and (e.dia, e.ini) == (e.dia_origen, e.ini_origen)]
    for llista in (moguts, resta):
        for e in llista:
            if time.time() - t0 > segons:
                return fets
            if not p.horari_legal(e, e.data, e.ini, e.fi):
                continue  # sessió pendent d'excepció: no es toca
            antic = (e.data, e.dia, e.ini, e.aula)
            dur = e.fi_origen - e.ini_origen
            inici, final = MATI if e.torn == "mati" else TARDA
            hores = list(range(inici, final - dur + 1, 30))
            if dins_finestra(e.ini_origen, e.fi_origen, e.torn) and e.ini_origen not in hores:
                hores.append(e.ini_origen)
            p.treure(e)
            cache: dict[str, float] = {}

            def valor(data: str, dia: str, ini: int) -> float:
                if data not in cache:
                    cache[data] = pes(objectiu_data(p.per_data[data]))
                e.ini = ini
                v = pes(objectiu_data(p.per_data[data] + [e])) - cache[data]
                return v + wf * len(e.ids) * ((dia, ini) != (e.dia_origen, e.ini_origen))

            millor_v, millor_pos = valor(antic[0], antic[1], antic[2]), None
            for dia in DIES:
                data = dia_setmana(e.data_origen, dia)
                for ini in hores:
                    if (data, ini) == (antic[0], antic[2]):
                        continue
                    if not p.es_legal(e, data, dia, ini, antic[3]):
                        continue
                    v = valor(data, dia, ini)
                    if v < millor_v - 1e-12:
                        millor_v, millor_pos = v, (data, dia, ini)
            if millor_pos is None:
                p.posar(e, *antic)
            else:
                data, dia, ini = millor_pos
                p.posar(e, data, dia, ini, antic[3])
                fets += 1
    return fets


def indicadors(p: Planificador, movibles: list[Event]) -> dict:
    """Indicadors propis i aproximats (el bo és el del verificador)."""
    franja = sum(len(e.ids) for e in movibles if (e.dia, e.ini) != (e.dia_origen, e.ini_origen))
    aula = sum(len(e.ids) for e in movibles if e.aula_origen and e.aula != e.aula_origen)
    mortes = desp = 0
    for data in list(p.per_data):
        m, d, _ = objectiu_data(p.per_data[data])
        mortes += m
        desp += d
    return {"canvis_franja": franja, "canvis_aula": aula,
            "desplacaments": desp, "hores_mortes_min": mortes,
            "conflictes_aula": len(conflictes_aula(p))}


def escriure_proposta(p: Planificador, movibles: list[Event], proposta: pd.DataFrame, cami: Path) -> None:
    colocades = set(p.colocades)
    per_id = {sid: e for e in movibles if e in colocades for sid in e.ids}
    out = proposta.copy()
    out["dia"] = out.id_sessio.map({s: e.dia for s, e in per_id.items()}).fillna(out["dia"])
    out["h_ini"] = out.id_sessio.map({s: hhmm(e.ini) for s, e in per_id.items()}).fillna(out["h_ini"])
    out["aula"] = out.id_sessio.map({s: e.aula for s, e in per_id.items()}).fillna(out["aula"])
    tmp = cami.with_name("." + cami.name + ".tmp")
    out.to_csv(tmp, index=False)
    # El reemplaç al final evita deixar un CSV truncat si l'escriptura falla.
    tmp.replace(cami)


def calcular_excepcions(movibles: list[Event]) -> tuple[list[str], list[str]]:
    torn_incorrecte_a_origen = lambda e: (
        e.torn in {"mati", "tarda"}
        and e.data == e.data_origen
        and e.ini == e.ini_origen
        and ((e.ini_origen < MATI[1]) != (e.torn == "mati"))
    )
    fixades_r1 = sorted({
        sid for e in movibles
        if torn_incorrecte_a_origen(e) and not e.movible and not e.aula_origen and e.aula
        for sid in e.ids
    })
    pendents_r1 = sorted({
        sid for e in movibles
        if torn_incorrecte_a_origen(e) and e.movible
        for sid in e.ids
    })
    return fixades_r1, pendents_r1


def escriure_excepcions(fixades_r1: list[str], pendents_r1: list[str], detall: list[str]) -> None:
    """IMPORTANT: la fila de les sessions fixades NO s'ha de treure. Són sessions fixes de 1r/2n a la tarda
    a les quals cal posar aula (R5); el verificador les compta com a R1-TORN i només es pot declarar."""
    files = []
    if fixades_r1:
        files.append({
            "restriccio": "R1-TORN",
            "sessions": "|".join(fixades_r1),
            "justificacio": (
                "Sessions fixades de GEI/GEET+GEST de 1r o 2n conservades al dia i hora "
                "de la partida (la regla 1 diu que no es toquen); només s'hi assigna aula "
                "per complir R5-SENSE-AULA. Es demana excepció explícita a R1-TORN."
            ),
        })
    if pendents_r1:
        files.append({
            "restriccio": "R1-TORN",
            "sessions": "|".join(pendents_r1),
            "justificacio": (
                "L'heurística (totes les franges i aules del torn dins la setmana, més reparació "
                "desplaçant fins a 6 sessions flexibles bloquejadores) no ha trobat cap franja de "
                "tarda lectiva sense conflicte. Es conserva el dia i hora d'origen. Detall: "
                + " | ".join(detall)
            ),
        })
    pd.DataFrame(files, columns=["restriccio", "sessions", "justificacio"]).to_csv(
        EXCEPCIONS, index=False, encoding="utf-8")


def escriure_graella(p: Planificador) -> None:
    comptes: dict[tuple, int] = defaultdict(int)
    for e in p.colocades:
        if e.aula:
            comptes[(e.aula, e.dia, hhmm(e.ini), hhmm(e.fi), e.codi, e.tipus,
                     f"{e.tipus}/{e.num_grup}")] += 1
    ordre = {d: i for i, d in enumerate(DIES)}
    files = [dict(aula=k[0], dia=k[1], h_ini=k[2], h_fi=k[3], codi=k[4], tipus=k[5],
                  grup=k[6], setmanes=v) for k, v in comptes.items()]
    files.sort(key=lambda r: (r["aula"], ordre[r["dia"]], r["h_ini"]))
    pd.DataFrame(files, columns=["aula", "dia", "h_ini", "h_fi", "codi", "tipus", "grup",
                                 "setmanes"]).to_csv(ARREL / "graella-setmanal-aules.csv", index=False)


# ---------------------------------------------------------------------------
# Guarda amb el verificador oficial
# ---------------------------------------------------------------------------
CLAUS_OBJECTIU = ("hores_mortes", "mortes", "desplacament", "canvis_franja",
                  "canvis_aula", "passadis", "te_extra")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _planar(obj, prefix: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _planar(v, f"{prefix}.{k}" if prefix else str(k))
    elif not isinstance(obj, list):
        yield prefix, obj


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def llegir_informe(cami: Path) -> dict | None:
    if not cami.exists():
        return None
    dades = json.loads(cami.read_text(encoding="utf-8"))
    plana = list(_planar(dades))
    veredicte = next((_norm(str(v)).upper() for _, v in plana
                      if isinstance(v, str) and _norm(v).upper().startswith(("VALIDA", "NO VALIDA"))), None)
    if veredicte is None:
        return None
    rang = 0 if veredicte.startswith("NO") else 1 if "RELAX" in veredicte else 2
    declarats = sum(v for k, v in plana if "incompliments_declarats" in _norm(k) and _num(v))
    compten = sum(v for k, v in plana if _norm(k).split(".")[-1] == "compten" and _num(v))
    objectius = {k: v for k, v in plana
                 if _num(v) and any(c in _norm(k) for c in CLAUS_OBJECTIU) and "context" not in _norm(k)}
    return {"rang": rang, "declarats": declarats, "compten": compten, "objectius": objectius}


def verificar(csv: Path) -> dict | None:
    sortida = CANDIDATES / f"informe-{csv.stem}.json"
    viol = CANDIDATES / f"violacions-{csv.stem}.csv"
    cmd = [sys.executable, "-m", "horaris", "check", str(csv.relative_to(ARREL)), "--semestre", "2",
           "--relaxacions", EXCEPCIONS.name, "--json", str(sortida.relative_to(ARREL)),
           "--violacions", str(viol.relative_to(ARREL))]
    try:
        subprocess.run(cmd, cwd=ARREL, capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "PYTHONUTF8": "1"})
        return llegir_informe(sortida)
    except Exception as exc:  # noqa: BLE001 - la guarda mai ha de trencar el lliurament
        print(f"  (no s'ha pogut verificar {csv.name}: {exc})")
        return None


def clau_validesa(inf: dict) -> tuple:
    return (-inf["rang"], inf["compten"], inf["declarats"])


def no_pitjor(base: dict, nou: dict) -> bool:
    if clau_validesa(nou) > clau_validesa(base):
        return False
    if not base["objectius"] or not nou["objectius"]:
        return False  # no es poden comparar els objectius: no es canvia res
    return all(nou["objectius"].get(k, v) <= v for k, v in base["objectius"].items())


def main() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")
    aules["capacitat"] = aules.capacitat.astype(int)
    # Sempre partim de la partida: així cada execució dona el mateix resultat.
    proposta = pd.read_csv(PAQUET / "proposta_partida.csv", dtype=str).fillna("")
    proposta_origen = proposta.set_index("id_sessio")
    calendari = pd.read_csv(PAQUET / "calendari.csv", dtype=str).fillna("")
    # Replica R2-CALENDARI: festius/no lectius tanquen tot el dia; les dates
    # d'avaluació només conserven docència que ja hi era, i les aturades poden
    # ser parcials. Això evita descartar franges legals.
    dies_tancats = set(calendari.loc[calendari.tipus.isin(["festiu", "no_lectiu"]), "data"])
    # El verificador també prohibeix traslladar una sessió a un dia laborable
    # sense cap classe a la proposta base, encara que no consti al calendari.
    dates_amb_classe = set(sessions["data"])
    dates = pd.to_datetime(sessions["data"], errors="coerce").dropna()
    if not dates.empty:
        for dia in pd.date_range(dates.min(), dates.max(), freq="D"):
            data = dia.strftime("%Y-%m-%d")
            if dia.weekday() < 5 and data not in dates_amb_classe:
                dies_tancats.add(data)
    dies_avaluacio = set(calendari.loc[calendari.tipus == "avaluacio", "data"])
    aturades: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for _, fila in calendari[calendari.tipus == "aturada"].iterrows():
        if fila.h_ini and fila.h_fi:
            aturades[fila.data].append((hm(fila.h_ini), hm(fila.h_fi)))
        else:
            dies_tancats.add(fila.data)
    movibles, fixats = construir_events(sessions, aules)
    ctx = (aules, dies_tancats, dies_avaluacio, aturades, fixats, movibles)

    # --- 1. Planificació voraç amb reintents adaptatius -------------------
    prioritaris: set[str] = set()
    millor: tuple[dict, list[str]] | None = None
    for attempt in range(INTENTS):
        current = Planificador(aules, dies_tancats, dies_avaluacio, aturades)
        for e in fixats:
            current.registrar(e)
        ordered = list(movibles)
        variant = attempt % 4
        if variant == 0:
            ordered.sort(key=lambda e: (e.ids[0] not in prioritaris, e.movible, len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.key))
        elif variant == 1:
            ordered.sort(key=lambda e: (e.ids[0] not in prioritaris, e.movible, len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.dia_origen, e.ini_origen))
        elif variant == 2:
            ordered.sort(key=lambda e: (e.ids[0] not in prioritaris, e.movible, len(e.aules),
                                        -(e.fi_origen - e.ini_origen), -e.alumnes, e.dia_origen,
                                        e.ini_origen, e.key))
        else:
            ordered.sort(key=lambda e: (e.ids[0] not in prioritaris, e.movible, len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.key[::-1]))
        sense_lloc: list[str] = []
        for e in ordered:
            opcio = next(current.candidats(e), None)
            if opcio is None:
                sense_lloc.append(e.ids[0])
                # Reserva l'horari original amb una aula LLIURE a aquella franja (evita R4-AULA).
                aula_actual = str(proposta_origen.loc[e.ids[0], "aula"]) if e.ids[0] in proposta_origen.index else ""
                ordre_aules = ([aula_actual] if aula_actual in e.aules else []) + sorted(
                    e.aules, key=lambda a: (a != e.aula_origen, current.cap.get(a, 0)))
                aula_reserva = next((a for a in ordre_aules
                                     if aula_lliure(current, e, e.data_origen, e.ini_origen, a)), None)
                if aula_reserva is None:
                    aula_reserva = aula_actual if aula_actual in e.aules else e.aula_origen
                current.posar(e, e.data_origen, e.dia_origen, e.ini_origen, aula_reserva)
            else:
                current.posar(e, *opcio)
        print(f"Intent {attempt + 1}/{INTENTS}: {len(sense_lloc)} sessions sense lloc")
        if millor is None or len(sense_lloc) < len(millor[1]):
            millor = (instantania(movibles), list(sense_lloc))
        prioritaris.update(sense_lloc)
        if not sense_lloc:
            break
    assert millor is not None
    estat_millor, sense_lloc = millor
    p = reconstruir(*ctx, estat_millor)

    # --- 2. Reparació de les pendents -------------------------------------
    if sense_lloc:
        per_id = {sid: e for e in movibles for sid in e.ids}
        for sid in list(sense_lloc):
            if reparar_una_sessio(p, per_id[sid]):
                sense_lloc.remove(sid)
    diagnosi: list[str] = []
    if sense_lloc:
        per_id = {sid: e for e in movibles for sid in e.ids}
        for sid in sense_lloc[:20]:
            e = per_id[sid]
            options = [
                (p.bloquejadors(e, data, ini, aula), (data, dia, ini, aula))
                for data, dia, ini, aula in p.candidats(e, ignorar_conflictes=True)
            ]
            if options:
                blockers, slot = min(options, key=lambda pair: len(pair[0]))
                names = ", ".join(
                    f"{x.ids[0]}{' [fixada]' if not x.movible else ''}" for x in blockers
                ) or "cap"
                blockage = f"; millor alternativa={slot[1]} {hhmm(slot[2])} {slot[3]}, bloquejada per {names}"
            else:
                blockage = "; no té franges legals segons torn/calendari"
            diagnosi.append(
                f"{sid} ({e.codi} {e.tipus}/{e.num_grup}, torn={e.torn}, alumnes={e.alumnes}, "
                f"aules compatibles={len(e.aules)}{blockage})"
            )
        print("La heurística no ha trobat lloc per a aquestes sessions:\n  " + "\n  ".join(diagnosi))
    arreglats = netejar_conflictes_aula(p, movibles)
    print(f"Conflictes d'aula arreglats: {arreglats}; pendents: {len(conflictes_aula(p))} (parelles)")

    # --- 3. Base ----------------------------------------------------------
    CANDIDATES.mkdir(exist_ok=True)
    estat_base = instantania(movibles)
    escriure_proposta(p, movibles, proposta, BASE_CSV)
    fixades_r1, pendents_r1 = calcular_excepcions(movibles)
    escriure_excepcions(fixades_r1, pendents_r1, diagnosi)
    ids_excepcionats = set(fixades_r1) | set(pendents_r1)
    pendents_sense_excepcio = set(sense_lloc) - ids_excepcionats
    print("Indicadors de la base:", indicadors(p, movibles))

    # --- 4. Candidates, validades pel verificador -------------------------
    print("Verificant la base...")
    inf_base = verificar(BASE_CSV)
    candidates_ok = []
    for nom, optimitzar in (("aules", False), ("optim", True)):
        try:
            p = reconstruir(*ctx, estat_base)
            n_o = optimitzar_slots(p, movibles, OPT_SEGONS) if optimitzar else 0
            n_b = assignar_aules_base(p, movibles)
            n_c = netejar_conflictes_aula(p, movibles)
            if calcular_excepcions(movibles) != (fixades_r1, pendents_r1):
                print(f"Candidata {nom}: canvien les excepcions R1, es descarta.")
                continue
            ruta = CANDIDATES / f"{nom}.csv"
            escriure_proposta(p, movibles, proposta, ruta)
            print(f"Candidata {nom}: {n_o} franges mogudes, {n_b} aules canviades, "
                  f"{n_c} conflictes arreglats -> {indicadors(p, movibles)}")
            inf = verificar(ruta)
            if inf:
                print(f"  verificador: rang={inf['rang']} compten={inf['compten']} "
                      f"declarats={inf['declarats']} suma_objectius={sum(inf['objectius'].values())}")
                candidates_ok.append((nom, ruta, inf, instantania(movibles)))
        except Exception as exc:  # noqa: BLE001
            print(f"Candidata {nom} descartada per error: {type(exc).__name__}: {exc}")

    triat = ("base", BASE_CSV, estat_base)
    if inf_base:
        print(f"  base: rang={inf_base['rang']} compten={inf_base['compten']} "
              f"declarats={inf_base['declarats']} suma_objectius={sum(inf_base['objectius'].values())}")
        bons = [c for c in candidates_ok
                if clau_validesa(c[2]) < clau_validesa(inf_base) or no_pitjor(inf_base, c[2])]
        if bons:
            nom, ruta, inf, estat = min(bons, key=lambda c: (clau_validesa(c[2]), sum(c[2]["objectius"].values())))
            if clau_validesa(inf) < clau_validesa(inf_base) or \
                    sum(inf["objectius"].values()) < sum(inf_base["objectius"].values()):
                triat = (nom, ruta, estat)
    p = reconstruir(*ctx, triat[2])
    shutil.copyfile(triat[1], SORTIDA)
    print(f"Proposta final: {triat[0]} -> {SORTIDA.name}")

    # --- 5. Lliuraments complementaris ------------------------------------
    text = resum(p.colocades, movibles, p, sense_lloc=sorted(pendents_sense_excepcio),
                 relaxacions_r1=fixades_r1 + pendents_r1)
    (ARREL / "resum-5_2.md").write_text(text, encoding="utf-8")
    escriure_graella(p)

    estat = "INCOMPLETA" if pendents_sense_excepcio else (
        "COMPLETA AMB EXCEPCIONS R1" if ids_excepcionats else "COMPLETA"
    )
    print(f"Actualitzat {SORTIDA.name} ({estat})")
    print(f"Excepcions R1 documentades: {len(ids_excepcionats)}")
    print("Valida-ho amb: python -m horaris check proposta-torns.csv --semestre 2 "
          "--relaxacions relaxacions-5_2.csv --json informe.json --violacions violacions.csv")


if __name__ == "__main__":
    main()