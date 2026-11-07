import pandas as pd
import numpy as np

# ----------------------------------------------------
# CARGA DE DATASETS
# ----------------------------------------------------
df_sessions = pd.read_csv('activitats_agrupades.csv')
df_aules    = pd.read_csv('paquet/aules.csv')

# Franja horària: matí < 14:30, tarda >= 14:30  (R2)
df_sessions['franja'] = np.where(df_sessions['h_ini'] < '14:30', 'matí', 'tarda')

print("==================================================")
print("   ANÀLISI COMPLETA NIVELL 1 – ESCOLA D'ENGINYERIA")
print("==================================================\n")

# =========================================================
# PUNT 1 – OCUPACIÓ DE CADA AULA PER DIA, FRANJA I SEMESTRE
# =========================================================
print("=" * 50)
print("[PUNT 1] OCUPACIÓ PER AULA, DIA, FRANJA I SEMESTRE")
print("=" * 50)

aules_aulari = df_aules['aula'].tolist()
df_con_aula  = df_sessions[df_sessions['aula_partida'].isin(aules_aulari)].copy()
df_con_aula['hores'] = df_con_aula['durada_min'] / 60.0

# --- 1a. Ocupació total acumulada per aula i semestre ---
ocup_sem = (
    df_con_aula
    .groupby(['aula_partida', 'semestre'])['hores']
    .sum()
    .unstack(fill_value=0)
    .reset_index()
)
ocup_sem.columns.name = None
# Garantim que existeixin les dues columnes de semestre
for col in ['C/1', 'C/2']:
    if col not in ocup_sem.columns:
        ocup_sem[col] = 0.0
ocup_sem = ocup_sem.rename(columns={'aula_partida': 'aula', 'C/1': 'hores_S1', 'C/2': 'hores_S2'})

df_ocup = df_aules[['aula', 'tipus', 'capacitat', 'ordinaria']].merge(ocup_sem, on='aula', how='left').fillna(0)

print("\nTop 10 aules més ocupades al 2n Semestre (C/2):")
print(df_ocup.sort_values('hores_S2', ascending=False)
                .head(10)[['aula', 'tipus', 'capacitat', 'hores_S1', 'hores_S2']]
                .to_string(index=False))

buides_s1 = df_ocup[df_ocup['hores_S1'] == 0]['aula'].tolist()
buides_s2 = df_ocup[df_ocup['hores_S2'] == 0]['aula'].tolist()
print(f"\nAules sense cap ús a S1: {len(buides_s1)} → {buides_s1}")
print(f"Aules sense cap ús a S2: {len(buides_s2)} → {buides_s2}")

# --- 1b. Ocupació per aula, DIA i FRANJA (setmana tipus) ---
# Comptem sessions úniques per evitar duplicats de setmana
ocup_dia_franja = (
    df_con_aula
    .drop_duplicates(subset=['aula_partida', 'dia', 'h_ini', 'h_fi', 'semestre'])
    .groupby(['semestre', 'aula_partida', 'dia', 'franja'])['hores']
    .sum()
    .reset_index()
    .rename(columns={'aula_partida': 'aula'})
)

print("\nOcupació per aula/dia/franja (mostra – S2, aules ordinàries, top 10 per hores):")
mostra = (
    ocup_dia_franja[ocup_dia_franja['semestre'] == 'C/2']
    .sort_values('hores', ascending=False)
    .head(10)
)
print(mostra.to_string(index=False))

# Exportar
df_ocup.to_csv('ocupacio_aules_semestre.csv', index=False)
ocup_dia_franja.to_csv('ocupacio_aules_dia_franja.csv', index=False)
print("\n→ Exportat: ocupacio_aules_semestre.csv  |  ocupacio_aules_dia_franja.csv")

# =========================================================
# PUNT 2 – BALANÇ HORES-AULA AL 2N SEMESTRE
# =========================================================
print("\n" + "=" * 50)
print("[PUNT 2] BALANÇ HORES-AULA AL 2n SEMESTRE (S2)")
print("=" * 50)

sem2 = df_sessions[df_sessions['semestre'] == 'C/2'].copy()
total_s2        = len(sem2)
n_sense_aula    = sem2['aula_partida'].isna().sum()

# Sessions que realment necessiten aula ordinària
# (s'exclouen: dobles titulacions sense espai propi + labs PLAB assignats per dept.)
mask_necessiten = (sem2['sense_espai'] != 1) & (sem2['tipus'] != 'PLAB')
sense_aula_req  = sem2[sem2['aula_partida'].isna() & mask_necessiten].copy()
sense_aula_req['hores'] = sense_aula_req['durada_min'] / 60.0

