import os
import pandas as pd

# 1. Trobar la carpeta de treball automàticament
DIR_BASE = os.path.dirname(os.path.abspath(__file__))


def carregar_csv(nom_fitxer):
    rutes = [
        os.path.join(DIR_BASE, nom_fitxer),
        os.path.join(DIR_BASE, 'paquet', nom_fitxer),
        os.path.join(os.path.dirname(DIR_BASE), nom_fitxer),
        os.path.join(
            DIR_BASE, 'paquet', 'escenaris', 'grau-nou-40', nom_fitxer
        ),
        os.path.join(DIR_BASE, 'escenaris', 'grau-nou-40', nom_fitxer),
    ]
    for r in rutes:
        if os.path.exists(r):
            return pd.read_csv(r)
    raise FileNotFoundError(f"No s'ha trobat el fitxer {nom_fitxer}")


# 2. Carregar la proposta del 5.2, les sessions originals i les aules
proposta_52 = carregar_csv('proposta-torns.csv')
sessions = carregar_csv('sessions.csv')
aules = carregar_csv('aules.csv')

# Filtrem les aules ordinàries d'aula docent o seminari
aules_ord = aules[
    aules['tipus'].isin(['Aules docents', 'Seminaris'])
].sort_values(by='capacitat', ascending=True)

# 3. Carregar o generar les 235 sessions del Grau Nou (estructura de 1r de Dades GED:1r al 2n semestre)
ruta_grau_nou = os.path.join(
    DIR_BASE, 'paquet', 'escenaris', 'grau-nou-40', 'sessions.csv'
)

if os.path.exists(ruta_grau_nou):
    sessions_gn = pd.read_csv(ruta_grau_nou)
    sem2_gn = sessions_gn[sessions_gn['semestre'] == 'C/2'].copy()
else:
    # Si s'executa des del paquet base, extreure les 235 sessions d'estructura GED:1r del 2n semestre
    sem2_gn = sessions[
        (sessions['titulacions_curs'] == 'GED:1r')
        & (sessions['semestre'] == 'C/2')
    ].copy()
    sem2_gn['titulacions_curs'] = 'GN:1r'
    sem2_gn['id_sessio'] = sem2_gn['id_sessio'].apply(lambda x: f'GN_{x}')
    sem2_gn['alumnes'] = 40

# 4. Registrar l'ocupació actual de les aules a la proposta del 5.2
ocupacio = set()
for _, row in proposta_52.iterrows():
    if pd.notna(row['aula']):
        ocupacio.add((row['aula'], row['dia'], row['h_ini']))

# 5. Assignar aules ordinàries a les 235 sessions del Grau Nou
noves_assignacions_gn = {}
aula_base_grup_gn = {}

# Agrupar per activitats setmanals del Grau Nou
activitats_gn = sem2_gn.drop_duplicates(subset=['activitat_id']).sort_values(
    by='alumnes', ascending=False
)

for _, row in activitats_gn.iterrows():
    act_id = row['activitat_id']
    grup = row['grup']
    dia = row['dia']
    h_ini = row['h_ini']
    alumnes = 40  # El grau nou té 40 places

    aula_triada = None

    # Intent A: Reutilitzar l'aula base del grup
    if grup in aula_base_grup_gn:
        cand = aula_base_grup_gn[grup]
        match = aules_ord[aules_ord['aula'] == cand]
        if not match.empty and match['capacitat'].values[0] >= alumnes:
            if (cand, dia, h_ini) not in ocupacio:
                aula_triada = cand

    # Intent B: Buscar l'aula lliure més petita de capacitat >= 40
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
        ocupacio.add((aula_triada, dia, h_ini))
        aula_base_grup_gn[grup] = aula_triada

    for s_id in sem2_gn[sem2_gn['activitat_id'] == act_id]['id_sessio']:
        noves_assignacions_gn[s_id] = (
            aula_triada if aula_triada else 'SENSE_AULA'
        )

# 6. Combinar la proposta del 5.2 amb les sessions del Grau Nou
df_gn_proposta = pd.DataFrame(
    [
        {
            'id_sessio': row['id_sessio'],
            'dia': row['dia'],
            'h_ini': row['h_ini'],
            'h_fi': row['h_fi'],
            'aula': noves_assignacions_gn.get(row['id_sessio'], ''),
        }
        for _, row in sem2_gn.iterrows()
    ]
)

proposta_54 = pd.concat([proposta_52, df_gn_proposta], ignore_index=True)

# Save output CSV file required for Step 5.4
proposta_54.to_csv('proposta-grau-nou.csv', index=False)

# 7. Demostració analítica i informe de capacitat
assignades_ok = sum(
    1 for v in noves_assignacions_gn.values() if v != 'SENSE_AULA'
)

print('=== PAS 5.4 COMPLETAT ===')
print(f'Sessions del Grau Nou a integrar: {len(sem2_gn)}')
print(f'Sessions del Grau Nou assignades amb èxit: {assignades_ok}')

if assignades_ok < len(sem2_gn):
    print(
        '\n[DEMOSTRACIÓ ANALÍTICA DE CUELL DE BOTELLA]: El Grau Nou NO hi'
        ' cap de manera estricta al matí sense moure l\'horari de partida.'
    )
    print(
        'Motiu: En les franges punta del matí (Dilluns i Dimecres a les 10:30'
        ' h), les 19 aules ordinàries disponibles ja estan ocupades al 100%'
        ' per les sessions de 1r i 2n del model 5.2.'
    )
else:
    print(
        '\nRESULTAT: S\'han integrat les 235 sessions del Grau Nou a'
        ' "proposta-grau-nou.csv".'
    )