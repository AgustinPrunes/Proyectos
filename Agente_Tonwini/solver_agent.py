import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
import re
import chromadb
import networkx as nx

# =========================================================================
# HIPERPARÁMETROS DEL ACTOR-CRÍTICO Y SEGURIDAD
# =========================================================================
MAX_INTENTOS_ACTOR_CRITICO = 3

# CORTACIRCUITOS DE PRODUCCIÓN: Evita el secuestro financiero / drenaje de tokens por caídas de red
MAX_RETRIES_API = 5
# =========================================================================

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")
client = genai.Client(api_key=api_key)

def limpiar_nombre_carpeta(texto):
    texto_limpio = re.sub(r'[^a-zA-Z0-9]', '_', texto)
    texto_limpio = re.sub(r'_+', '_', texto_limpio)
    return texto_limpio.strip('_')

def buscar_contexto(query, n_results=5):
    """Consulta el Cerebro Híbrido (Vectorial + Semántico) para resolver el problema."""
    texto_vectorial = ""
    try:
        cliente_chroma = chromadb.PersistentClient(path="chroma_db")
        coleccion = cliente_chroma.get_collection(name="conocimiento_fisica")
        resultados = coleccion.query(query_texts=[query], n_results=n_results)
        
        if resultados and resultados['documents'] and resultados['documents'][0]:
            texto_vectorial = "\n\n...[salto]...\n\n".join(resultados['documents'][0])
    except Exception:
        pass

    texto_grafo = ""
    try:
        ruta_grafo = "conocimiento_grafo.json"
        if os.path.exists(ruta_grafo):
            with open(ruta_grafo, 'r', encoding='utf-8') as f:
                data = json.load(f)
                G = nx.node_link_graph(data)
            
            query_lower = query.lower()
            nodos_encontrados = [n for n in G.nodes() if isinstance(n, str) and len(n) > 4 and n.lower() in query_lower]
            
            conexiones = []
            for nodo in nodos_encontrados[:10]:  
                for destino in G.successors(nodo):
                    rel = G.edges[nodo, destino].get('relacion', 'se relaciona con')
                    conexiones.append(f"[{nodo}] --({rel})--> [{destino}]")
                for origen in G.predecessors(nodo):
                    rel = G.edges[origen, nodo].get('relacion', 'se relaciona con')
                    conexiones.append(f"[{origen}] --({nodo})--> [{nodo}]")

            if conexiones:
                conexiones_unicas = list(set(conexiones))[:20] 
                texto_grafo = "\n".join(conexiones_unicas)
    except Exception:
        pass

    contexto_final = ""
    if texto_vectorial:
        contexto_final += "--- FRAGMENTOS VECTORIALES (MACRO-CONTEXTO) ---\n" + texto_vectorial + "\n\n"
    if texto_grafo:
        contexto_final += "--- MAPA LÓGICO DEL GRAFO ---\n" + texto_grafo + "\n\n"
        
    return contexto_final.strip()

def auditar_contexto_rag(problema, contexto_bruto):
    """Agente Portero: Verifica si el macro-contexto recuperado es útil para resolver el problema."""
    if not contexto_bruto.strip():
        return False
        
    print(f"   🛡️ Agente Portero: Auditando relevancia de la bibliografía recuperada...")
    system_instruction = """Eres un Juez Auditor de Contexto Académico.
    Tu tarea es leer el ENUNCIADO de un problema/pregunta y el CONTEXTO RECUPERADO de una base de datos.
    Evalúa si el contexto pertenece EXACTAMENTE a la misma disciplina y si aporta fórmulas, teoría o datos útiles para resolver la pregunta.
    Si el contexto es irrelevante, pertenece a otra rama o está contaminado, DEBES rechazarlo.
    Responde ÚNICAMENTE con la palabra 'APROBADO' o 'RECHAZADO'."""
    
    user_prompt = f"ENUNCIADO DEL PROBLEMA:\n{problema}\n\nCONTEXTO RECUPERADO:\n{contexto_bruto}"
    
    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0, 
            )
        )
        decision = response.text.strip().upper()
        if "APROBADO" in decision:
            print("      ✅ Veredicto: APROBADO. El macro-contexto se usará para la resolución.")
            return True
        else:
            print("      ❌ Veredicto: RECHAZADO. El macro-contexto es inútil o está fuera de dominio. El Agente usará su memoria interna.")
            return False
    except Exception as e:
        print(f"      ⚠️ Error en el Agente Portero ({e}). Rechazando bibliografía por seguridad.")
        return False

