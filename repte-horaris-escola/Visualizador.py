import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

def plot_all(ocupacio_df, balance_dict, fora_torn_df, pico_dict, aforament_dict, output_dir="grafics"):
    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid")
    
    # 1. HEATMAP DE OCUPACIÓN (2n Semestre)
    plt.figure(figsize=(10, 6))
    s2_ocup = ocupacio_df[ocupacio_df['semestre_calc'] == 2]
    pivot_heat = s2_ocup.pivot_table(index='h_ini', columns='dia_setmana', values='aules_ocupades', aggfunc='mean').fillna(0)
    cols_order = [d for d in ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres'] if d in pivot_heat.columns]
    pivot_heat = pivot_heat[cols_order]
    
    sns.heatmap(pivot_heat, annot=True, fmt=".1f", cmap="YlOrRd", cbar_kws={'label': 'Aules Ocupades'})
    plt.title("Ocupació Mitjana d'Aules per Franja i Dia (2n Semestre)")
    plt.xlabel("Dia de la Setmana")
    plt.ylabel("Franja Horària (h_ini)")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/1_heatmap_ocupacio_s2.png", dpi=300)
    plt.close()
    
    # 2. PICO DE SIMULTANEIDAD MATINAL VS CAPACIDAD
    plt.figure(figsize=(10, 5))
    sim_df = pico_dict['simultanees_df']
    sim_agg = sim_df.groupby('h_ini')['classes_simultanies'].max().reset_index()
    
    sns.barplot(data=sim_agg, x='h_ini', y='classes_simultanies', color='#1f77b4')
    plt.axhline(19, color='red', linestyle='--', linewidth=2, label='Capacitat màxima neta (19 aules)')
    plt.axhline(15, color='orange', linestyle=':', linewidth=2, label="Pic partida (15 classes)")
    plt.title(f"Pic de Simultaneïtat al Matí (1r i 2n) - Màxim: {pico_dict['pico_maxim']} classes")
    plt.xlabel("Franja Horària (h_ini)")
    plt.ylabel("Classes Simultànies")
    plt.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(f"{output_dir}/2_pico_matinal_vs_capacitat.png", dpi=300)
    plt.close()
    
    # 3. SESIONES FUERA DE TURNO POR COHORT (Top 10)
    plt.figure(figsize=(11, 5))
    s2_fora = fora_torn_df[fora_torn_df['semestre_calc'] == 2].head(10)
    
    sns.barplot(data=s2_fora, x='cohort', y='n_sessions_fora_torn', palette='mako')
    plt.title("Top 10 Cohorts amb més Sessions Fora de Torn (2n Semestre)")
    plt.xlabel("Cohort (Titulació i Curs)")
    plt.ylabel("Nº de Sessions a Reubicar")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/3_fora_de_torn_top_cohorts.png", dpi=300)
    plt.close()
    
    # 4. BALANCE DE HORAS-AULA
    plt.figure(figsize=(7, 5))
    categories = ['Hores Demanades\n(Sessions Sense Aula)', 'Hores Disponibles\n(Aulari 19 Aules)']
    values = [balance_dict['hores_requerides_sense_aula'], balance_dict['hores_disponibles_aulari']]
    
    bars = plt.bar(categories, values, color=['#d95f02', '#2ca02c'], width=0.5)
    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., h + 200, f"{h:,.0f} h", ha='center', va='bottom', fontweight='bold')
        
    plt.title("Balanç d'Hores-Aula (2n Semestre)")
    plt.ylabel("Hores")
    plt.ylim(0, max(values) * 1.15)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/4_balanc_hores_aula.png", dpi=300)
    plt.close()
    
    # 5. EXCESOS DE AFORO (ALUMNES VS CAPACITAT)
    plt.figure(figsize=(9, 6))
    df_ex = aforament_dict['detall']

    if len(df_ex) > 0:
        # Agrupamos para contar cuántas sesiones idénticas hay en cada coordenada
        conteo = df_ex.groupby(['capacitat', 'alumnes', 'aula']).size().reset_index(name='n_sessions')
        
        # Dibujamos puntos con tamaño proporcional al número de sesiones
        scatter = plt.scatter(
            conteo['capacitat'], 
            conteo['alumnes'], 
            s=conteo['n_sessions'] * 15,  # tamaño proporcional
            color='#e7298a', 
            alpha=0.6, 
            edgecolors='black',
            linewidth=1.5
        )
        
        # Añadimos etiquetas con el número de sesiones y el aula
        for _, row in conteo.iterrows():
            plt.annotate(
                f"{row['n_sessions']} sessions\n(Aula {row['aula']})", 
                xy=(row['capacitat'], row['alumnes']),
                xytext=(row['capacitat'] - 12, row['alumnes'] + 3),
                fontsize=10,
                fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#e7298a", lw=1)
            )
            
        lims = [0, max(df_ex['alumnes'].max(), df_ex['capacitat'].max()) + 15]
        plt.plot(lims, lims, '--k', alpha=0.75, zorder=0, label='Límit aforament (y = x)')
        plt.xlim(80, lims[1])
        plt.ylim(80, lims[1])
        plt.title(f"Sessions amb Excés d'Aforament (Total: {aforament_dict['total_excessos']} sessions en 2 grups)")
        plt.xlabel("Capacitat de l'Aula Assignada (places)")
        plt.ylabel("Alumnes Matriculats")
        plt.legend(loc='upper left')
    else:
        plt.text(0.5, 0.5, "Sense excessos d'aforament", ha='center', va='center')
        plt.title("Excessos d'Aforament")

    plt.tight_layout()
    plt.savefig(f"{output_dir}/5_excessos_aforament.png", dpi=300)
    plt.close()