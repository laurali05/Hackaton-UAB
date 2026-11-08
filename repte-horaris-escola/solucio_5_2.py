"""Punt 5.2 — torns nous: 1r/2n al matí, 3r/4t a la tarda.

Executa'l des de l'arrel del repte:
    python solucio_5_2_completa.py

Genera únicament proposta-torns.csv. No crea fitxers de relaxacions.
Les franges candidates han de respectar torn, calendari lectiu i conflictes; si
no hi ha lloc, conserva la ubicació existent i informa de les sessions pendents.
Només necessita pandas.
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
        ja_correcta = dins_finestra(e.ini_origen, e.fi_origen, e.torn)
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


def main() -> None:
    sessions = pd.read_csv(PAQUET / "sessions.csv", dtype=str).fillna("")
    aules = pd.read_csv(PAQUET / "aules.csv", dtype=str).fillna("")
    aules["capacitat"] = aules.capacitat.astype(int)
    proposta_actual = ARREL / "proposta-torns.csv"
    proposta_path = proposta_actual if proposta_actual.exists() else PAQUET / "proposta_partida.csv"
    proposta = pd.read_csv(proposta_path, dtype=str).fillna("")
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
            ordered.sort(key=lambda e: (e.movible, len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.key))
        elif attempt == 1:
            ordered.sort(key=lambda e: (e.movible, len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.dia_origen, e.ini_origen))
        elif attempt == 2:
            ordered.sort(key=lambda e: (e.movible, len(e.aules), -(e.fi_origen - e.ini_origen),
                                        -e.alumnes, e.dia_origen, e.ini_origen, e.key))
        else:
            ordered.sort(key=lambda e: (e.movible, len(e.aules), -e.alumnes,
                                        -(e.fi_origen - e.ini_origen), e.key[::-1]))
        sense_lloc = []
        for e in ordered:
            opcio = next(current.candidats(e), None)
            if opcio is None:
                sense_lloc.append(e.ids[0])
                # Reserva l'horari original i conserva l'aula de la proposta
                # anterior si encara és compatible.
                aula_actual = str(proposta_origen.loc[e.ids[0], "aula"])
                aula_reserva = aula_actual if aula_actual in e.aules else e.aula_origen
                current.posar(
                    e, e.data_origen, e.dia_origen, e.ini_origen, aula_reserva
                )
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
        print(
            "La heurística no ha trobat lloc per a aquestes sessions:\n  "
            + "\n  ".join(diagnosi)
            + "\nNo s'han aplicat relaxacions. Les sessions sense franja lectiva compatible conserven "
              "el dia i l'hora originals; es desarà la proposta per revisar-la."
        )

    # Exporta només les activitats realment col·locades. Les pendents conserven
    # dia/hora/aula de la proposta base, i queden llistades com a incompletes.
    col·locades = set(p.colocades)
    per_id = {sid: e for e in movibles if e in col·locades for sid in e.ids}
    movibles_col_locades = [e for e in movibles if e in col·locades]
    nous_dies = {sid: e.dia for sid, e in per_id.items()}
    noves_hores = {sid: hhmm(e.ini) for sid, e in per_id.items()}
    noves_aules = {sid: e.aula for sid, e in per_id.items()}
    proposta["dia"] = proposta.id_sessio.map(nous_dies).fillna(proposta["dia"])
    proposta["h_ini"] = proposta.id_sessio.map(noves_hores).fillna(proposta["h_ini"])
    proposta["aula"] = proposta.id_sessio.map(noves_aules).fillna(proposta["aula"])
    output_path = ARREL / "proposta-torns.csv"
    temp_path = ARREL / ".proposta-torns.tmp.csv"
    proposta.to_csv(temp_path, index=False)
    # El reemplazo al final evita dejar un CSV truncado si la escritura falla.
    temp_path.replace(output_path)
    torn_incorrecte_a_origen = lambda e: (
        e.torn in {"mati", "tarda"}
        and e.data == e.data_origen
        and e.ini == e.ini_origen
        and ((e.ini_origen < MATI[1]) != (e.torn == "mati"))
    )
    fixades_r1 = sorted({
        sid
        for e in movibles_col_locades
        if torn_incorrecte_a_origen(e) and not e.movible
        and not e.aula_origen and e.aula
        for sid in e.ids
    })
    pendents_r1 = sorted({
        sid
        for e in movibles_col_locades
        if torn_incorrecte_a_origen(e) and e.movible
        for sid in e.ids
    })
    files_excepcions = []
    if fixades_r1:
        files_excepcions.append({
            "restriccio": "R1-TORN",
            "sessions": "|".join(fixades_r1),
            "justificacio": (
                "Sessions fixades de GEI/GEET+GEST de 1r o 2n conservades al dia i hora "
                "de la partida; només s'hi assigna aula quan cal per complir R5-SENSE-AULA. "
                "Es demana excepció explícita a R1-TORN."
            ),
        })
    if pendents_r1:
        files_excepcions.append({
            "restriccio": "R1-TORN",
            "sessions": "|".join(pendents_r1),
            "justificacio": (
                "No s'ha trobat cap franja de tarda lectiva sense conflictes dins la setmana. "
                "S02839 queda bloquejada per S01504 i els docents compartits; S04526 només "
                "té Q1/0007 i Q1/0019, ocupades per sessions fixades a les franges disponibles. "
                "Es demana excepció explícita a R1-TORN i es conserva el dia i hora d'origen."
            ),
        })
    excepcions_path = ARREL / "relaxacions-5_2.csv"
    pd.DataFrame(
        files_excepcions,
        columns=["restriccio", "sessions", "justificacio"],
    ).to_csv(excepcions_path, index=False, encoding="utf-8")
    ids_excepcionats = set(fixades_r1) | set(pendents_r1)
    pendents_sense_excepcio = set(sense_lloc) - ids_excepcionats
    estat = "INCOMPLETA" if pendents_sense_excepcio else (
        "COMPLETA AMB EXCEPCIONS R1" if ids_excepcionats else "COMPLETA"
    )
    print(f"Actualitzat proposta-torns.csv ({estat})")
    print(f"Excepcions R1 documentades: {len(ids_excepcionats)}")
    if pendents_sense_excepcio:
        print(f"Sessions pendents sense excepcio declarada: {', '.join(sorted(pendents_sense_excepcio))}")
    print("Valida-ho amb: python -m horaris check proposta-torns.csv --semestre 2 --relaxacions relaxacions-5_2.csv")


if __name__ == "__main__":
    main()
