import os
import json
import duckdb
import streamlit as st
from openai import OpenAI
from horaris.check import avalua

# Configuración de página
st.set_page_config(page_title="Assistent Gestió Acadèmica - UAB", layout="wide")
st.title("Assistent d'Horaris i Espais - Escola d'Enginyeria UAB")

# 1. Configuración del cliente LLM (servidor DCC de la UAB)
client = OpenAI(
    base_url="https://dcc-llm-gw.uab.cat/uabthehack/v1",  # Cambiar a la IP/puerto del hack
    api_key="uth-e0e1b8b5b0aea0259dc0ec2bcbe5ee946269671c"
)

# 2. Conexión SQL en memoria con DuckDB
@st.cache_resource
def init_db():
    con = duckdb.connect(database=':memory:')
    con.execute("CREATE VIEW sessions AS SELECT * FROM 'paquet/sessions.csv'")
    con.execute("CREATE VIEW aules AS SELECT * FROM 'paquet/aules.csv'")
    return con

con = init_db()

# Herramientas del sistema
def consultar_horari(query_sql: str):
    try:
        if not query_sql.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Només es permeten consultes SELECT."})
        df = con.execute(query_sql).fetchdf()
        return df.head(15).to_json(orient="records")
    except Exception as e:
        return json.dumps({"error": str(e)})