def limpiar_markdown_latex(texto):
    contenido = texto.strip()
    marca_inicio = chr(96) * 3 + 'latex'
    marca_fin = chr(96) * 3
    if contenido.startswith(marca_inicio): contenido = contenido[len(marca_inicio):]
    if contenido.endswith(marca_fin): contenido = contenido[:-len(marca_fin)]
    if contenido.startswith(chr(96)*3): contenido = contenido[3:]
    return contenido.strip()

def generar_resolucion_actor(problema_completo, contexto_rag, memoria_corto_plazo, critica_previa=None):
    """Agente Actor: Genera la resolución paso a paso aplicando la Directriz Camaleónica."""
    
    bloque_critica = ""
    if critica_previa:
        bloque_critica = f"\n--- FEEDBACK DEL CRÍTICO EN INTENTO ANTERIOR ---\nEl Crítico encontró fallos en tu resolución anterior. Corrige obligatoriamente lo siguiente:\n{critica_previa}\n-------------------------------------------------\n"

    system_instruction = """Eres un Agente Resolutor (Actor) Universitario de élite y de naturaleza puramente agnóstica.
    Tu objetivo es leer un enunciado y generar la respuesta pedagógica definitiva en código LaTeX puro.

    DIRECTRIZ CAMALEÓNICA (ADAPTACIÓN ESTRICTA AL DOMINIO):
    Lee el enunciado y detecta de inmediato la disciplina a la que pertenece (Filosofía, Literatura, Física Cuántica, Derecho, Medicina, etc.).
    - Si la pregunta es TEÓRICA, HUMANISTA, LEGAL O CLÍNICA: Responde con ensayo, exégesis, prosa académica y viñetas lógicas. Tienes ESTRICTAMENTE PROHIBIDO inventar variables espurias (ej. "Sea X la ética"), usar el entorno de ecuaciones (\\begin{align*}) o "seudo-matematizar" conceptos que son puramente cualitativos. Escribe con la jerga erudita y nativa de su disciplina.
    - Si la pregunta es MATEMÁTICA, INGENIERIL O EXACTA: Eres un científico. Aplica rigor analítico, deriva las ecuaciones paso a paso obligatoriamente usando el entorno \\begin{align*} ... \\end{align*} con saltos de línea explícitos (\\\\) para cálculos largos. 

    REGLAS DE FORMATO Y ESTILO:
    1. NO uses \\begin{document} ni \\documentclass. No copies el enunciado de nuevo en tu respuesta.
    2. Ve directo a la solución/respuesta con un desarrollo extenso y riguroso.
    3. Si estás respondiendo un inciso que depende de un inciso anterior, USA la Memoria a Corto Plazo provista para arrastrar los resultados matemáticos o argumentativos.

    ESTRUCTURA OBLIGATORIA DE TU RESPUESTA:
    <razonamiento>
    (Piensa paso a paso. ¿De qué disciplina es esto? ¿Necesito ecuaciones reales o solo ensayo crítico? ¿Cómo incorporo el feedback del crítico si lo hay? Resuelve el problema aquí mentalmente)
    </razonamiento>
    ```latex
    (Tu respuesta final en LaTeX crudo)
    ```"""

    user_prompt = f"""
    ENUNCIADO A RESOLVER:
    {problema_completo}
    
    MEMORIA DE INCISOS ANTERIORES (CORTA PLAZO):
    {memoria_corto_plazo if memoria_corto_plazo.strip() else "[Este es el primer inciso o una pregunta única]"}
    
    CONTEXTO DE LA BIBLIOGRAFÍA RAG:
    {contexto_rag if contexto_rag.strip() else "[No hay contexto en RAG. Confía en tu conocimiento experto de la disciplina]"}
    
    {bloque_critica}
    
    Resuelve el problema obedeciendo la Directriz Camaleónica:
    """

    intentos_red = 0
    while intentos_red < MAX_RETRIES_API:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite', 
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                )
            )
            texto_crudo = respuesta.text.strip()
            
            match_pensamiento = re.search(r'<razonamiento>(.*?)</razonamiento>', texto_crudo, re.DOTALL | re.IGNORECASE)
            pensamiento = match_pensamiento.group(1).strip() if match_pensamiento else "No se detectó razonamiento."
            
            contenido = re.sub(r'<razonamiento>.*?</razonamiento>', '', texto_crudo, flags=re.DOTALL).strip()
            
            return limpiar_markdown_latex(contenido), pensamiento
            
        except Exception as e:
            intentos_red += 1
            if intentos_red >= MAX_RETRIES_API:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico en el Actor tras {MAX_RETRIES_API} intentos de red.")
                raise RuntimeError(f"Fallo Actor: {e}")
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"      ⏳ Límite de API en Actor. Intento {intentos_red}/{MAX_RETRIES_API}. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"      🔥 Servidor saturado (503). Intento {intentos_red}/{MAX_RETRIES_API}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"      ⚠️ Error en Actor. Intento {intentos_red}/{MAX_RETRIES_API}. Reintentando en 15s... ({e})")
                time.sleep(15)

