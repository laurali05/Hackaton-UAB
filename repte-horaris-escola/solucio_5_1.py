import pandas as pd

# 1. Carregar les dades de sessions i aules
sessions = pd.read_csv('sessions.csv')
aules = pd.read_csv('aules.csv')

# 2. Filtrar només el 2n semestre (C/2)
sem2 = sessions[sessions['semestre'] == 'C/2'].copy()

# Aules ordinàries d'aula docent / seminari que podem assignar
aules_ordinaries = aules[
    aules['tipus'].isin(['Aules docents', 'Seminaris'])
].copy()
aules_ordinaries = aules_ordinaries.sort_values(
    by='capacitat', ascending=True
)

# Diccionari per controlar l'ocupació en temps real: (aula, dia, h_ini) -> True/False
ocupacio = {}

# Marquem com a ocupades les aules que ja tenen classe assignada al 2n semestre
for _, row in sem2.iterrows():
    aula_act = row['aula_partida']
    if pd.notna(aula_act):
        ocupacio[(aula_act, row['dia'], row['h_ini'])] = True

# Diccionari per recordar l'aula assignada a cada grup (per mantenir l'aula base)
aula_base_grup = {}

# 3. Filtrar les sessions que realment necessiten assignació (sense aula, no PLAB, no sense_espai)
sessions_a_assignar = sem2[
    (sem2['aula_partida'].isna())
    & (sem2['sense_espai'] != 1)
    & (sem2['tipus'] != 'PLAB')
].copy()

# Ordre per prioritat: de més a menys alumnes
sessions_a_assignar = sessions_a_assignar.sort_values(
    by='alumnes', ascending=False
)

noves_assignacions = {}

# 4. Assignar aula a cada sessió
for idx, row in sessions_a_assignar.iterrows():
    grup = row['grup']
    dia = row['dia']
    h_ini = row['h_ini']
    alumnes = row['alumnes']

    aula_triada = None

    # Intent A: Reutilitzar l'aula base del mateix grup si està lliure i hi cap
    if grup in aula_base_grup:
        cand = aula_base_grup[grup]
        cap = aules_ordinaries[aules_ordinaries['aula'] == cand][
            'capacitat'
        ].values[0]
        if cap >= alumnes and (cand, dia, h_ini) not in ocupacio:
            aula_triada = cand

    # Intent B: Buscar l'aula més petita on hi càpiga l'alumnat i estigui lliure
    if not aula_triada:
        for _, a_row in aules_ordinaries.iterrows():
            cand = a_row['aula']
            cap = a_row['capacitat']
            if cap >= alumnes and (cand, dia, h_ini) not in ocupacio:
                aula_triada = cand
                break

    # Si trobem aula, la guardem i la marquem com a ocupada
    if aula_triada:
        noves_assignacions[row['id_sessio']] = aula_triada
        ocupacio[(aula_triada, dia, h_ini)] = True
        aula_base_grup[grup] = aula_triada

# 5. Generar el fitxer final proposta-aules.csv per al verificador
proposta = pd.read_csv('proposta_partida.csv')

# Actualitzem les aules de les sessions assignades
proposta['aula'] = proposta['id_sessio'].map(noves_assignacions).fillna(proposta['aula'])

# Guardar el fitxer de sortida exigit pel 5.1
proposta.to_csv('proposta-aules.csv', index=False)

print('=== ASSIGNACIÓ COMPLETA ===')
print(f'Sessions assignades amb èxit: {len(noves_assignacions)}')
print('Fitxer "proposta-aules.csv" generat correctament.')