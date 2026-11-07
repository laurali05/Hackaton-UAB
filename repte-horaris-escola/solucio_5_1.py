import os
import pandas as pd

# Funció per trobar el fitxer tant si està a 'paquet/fitxer.csv' com a 'fitxer.csv'
def carregar_csv(nom_fitxer):
    ruta_paquet = os.path.join('paquet', nom_fitxer)
    if os.path.exists(ruta_paquet):
        return pd.read_csv(ruta_paquet)
    elif os.path.exists(nom_fitxer):
        return pd.read_csv(nom_fitxer)
    else:
        raise FileNotFoundError(f"No s'ha trobat el fitxer {nom_fitxer} ni a l'arrel ni a 'paquet/'.")

# 1. Carregar dades
sessions = carregar_csv('sessions.csv')
aules = carregar_csv('aules.csv')
proposta = carregar_csv('proposta_partida.csv')

# 2. Filtrar només el 2n semestre (C/2)
sem2 = sessions[sessions['semestre'] == 'C/2'].copy()

# Aules ordinàries d'aula docent / seminari que podem assignar
aules_ordinaries = aules[
    aules['tipus'].isin(['Aules docents', 'Seminaris'])
].copy()
aules_ordinaries = aules_ordinaries.sort_values(
    by='capacitat', ascending=True
)

# Control d'ocupació en temps real: (aula, dia, h_ini) -> True
ocupacio = {}

# Marquem com a ocupades les aules que ja tenen classe assignada al 2n semestre
for _, row in sem2.iterrows():
    aula_act = row['aula_partida']
    if pd.notna(aula_act):
        ocupacio[(aula_act, row['dia'], row['h_ini'])] = True

aula_base_grup = {}

# 3. Filtrar les sessions que necessiten assignació (sense aula, no PLAB, no sense_espai)
sessions_a_assignar = sem2[
    (sem2['aula_partida'].isna())
    & (sem2['sense_espai'] != 1)
    & (sem2['tipus'] != 'PLAB')
].copy()

# Ordenar per prioritat: de més a menys alumnes
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
        match_aula = aules_ordinaries[aules_ordinaries['aula'] == cand]
        if not match_aula.empty:
            cap = match_aula['capacitat'].values[0]
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
proposta['aula'] = proposta['id_sessio'].map(noves_assignacions).fillna(proposta['aula'])

# Desament a la carpeta arrel i a paquet per seguretat
proposta.to_csv('proposta-aules.csv', index=False)
if os.path.exists('paquet'):
    proposta.to_csv('paquet/proposta-aules.csv', index=False)

print('=== ASSIGNACIÓ COMPLETA ===')
print(f'Sessions assignades amb èxit: {len(noves_assignacions)}')
print('Fitxer "proposta-aules.csv" generat correctament.')