def evaluar_resolucion_critico(enunciado, resolucion_actor):
    """Agente Crítico: Audita el rigor y la adaptación al dominio de la respuesta del Actor."""
    
    system_instruction = """Eres un Profesor Revisor (Crítico) Universitario Implacable.
    Tu trabajo es evaluar la resolución propuesta por tu colega (Actor) frente a un enunciado.
    
    DIRECTRIZ CAMALEÓNICA DE REVISIÓN:
    Debes ser justo y adaptarte a la disciplina:
    1. Si la pregunta es de Letras, Filosofía, Derecho o cualitativa, y el Actor usó "variables X e Y", demostraciones de lógica matemática falsas o un formato de ingeniería, PENALÍZALO y exige prosa académica pura.
    2. Si la pregunta es de Ciencias Exactas y el Actor no demostró matemáticamente los pasos, se saltó álgebra o no usó el entorno \\begin{align*}, PENALÍZALO y exige rigor.
    
    Criterios Generales de Falla:
    - Falla matemática o lógica argumentativa.
    - Se repite el enunciado de forma inútil al principio de la respuesta.
    - El LaTeX está mal formado o usa comandos ilegales como \\begin{document}.
    
    Tu respuesta DEBE ser ÚNICAMENTE un JSON estricto:
    {
       "aprobado": true o false,
       "critica": "Motivo detallado del rechazo indicando qué debe corregir, o string vacío si es true"
    }"""

    user_prompt = f"ENUNCIADO ORIGINAL:\n{enunciado}\n\nRESOLUCIÓN DEL ACTOR:\n{resolucion_actor}"

    intentos_red = 0
    while intentos_red < MAX_RETRIES_API:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite', 
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            # --- BLINDAJE JSON QUIRÚRGICO (RESCATE DE LATEX) ---
            texto_crudo = respuesta.text.strip()
            texto_crudo = re.sub(r'^```json', '', texto_crudo, flags=re.IGNORECASE)
            texto_crudo = re.sub(r'```$', '', texto_crudo).strip()
            texto_crudo = re.sub(r'^```', '', texto_crudo).strip()
            
            try:
                datos = json.loads(texto_crudo)
            except json.JSONDecodeError:
                print("      🛡️ Crítico: JSON malformado por caracteres LaTeX. Aplicando saneamiento...")
                # Escapa las barras invertidas que no sean de secuencias de escape nativas de JSON
                texto_saneado = re.sub(r'(?<!\\)\\(?![\\/"bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', texto_crudo)
                datos = json.loads(texto_saneado)
            # ----------------------------------------------------

            return datos.get("aprobado", False), datos.get("critica", "Error de formato en crítica.")
            
        except Exception as e:
            intentos_red += 1
            if intentos_red >= MAX_RETRIES_API:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico en el Crítico tras {MAX_RETRIES_API} intentos de red.")
                raise RuntimeError(f"Fallo Crítico: {e}")
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                print(f"      ⏳ Límite de API en Crítico. Intento {intentos_red}/{MAX_RETRIES_API}. Esperando 60s...")
                time.sleep(60)
            else:
                print(f"      ⚠️ Error en decodificación del Crítico. Intento {intentos_red}/{MAX_RETRIES_API}. Reintentando en 15s... ({e})")
                time.sleep(15)

