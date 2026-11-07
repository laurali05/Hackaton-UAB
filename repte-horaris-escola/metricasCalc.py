import os
import pandas as pd
import numpy as np

def load_data(sessions_path="paquet/sessions.csv", aules_path="paquet/aules.csv"):
    df_sessions = pd.read_csv(sessions_path)
    df_aules = pd.read_csv(aules_path)
    
    # 1. Estandarizar identificador de aula
    df_aules['codi'] = df_aules['aula']
    
    if 'aula' not in df_sessions.columns and 'aula_partida' in df_sessions.columns:
        df_sessions['aula'] = df_sessions['aula_partida']
    elif 'aula' not in df_sessions.columns:
        df_sessions['aula'] = np.nan

    # 2. Estandarizar cohort (titulación y curso)
    cohort_candidates = ['cohort', 'titulacions_curs', 'titulacio_curs', 'pla_curs']
    found_cohort = next((c for c in cohort_candidates if c in df_sessions.columns), None)
    
    if found_cohort:
        df_sessions['cohort'] = df_sessions[found_cohort].astype(str)
    elif 'titulacio' in df_sessions.columns and 'curs' in df_sessions.columns:
        df_sessions['cohort'] = df_sessions['titulacio'].astype(str) + ":" + df_sessions['curs'].astype(str)
    elif 'pla' in df_sessions.columns and 'curs' in df_sessions.columns:
        df_sessions['cohort'] = df_sessions['pla'].astype(str) + ":" + df_sessions['curs'].astype(str)
    else:
        df_sessions['cohort'] = "Desconegut"

    # 3. Fechas y semestre
    df_sessions['data_dt'] = pd.to_datetime(df_sessions['data'])
    df_sessions['semestre_calc'] = df_sessions['data_dt'].apply(lambda d: 1 if d.month in [9, 10, 11, 12, 1] else 2)
    
    # 4. Duración en horas
    df_sessions['h_ini_num'] = df_sessions['h_ini'].apply(lambda x: int(str(x).split(':')[0]) + int(str(x).split(':')[1])/60.0)
    df_sessions['h_fi_num'] = df_sessions['h_fi'].apply(lambda x: int(str(x).split(':')[0]) + int(str(x).split(':')[1])/60.0)
    df_sessions['durada_h'] = df_sessions['h_fi_num'] - df_sessions['h_ini_num']
    
    dies_map = {0: 'Dilluns', 1: 'Dimarts', 2: 'Dimecres', 3: 'Dijous', 4: 'Divendres', 5: 'Dissabte', 6: 'Diumenge'}
    df_sessions['dia_setmana'] = df_sessions['data_dt'].dt.dayofweek.map(dies_map)
    
    return df_sessions, df_aules

def compute_ocupacio_aules(df_sessions, df_aules):
    if 'ordinaria' in df_aules.columns:
        docents_aules = df_aules[df_aules['ordinaria'] == 1]['aula'].tolist()
    else:
        docents_aules = df_aules[df_aules['tipus'] == 'aula']['aula'].tolist()
        
    total_aules_docents = len(docents_aules) if len(docents_aules) > 0 else 21
    
    doc_sess = df_sessions[df_sessions['aula'].isin(docents_aules)].copy()
    
    ocupacio = doc_sess.groupby(['semestre_calc', 'dia_setmana', 'h_ini'])['aula'].nunique().reset_index()
    ocupacio.rename(columns={'aula': 'aules_ocupades'}, inplace=True)
    ocupacio['total_aules'] = total_aules_docents
    ocupacio['aules_buides'] = ocupacio['total_aules'] - ocupacio['aules_ocupades']
    ocupacio['pct_ocupacio'] = (ocupacio['aules_ocupades'] / ocupacio['total_aules']) * 100
    
    return ocupacio

def compute_balance_hores_aula(df_sessions, df_aules):
    s2 = df_sessions[df_sessions['semestre_calc'] == 2].copy()
    
    sense_aula_mask = s2['aula'].isna() | (s2['aula'] == '') | (s2['aula'] == 'SENSE_AULA')
    sense_aula_total = s2[sense_aula_mask]
    
    demanda_ordinaria = s2[sense_aula_mask & 
                           (s2.get('tipus', '') != 'PLAB') & 
                           (s2.get('sense_espai', 0) != 1)]
    
    hores_requerides = demanda_ordinaria['durada_h'].sum()
    
    dies_lectius = s2['data'].nunique()
    hores_diaries_aulari = 12.5
    aules_disponibles = 19
    hores_disponibles_total = aules_disponibles * hores_diaries_aulari * dies_lectius
    
    return {
        'hores_requerides_sense_aula': hores_requerides,
        'hores_disponibles_aulari': hores_disponibles_total,
        'total_sessions_sense_aula': len(sense_aula_total),
        'ordinaries_sense_aula': len(demanda_ordinaria),
        'plab_sense_aula': len(s2[sense_aula_mask & (s2.get('tipus', '') == 'PLAB')]),
        'dobles_sense_espai': len(s2[sense_aula_mask & (s2.get('sense_espai', 0) == 1)]),  # <-- añadido sense_aula_mask
        'dies_lectius_s2': dies_lectius
    }