def verificar_proposta(ruta_csv: str, semestre: int = 2):
    try:
        informe = avalua(ruta_csv, semestre=semestre)
        return json.dumps({
            "valida": informe.get("valida", False),
            "incompliments": informe.get("incompliments", {}),
            "resum": informe.get("resum", {})
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

def generar_registre_canvi(id_sessio: str, aula_nova: str, dia_nou: str, h_ini_nova: str, motiu: str):
    q = f"SELECT id_sessio, assignatura, grup, aula, dia, h_ini, docent FROM sessions WHERE id_sessio = '{id_sessio}'"
    info = con.execute(q).fetchdf().to_dict(orient="records")
    if not info:
        return json.dumps({"error": f"No s'ha trobat la sessió {id_sessio}"})
    s = info[0]
    return json.dumps({
        "id_sessio": id_sessio,
        "assignatura": s["assignatura"],
        "grup": s["grup"],
        "origen": f"{s['dia']} {s['h_ini']} (Aula {s['aula']})",
        "desti": f"{dia_nou} {h_ini_nova} (Aula {aula_nova})",
        "motiu": motiu,
        "afecta_a": f"Docent {s['docent']} i estudiants del grup {s['grup']}"
    }, ensure_ascii=False)

tools = [
    {
        "type": "function",
        "function": {
            "name": "consultar_horari",
            "description": "Executa SQL SELECT a sessions o aules. Retorna columnes clau com id_sessio, grup, aula, dia, h_ini.",
            "parameters": {
                "type": "object",
                "properties": {"query_sql": {"type": "string"}},
                "required": ["query_sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verificar_proposta",
            "description": "Comprova un fitxer CSV de proposta amb el verificador oficial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_csv": {"type": "string"},
                    "semestre": {"type": "integer", "default": 2}
                },
                "required": ["ruta_csv"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_registre_canvi",
            "description": "Genera el registre formal de canvi per a un imprevist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_sessio": {"type": "string"},
                    "aula_nova": {"type": "string"},
                    "dia_nou": {"type": "string"},
                    "h_ini_nova": {"type": "string"},
                    "motiu": {"type": "string"}
                },
                "required": ["id_sessio", "aula_nova", "dia_nou", "h_ini_nova", "motiu"]
            }
        }
    }
]

SYSTEM_PROMPT = """Ets l'Assistent d'Intel·ligència Artificial de Gestió Acadèmica de l'Escola d'Enginyeria de la UAB (Repte d'Horaris i Espais 2027-28).
La teva missió és resoldre consultes sobre l'horari, auditar propostes amb el verificador oficial, gestionar imprevistos i generar registres de canvis i avisos formals de màxima fidelitat.

==================================================
1. REGLA SUPREMA DE FIDELITAT (TOLERÀNCIA ZERO AMB ALUCINACIONS)
==================================================
- TOTA dada sobre hores, aules, capacitats, docents o disponibilitat HA DE PROVENIR exclusivament dels fitxers del paquet (sessions.csv, aules.csv, calendari.csv) o de la sortida de les teves eines (SQL / verificador).
- NUNCA inventis un id_sessio, una aula buida, un aforament o un estat d'ocupació. Una aula mai està lliure a menys que s'hagi comprovat que cap sessió hi té lloc en aquella franja.
- CITA OBLIGATÒRIA: Tota afirmació sobre una classe o assignació ha d'anar acompanyada del seu `id_sessio` explícit (p. ex., S04512) perquè el jurat o Gestió Acadèmica pugui contrastar-ho al CSV en menys de 3 segons.

==================================================
2. CONEIXEMENT CRÍTIC DEL MODEL I REGLAMENT (REGLIS R1 A R8)
==================================================
Quan analitzis consultes o sortides del verificador, aplica amb exactitud aquests criteris:
- R1-TORN & R1-FIXADA:
  * Torn de matí: 8:30 a 14:30 (1r i 2n de tots els graus).
  * Torn de tarda: 14:30 a 21:00 (3r, 4t, dobles titulacions i màsters).
  * FIXADES: Els grups de GEI i GEET+GEST de 1r i 2n NO ES TOQUEN.
  * Dobles titulacions (grups que comencen per 5: TE/51, PAUL/511): van a la tarda i tenen sense_espai = 1 (no necessiten ni demanen aula).
- R2-FINESTRA & R2-CALENDARI:
  * Horaris permesos de 8:30 a 21:00. Una sessió que comenci abans de les 14:30 i acabi després infringeix la regla.
  * Dies lectius segons calendari.csv (respectar festius, MEMEnginy del 18/03/2027, festa de l'Escola i setmanes d'avaluació intrasemestral).
- R3-AULA, TIPUS & AFORAMENT:
  * L'aforament es valida contra la columna alumnes.
  * Teoria (TE) MAI pot anar a un laboratori.
  * Les sessions de les aules J s'han de reubicar a l'aulari. B3/0021 i QC/1082 es mantenen.
- R4-SOLAPAMENTS:
  * Cap conflicte simultani d'aula, docent o cohort (alumnat). Una TE i un PAUL del mateix grup o subgrup no poden coincidir.
  * R4-PLAB: Una TE o PAUL no pot coincidir temporalment amb un PLAB de la mateixa assignatura.
- R6-MATEIX PASSADÍS (INDICADOR):
  * "Mateix passadís" = mateixa espina i mateixa planta (indicada pel primer dígit del número d'aula; p. ex., Q4/0011 és planta 0; Q4/1013 és planta 1).
- R7-PLAB: Els laboratoris pràctics no es toquen ni en horari ni en espai.
- R8-RESERVA: En tot moment (de 8:30 a 21:00) han de quedar com a mínim 2 aules ordinàries lliures a cada franja horària.

==================================================
3. GESTIÓ D'IMPREVISTOS I PROTOCOL D'AVISOS (NIVELL 5.3)
==================================================
Davant de contingències:
1. Proposa la reubicació o recuperació minimitzant canvis respecte a la referència.
2. Comprova la disponibilitat sense trencar aforament ni la reserva de 2 aules (R8).
3. Redacta SEMPRE l'entrada formal per al Registre de Canvis de l'Escola amb aquesta estructura:
   - id_sessio: [Identificador exacte]
   - Assignatura i Grup: [Codi / Nom / Grup]
   - Origen: [Dia, franja i aula originals]
   - Destí: [Dia, franja i aula nous]
   - Motiu: [Raó tècnica de la reubicació]
   - Col·lectiu afectat: [Docent responsable i grup d'estudiants]
   - Data de l'avís: [Data corresponent]
4. Genera un esborrany breu, clar i professional de comunicat per a la comunitat afectada.

==================================================
4. FORMAT DE LES RESPOSTES
==================================================
- Idioma: Català (o castellà si l'usuari ho demana).
- Resposta directa en les primeres dues línies.
- Taula o dades amb id_sessio per a comprovació immediata.
"""

# Inicializar historial de chat
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Mostrar mensajes previos
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# Entrada de usuario
if prompt := st.chat_input("Fes una consulta a Gestió Acadèmica (ex: On té classe el grup 81 dimarts?)..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # 1. Llamada inicial al modelo con tools
        response = client.chat.completions.create(
            model="ornith",
            messages=st.session_state.messages,
            tools=tools,
            tool_choice="auto"
        )
        msg = response.choices[0].message

        # 2. Si el modelo pide invocar herramientas
        if msg.tool_calls:
            st.session_state.messages.append(msg)
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                if func_name == "consultar_horari":
                    res = consultar_horari(args.get("query_sql", ""))
                elif func_name == "verificar_proposta":
                    res = verificar_proposta(args.get("ruta_csv", ""), args.get("semestre", 2))
                elif func_name == "generar_registre_canvi":
                    res = generar_registre_canvi(
                        args.get("id_sessio", ""), args.get("aula_nova", ""),
                        args.get("dia_nou", ""), args.get("h_ini_nova", ""),
                        args.get("motiu", "")
                    )
                else:
                    res = json.dumps({"error": "Eina desconeguda"})

                st.session_state.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res
                })

            # Llamada final con las respuestas de las funciones
            segona_resposta = client.chat.completions.create(
                model="ornith",
                messages=st.session_state.messages
            )
            final_content = segona_resposta.choices[0].message.content
        else:
            final_content = msg.content

        message_placeholder.markdown(final_content)
        st.session_state.messages.append({"role": "assistant", "content": final_content})