#!/usr/bin/env python3
"""Repte 5.3 (imprevist). Parteix de proposta-torns.csv (la del 5.2).

Ús:
    python solucio_5_3.py --base proposta-torns.csv --check

Fa NOMÉS aquests canvis sobre la base:
  1. TE/21 de Transmissió de Calor (GEQ 2n): 130 alumnes -> una sola aula >=130.
  2. Q3/0013 reservada del 15 al 19/3/2027 -> mou les classes d'aquells dies.
  3. Q1/1003 avariada el 10/3/2027 -> mou les classes d'aquell dia.
  4. S11527 (8/3) cancel·lada -> recuperada fins al 19/3, amb la columna `data`.
Tot es fa amb solapament per INTERVAL, data real (si el 5.2 ha canviat el dia),
aforament, reserva R8 (2 aules ordinàries lliures) i conflictes de docent/alumnat.
Si no troba solució, s'atura amb error: mai deixa una sessió malament en silenci.
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path
import pandas as pd
from horaris.model import carrega_base
from horaris.check import _alumnat_comparteix, _espai_ok

PAQUET = "paquet"

# ---- NOMS DE COLUMNA de paquet/sessions.csv: COMPROVEU-LOS amb DICCIONARI.md ----
SC = dict(data="data", dia="dia", ini="h_ini", fi="h_fi", tipus="tipus", grup="grup",
          assig="assignatura", codi="codi", alum="alumnes", fix="fixada", doc=["docents", "docent", "professorat"],
          coh=["cohort", "titulacions_curs", "titulacio_curs"], torn="torn_requerit", esp="sense_espai")
# ---- paquet/aules.csv ----
AC = dict(aula="aula", cap="capacitat", tipus="tipus")   # ordinària = tipus que conté "docent"

SLOTS = list(range(510, 1260, 60))  # franges d'una hora, 8.30 .. 20.30 (l'última acaba a les 21.00)


def tmin(x):
    a = re.split(r"[:.hH]", str(x).strip())
    return int(a[0]) * 60 + int(a[1])


def rd(p):
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def passadis(r):
    m = re.match(r"(Q\d)/(\d)", r)
    return m.groups() if m else r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="proposta-torns.csv")
    ap.add_argument("--out", default="proposta-imprevist.csv")
    ap.add_argument("--escenari", default=f"{PAQUET}/escenaris/contingencies")
    ap.add_argument("--check", action="store_true", help="executa el verificador oficial")
    a = ap.parse_args()

    if not os.path.exists(a.base):
        sys.exit(f"ERROR: no trobo {a.base}. Ha de ser la proposta del 5.2 (no s'usa cap alternativa en silenci).")
    prop, ses, aul = rd(a.base), rd(f"{PAQUET}/sessions.csv"), rd(f"{PAQUET}/aules.csv")
    if os.path.isdir(a.escenari):
        print("[i] Fitxers de l'escenari:", sorted(os.listdir(a.escenari)))
    else:
        print(f"[!] No existeix {a.escenari}")
        sys.exit(2)
    config = json.loads((Path(a.escenari) / "escenari.json").read_text(encoding="utf-8"))
    problemes = []
    closed_dates = {}
    base_regles = carrega_base(Path(PAQUET), semestre=2, escenari=Path(a.escenari))
    for item in config.get("aules_tancades", []):
        dates = set(pd.date_range(item["data_ini"], item["data_fi"]).strftime("%Y-%m-%d"))
        closed_dates.setdefault(item["aula"], set()).update(dates)
    cancel_cfg = config.get("cancellades", [])
    if len(cancel_cfg) != 1:
        sys.exit(f"ERROR: s'esperava una sessió cancel·lada a l'escenari; trobades {len(cancel_cfg)}")
    SID_CANCEL = cancel_cfg[0]["id_sessio"]
    DATA_RECUP_MAX = cancel_cfg[0]["recuperar_fins"]
    updates = config.get("alumnes", [])
    if len(updates) != 1:
        sys.exit(f"ERROR: s'esperava un canvi d'aforament; trobats {len(updates)}")
    GRUP_AFORAMENT_NOU = int(updates[0]["alumnes"])

    for c in ["id_sessio", "dia", "h_ini", "aula"]:
        assert c in prop.columns, f"{a.base} no té la columna {c}"
    for k, v in list(SC.items()):  # acceptem diversos noms possibles per columna
        trobat = next((c for c in (v if isinstance(v, list) else [v]) if c in ses.columns), None)
        if trobat is None:
            sys.exit(f"ERROR: a sessions.csv no hi ha cap columna per a '{k}' (provat: {v}).\n"
                     f"Columnes disponibles: {list(ses.columns)}\nAjusteu SC a dalt de l'script.")
        SC[k] = trobat
    assert "id_sessio" in ses.columns
    assert ses["id_sessio"].is_unique

    inv = {v: k for k, v in SC.items()}
    s = ses[["id_sessio"] + list(SC.values())].rename(columns=inv).rename(
        columns={"data": "data0", "dia": "dia0", "ini": "ini0", "fi": "fi0"})
    df = prop[["id_sessio", "dia", "h_ini", "aula"]].merge(s, on="id_sessio", how="left", validate="one_to_one")
    assert df["data0"].ne("").all() and df["data0"].notna().all(), "Hi ha id_sessio de la proposta que no són a sessions.csv"
    assert df["data0"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all(), "Format de data inesperat a sessions.csv"
    base_aula, base_dia, base_ini = df["aula"].copy(), df["dia"].copy(), df["h_ini"].copy()

    # dia (dl/dm/..) <-> dia de la setmana, deduït de les dades (no suposem els codis)
    wd_ses = pd.to_datetime(ses[SC["data"]]).dt.day_of_week
    dia2wd = {d: int(g.mode()[0]) for d, g in wd_ses.groupby(ses[SC["dia"]])}
    wd2dia = {v: k for k, v in dia2wd.items()}
    print("[i] codis de dia:", dia2wd)
    assert df["dia"].isin(dia2wd).all(), "La proposta té codis de dia desconeguts"

    # DATA REAL: si el 5.2 ha mogut la sessió de dia, la data canvia dins de la setmana
    d0 = pd.to_datetime(df["data0"])
    df["date"] = (d0 + pd.to_timedelta(df["dia"].map(dia2wd) - d0.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")
    df["s"] = df["h_ini"].map(tmin)
    df["dur"] = df["fi0"].map(tmin) - df["ini0"].map(tmin)
    df["e"] = df["s"] + df["dur"]
    df["ncap"] = pd.to_numeric(df["alum"], errors="coerce").fillna(0)
    for canvi in updates:
        mask = (df["codi"] == str(canvi["codi"])) & (df["grup"] == str(canvi["grup"]))
        if not mask.any():
            sys.exit(f"ERROR: l'escenari demana canviar {canvi['codi']} {canvi['grup']}, però no surt a la proposta.")
        df.loc[mask, "ncap"] = int(canvi["alumnes"])
    # Qualsevol motiu no buit (p. ex. "R1: GEI 2n" o "R7: PLAB") vol dir
    # que la sessió és fixada. PLAB tampoc no es mou mai en aquest repte.
    fix = df["fix"].str.strip().ne("")
    df["lock_time"] = fix | df["tipus"].str.upper().eq("PLAB")
    # R1 fixa dia/hora, però permet reassignar aula; R7 fixa l'aula PLAB.
    source_rooms = ses.set_index("id_sessio")["aula_partida"].to_dict()
    df["lock_room"] = df["tipus"].str.upper().eq("PLAB") | (fix & df["id_sessio"].map(source_rooms).fillna("").ne(""))
    df["sinesp"] = df["esp"].str.strip().isin(["1", "1.0", "True", "true"])

    for c in (AC["aula"], AC["cap"]):
        if c not in aul.columns:
            sys.exit(f"ERROR: aules.csv no té la columna '{c}'. Columnes: {list(aul.columns)}. Ajusteu AC.")
    cap = dict(zip(aul[AC["aula"]].str.strip(), pd.to_numeric(aul[AC["cap"]], errors="coerce")))
    # Les 21 aules ordinàries («Aules docents») segons la taula de l'enunciat (apartat 2)
    ORDI_ENUNCIAT = {"Q1/1003": 90, "Q1/1007": 90, "Q1/1011": 160,
                     "Q2/1003": 63, "Q2/1005": 63, "Q2/1009": 90, "Q2/1013": 90,
                     "Q3/0003": 100, "Q3/0009": 48, "Q3/0011": 24, "Q3/0013": 48,
                     "Q3/1003": 100, "Q3/1007": 130, "Q3/1011": 130,
                     "Q4/0003": 90, "Q4/0007": 117, "Q4/0011": 117,
                     "Q4/1003": 48, "Q4/1005": 50, "Q4/1009": 88, "Q4/1013": 88}
    ordi = set(ORDI_ENUNCIAT)
    absents = sorted(ordi - set(cap))
    assert not absents, f"Aules de l'enunciat que no són a aules.csv: {absents}"
    for r, c in ORDI_ENUNCIAT.items():
        if cap[r] != c:
            print(f"[!] Capacitat de {r}: aules.csv={cap[r]} enunciat={c} (s'usa aules.csv)")

    # ---------- ocupació per (data, aula) -> {idx: (ini, fi)} ----------
    occ = {}
    for i, (dt, r, st, en, sp) in enumerate(zip(df["date"], df["aula"], df["s"], df["e"], df["sinesp"])):
        if r and not sp:
            occ.setdefault((dt, r), {})[i] = (st, en)

    def closed(r, dt):
        return dt in closed_dates.get(r, ())

    def busy(dt, r, st, en, ig):
        return any(j not in ig and not (en <= s2 or e2 <= st) for j, (s2, e2) in occ.get((dt, r), {}).items())

    def free_count(dt, t0, t1, ig, extra):
        return sum(1 for r in ordi if r != extra and not closed(r, dt) and not busy(dt, r, t0, t1, ig))

    def reserve_ok(dt, st, en, room, ig):
        for t in SLOTS:
            if t < en and t + 60 > st and free_count(dt, t, min(t + 60, 1260), ig, room) < 2:
                return False
        return True

    def move(ig, new_room):
        for i in ig:
            occ.get((df.at[i, "date"], df.at[i, "aula"]), {}).pop(i, None)
            df.at[i, "aula"] = new_room
            occ.setdefault((df.at[i, "date"], new_room), {})[i] = (df.at[i, "s"], df.at[i, "e"])

    def move_schedule(i, new_date, new_start, new_room):
        old_date, old_room = df.at[i, "date"], df.at[i, "aula"]
        occ.get((old_date, old_room), {}).pop(i, None)
        if i in by_date.get(old_date, []):
            by_date[old_date].remove(i)
        new_end = new_start + int(df.at[i, "dur"])
        df.at[i, "date"] = new_date
        df.at[i, "dia"] = wd2dia[pd.Timestamp(new_date).day_of_week]
        df.at[i, "s"], df.at[i, "e"] = new_start, new_end
        df.at[i, "h_ini"] = f"{new_start // 60:02d}:{new_start % 60:02d}"
        df.at[i, "aula"] = new_room
        if new_room and not df.at[i, "sinesp"]:
            occ.setdefault((new_date, new_room), {})[i] = (new_start, new_end)

    def find_room(ig, dt, st, en, need, old, pref=None, allow_old=False):
        c = [r for r in ordi if cap[r] >= need and (allow_old or r != old) and not closed(r, dt)
             and not busy(dt, r, st, en, ig)
             and all((sid := base_regles.sessions.get(df.at[i, "id_sessio"])) is None
                     or _espai_ok(base_regles, sid, r) for i in ig)]
        c.sort(key=lambda r: (r != pref, passadis(r) != passadis(old or ""), cap[r], r))
        for r in c:
            if reserve_ok(dt, st, en, r, ig):
                return r, True
        # No es deixa una proposta invàlida per R8 només perquè sigui l'única aula.
        return None, False

    def agrupa(idxs):
        g = {}
        for i in idxs:
            g.setdefault((df.at[i, "date"], df.at[i, "s"], df.at[i, "e"], df.at[i, "aula"], df.at[i, "doc"]), []).append(i)
        return g

    # ---------- 1. Grup que ja no hi cap (dades de l'escenari) ----------
    canvi = updates[0]
    ka, kg = str(canvi["codi"]), str(canvi["grup"])
    gm = (df["codi"] == ka) & (df["grup"] == kg) & (df["tipus"].str.upper() == "TE")
    if not gm.any():
        sys.exit(f"ERROR: no identifico el grup TE {ka} {kg} de l'escenari.")
    print(f"[i] Grup identificat: codi={ka} grup={kg}, alumnat={GRUP_AFORAMENT_NOU}")
    gi = [i for i in df.index[gm] if cap.get(df.at[i, "aula"], 0) < GRUP_AFORAMENT_NOU]
    gi = [i for i in gi if not df.at[i, "lock_room"]]
    if gi:
        ig = set(gi)
        triat = None
        for r in sorted((r for r in ordi if cap[r] >= GRUP_AFORAMENT_NOU), key=lambda r: (cap[r], r)):
            simultanies = any(
                df.at[i, "date"] == df.at[j, "date"]
                and not (df.at[i, "e"] <= df.at[j, "s"] or df.at[j, "e"] <= df.at[i, "s"])
                for pos, i in enumerate(gi) for j in gi[pos + 1:]
            )
            if simultanies:
                continue
            if all(not closed(r, df.at[i, "date"])
                   and not busy(df.at[i, "date"], r, df.at[i, "s"], df.at[i, "e"], ig)
                   and reserve_ok(df.at[i, "date"], df.at[i, "s"], df.at[i, "e"], r, ig)
                   for i in gi):
                triat = r
                break
        if triat:
            move(ig, triat)
            print(f"[✔] TE/21 ({len(gi)} sessions) -> {triat}")
        else:
            print("[!] Cap aula >=130 lliure per a TOTES les sessions; provo sessió a sessió")
            pref = None
            for i in gi:
                r, ok = find_room({i}, df.at[i, "date"], df.at[i, "s"], df.at[i, "e"], GRUP_AFORAMENT_NOU,
                                  df.at[i, "aula"], pref)
                if r is None:
                    problemes.append(f"TE/21 sense aula >=130: {df.at[i, 'id_sessio']}")
                else:
                    move({i}, r)
                    pref = r

    # Els moviments que l'enunciat excepcionalment demana es documenten en un CSV de relaxacions.
    relaxacions_noves = {"R1-FIXADA": set(), "R7-PLAB": set()}

    # ---------- 2 i 3. Aula reservada / avariada ----------
    def desallotja(room, etiqueta):
        idx = [i for i in df.index[(df["aula"] == room) & df["date"].isin(closed_dates.get(room, set()))
                                   & ~df["sinesp"]]]
        n = 0
        # Seguim la recomanació del verificador: desallotjar també sessions fixades i PLAB,
        # mantenint dia/hora i cercant una aula compatible, lliure i amb reserva R8.
        for (dt, st, en, old, _), ig in agrupa(idx).items():
            need = df.loc[ig, "ncap"].max()
            r, ok = find_room(set(ig), dt, st, en, need, old)
            if r is None:
                problemes.append(f"{etiqueta}: sense aula per a {[df.at[i, 'id_sessio'] for i in ig]} el {dt}")
                continue
            if not ok:
                print(f"[!] {etiqueta}: {ig} a {r} no garanteix R8")
            move(ig, r)
            for j in ig:
                if df.at[j, "lock_room"]:
                    regla = "R7-PLAB" if df.at[j, "tipus"].upper() == "PLAB" else "R1-FIXADA"
                    relaxacions_noves[regla].add(df.at[j, "id_sessio"])
            n += len(ig)
        print(f"[✔] {etiqueta}: {n} sessions mogudes")

    desallotja("Q3/0013", "Sala reservada")
    desallotja("Q1/1003", "Avaria")

    # ---------- 3b. Correcció del torn de les dues sessions assenyalades ----------
    # Es busquen franges de tarda de la mateixa setmana, prioritzant el mínim canvi.
    sid_to_sessio = base_regles.sessions
    by_date = {}
    for j, dt in enumerate(df["date"]):
        by_date.setdefault(dt, []).append(j)
    cal_path = Path(PAQUET) / "calendari.csv"
    calendari = rd(cal_path) if cal_path.exists() else pd.DataFrame()
    dias_no_lectius = set()
    aturades_cal = {}
    for row in calendari.to_dict("records"):
        dt = row.get("data", "")
        if not dt:
            continue
        hi, hf = row.get("h_ini", ""), row.get("h_fi", "")
        if hi and hf:
            aturades_cal.setdefault(dt, []).append((tmin(hi), tmin(hf)))
        else:
            dias_no_lectius.add(dt)

    def doc_tokens(j):
        return set(re.split(r"[^A-Za-z0-9]+", df.at[j, "doc"])) - {""}

    def recoloca_torn(sid):
        ids = df.index[df["id_sessio"].eq(sid)].tolist()
        if len(ids) != 1:
            problemes.append(f"No s'ha identificat exactament una sessió {sid}")
            return
        i = ids[0]
        if df.at[i, "lock_time"]:
            problemes.append(f"{sid}: la sessió té dia/hora fixats i no es pot moure")
            return
        origin = pd.Timestamp(df.at[i, "date"])
        monday = origin - pd.Timedelta(days=origin.day_of_week)
        week_dates = [(monday + pd.Timedelta(days=k)).strftime("%Y-%m-%d") for k in range(5)]
        dates = [d for d in week_dates
                 if d in by_date and d not in dias_no_lectius and d not in base_regles.dies_sense_classe]
        duration, old_start, old_room = int(df.at[i, "dur"]), int(df.at[i, "s"]), df.at[i, "aula"]
        earliest = 870 if str(df.at[i, "torn"]).strip().lower().startswith("tar") else 510
        latest = 1260 if earliest == 870 else 870
        starts = range(earliest, latest - duration + 1, 30)
        candidates = sorted(((d, t) for d in dates for t in starts
            if not any(max(t, a0) < min(t + duration, b0) for a0, b0 in aturades_cal.get(d, []))),
            key=lambda x: (x[0] != str(df.at[i, "date"]), abs((pd.Timestamp(x[0]) - origin).days), abs(x[1] - old_start), x[0], x[1]))
        for dt, st in candidates:
            en = st + duration
            conflicte = False
            for j in by_date.get(dt, []):
                if j == i or df.at[j, "e"] <= st or en <= df.at[j, "s"]:
                    continue
                si = sid_to_sessio.get(sid)
                sj = sid_to_sessio.get(df.at[j, "id_sessio"])
                comparteix = bool(si and sj and _alumnat_comparteix(si, sj))
                ti, tj = df.at[i, "tipus"].upper(), df.at[j, "tipus"].upper()
                xoc_plab = df.at[i, "codi"] == df.at[j, "codi"] and "PLAB" in {ti, tj} and bool({ti, tj} & {"TE", "PAUL"})
                if doc_tokens(i) & doc_tokens(j) or comparteix or xoc_plab:
                    conflicte = True
                    break
            if conflicte:
                continue
            room, _ = find_room({i}, dt, st, en, df.at[i, "ncap"], old_room, allow_old=True)
            if room:
                move_schedule(i, dt, st, room)
                by_date.setdefault(dt, []).append(i)
                print(f"[✔] {sid} reubicada: {dt} {df.at[i, 'dia']} {df.at[i, 'h_ini']} aula {room}")
                return
        problemes.append(f"{sid}: no s'ha trobat cap franja de tarda lectiva sense conflictes i amb aula")

    recoloca_torn("S02839")
    recoloca_torn("S04526")

    # ---------- 4. Sessió cancel·lada ----------
    ii = df.index[df["id_sessio"] == SID_CANCEL]
    assert len(ii) == 1, f"{SID_CANCEL} no és a la proposta"
    i = ii[0]
    if df.at[i, "lock_time"]:
        problemes.append(f"{SID_CANCEL} té dia/hora fixats i no es pot recuperar movent-la")
    cal_path = Path(PAQUET) / "calendari.csv"
    calendari = rd(cal_path) if cal_path.exists() else pd.DataFrame()
    dies_tancats = set()
    aturades_cal: dict[str, list[tuple[int, int]]] = {}
    for row in calendari.to_dict("records"):
        dt = row.get("data", "")
        if not dt:
            continue
        hi, hf = row.get("h_ini", ""), row.get("h_fi", "")
        if hi and hf:
            aturades_cal.setdefault(dt, []).append((tmin(hi), tmin(hf)))
        else:
            # El verificador tracta qualsevol fila de calendari sense franja
            # horària com un tancament de tot el dia.
            dies_tancats.add(dt)
    dates_amb_classe = set(df["date"])
    data_origen = str(df.at[i, "data0"])
    dies = [d.strftime("%Y-%m-%d") for d in pd.date_range(
        pd.Timestamp(data_origen) + pd.Timedelta(days=1), DATA_RECUP_MAX
    ) if d.day_of_week < 5]
    dies = [d for d in dies if d not in dies_tancats and d in dates_amb_classe]
    print("[i] Dies candidats a recuperació:", dies)
    mati = df.at[i, "torn"].strip().lower().startswith("mat")
    win = (510, 870) if mati else (870, 1260)
    starts = list(range(win[0], win[1] - int(df.at[i, "dur"]) + 1, 30))
    ini_txt = dict(zip(df["s"], df["h_ini"]))
    docs = lambda j: set(re.split(r"[^A-Za-z0-9]+", df.at[j, "doc"])) - {""}
    base_regles = carrega_base(Path(PAQUET), semestre=2, escenari=Path(a.escenari))
    sid_to_sessio = base_regles.sessions
    by_date = {}
    for j, dt in enumerate(df["date"]):
        by_date.setdefault(dt, []).append(j)
    dur, orig_s, orig_room = df.at[i, "dur"], df.at[i, "s"], df.at[i, "aula"]
    cands = sorted(
        ((d, t) for d in dies for t in starts
         if not any(max(t, a0) < min(t + dur, b0) for a0, b0 in aturades_cal.get(d, []))),
        key=lambda x: (
            x[1] != orig_s,
            abs((pd.Timestamp(x[0]) - pd.Timestamp(data_origen)).days),
            abs(x[1] - orig_s), x[0], x[1],
        ),
    )
    elegit = None
    for dt, t in cands:
        en = t + dur
        conflicte = False
        for j in by_date.get(dt, []):
            if j == i or df.at[j, "e"] <= t or en <= df.at[j, "s"]:
                continue
            sid_i, sid_j = df.at[i, "id_sessio"], df.at[j, "id_sessio"]
            si, sj = sid_to_sessio.get(sid_i), sid_to_sessio.get(sid_j)
            comparteix_alumnat = bool(si and sj and _alumnat_comparteix(si, sj))
            tipus_i, tipus_j = df.at[i, "tipus"].upper(), df.at[j, "tipus"].upper()
            xoc_plab = (
                df.at[i, "codi"] == df.at[j, "codi"]
                and "PLAB" in {tipus_i, tipus_j}
                and bool({tipus_i, tipus_j} & {"TE", "PAUL"})
            )
            if (docs(i) & docs(j)) or comparteix_alumnat or xoc_plab:
                conflicte = True
                break
        if conflicte:
            continue
        if orig_room and not df.at[i, "sinesp"]:
            r, ok = find_room({i}, dt, t, en, df.at[i, "ncap"], orig_room, pref=orig_room, allow_old=True)
            if r is None:
                continue
            if not ok:
                continue  # exigim R8 també a la recuperació
        else:
            r = orig_room
        elegit = (dt, t, r)
        break
    nova_data = ""
    if elegit is None:
        problemes.append(f"No hi ha franja vàlida per recuperar {SID_CANCEL}")
    else:
        dt, t, r = elegit
        occ.get((df.at[i, "date"], df.at[i, "aula"]), {}).pop(i, None)
        df.at[i, "date"], df.at[i, "s"], df.at[i, "e"] = dt, t, t + dur
        df.at[i, "dia"] = wd2dia[pd.Timestamp(dt).day_of_week]
        df.at[i, "h_ini"] = ini_txt.get(t, f"{t // 60:02d}:{t % 60:02d}")
        df.at[i, "aula"] = r
        if r and not df.at[i, "sinesp"]:
            occ.setdefault((dt, r), {})[i] = (t, t + dur)
        nova_data = dt
        print(f"[✔] {SID_CANCEL} recuperada: {dt} {df.at[i, 'dia']} {df.at[i, 'h_ini']} aula {r}")

    # ---------- autocomprovació ----------
    for (dt, r), d in occ.items():
        if closed(r, dt):
            for j in d:
                problemes.append(f"Queda {df.at[j, 'id_sessio']} a {r} el {dt} (tancada)")
    for j in df.index:
        r = df.at[j, "aula"]
        if r in ordi and df.at[j, "ncap"] > cap[r] and df.at[j, "aula"] != base_aula[j]:
            problemes.append(f"Aforament: {df.at[j, 'id_sessio']} a {r}")

    out = df[["id_sessio", "dia", "h_ini", "aula"]].copy()
    out["data"] = ""
    if nova_data:
        out.loc[i, "data"] = nova_data
    out.to_csv(a.out, index=False)

    relax_base = Path("relaxacions-5_2.csv")
    relax_out = Path("relaxacions-imprevist.csv")
    relax_df = rd(relax_base) if relax_base.exists() else pd.DataFrame(columns=["restriccio", "sessions", "justificacio"])
    for regla, ids in relaxacions_noves.items():
        ids = sorted(ids)
        if not ids:
            continue
        justificacio = (
            "Excepció per evacuar una aula tancada per l'escenari, mantenint dia i hora i evitant R3-TANCADA."
            if regla == "R1-FIXADA" else
            "Excepció per traslladar els PLAB de Q3/0013, reservada per l'escenari, a una aula lliure."
        )
        files = relax_df.index[relax_df["restriccio"].eq(regla)].tolist()
        if files:
            k = files[0]
            combinats = set(filter(None, relax_df.at[k, "sessions"].split("|"))) | set(ids)
            relax_df.at[k, "sessions"] = "|".join(sorted(combinats))
            relax_df.at[k, "justificacio"] = (str(relax_df.at[k, "justificacio"]).strip() + " " + justificacio).strip()
        else:
            relax_df.loc[len(relax_df)] = [regla, "|".join(ids), justificacio]
    relax_df.to_csv(relax_out, index=False)
    print(f"[✔] Relaxacions declarades escrites a: {relax_out}")
    canvis_aula = int((df["aula"] != base_aula).sum())
    canvis_franja = int(((df["dia"] != base_dia) | (df["h_ini"] != base_ini)).sum())
    print(f"[✔] {a.out}: {len(out)} files (base {len(prop)}). canvis_aula={canvis_aula} canvis_franja={canvis_franja}")

    if problemes:
        print("\n=== PROBLEMES (cal revisar abans de lliurar) ===")
        for p in problemes:
            print(" -", p)
    if a.check:
        cmd = [sys.executable, "-m", "horaris", "check", a.out, "--semestre", "2", "--escenari", a.escenari,
               "--referencia", a.base, "--json", "informe.json", "--violacions", "violacions.csv"]
        relaxacions = Path("relaxacions-imprevist.csv")
        if relaxacions.is_file():
            cmd.extend(["--relaxacions", str(relaxacions)])
        print("$", " ".join(cmd))
        resultat = subprocess.run(cmd, check=False)
        if resultado := resultat.returncode:
            problemes.append(f"El verificador oficial retorna codi {resultado}; consulta violacions.csv i informe.json.")
    sys.exit(1 if problemes else 0)


if __name__ == "__main__":
    main()
