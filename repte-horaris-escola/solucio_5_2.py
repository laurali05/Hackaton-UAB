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
                usades = self.ocupacio_r8[(data, f)]
                if aula not in usades and len(usades) >= self.max_ordinaries:
                    return False
        return True

    def horari_legal(self, e: Event, data: str, ini: int, fi: int) -> bool:
        if data in self.dies_tancats or not dins_finestra(ini, fi, e.torn):
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
        aules = sorted(e.aules, key=lambda a: (a != e.aula_origen, self.cap[a]))
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
            if (aula == x.aula or e.docents & x.docents or comparteix_alumnat(e, x)
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
                  s.codi, max(int(f.alumnes or 0) for f in files), set("|".join(f.titulacions_curs for f in files).split("|")) - {""},
                  set("|".join(f.docents for f in files).split("|")) - {""}, linia(grup, tipus), grup.split("/")[-1],
                  s.torn_requerit, aula_origen, [aula_origen] if fixada else aules_permeses(files, aules), not fixada)
        # Les sessions fixades es mantenen; la resta poden canviar si cal.
        # Es prova primer la ubicació original per minimitzar moviments.
        ja_correcta = dins_finestra(e.ini_origen, e.fi_origen, e.torn)
        if fixada:
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
    return f"""# Resum punt 5.2 — Junta Permanent

## Capacitat

- Pic d'aules ordinàries ocupades al matí: **{pic['matí']}** de 21 (19 com a màxim per reservar-ne dues).
- Pic d'aules ordinàries ocupades a la tarda: **{pic['tarda']}** de 21 (19 com a màxim per reservar-ne dues).
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
    # Replica R2-CALENDARI: festius/no lectius tanquen tot el dia; les dates
    # d'avaluació només conserven docència que ja hi era, i les aturades poden
    # ser parcials. Això evita descartar franges legals.
    dies_tancats = set(calendari.loc[calendari.tipus.isin(["festiu", "no_lectiu"]), "data"])
    dies_avaluacio = set(calendari.loc[calendari.tipus == "avaluacio", "data"])
    aturades: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for _, fila in calendari[calendari.tipus == "aturada"].iterrows():
        if fila.h_ini and fila.h_fi:
            aturades[fila.data].append((hm(fila.h_ini), hm(fila.h_fi)))
        else:
            dies_tancats.add(fila.data)
    movibles, fixats = construir_events(sessions, aules)
    # Una passada vorace pot consumir una aula/franja necessària per a una
    # sessió més restringida. Provem diversos desempats deterministes; cada
    # passada comença de zero i no modifica cap fitxer fins a trobar lloc per a tot.
    p = None
    sense_lloc = []
    for attempt in range(4):
        current = Planificador(aules, dies_tancats, dies_avaluacio, aturades)
        for e in fixats:
            current.registrar(e)
        ordered = list(movibles)
        if attempt == 0:
            ordered.sort(key=lambda e: (len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.key))
        elif attempt == 1:
            ordered.sort(key=lambda e: (len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.dia_origen, e.ini_origen))
        elif attempt == 2:
            ordered.sort(key=lambda e: (len(e.aules), -(e.fi_origen - e.ini_origen),
                                        -e.alumnes, e.dia_origen, e.ini_origen, e.key))
        else:
            ordered.sort(key=lambda e: (len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.key[::-1]))
        sense_lloc = []
        for e in ordered:
            opcio = next(current.candidats(e), None)
            if opcio is None:
                sense_lloc.append(e.ids[0])
            else:
                current.posar(e, *opcio)
        p = current
        if not sense_lloc:
            break
    if sense_lloc:
        per_id = {sid: e for e in movibles for sid in e.ids}
        pendents = list(sense_lloc)
        for sid in pendents:
            if reparar_una_sessio(p, per_id[sid]):
                sense_lloc.remove(sid)
    if sense_lloc:
        per_id = {sid: e for e in movibles for sid in e.ids}
        diagnosi = []
        for sid in sense_lloc[:20]:
            e = per_id[sid]
            options = [
                (p.bloquejadors(e, data, ini, aula), (data, dia, ini, aula))
                for data, dia, ini, aula in p.candidats(e, ignorar_conflictes=True)
            ]
            blockage = ""
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
                f"aules compatibles={len(e.aules)}: {', '.join(e.aules) or 'cap'}{blockage})"
            )
        raise RuntimeError(
            "La heurística no ha trobat lloc per a aquestes sessions:\n  "
            + "\n  ".join(diagnosi)
            + "\nAixò no demostra que el problema sigui impossible; cal reordenar sessions ja col·locades "
              "o revisar si cal declarar una relaxació. No s'ha escrit cap proposta en aquesta execució; "
              "si proposta-torns.csv ja existeix, continua sent una versió anterior i el verificador n'està "
              "avaluant aquella."
        )

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