print(f"\nTotal sessions S2            : {total_s2}")
print(f"Sessions sense aula (total)  : {n_sense_aula}  ({n_sense_aula/total_s2*100:.1f} %)")
print(f"  · Dobles titulacions (sense espai propi) : {sem2[sem2['aula_partida'].isna() & (sem2['sense_espai'] == 1)].shape[0]}")
print(f"  · Labs PLAB (dept. assigna) : {sem2[sem2['aula_partida'].isna() & (sem2['sense_espai'] != 1) & (sem2['tipus'] == 'PLAB')].shape[0]}")
print(f"  → Sessions NETES a assignar : {len(sense_aula_req)}")

# --- Demanda per franja (hores-aula totals al semestre, sessions sense aula) ---
dem_franja = sense_aula_req.groupby('franja')['hores'].sum()
print(f"\nDemanda hores-aula pendents (semestre):")
print(f"  Matí : {dem_franja.get('matí', 0):8.1f} h")
print(f"  Tarda: {dem_franja.get('tarda', 0):8.1f} h")

# --- Oferta real calculada des de les dades ---
# Aules ordinàries disponibles (ordinaria == 1), llevant 2 de reserva
aules_ord = df_aules[df_aules['ordinaria'] == 1]
n_aules_tot = len(aules_ord)
n_aules_disp = n_aules_tot - 2   # 2 de reserva
print(f"\nAules docents ordinàries al aulari: {n_aules_tot}  (disponibles: {n_aules_disp})")

# Hores setmanals de cada franja: mirem quantes hores de classe reals hi ha per franja i dia
# (una aula pot tenir fins a tantes hores com franges diferents)
# Estimem la finestra horària de cada franja des de les dades reals
h_mati_sessio  = df_sessions[df_sessions['franja'] == 'matí']['durada_min'].mean() / 60.0
h_tarda_sessio = df_sessions[df_sessions['franja'] == 'tarda']['durada_min'].mean() / 60.0

# Hores disponibles per aula i setmana: franges úniques per dia (L,M,X,J,V) × hores franja
dies = ['L', 'M', 'X', 'J', 'V']
# Hores reals de matí i tarda disponibles per aula i dia (des de les hores d'inici/fi)
h_ini_mati   = df_sessions[df_sessions['franja'] == 'matí']['h_ini'].min()
h_fi_mati    = df_sessions[df_sessions['franja'] == 'matí']['h_fi'].max()
h_ini_tarda  = df_sessions[df_sessions['fran ja'] == 'tarda']['h_ini'].min()
h_fi_tarda   = df_sessions[df_sessions['franja'] == 'tarda']['h_fi'].max()

def hores_franja(h_ini_str, h_fi_str):
    """Calcula hores entre dues strings 'HH:MM'."""
    h1, m1 = map(int, h_ini_str.split(':'))
    h2, m2 = map(int, h_fi_str.split(':'))
    return (h2 * 60 + m2 - h1 * 60 - m1) / 60.0

hores_mati_dia   = hores_franja(h_ini_mati, h_fi_mati)
hores_tarda_dia  = hores_franja(h_ini_tarda, h_fi_tarda)
setmanes = 15

oferta_mati_sem  = n_aules_disp * hores_mati_dia  * len(dies) * setmanes
oferta_tarda_sem = n_aules_disp * hores_tarda_dia * len(dies) * setmanes

print(f"\nFinestra horària matí : {h_ini_mati} – {h_fi_mati}  ({hores_mati_dia:.1f} h/dia·aula)")
print(f"Finestra horària tarda: {h_ini_tarda} – {h_fi_tarda}  ({hores_tarda_dia:.1f} h/dia·aula)")
print(f"\nOferta total {n_aules_disp} aules × {setmanes} set.:")
print(f"  Matí : {oferta_mati_sem:8.1f} h (semestre)")
print(f"  Tarda: {oferta_tarda_sem:8.1f} h (semestre)")

# =========================================================
# PUNT 3 – SESSIONS AL TORN INCORRECTE (R1), PER TIT. I CURS
# =========================================================
print("\n" + "=" * 50)
print("[PUNT 3] SESSIONS AL TORN INCORRECTE (R1), PER TITULACIÓ I CURS")
print("=" * 50)

sem2['es_mati_real'] = sem2['h_ini'] < '14:30'
sem2['incumple_r1']  = (
    ((sem2['torn_requerit'] == 'mati')  & (~sem2['es_mati_real'])) |
    ((sem2['torn_requerit'] == 'tarda') &  (sem2['es_mati_real']))
)

desviades = sem2[sem2['incumple_r1']].copy()

# Separar titulació i curs (format "GEO:2n")
split_df = desviades['titulacions_curs'].astype(str).str.split(':', n=1, expand=True)
desviades['titulacio'] = split_df[0]
desviades['curs'] = split_df[1] if split_df.shape[1] > 1 else np.nan

print(f"\nTotal sessions fora de torn a S2: {len(desviades)}")

print("\n── Per TITULACIÓ ──────────────────────────────")
per_titulacio = (
    desviades.groupby('titulacio')
    .size()
    .reset_index(name='n_sessions')
    .sort_values('n_sessions', ascending=False)
)
print(per_titulacio.to_string(index=False))

