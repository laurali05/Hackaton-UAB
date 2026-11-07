#!/usr/bin/env python3
"""Repte 5.3 (imprevist). Parteix de proposta-torns.csv (la del 5.2).

Ús:
    python resolver_contingencies.py --base proposta-torns.csv --check

Fa NOMÉS aquests canvis sobre la base:
  1. TE/21 de Transmissió de Calor (GEQ 2n): 130 alumnes -> una sola aula >=130.
  2. Q3/0013 reservada del 15 al 19/3/2027 -> mou les classes d'aquells dies.
  3. Q1/1003 avariada el 10/3/2027 -> mou les classes d'aquell dia.
  4. S11527 (8/3) cancel·lada -> recuperada fins al 19/3, amb la columna `data`.
Tot es fa amb solapament per INTERVAL, data real (si el 5.2 ha canviat el dia),
aforament, reserva R8 (2 aules ordinàries lliures) i conflictes de docent/alumnat.
Si no troba solució, s'atura amb error: mai deixa una sessió malament en silenci.
"""
import argparse, os, re, subprocess, sys
import pandas as pd

PAQUET = "paquet"

# ---- NOMS DE COLUMNA de paquet/sessions.csv: COMPROVEU-LOS amb DICCIONARI.md ----
SC = dict(data="data", dia="dia", ini="h_ini", fi="h_fi", tipus="tipus", grup="grup",
          assig="assignatura", alum="alumnes", fix="fixada", doc=["docents", "docent", "professorat"],
          coh=["cohort", "titulacions_curs", "titulacio_curs"], torn="torn_requerit", esp="sense_espai")
# ---- paquet/aules.csv ----
AC = dict(aula="aula", cap="capacitat", tipus="tipus")   # ordinària = tipus que conté "docent"

CLOSED = {"Q3/0013": {"2027-03-15", "2027-03-16", "2027-03-17", "2027-03-18", "2027-03-19"},
          "Q1/1003": {"2027-03-10"}}
SID_CANCEL, DATA_RECUP_MIN, DATA_RECUP_MAX, DATA_NO_LECTIVA = "S11527", "2027-03-08", "2027-03-19", {"2027-03-18"}
GRUP_AFORAMENT_NOU = 130
SLOTS = list(range(510, 1260, 60))  # franges d'una hora, 8.30 .. 20.30 (l'última acaba a les 21.00)

