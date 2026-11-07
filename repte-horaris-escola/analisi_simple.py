import pandas as pd

# 1. Carregar les dades de les sessions
sessions = pd.read_csv('paquet/sessions.csv')

# 2. Filtrar només el 2n semestre (C/2)
sem2 = sessions[sessions['semestre'] == 'C/2']

# ==========================================
# APARTAT A: "Hi cap el matí?"
# ==========================================
print('=== APARTAT A: Hi cap el matí? ===')

# Filtrar sessions que volen matí (excloent PLAB i dobles graus sense espai)
demanda_mati = sem2[
    (sem2['torn_requerit'] == 'mati')
    & (sem2['sense_espai'] != 1)
    & (sem2['tipus'] != 'PLAB')
]

# Treure l'activitat única per comptar el pic màxim en una setmana tipus
activitats_mati = demanda_mati.drop_duplicates(subset=['activitat_id'])
classes_per_franja = activitats_mati.groupby(['dia', 'h_ini']).size()
pico_max = classes_per_franja.max()

print(f'Pic màxim de classes alhora: {pico_max}')
print('Aules ordinàries lliures: 19 (21 aules docents - 2 de reserva)')
if pico_max <= 19:
    print('DIAGNÒSTIC: SÍ hi cap el matí (fregant el límit en franges punta).\n')
else:
    print('DIAGNÒSTIC: NO hi cap el matí.\n')


# ==========================================
# APARTAT B: Radiografia de les sessions sense aula
# ==========================================
print('=== APARTAT B: Sessions sense aula (2n Semestre) ===')

total_sense_aula = sem2['aula_partida'].isna().sum()

# Filtrar les excepcions que NO necessiten aula ordinària
dobles_sense_aula = sem2[
    (sem2['aula_partida'].isna()) & (sem2['sense_espai'] == 1)
].shape[0]

plab_sense_aula = sem2[
    (sem2['aula_partida'].isna())
    & (sem2['sense_espai'] != 1)
    & (sem2['tipus'] == 'PLAB')
].shape[0]

# Restar per obtenir les sessions netes que l'algorisme ha d'assignar
netes_a_assignar = total_sense_aula - dobles_sense_aula - plab_sense_aula

print(f'Total sessions sense aula a les dades: {total_sense_aula}')
print(f' - Dobles graus (sense espai propi): {dobles_sense_aula}')
print(f' - Laboratoris PLAB (van a departament): {plab_sense_aula}')
print(f'---------------------------------------------------')
print(f'SESSIONS NETES A ASSIGNAR: {netes_a_assignar}')