def orquestar_resolucion(json_path):
    print(f"🚀 Motor de Resolución Activado: Bucle Actor-Crítico y Directriz Camaleónica...")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        estructura = json.load(f)
        
    # --- CORTACIRCUITOS DE METADATA (KeyError Fix) ---
    metadata = estructura.get('metadata', {})
    titulo_real = metadata.get('titulo', 'Guia_de_Ejercicios')
    titulo_guia = limpiar_nombre_carpeta(titulo_real)
    
    guias_out_dir = "guias_out"
    os.makedirs(guias_out_dir, exist_ok=True)
    
    ruta_salida = os.path.join(guias_out_dir, f"guia_resuelta_{titulo_guia}.tex")
    
    os.makedirs("Pensamientos", exist_ok=True)
    ruta_pensamientos = os.path.join("Pensamientos", f"Pensamientos_Solver_{titulo_guia}.tex")
    
    # Iniciar archivo de pensamientos
    with open(ruta_pensamientos, 'w', encoding='utf-8') as f_pens:
        f_pens.write(f"\\documentclass[12pt, a4paper]{{article}}\n")
        f_pens.write(f"\\usepackage[utf8]{{inputenc}}\n\\usepackage{{geometry}}\n\\geometry{{margin=2.5cm}}\n")
        f_pens.write(f"\\usepackage{{listings}}\n")
        f_pens.write(f"\\lstset{{breaklines=true, basicstyle=\\ttfamily\\small}}\n")
        f_pens.write(f"\\title{{Bitácora Actor-Crítico: Solver \\\\ \\large Guía: {titulo_real}\n}}\n")
        f_pens.write(f"\\author{{Registro de Agente Autónomo}}\n\\begin{{document}}\n\\maketitle\n\n")

    # RESTAURACIÓN: El preámbulo LaTeX para que la guía resuelta sea un documento compilable.
    texto_documento = f"\\documentclass[12pt, a4paper]{{article}}\n"
    texto_documento += f"\\usepackage[utf8]{{inputenc}}\n"
    texto_documento += f"\\usepackage{{geometry}}\n\\geometry{{margin=2.5cm}}\n"
    texto_documento += f"\\usepackage{{amsmath, amssymb, physics}}\n" # Seguro para dominio multidisciplinario
    texto_documento += f"\\usepackage{{hyperref}}\n\n"
    texto_documento += f"\\title{{Resolución de Prácticas: {titulo_real}}}\n"
    texto_documento += f"\\author{{Agustín Prunés Fuenzalida}}\n"
    texto_documento += f"\\date{{\\today}}\n\n"
    texto_documento += f"\\begin{{document}}\n\n"
    texto_documento += f"\\maketitle\n\n"

    for item in estructura.get("items", []):
        print(f"\n🧩 Abordando Problema Principal: {item['id']}")
        
        # 1. Búsqueda y Auditoría RAG para el problema principal
        query_rag = f"Problema: {item['contexto_base']}"
        contexto_bruto = buscar_contexto(query_rag, n_results=5)
        contexto_aprobado = ""
        
        if contexto_bruto:
            es_valido = auditar_contexto_rag(item['contexto_base'], contexto_bruto)
            if es_valido:
                contexto_aprobado = contexto_bruto
        
        texto_documento += f"\\section*{{Problema {item['id'].replace('prob_', '')}}}\n"
        texto_documento += f"\\textbf{{Contexto general:}} {item['contexto_base']}\n\n"
        
        with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
            f_pens.write(f"\\section*{{Problema: {item['id']}}}\n")

        memoria_corto_plazo = "" # Se resetea con cada nuevo problema principal

        # Iterar sobre los incisos de este problema
        for inciso in item.get("sub_items", []):
            print(f"   ▶️  Resolviendo inciso {inciso['id_letra']}) ...")
            
            enunciado_inciso = f"CONTEXTO DEL PROBLEMA:\n{item['contexto_base']}\n\nPREGUNTA ESPECÍFICA ({inciso['id_letra']}):\n{inciso['pregunta']}"
            
            intento_actual = 1
            critica_acumulada = None
            resolucion_final = ""
            pensamiento_final = ""
            
            # BUCLE LÓGICO ACTOR-CRÍTICO (Independiente del bucle de red)
            while intento_actual <= MAX_INTENTOS_ACTOR_CRITICO:
                print(f"      🧠 Actor (Intento {intento_actual}/{MAX_INTENTOS_ACTOR_CRITICO}): Generando resolución...")
                resolucion_actor, pensamiento_actor = generar_resolucion_actor(
                    problema_completo=enunciado_inciso,
                    contexto_rag=contexto_aprobado,
                    memoria_corto_plazo=memoria_corto_plazo,
                    critica_previa=critica_acumulada
                )
                
                print(f"      ⚖️  Crítico: Evaluando rigor de la respuesta...")
                aprobado, critica = evaluar_resolucion_critico(enunciado_inciso, resolucion_actor)
                
                if aprobado:
                    print("      ✅ Crítico: Resolución APROBADA.")
                    resolucion_final = resolucion_actor
                    pensamiento_final = f"Intento {intento_actual}: APROBADO.\n{pensamiento_actor}"
                    break
                else:
                    print(f"      ❌ Crítico: RECHAZADA. Motivo: {critica}")
                    critica_acumulada = critica
                    pensamiento_final += f"\n--- Intento {intento_actual} RECHAZADO ---\nPensamiento Actor: {pensamiento_actor}\nCrítica: {critica}\n"
                    intento_actual += 1
            
            if intento_actual > MAX_INTENTOS_ACTOR_CRITICO:
                print("      ⚠️ Máximo de intentos lógicos alcanzado. Se forzará la inserción de la última respuesta del Actor.")
                resolucion_final = resolucion_actor # Guardamos la última por fuerza bruta
                pensamiento_final += f"\n--- FORZADO TRAS {MAX_INTENTOS_ACTOR_CRITICO} INTENTOS ---\n"
                
            texto_documento += f"\\textbf{{{inciso['id_letra']})}} {inciso['pregunta']}\n\n"
            texto_documento += f"\\textbf{{Solución:}}\n\n"
            texto_documento += f"% === INICIO RESOLUCION: {item['id']}_{inciso['id_letra']} ===\n"
            texto_documento += f"{resolucion_final}\n"
            texto_documento += f"% === FIN RESOLUCION: {item['id']}_{inciso['id_letra']} ===\n\n"
            
            # Alimentar la memoria de corto plazo para el siguiente inciso
            memoria_corto_plazo += f"\nResultado de inciso {inciso['id_letra']}):\n{resolucion_final}\n"

            # Registrar pensamientos del bucle
            with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
                f_pens.write(f"\\subsection*{{Inciso {inciso['id_letra']}}}\n\\begin{{lstlisting}}\n{pensamiento_final}\n\\end{{lstlisting}}\n\n")

            time.sleep(2)

    # RESTAURACIÓN: Cierre del documento LaTeX
    texto_documento += f"\n\\end{{document}}\n"

    # Escribir el documento final
    with open(ruta_salida, 'w', encoding='utf-8') as f_tex:
        f_tex.write(texto_documento)
        
    with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
        f_pens.write(f"\n\\end{{document}}\n")

    print(f"\n🎉 ¡Pipeline de Resolución de Guías Finalizado! Archivo compilable '{ruta_salida}' generado.")

if __name__ == "__main__":
    orquestar_resolucion("guide_structure.json")