problemes = []


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
    wd_ses = pd.to_datetime(ses[SC["data"]]).dt.weekday
    dia2wd = {d: int(g.mode()[0]) for d, g in wd_ses.groupby(ses[SC["dia"]])}
    wd2dia = {v: k for k, v in dia2wd.items()}
    print("[i] codis de dia:", dia2wd)
    assert df["dia"].isin(dia2wd).all(), "La proposta té codis de dia desconeguts"

    # DATA REAL: si el 5.2 ha mogut la sessió de dia, la data canvia dins de la setmana
    d0 = pd.to_datetime(df["data0"])
    df["date"] = (d0 + pd.to_timedelta(df["dia"].map(dia2wd) - d0.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    df["s"] = df["h_ini"].map(tmin)
    df["dur"] = df["fi0"].map(tmin) - df["ini0"].map(tmin)
    df["e"] = df["s"] + df["dur"]
    df["ncap"] = pd.to_numeric(df["alum"], errors="coerce").fillna(0)
    fix = df["fix"].str.strip().str.lower().isin(["1", "1.0", "true", "si", "sí"])
    df["lock"] = fix | df["tipus"].str.upper().eq("PLAB")
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
        return dt in CLOSED.get(r, ())

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

    def find_room(ig, dt, st, en, need, old, pref=None, allow_old=False):
        c = [r for r in ordi if cap[r] >= need and (allow_old or r != old) and not closed(r, dt)
             and not busy(dt, r, st, en, ig)]
        c.sort(key=lambda r: (r != pref, passadis(r) != passadis(old or ""), cap[r], r))
        for r in c:
            if reserve_ok(dt, st, en, r, ig):
                return r, True
        return (c[0], False) if c else (None, False)

    def agrupa(idxs):
        g = {}
        for i in idxs:
            g.setdefault((df.at[i, "date"], df.at[i, "s"], df.at[i, "e"], df.at[i, "aula"], df.at[i, "doc"]), []).append(i)
        return g

    # ---------- 1. Grup que ja no hi cap ----------
    m = (df["tipus"].str.upper() == "TE") & (df["aula"] == "Q4/0011") & (df["ncap"] == 91) \
        & df["grup"].str.fullmatch(r"(TE/)?21")
    keys = df.loc[m, ["assig", "grup"]].drop_duplicates()
    if len(keys) != 1:  # la base pot haver canviat l'aula: provem per nom
        m = (df["tipus"].str.upper() == "TE") & (df["ncap"] == 91) & df["grup"].str.fullmatch(r"(TE/)?21") \
            & df["assig"].str.contains("calor|termot", case=False)
        keys = df.loc[m, ["assig", "grup"]].drop_duplicates()
    if len(keys) != 1:
        sys.exit(f"ERROR: no identifico el grup TE/21 de Calor de forma única: {keys.to_dict('records')}. "
                 "Reviseu els filtres de l'apartat 1.")
    ka, kg = keys.iloc[0]
    print(f"[i] Grup identificat: assignatura={ka} grup={kg}")
    sem2 = ~pd.to_datetime(df["date"]).dt.month.isin([9, 10, 11, 12, 1])
    gm = (df["assig"] == ka) & (df["grup"] == kg) & (df["tipus"].str.upper() == "TE") & sem2 & ~df["lock"]
    gi = [i for i in df.index[gm] if cap.get(df.at[i, "aula"], 0) < GRUP_AFORAMENT_NOU]
    if gi:
        ig = set(gi)
        triat = None
        for exigeix_reserva in (True, False):
            for r in sorted((r for r in ordi if cap[r] >= GRUP_AFORAMENT_NOU), key=lambda r: (cap[r], r)):
                if all(not closed(r, df.at[i, "date"]) and not busy(df.at[i, "date"], r, df.at[i, "s"], df.at[i, "e"], ig)
                       and (not exigeix_reserva or reserve_ok(df.at[i, "date"], df.at[i, "s"], df.at[i, "e"], r, ig))
                       for i in gi):
                    triat = r
                    break
            if triat:
                if not exigeix_reserva:
                    print("[!] Aula única trobada però sense garantir R8 a totes les franges")
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

    # ---------- 2 i 3. Aula reservada / avariada ----------
    def desallotja(room, etiqueta):
        idx = [i for i in df.index[(df["aula"] == room) & df["date"].isin(CLOSED[room])]]
        for i in idx:
            if df.at[i, "lock"]:
                problemes.append(f"{etiqueta}: {df.at[i, 'id_sessio']} és fixada/PLAB i no es pot moure (declareu-ho com a relaxació)")
        n = 0
        for (dt, st, en, old, _), ig in agrupa([i for i in idx if not df.at[i, "lock"]]).items():
            need = df.loc[ig, "ncap"].max()
            r, ok = find_room(set(ig), dt, st, en, need, old)
            if r is None:
                problemes.append(f"{etiqueta}: sense aula per a {[df.at[i, 'id_sessio'] for i in ig]} el {dt}")
                continue
            if not ok:
                print(f"[!] {etiqueta}: {ig} a {r} no garanteix R8")
            move(ig, r)
            n += len(ig)
        print(f"[✔] {etiqueta}: {n} sessions mogudes")

    desallotja("Q3/0013", "Sala reservada")
    desallotja("Q1/1003", "Avaria")

    # ---------- 4. Sessió cancel·lada ----------
    ii = df.index[df["id_sessio"] == SID_CANCEL]
    assert len(ii) == 1, f"{SID_CANCEL} no és a la proposta"
    i = ii[0]
    if df.at[i, "date"] != DATA_RECUP_MIN:
        print(f"[!] {SID_CANCEL} és el {df.at[i, 'date']} a la base (l'enunciat diu el 8/3)")
    if df.at[i, "lock"]:
        problemes.append(f"{SID_CANCEL} és fixada/PLAB")
    festius = set()
    cal = os.path.join(PAQUET, "calendari.csv")
    if os.path.exists(cal):
        festius = set(re.findall(r"\d{4}-\d{2}-\d{2}", open(cal, encoding="utf-8").read()))
    dates_amb_classe = set(df["date"])
    dies = [d.strftime("%Y-%m-%d") for d in pd.date_range(DATA_RECUP_MIN, DATA_RECUP_MAX) if d.weekday() < 5]
    dies = [d for d in dies if d != df.at[i, "date"] and d not in DATA_NO_LECTIVA and d not in festius
            and d in dates_amb_classe]
    print("[i] Dies candidats a recuperació:", dies)
    mati = df.at[i, "torn"].strip().lower().startswith("mat")
    win = (510, 870) if mati else (870, 1260)
    starts = sorted(set(df.loc[~df["lock"], "s"]))
    starts = [t for t in starts if t >= win[0] and t + df.at[i, "dur"] <= win[1]]
    ini_txt = dict(zip(df["s"], df["h_ini"]))
    docs = lambda j: set(re.split(r"[^A-Za-z0-9]+", df.at[j, "doc"])) - {""}
    cohs = lambda j: set(re.split(r"[;,|]\s*", df.at[j, "coh"])) - {""}
    by_date = {}
    for j, dt in enumerate(df["date"]):
        by_date.setdefault(dt, []).append(j)
    dur, orig_s, orig_room = df.at[i, "dur"], df.at[i, "s"], df.at[i, "aula"]
    cands = sorted(((d, t) for d in dies for t in starts),
                   key=lambda x: (x[1] != orig_s, abs((pd.Timestamp(x[0]) - pd.Timestamp(df.at[i, "date"])).days), x))
    elegit = None
    for dt, t in cands:
        en = t + dur
        conflicte = False
        for j in by_date.get(dt, []):
            if j == i or df.at[j, "e"] <= t or en <= df.at[j, "s"]:
                continue
            if (docs(i) & docs(j)) or (cohs(i) & cohs(j)) or \
               (df.at[j, "tipus"].upper() == "PLAB" and df.at[j, "assig"] == df.at[i, "assig"]):
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
        df.at[i, "dia"] = wd2dia[pd.Timestamp(dt).weekday()]
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
                if not df.at[j, "lock"]:
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
        print("$", " ".join(cmd))
        subprocess.run(cmd)
    sys.exit(1 if problemes else 0)


if __name__ == "__main__":
    main()