import os
import pandas as pd

# Obtenim la carpeta base per evitar errors de ruta a Windows
DIR_BASE = os.path.dirname(os.path.abspath(__file__))


def carregar_csv(nom_fitxer):
    rutes = [
        os.path.join(DIR_BASE, nom_fitxer),
        os.path.join(DIR_BASE, 'paquet', nom_fitxer),
        os.path.join(os.path.dirname(DIR_BASE), nom_fitxer),
    ]
    for r in rutes:
        if os.path.exists(r):
            return pd.read_csv(r)
    raise FileNotFoundError(f"No s'ha trobat el fitxer {nom_fitxer}")


# 1. Carregar dades inicials
sessions = carregar_csv('sessions.csv')
aules = carregar_csv('aules.csv')
proposta = carregar_csv('proposta_partida.csv')

# Filtrem només el 2n semestre (C/2)
sem2 = sessions[sessions['semestre'] == 'C/2'].copy()

# Aules ordinàries docents i seminaris ordenades per capacitat
aules_ord = aules[
    aules['tipus'].isin(['Aules docents', 'Seminaris'])
].sort_values(by='capacitat', ascending=True)

# 2. Desplaçar de torn les sessions movibles (fixada isna)
noves_hores_ini = {}
noves_hores_fi = {}

for _, row in sem2.iterrows():
    id_s = row['id_sessio']

    # Només movem si la classe NO està fixada per la regla 1 ni és un PLAB
    if pd.isna(row['fixada']):
        h_ini = row['h_ini']
        h_fi = row['h_fi']
        torn_req = row['torn_requerit']

        # De tarda a matí (restem 6 hores)
        if torn_req == 'mati' and h_ini >= '14:30':
            hi, mi = map(int, h_ini.split(':'))
            hf, mf = map(int, h_fi.split(':'))
            noves_hores_ini[id_s] = f'{hi - 6:02d}:{mi:02d}'
            noves_hores_fi[id_s] = f'{hf - 6:02d}:{mf:02d}'

        # De matí a tarda (sumem 6 hores)
        elif torn_req == 'tarda' and h_ini < '14:30':
            hi, mi = map(int, h_ini.split(':'))
            hf, mf = map(int, h_fi.split(':'))
            noves_hores_ini[id_s] = f'{hi + 6:02d}:{mi:02d}'
            noves_hores_fi[id_s] = f'{hf + 6:02d}:{mf:02d}'

# Apliquem el canvi d'horari a la taula temporal
sem2['h_ini'] = sem2['id_sessio'].map(noves_hores_ini).fillna(sem2['h_ini'])
sem2['h_fi'] = sem2['id_sessio'].map(noves_hores_fi).fillna(sem2['h_fi'])

# 3. Assignar aules a les noves hores per activitats setmanals
ocupacio = set()
for _, row in sem2.iterrows():
    aula_act = row['aula_partida']
    if pd.notna(aula_act):
        ocupacio.add((aula_act, row['dia'], row['h_ini']))

# Sessions que requereixen assignació d'aula
ordinaries = sem2[
    (sem2['aula_partida'].isna())
    & (sem2['sense_espai'] != 1)
    & (sem2['tipus'] != 'PLAB')
]

activitats = ordinaries.drop_duplicates(subset=['activitat_id']).sort_values(
    by='alumnes', ascending=False
)

aula_per_activitat = {}
aula_base_grup = {}

for _, row in activitats.iterrows():
    act_id = row['activitat_id']
    grup = row['grup']
    dia = row['dia']
    h_ini = row['h_ini']
    alumnes = row['alumnes']

    aula_triada = None

    # Intent A: Reutilitzar l'aula base del mateix grup
    if grup in aula_base_grup:
        cand = aula_base_grup[grup]
        match = aules_ord[aules_ord['aula'] == cand]
        if not match.empty and match['capacitat'].values[0] >= alumnes:
            if (cand, dia, h_ini) not in ocupacio:
                aula_triada = cand

    # Intent B: Buscar l'aula més petita lliure on caben tots
    if not aula_triada:
        for _, a_row in aules_ord.iterrows():
            cand = a_row['aula']
            if (
                a_row['capacitat'] >= alumnes
                and (cand, dia, h_ini) not in ocupacio
            ):
                aula_triada = cand
                break

    if aula_triada:
        aula_per_activitat[act_id] = aula_triada
        ocupacio.add((aula_triada, dia, h_ini))
        aula_base_grup[grup] = aula_triada

noves_assignacions = {}
for _, row in ordinaries.iterrows():
    act_id = row['activitat_id']
    if act_id in aula_per_activitat:
        noves_assignacions[row['id_sessio']] = aula_per_activitat[act_id]

# 4. Generar el fitxer oficial de sortida proposta-torns.csv
proposta['h_ini'] = (
    proposta['id_sessio'].map(noves_hores_ini).fillna(proposta['h_ini'])
)
proposta['h_fi'] = (
    proposta['id_sessio'].map(noves_hores_fi).fillna(proposta['h_fi'])
)
proposta['aula'] = (
    proposta['id_sessio'].map(noves_assignacions).fillna(proposta['aula'])
)

proposta.to_csv('proposta-torns.csv', index=False)

print('=== PAS 5.2 COMPLETAT ===')
print(f'Sessions desplaçades de torn: {len(noves_hores_ini)}')
print(f'Sessions ordinàries amb aula assignada: {len(noves_assignacions)}')
print('Fitxer "proposta-torns.csv" generat amb èxit.')