def compute_fora_de_torn(df_sessions):
    s2 = df_sessions[df_sessions['semestre_calc'] == 2].copy()
    
    violacions_path = "violacions_partida.csv"
    if os.path.exists(violacions_path):
        df_v = pd.read_csv(violacions_path)
        # Filtrar R1-TORN que cuentan (compta == 1)
        v_torn = df_v[(df_v['regla'] == 'R1-TORN') & (df_v['compta'] == 1)]
        ids_torn = set(v_torn['sessions'].astype(str))
        s2['fora_de_torn'] = s2['id_sessio'].astype(str).isin(ids_torn)
    else:
        def torn_real(h_ini_str):
            parts = str(h_ini_str).split(':')
            h = int(parts[0]) + int(parts[1])/60.0
            return 'mati' if h < 14.5 else 'tarda'
        s2['torn_real'] = s2['h_ini'].apply(torn_real)
        es_fixada = s2.get('fixada', 0).astype(str).str.lower().isin(['1', 'true', 'si', 'sí', '1.0'])
        es_sense_espai = s2.get('sense_espai', 0).astype(str).isin(['1', '1.0', 'True', 'true'])
        s2['fora_de_torn'] = (s2['torn_requerit'] != s2['torn_real']) & (~es_fixada) & (~es_sense_espai)

    fora_torn_df = s2[s2['fora_de_torn']].groupby(['semestre_calc', 'cohort']).size().reset_index(name='n_sessions_fora_torn')
    fora_torn_df = fora_torn_df.sort_values(by='n_sessions_fora_torn', ascending=False)
    return fora_torn_df

def compute_excessos_aforament(df_sessions, df_aules):
    s2 = df_sessions[df_sessions['semestre_calc'] == 2].copy()
    
    violacions_path = "violacions_partida.csv"
    if os.path.exists(violacions_path):
        df_v = pd.read_csv(violacions_path)
        # Filtrar R3-AFORAMENT que cuentan (compta == 1)
        v_afor = df_v[(df_v['regla'] == 'R3-AFORAMENT') & (df_v['compta'] == 1)]
        ids_afor = set(v_afor['sessions'].astype(str))
        
        excessos = s2[s2['id_sessio'].astype(str).isin(ids_afor)].copy()
        excessos = excessos.merge(df_aules[['aula', 'capacitat']], on='aula', how='left')
        excessos['diferencia'] = excessos['alumnes'] - excessos['capacitat']
    else:
        aules_ord = df_aules[df_aules.get('ordinaria', 1).astype(str).isin(['1', '1.0', 'True', 'true'])]['aula'].tolist()
        s2_valides = s2[s2['aula'].isin(aules_ord) & (s2['alumnes'] > 0)].copy()
        df_merged = s2_valides.merge(df_aules[['aula', 'capacitat']], on='aula', how='inner')
        excessos = df_merged[df_merged['alumnes'] > df_merged['capacitat']].copy()
        excessos['diferencia'] = excessos['alumnes'] - excessos['capacitat']

    cols = [c for c in ['id_sessio', 'assignatura', 'grup', 'aula', 'capacitat', 'alumnes', 'diferencia', 'semestre_calc'] if c in excessos.columns]
    return {
        'total_excessos': len(excessos),
        'detall': excessos[cols]
    }
def compute_pico_matinal(df_sessions):
    s2 = df_sessions[df_sessions['semestre_calc'] == 2].copy()
    
    mati_s2 = s2[(s2['torn_requerit'] == 'mati') & 
                 (s2.get('tipus', '') != 'PLAB') & 
                 (s2.get('sense_espai', 0) != 1)].copy()
    
    simultanees = mati_s2.groupby(['data', 'dia_setmana', 'h_ini']).size().reset_index(name='classes_simultanies')
    pico_maxim = simultanees['classes_simultanies'].max() if len(simultanees) > 0 else 0
    pico_row = simultanees.loc[simultanees['classes_simultanies'].idxmax()] if len(simultanees) > 0 else None
    
    return {
        'pico_maxim': pico_maxim,
        'detall_pico': pico_row.to_dict() if pico_row is not None else {},
        'aules_operatives': 19,
        'aules_totals': 21,
        'aules_reserva': 2,
        'simultanees_df': simultanees
    }

