"""Comprovació INDEPENDENT de les respostes de l'assistent: llegeix paquet/*.csv directament,
sense cap codi de nucli.py (així es fa el que farà el jurat).

  python comprovar.py grup 81 dimarts
  python comprovar.py lliures dijous 10:00 60          # aules amb >= 60 places lliures
  python comprovar.py aula Q4/0011 2027-03-08
  python comprovar.py sessio S11527
"""
import sys
import pandas as pd

s = pd.read_csv("paquet/sessions.csv", dtype=str, keep_default_na=False)
a = pd.read_csv("paquet/aules.csv", dtype=str, keep_default_na=False)
s["wd"] = pd.to_datetime(s["data"]).dt.day_of_week
s["sem"] = pd.to_datetime(s["data"]).dt.month.map(lambda m: 1 if m in (9, 10, 11, 12, 1) else 2)
DIES = {"dilluns": 0, "dimarts": 1, "dimecres": 2, "dijous": 3, "divendres": 4}
mins = lambda x: int(x.split(":")[0]) * 60 + int(x.split(":")[1])
pd.set_option("display.width", 250, "display.max_rows", 200, "display.max_columns", 30)
col_aula = "aula_partida" if "aula_partida" in s.columns else "aula"

cmd, args = sys.argv[1], sys.argv[2:]
if cmd == "grup":
    g, dia = args[0].upper(), DIES[args[1].lower()]
    d = s[(s["sem"] == 2) & ((s.grup.str.upper() == g) | s.grup.str.upper().str.endswith("/" + g)) & (s.wd == dia)]
    print(d[["id_sessio", "assignatura", "grup", "tipus", "data", "dia", "h_ini", "h_fi", col_aula]].sort_values("data").to_string(index=False))
elif cmd == "lliures":
    dia, t0, dur, minp = DIES[args[0].lower()], mins(args[1]), int(args[2]) if len(args) > 2 else 60, int(args[3]) if len(args) > 3 else 0
    d = s[(s["sem"] == 2) & (s.wd == dia) & (s.h_ini.map(mins) < t0 + dur) & (s.h_fi.map(mins) > t0)]
    ocup = set(d[col_aula]) - {""}
    print("Aules OCUPADES a la franja (algun dia del semestre):", sorted(ocup))
    print("Sessions de la franja SENSE aula a les dades:", int((d[col_aula] == "").sum()), "(poden ocupar-ne una)")
    lliures = a[~a["aula"].isin(ocup) & (pd.to_numeric(a["capacitat"]) >= minp)]
    print(lliures[["aula", "capacitat", "tipus"]].to_string(index=False))
elif cmd == "aula":
    d = s[(s[col_aula] == args[0]) & (s.data == args[1])] if len(args) > 1 else s[s[col_aula] == args[0]]
    print(d[["id_sessio", "assignatura", "grup", "tipus", "data", "h_ini", "h_fi", "alumnes"]].to_string(index=False))
elif cmd == "sessio":
    print(s[s.id_sessio == args[0]].T)