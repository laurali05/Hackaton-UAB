import pandas as pd

# 1. Cargar el dataset de sesiones
df_sessions = pd.read_csv('paquet/sessions.csv')

# 2. Agrupar las sesiones por activitat_id
# Cada activitat_id representa la misma clase que se repite semanalmente
activitats = df_sessions.groupby('activitat_id').agg(
    # Guardamos la lista de id_sessio que pertenecen a esta actividad
    sessions_ids=('id_sessio', list),
    total_sessions=('id_sessio', 'count'),
    
    # Metadatos docentes y académicos
    codi=('codi', 'first'),
    assignatura=('assignatura', 'first'),
    tipus=('tipus', 'first'),
    grup=('grup', 'first'),
    titulacions_curs=('titulacions_curs', 'first'),
    semestre=('semestre', 'first'),
    
    # Horario recurrente semanal
    dia=('dia', 'first'),
    h_ini=('h_ini', 'first'),
    h_fi=('h_fi', 'first'),
    durada_min=('durada_min', 'first'),
    
    # Restricciones y requisitos
    alumnes=('alumnes', 'max'),
    torn_requerit=('torn_requerit', 'first'),
    fixada=('fixada', 'first'),
    docents=('docents', 'first'),
    sense_espai=('sense_espai', 'first'),
    aula_partida=('aula_partida', 'first')
).reset_index()

print(f"Total sesiones originales: {len(df_sessions)}")
print(f"Total actividades agrupadas: {len(activitats)}")

# 3. Filtrar para el 2º Semestre (el foco principal de las preguntas 5.1 a 5.4)
activitats_s2 = activitats[activitats['semestre'] == 'C/2'].copy()
print(f"Actividades para el 2º semestre: {len(activitats_s2)}")

# Guardar la tabla agrupada para trabajar con vuestro algoritmo / solver
activitats.to_csv('activitats_agrupades.csv', index=False)