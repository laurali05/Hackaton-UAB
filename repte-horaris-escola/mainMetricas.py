import os
from metricasCalc import (
    load_data, 
    compute_ocupacio_aules, 
    compute_balance_hores_aula, 
    compute_fora_de_torn, 
    compute_pico_matinal, 
    compute_excessos_aforament
)
from Visualizador import plot_all

def main():
    print("=== EXECUTANT ANÀLISI NIVELL 1 (UAB THE HACK 2026) ===")
    
    sessions_path = "paquet/sessions.csv"
    aules_path = "paquet/aules.csv"
    
    if not os.path.exists(sessions_path) or not os.path.exists(aules_path):
        print(f"[!] Error: No es troben els fitxers a 'paquet/'. Revisa la ruta.")
        return
        
    df_sessions, df_aules = load_data(sessions_path, aules_path)
    print(f"[+] Dades carregades: {len(df_sessions)} sessions i {len(df_aules)} aules.")

    print("\n--- CALCULANT MÈTRIQUES OBLIGATÒRIES ---")
    ocupacio = compute_ocupacio_aules(df_sessions, df_aules)
    balance = compute_balance_hores_aula(df_sessions, df_aules)
    fora_torn = compute_fora_de_torn(df_sessions)
    pico = compute_pico_matinal(df_sessions)
    aforament = compute_excessos_aforament(df_sessions, df_aules)

    print("\n=======================================================")
    print("                   5 TROBALLES CLAU")
    print("=======================================================")
    
    # Troballa 1: Pic matinal
    print(f"1. PIC MATINAL: {pico['pico_maxim']} classes simultànies (Capacitat neta: {pico['aules_operatives']} aules).")
    if pico['detall_pico']:
        d = pico['detall_pico']
        print(f"   -> Moment crític: {d.get('data')} ({d.get('dia_setmana')}) a les {d.get('h_ini')} h.")
    
    # Troballa 2: Balanç d'hores-aula
    print(f"2. BALANÇ HORES-AULA (S2): {balance['hores_requerides_sense_aula']:,.1f} hores demanades per les {balance['ordinaries_sense_aula']} sessions ordinàries sense aula.")
    print(f"   -> Oferta disponible de l'aulari (19 aules): {balance['hores_disponibles_aulari']:,.1f} hores.")
    
    # Troballa 3: Sessions fora de torn
    total_fora_torn = fora_torn['n_sessions_fora_torn'].sum()
    top_cohort = fora_torn.iloc[0] if len(fora_torn) > 0 else None
    print(f"3. SESSIONS FORA DE TORN: {total_fora_torn} sessions totals.")
    if top_cohort is not None:
        print(f"   -> Cohort més afectada: {top_cohort['cohort']} amb {top_cohort['n_sessions_fora_torn']} sessions.")
        
    # Troballa 4: Desglossament sessions sense aula
    print(f"4. DESGLOSSAMENT SENSE AULA (S2): Total {balance['total_sessions_sense_aula']} sessions.")
    print(f"   -> {balance['ordinaries_sense_aula']} ordinàries (R5), {balance['plab_sense_aula']} PLAB, {balance['dobles_sense_espai']} dobles.")
    
    # Troballa 5: Excessos d'aforament
    print(f"5. EXCESSOS D'AFORAMENT: {aforament['total_excessos']} sessions superen la capacitat de l'aula.")
    print("=======================================================\n")

    print("[*] Generant figures...")
    plot_all(ocupacio, balance, fora_torn, pico, aforament, output_dir="grafics")
    print("[✔] Procés completat amb èxit!")

if __name__ == "__main__":
    main()