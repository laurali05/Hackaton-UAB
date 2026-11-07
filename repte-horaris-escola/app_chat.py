import streamlit as st
import pandas as pd
from openai import OpenAI

# 1. Credenciales DCC UAB
UAB_BASE_URL = "https://dcc-llm-gw.uab.cat/uabthehack/v1"
UAB_API_KEY = "uth-e0e1b8b5b0aea0259dc0ec2bcbe5ee946269671c"  
MODEL_NAME = "ornith"

client = OpenAI(base_url=UAB_BASE_URL, api_key=UAB_API_KEY)

# 2. Cargar datos
@st.cache_data
def cargar_datos():
    df_sess = pd.read_csv('paquet/sessions.csv')
    df_aul = pd.read_csv('paquet/aules.csv')
    return df_sess, df_aul

df_sessions, df_aules = cargar_datos()

# 3. Herramienta de consulta contextual sin alucinaciones
def obtener_contexto(pregunta):
    p = pregunta.lower()
    
    # Consulta de aulas libres o por capacidad
    if any(k in p for k in ['aula', 'aules', 'lliure', 'libre', 'capacitat', 'places']):
        places = 0
        for palabra in p.split():
            if palabra.isdigit():
                places = int(palabra)
                break
        
        # Filtro con la columna exacta 'capacitat'
        filtradas = df_aules[df_aules['capacitat'] >= places]
        cols = ['aula', 'tipus', 'capacitat', 'ordinaria']
        return f"Aules al sistema amb capacitat >= {places} places:\n" + filtradas[cols].head(15).to_string(index=False)
    
    # Consulta por grupo o asignatura
    for palabra in pregunta.replace('/', ' ').split():
        if len(palabra) >= 2:
            coincidencias = df_sessions[df_sessions['grup'].astype(str).str.contains(palabra, case=False, na=False)]
            if not coincidencias.empty:
                cols = ['id_sessio', 'assignatura', 'grup', 'dia', 'h_ini', 'h_fi', 'aula_partida']
                resumen = coincidencias[cols].drop_duplicates(subset=['grup', 'dia', 'h_ini']).head(10)
                return f"Sessions registrades per a '{palabra}':\n" + resumen.to_string(index=False)
                
    return f"Estat del sistema: {len(df_aules)} aules i {len(df_sessions)} sessions registrades."

# 4. Interfaz Streamlit
st.set_page_config(page_title="Assistent Gestió Acadèmica UAB", page_icon="🎓")
st.title("🎓 Assistent de Gestió Acadèmica")
st.caption("Model DCC UAB: Nemotron | Verificació oficial d'horaris i espais")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Fes una consulta (ex: Quines aules tenen més de 80 places? o On té classe TE/21?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    contexto = obtener_contexto(prompt)

    system_prompt = (
        "Ets l'assistent de Gestió Acadèmica de l'Escola d'Enginyeria de la UAB. "
        "Fes servir ÚNICAMENT les dades proporcionades a continuació per respondre. "
        "Si indiques aules, cita el seu codi i la columna 'capacitat'. "
        "Si menciones sessions, cita el seu 'id_sessio'. "
        "No inventis dades."
    )

    with st.chat_message("assistant"):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"DADES DEL SISTEMA:\n{contexto}\n\nPREGUNTA DE L'USUARI: {prompt}"}
            ],
            temperature=0.1
        )
        reply = response.choices[0].message.content
        st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})