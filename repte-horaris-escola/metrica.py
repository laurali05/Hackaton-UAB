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

# 1. Cargar la tabla de actividades agrupadas que generaste con agrupador.py
df_activitats = pd.read_csv('activitats_agrupades.csv')

# 2. Filtrar actividades del 2º semestre (C/2)
act_s2 = df_activitats[df_activitats['semestre'] == 'C/2'].copy()
print(f"Total actividades cargadas para el 2º semestre: {len(act_s2)}\n")

# ==============================================================================
# APARTADO C: MAPA DE OCUPACIÓN Y VALIDACIÓN DE TIPOS DE ESPACIO
# ==============================================================================
print("=== APARTADO C: MATRIZ DE OCUPACIÓN Y TIPOS DE AULA ===")

# 1. Ocupación de aulas en la propuesta de partida (actividades que sí tienen aula)
act_con_aula = act_s2[act_s2['aula_partida'].notna()].copy()

mapa_ocupacio = pd.crosstab(
    index=act_con_aula['aula_partida'],
    columns=[act_con_aula['dia'], act_con_aula['h_ini']]
)
# Detectar solapamientos directos en la partida (> 1 actividad compartiendo aula y hora)
solapaments = (mapa_ocupacio > 1).sum().sum()
print(f"Franjas con solapamiento de aula en la partida: {solapaments}")

# 2. Validación de tipos de espacio (R3-TIPUS)
aules_df = pd.read_csv('paquet/aules.csv')
act_con_aula = act_con_aula.merge(
    aules_df, 
    left_on='aula_partida', 
    right_on='aula', 
    suffixes=('_act', '_aula')
)

# Buscar clases teóricas/problemas asignadas a laboratorios no permitidos (ej. espina Q6)
incompatibles = act_con_aula[
    (act_con_aula['tipus_act'].isin(['TE', 'PAUL'])) & 
    (act_con_aula['tipus_aula'] == 'PLAB')
]
print(f"Actividades SEM/PAUL asignadas erróneamente a laboratorios PLAB: {len(incompatibles)}")

act_con_aula = act_s2[act_s2['aula_partida'].notna()].copy()

# Encontrar combinaciones de (aula, dia, h_ini) que tienen más de 1 actividad
solapadas_keys = act_con_aula.groupby(['aula_partida', 'dia', 'h_ini']).filter(lambda x: len(x) > 1)

# Ordenar por aula y horario para facilitar su revisión
df_solapamientos = solapadas_keys.sort_values(by=['aula_partida', 'dia', 'h_ini'])

# Seleccionar columnas clave para la inspección
cols_solapamiento = [
    'aula_partida', 'dia', 'h_ini', 'h_fi', 'activitat_id', 
    'codi', 'assignatura', 'tipus', 'grup', 'titulacions_curs', 'docents'
]

# Exportar a CSV
df_solapamientos[cols_solapamiento].to_csv('solapamientos_aulas.csv', index=False)
print(f"'solapamientos_aulas.csv' generado con {len(df_solapamientos)} filas en conflicto.")

# ==============================================================================
# APARTADO D: IMPACTO DEL CAMBIO DE TURNO POR TITULACIÓN Y CURSO
# ==============================================================================
print("\n=== APARTADO D: IMPACTO DEL CAMBIO DE TURNO (R1-TORN) ===")

# 1. Calcular el turno real según hora de inicio (< 14:30 es mañana)
def obtener_turno(h_ini):
    hora = int(str(h_ini).split(':')[0]) if ':' in str(h_ini) else int(h_ini)
    return 'mati' if hora < 14 else 'tarda'

act_s2['torn_real'] = act_s2['h_ini'].apply(obtener_turno)

# 2. Identificar desviaciones entre el turno requerido y el turno real
desviades = act_s2[act_s2['torn_requerit'] != act_s2['torn_real']]

# 3. Agrupar por cohorte/titulación y ordenar de mayor a menor impacto
impacto_grados = desviades.groupby('titulacions_curs').agg(
    activitats_desviades=('activitat_id', 'count'),
    total_sessions_desviades=('total_sessions', 'sum')
).reset_index().sort_values(by='total_sessions_desviades', ascending=False)

print("Titulaciones y Cursos con sesiones fuera de su turno:")
print(impacto_grados.to_string(index=False))

# Filtrar actividades cuyo turno real no coincide con el turno requerido (R1-TORN)
df_desviadas = act_s2[act_s2['torn_requerit'] != act_s2['torn_real']].copy()

# Ordenar por cohorte/titulación y horario
df_desviadas = df_desviadas.sort_values(by=['titulacions_curs', 'dia', 'h_ini'])

# Seleccionar columnas clave para el análisis
cols_desviadas = [
    'activitat_id', 'codi', 'assignatura', 'grup', 'titulacions_curs', 
    'torn_requerit', 'torn_real', 'dia', 'h_ini', 'h_fi', 'total_sessions', 'aula_partida'
]

# Exportar a CSV
df_desviadas[cols_desviadas].to_csv('sesiones_desviadas.csv', index=False)
print(f"'sesiones_desviadas.csv' generado con {len(df_desviadas)} actividades fuera de turno.")
