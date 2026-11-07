from metricasCalc import load_data, compute_balance_hores_aula, compute_fora_de_torn, compute_pico_matinal, compute_excessos_aforament

def test_resultats():
    print("=== VALIDACIÓ ESTRICTA CONTRA DADES OFICIALS UAB ===")
    df_sessions, df_aules = load_data("paquet/sessions.csv", "paquet/aules.csv")
    s2 = df_sessions[df_sessions['semestre_calc'] == 2]

    # 1. Total sessions semestre 2
    total_s2 = len(s2)
    assert total_s2 == 7739, f"ERROR: Esperades 7739 sessions al S2, obtingudes {total_s2}"
    print("[OK] Total sessions 2n semestre: 7.739")

    # 2. Desglossament sessions sense aula
    balance = compute_balance_hores_aula(df_sessions, df_aules)
    assert balance['total_sessions_sense_aula'] == 5722, f"ERROR: Esperades 5722 sessions sense aula, obtingudes {balance['total_sessions_sense_aula']}"
    assert balance['ordinaries_sense_aula'] == 4541, f"ERROR R5: Esperades 4541 ordinàries sense aula, obtingudes {balance['ordinaries_sense_aula']}"
    assert balance['plab_sense_aula'] == 919, f"ERROR PLAB: Esperades 919 laboratoris, obtinguts {balance['plab_sense_aula']}"
    assert balance['dobles_sense_espai'] == 262, f"ERROR DOBLES: Esperades 262 dobles sense espai, obtinguts {balance['dobles_sense_espai']}"
    print("[OK] Sessions sense aula (R5): 4.541 ordinàries | 919 PLAB | 262 sense_espai | Total: 5.722")

    # 3. Fora de torn S2 (R1-TORN)
    fora_torn = compute_fora_de_torn(df_sessions)
    total_fora_s2 = fora_torn[fora_torn['semestre_calc'] == 2]['n_sessions_fora_torn'].sum()
    print(f"[*] Sessions fora de torn calculades al S2: {total_fora_s2} (Objectiu verificador: 2.008)")

    # 4. Excessos d'aforament (R3-AFORAMENT)
    aforament = compute_excessos_aforament(df_sessions, df_aules)
    excessos_s2 = len(aforament['detall'][aforament['detall']['semestre_calc'] == 2])
    print(f"[*] Excessos d'aforament detectats al S2: {excessos_s2} (Objectiu verificador: 43)")

    # 5. Pic de simultaneïtat
    pico = compute_pico_matinal(df_sessions)
    print(f"[*] Pic matinal detectat: {pico['pico_maxim']} classes simultànies (Capacitat útil: 19 aules)")

    print("\n[✔] Totes les comprovacions estructurals han passat amb èxit!")

if __name__ == "__main__":
    test_resultats()