print("\n── Per CURS ───────────────────────────────────")
per_curs = (
    desviades.groupby('curs')
    .size()
    .reset_index(name='n_sessions')
    .sort_values('n_sessions', ascending=False)
)
print(per_curs.to_string(index=False))

# Exportar
desviades.to_csv('sessions_torn_incorrecte.csv', index=False)
print("\n→ Exportat: sessions_torn_incorrecte.csv")

# =========================================================
# PUNT 4 – HI CAP EL MATÍ? (1r I 2n CURS, S2)
# =========================================================
print("\n" + "=" * 50)
print("[PUNT 4] HI CAP EL MATÍ? (1r I 2n CURS A S2)")
print("=" * 50)

# Demanda: sessions de torn matí que necessiten aula ordinària
dem_mati = sem2[
    (sem2['torn_requerit'] == 'mati') &
    (sem2['sense_espai'] != 1) &
    (sem2['tipus'] != 'PLAB')
].copy()
dem_mati['hores'] = dem_mati['durada_min'] / 60.0

hores_dem_total  = dem_mati['hores'].sum()
hores_dem_setm   = hores_dem_total / setmanes

# Oferta: aules ordinàries disponibles (ja calculades al Punt 2)
oferta_setm_mati = n_aules_disp * hores_mati_dia * len(dies)
oferta_total_mati = oferta_setm_mati * setmanes
pct = (hores_dem_setm / oferta_setm_mati) * 100 if oferta_setm_mati > 0 else 0

print(f"\nDemanda 1r+2n (semestre total)    : {hores_dem_total:8.1f} h")
print(f"Demanda 1r+2n (setmana promig)    : {hores_dem_setm:8.1f} h/set")
print(f"Oferta aulari matí (setmana)      : {oferta_setm_mati:8.1f} h/set  "
        f"({n_aules_disp} aules × {hores_mati_dia:.1f}h × 5 dies)")
print(f"Ocupació sobre la capacitat       : {pct:5.1f} %")

# Pic màxim simultani (setmana tipus, sense duplicar setmanes)
pico = (
    dem_mati.drop_duplicates(subset=['activitat_id', 'dia', 'h_ini'])
    .groupby(['dia', 'h_ini'])
    .size()
    .max()
)
print(f"Pic màxim de classes alhora       : {pico} (aules disponibles: {n_aules_disp})")

if pico <= n_aules_disp and pct <= 100:
    print("→ VEREDICTE: SÍ hi cap (demanda < oferta i pic <= aules disponibles)")
elif pico > n_aules_disp:
    print(f"→ VEREDICTE: NO hi cap — el pic ({pico}) supera les {n_aules_disp} aules disponibles")
else:
    print(f"→ VEREDICTE: JUST — {pct:.1f}% d'ocupació, revisar franges crítiques")

# =========================================================
# PUNT 5 – GRUPS AMB MÉS ALUMNES QUE PLACES
# =========================================================
print("\n" + "=" * 50)
print("[PUNT 5] GRUPS AMB MÉS ALUMNES QUE PLACES A L'AULA ACTUAL")
print("=" * 50)

# 1. Hacemos el merge trayendo la capacidad de la tabla de aulas
sem2_con_aula = (
    sem2.dropna(subset=['aula_partida'])
        .merge(df_aules[['aula', 'capacitat']], left_on='aula_partida', right_on='aula', how='left')
)

# 2. Si existía 'capacitat' en sem2, pandas habrá creado 'capacitat_y', si no, se llama 'capacitat'
col_cap = 'capacitat_y' if 'capacitat_y' in sem2_con_aula.columns else 'capacitat'

# 3. Filtramos los excesos usando la columna correcta
excesos = sem2_con_aula[sem2_con_aula['alumnes'] > sem2_con_aula[col_cap]].copy()
excesos['capacitat_aula'] = excesos[col_cap]
excesos['excedent'] = excesos['alumnes'] - excesos['capacitat_aula']

print(f"\nTotal sessions amb excés d'aforament a S2: {len(excesos)}")

# Agrupació per grup (activitat única, no per setmana)
excesos_grup = (
    excesos.drop_duplicates(subset=['activitat_id'])
    [['assignatura', 'grup', 'titulacions_curs', 'alumnes', 'aula_partida', 'capacitat_aula', 'excedent']]
    .sort_values('excedent', ascending=False)
)
print(f"Grups únics afectats: {len(excesos_grup)}")
print("\nTop 15 grups amb major excedent:")
print(excesos_grup.head(15).to_string(index=False))

# Exportar
excesos_grup.to_csv('grups_exceso_aforament.csv', index=False)
print("\n→ Exportat: grups_exceso_aforament.csv")

print("\n" + "=" * 50)
print("   ANÀLISI FINALITZADA – ARXIUS CSV GENERATS")
print("=" * 50)