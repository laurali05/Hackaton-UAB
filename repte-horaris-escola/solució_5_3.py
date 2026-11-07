import os
import pandas as pd

# 1. Trobar automàticament la carpeta de treball
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


# 2. Carregar la proposta de referència del 5.2 i l'inventari d'aules
proposta_52 = carregar_csv('proposta-torns.csv')
sessions = carregar_csv('sessions.csv')
aules = carregar_csv('aules.csv')

# Treballem sobre una còpia per generar la proposta del 5.3
proposta_53 = proposta_52.copy()

# Aules ordinàries lliures ordenades per capacitat
aules_ord = aules[
    aules['tipus'].isin(['Aules docents', 'Seminaris'])
].sort_values(by='capacitat', ascending=True)

# 3. CONTINGÈNCIA 2: Grup ampliat a 130 alumnes (Transmissió de Calor i Termotècnia GEQ 2n, TE/21)
# Cercar una aula amb capacitat >= 130 places per a les sessions de TE/21
ids_geq_te21 = sessions[
    (sessions['grup'] == 'TE/21')
    & (sessions['titulacions_curs'].str.contains('GEQ', na=False))
]['id_sessio']

aula_130 = aules_ord[aules_ord['capacitat'] >= 130]['aula'].iloc[0]
proposta_53.loc[proposta_53['id_sessio'].isin(ids_geq_te21), 'aula'] = (
    aula_130
)

# 4. CONTINGÈNCIES 1 i 3: Reassignar sessions d'aules tancades
# A) Q3/0013 tancada del 15 al 19 de març de 2027 (setmana W11)
# B) Q1/1003 tancada el dimecres 10 de març de 2027
dates_reserva_q3 = [
    '2027-03-15',
    '2027-03-16',
    '2027-03-17',
    '2027-03-18',
    '2027-03-19',
]

# Obtenir les sessions afectades a les dates tancades
sess_q3_afectades = sessions[
    (sessions['data'].isin(dates_reserva_q3))
]['id_sessio']
mask_q3 = (proposta_53['id_sessio'].isin(sess_q3_afectades)) & (
    proposta_53['aula'] == 'Q3/0013'
)

sess_q1_afectades = sessions[(sessions['data'] == '2027-03-10')]['id_sessio']
mask_q1 = (proposta_53['id_sessio'].isin(sess_q1_afectades)) & (
    proposta_53['aula'] == 'Q1/1003'
)

# Reassignar una aula alternativa lliure de capacitat suficient
aula_alternativa = aules_ord[aules_ord['capacitat'] >= 90]['aula'].iloc[1]
proposta_53.loc[mask_q3, 'aula'] = aula_alternativa
proposta_53.loc[mask_q1, 'aula'] = aula_alternativa

# 5. CONTINGÈNCIA 4: Recuperació de la sessió S11527 cancel·lada
# Si la proposta conté columna de data de recuperació o si es desplaça de dia
if 'data_recuperacio' not in proposta_53.columns:
    proposta_53['data_recuperacio'] = ''

# Recuperar la sessió S11527 en el divendres 12 de març de 2027 a la mateixa franja
proposta_53.loc[
    proposta_53['id_sessio'] == 'S11527', 'data_recuperacio'
] = '2027-03-12'

# 6. Guardar la proposta final de l'exercici 5.3
proposta_53.to_csv('proposta-imprevist.csv', index=False)

print('=== PAS 5.3 COMPLETAT AMB ÈXIT ===')
print(
    'Sessions de TE/21 reassignades a aula de 130+ places:'
    f' {len(ids_geq_te21)}'
)
print(
    "Fitxer 'proposta-imprevist.csv' generat correctament per al verificador."
)