import pandas as pd

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

print("Top 10 Titulaciones y Cursos con más sesiones fuera de su turno:")
print(impacto_grados.head(10).to_string(index=False))

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
