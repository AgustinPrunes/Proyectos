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
# HIPERPARÁMETROS DE EDICIÓN Y SEGURIDAD
# =========================================================================
# ACTIVAR_REVISION_NIVEL_1: Audita y rediseña zonas al terminar CADA CAPÍTULO.
# ACTIVAR_REVISION_NIVEL_2: Audita y rediseña zonas al terminar EL LIBRO COMPLETO.
# (Apagarlos acelera la generación y reduce drásticamente el consumo de tokens)
ACTIVAR_REVISION_NIVEL_1 = False
ACTIVAR_REVISION_NIVEL_2 = False

# CORTACIRCUITOS DE PRODUCCIÓN: Evita el secuestro financiero / drenaje de tokens
MAX_RETRIES = 5
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

def recortar_historial(texto, max_chars=12000):
    """
    Mecanismo de Ventana Deslizante (Sliding Window).
    Evita el Error 429 RESOURCE_EXHAUSTED recortando el historial masivo.
    Solo envía los últimos `max_chars` al LLM para mantener coherencia
    sin drenar la cuota de tokens por minuto.
    """
    if len(texto) <= max_chars:
        return texto
    return "\n...[TEXTO HISTÓRICO ANTERIOR OMITIDO PARA AHORRO DE MEMORIA]...\n" + texto[-max_chars:]

def buscar_contexto(query, n_results=8):
    """Consulta el Cerebro Híbrido (Vectorial + Semántico) a nivel MACRO."""
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
            for nodo in nodos_encontrados[:15]:  
                for destino in G.successors(nodo):
                    rel = G.edges[nodo, destino].get('relacion', 'se relaciona con')
                    conexiones.append(f"[{nodo}] --({rel})--> [{destino}]")
                for origen in G.predecessors(nodo):
                    rel = G.edges[origen, nodo].get('relacion', 'se relaciona con')
                    conexiones.append(f"[{origen}] --({nodo})--> [{nodo}]")

            if conexiones:
                conexiones_unicas = list(set(conexiones))[:40] 
                texto_grafo = "\n".join(conexiones_unicas)
    except Exception:
        pass

    contexto_final = ""
    if texto_vectorial:
        contexto_final += "--- FRAGMENTOS VECTORIALES (MACRO-CONTEXTO) ---\n" + texto_vectorial + "\n\n"
    if texto_grafo:
        contexto_final += "--- MAPA LÓGICO DEL GRAFO ---\n" + texto_grafo + "\n\n"
        
    return contexto_final.strip()

def auditar_contexto_rag(instruccion_capitulo, contexto_bruto):
    """Agente Portero: Verifica si el macro-contexto recuperado pertenece al dominio del capítulo."""
    if not contexto_bruto.strip():
        return False
        
    print(f"   🛡️ Agente Portero: Auditando relevancia del macro-contexto del capítulo...")
    system_instruction = """Eres un Juez Auditor de Contexto Editorial.
    Tu tarea es leer los temas de un CAPÍTULO COMPLETO y el contexto recuperado de una base de datos.
    Evalúa si el contexto pertenece EXACTAMENTE a la misma disciplina y si aporta rigor académico válido para redactar la teoría.
    Si el contexto es irrelevante, pertenece a otra rama o está contaminado con conceptos ajenos a la materia principal, DEBES rechazarlo.
    Responde ÚNICAMENTE con la palabra 'APROBADO' o 'RECHAZADO'."""
    
    user_prompt = f"TEMAS DEL CAPÍTULO A REDACTAR:\n{instruccion_capitulo}\n\nCONTEXTO RECUPERADO:\n{contexto_bruto}"
    
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
            print("      ✅ Veredicto: APROBADO. El macro-contexto se usará como bibliografía.")
            return True
        else:
            print("      ❌ Veredicto: RECHAZADO. El macro-contexto está contaminado o fuera de dominio. Se descartará.")
            return False
    except Exception as e:
        print(f"      ⚠️ Error en el Agente Portero ({e}). Rechazando por seguridad.")
        return False

def limpiar_markdown_latex(texto):
    contenido = texto.strip()
    marca_inicio = chr(96) * 3 + 'latex'
    marca_fin = chr(96) * 3
    if contenido.startswith(marca_inicio): contenido = contenido[len(marca_inicio):]
    if contenido.endswith(marca_fin): contenido = contenido[:-len(marca_fin)]
    if contenido.startswith(chr(96)*3): contenido = contenido[3:]
    return contenido.strip()

def limpiar_comandos_estructurales(texto):
    """
    Filtro coercitivo (Regex): Purga cualquier alucinación estructural del LLM
    para evitar el 'Eco de Títulos' en el índice LaTeX (Falla 2).
    """
    # 1. Elimina comandos con argumentos: \section{...}, \subsection*{...}, etc.
    patron_completo = r'\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?(?:\[[^\]]*\])?\{[^\}]*\}'
    texto_purgado = re.sub(patron_completo, '', texto, flags=re.IGNORECASE)
    
    # 2. Elimina comandos huérfanos sin llaves que el LLM pueda haber dejado colgados
    patron_residual = r'\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?\b'
    texto_purgado = re.sub(patron_residual, '', texto_purgado, flags=re.IGNORECASE)
    
    return texto_purgado.strip()

def reemplazar_bloque_quirurgico(texto_completo, tag_id, nuevo_contenido, tipo="INCISO"):
    """Reemplaza una zona delimitada por etiquetas ocultas sin alterar el resto del documento."""
    patron = rf"% === INICIO {tipo}: {tag_id} ===.*?% === FIN {tipo}: {tag_id} ==="
    bloque_nuevo = f"% === INICIO {tipo}: {tag_id} ===\n{nuevo_contenido.strip()}\n% === FIN {tipo}: {tag_id} ==="
    texto_modificado, count = re.subn(patron, lambda _: bloque_nuevo, texto_completo, flags=re.DOTALL)
    return texto_modificado

def generar_subseccion_completa(instrucciones_agrupadas, nivel, texto_acumulado_capitulo, texto_absolute_previo, temas_futuros, bloque_contexto_capitulo, es_preambulo=False):
    """Genera la redacción utilizando el macro-contexto ya validado a nivel de capítulo."""
    bloque_fronteras = ""
    if temas_futuros:
        bloque_fronteras = "\n--- FRONTERAS TEMÁTICAS GLOBALES (PROHIBICIÓN ESTRICTA) ---\n"
        bloque_fronteras += "Los siguientes temas pertenecen a capítulos o secciones FUTURAS de este libro.\n"
        bloque_fronteras += "Está ESTRICTAMENTE PROHIBIDO adelantarte, usarlos como ejemplo o mencionarlos. Haz como si no existieran aún:\n"
        for tema in temas_futuros[:10]:
            bloque_fronteras += f"- PROHIBIDO TOCAR: {tema}\n"
        bloque_fronteras += "----------------------------------------------------------------------\n"

    system_instruction = f"""Eres un Autor Académico y Catedrático de élite multidisciplinario escribiendo un libro de texto de nivel {nivel}.
    
    REGLAS BASE (ESTRICTAMENTE PROHIBIDO):
    1. Usar comandos de documento (\\documentclass, \\begin{{document}}).
    2. Usar comandos de estructura (\\chapter, \\section, \\subsection, \\subsubsection). Tu salida debe ser texto narrativo puro, el sistema orquestador ya coloca los títulos. ESTO ES CRÍTICO.
    3. Usar formato markdown final (solo LaTeX puro).
    4. Saludar o concluir textualmente como un asistente de chat.
    5. ESTRICTAMENTE PROHIBIDO usar los entornos `aligned` (sin un bloque contenedor align) o `boxed`, ya que rompen los márgenes de la página.
    6. REGLA ANTI-ECO (CRÍTICA): Tienes ESTRICTAMENTE PROHIBIDO iniciar tu redacción repitiendo el título del inciso o sección. Arranca directamente con el desarrollo y la explicación de la teoría.
    
    DIRECTRIZ CAMALEÓNICA (ADAPTACIÓN INTEGRAL Y FLUIDA DE DOMINIO):
    Identifica de forma totalmente autónoma la naturaleza epistémica y la disciplina exacta del manuscripto (ej. Literatura, Medicina, Derecho, Ingeniería, Bellas Artes, Economía, Música, Filosofía, Arquitectura, Ciencias Sociales, etc.). Tienes la obligación inquebrantable de mimetizarte al 100% con la jerga técnica, el tono formal, el estilo expresivo y las convenciones metodológicas naturales de dicha especialidad, sin imponer nunca marcos analíticos artificiales ajenos a ella.
    - Las reglas de visualización matemática son estrictamente condicionales: úsalas de forma explícita únicamente si el tema actual o campo epistémico exige formalismos abstractos, lógica cuantitativa, ecuaciones o derivaciones analíticas/algebraicas.
    - Si el tema es discursivo, conceptual, interpretativo, hermenéutico, descriptivo o clínico (como poesía, análisis histórico, jurisprudencia, semiología médica, etc.), queda ESTRICTAMENTE PROHIBIDO inventar variables lógicas espurias (ej. X, Y), usar expresiones seudo-matemáticas artificiales o forzar bloques de ecuaciones que degraden la naturalidad y rigor orgánico de la prosa académica. Escribe con la densidad teórica, exégesis y riqueza terminológica nativa de la especialidad.

    DIRECTRIZ CRÍTICA DE CONOCIMIENTO:
    Si se te proporciona el 'MACRO-CONTEXTO DEL CAPÍTULO', utilízalo como base principal. Si no hay contexto útil, confía exclusivamente en tu conocimiento interno de élite multidisciplinario.
    
    REGLAS DE VISUALIZACIÓN MATEMÁTICA Y FORMATO (CONDICIONALES AL DOMINIO REQUERIDO):
    - Para ecuaciones o términos breves dentro de un párrafo (inline math), usa la notación estándar $...$. Asegúrate de que fluyan y se visualicen correctamente en la misma línea.
    - Para ecuaciones o fórmulas fuera del párrafo (display math), utiliza entornos formales como `\\begin{{equation}} ... \\end{{equation}}` o `\\[ ... \\]`.
    - Si un desarrollo algebraico o una ecuación es extensa y requiere de varias líneas, usa obligatoriamente el entorno `\\begin{{align*}} ... \\end{{align*}}` con saltos de línea explícitos (`\\\\`). Prohibido forzar una ecuación multilínea en una sola línea continua.
    
    REGLA DE MEMORIA ABSOLUTA:
    Se te proporcionará el texto EXACTO de los capítulos anteriores y del capítulo actual. DEBES mantener una coherencia notacional estricta. Si un concepto o ecuación ya fue demostrado, NO LO VUELVAS A DESARROLLAR; cítalo formalmente.
    
    REGLA DE EXIGENCIA PEDAGÓGICA EXTENSA:
    Está estrictamente prohibido resumir o dar explicaciones escuetas. Desarrolla el contenido procedimental de forma exhaustiva.

    ESTRUCTURA DE TU RESPUESTA (OBLIGATORIA):
    <razonamiento>
    (Planifica tu enfoque: ¿Qué conceptos explicarás primero? ¿Qué marcos teóricos o metodológicos incluirás? ¿Cómo estructurarás la pedagogía de este texto basándote en la Directriz Camaleónica para respetar la disciplina exacta sin forzar estructuras ajenas?)
    </razonamiento>
    ```latex
    (Tu redacción final en LaTeX puro crudo)
    ```"""

    # Aplicamos la ventana deslizante para evitar el 429 Error
    historial_recortado = recortar_historial(texto_absolute_previo)

    user_prompt = f"""
    --- HISTORIAL DE CAPÍTULOS ANTERIORES (CONTEXTO RECIENTE) ---
    {historial_recortado if historial_recortado.strip() else "[Este es el primer capítulo del libro]"}
    
    --- TEXTO ACUMULADO DEL CAPÍTULO ACTUAL ---
    {texto_acumulado_capitulo if texto_acumulado_capitulo.strip() else "[Inicio del capítulo]"}
    
    TU TAREA ES CONTINUAR EL TEXTO DE FORMA FLUIDA DESDE EL FINAL DEL CAPÍTULO ACTUAL.
    Debes redactar esta {'introducción' if es_preambulo else 'sección atómica (inciso)'} integrando los siguientes requerimientos:
    
    REQUERIMIENTOS A DESARROLLAR:
    {instrucciones_agrupadas}
    
    {bloque_fronteras}
    
    {bloque_contexto_capitulo}
    
    Genera tu respuesta con el bloque de razonamiento y luego el LaTeX:
    """
    
    intentos = 0
    while intentos < MAX_RETRIES:
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
            pensamiento = match_pensamiento.group(1).strip() if match_pensamiento else "No se detectó bloque de razonamiento."
            
            contenido = re.sub(r'<razonamiento>.*?</razonamiento>', '', texto_crudo, flags=re.DOTALL).strip()
            contenido = limpiar_markdown_latex(contenido)
            contenido = limpiar_comandos_estructurales(contenido) # Purga coercitiva de estructuras
            
            return contenido + "\n\n", pensamiento
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"   🚨 CORTACIRCUITOS ACTIVADO: 5 fallos consecutivos. Abortando para proteger cuota.")
                raise RuntimeError(f"Fallo crítico en generación tras {MAX_RETRIES} intentos: {e}")

            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                # Incrementado a 90s para mitigar cuellos de botella de API reales
                print(f"   ⏳ Límite de API alcanzado. Intento {intentos}/{MAX_RETRIES}. Esperando 90s...")
                time.sleep(90)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"   🔥 Servidor saturado (503). Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"   ⚠️ Error o congestión. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s... ({e})")
                time.sleep(15)

def planificar_mejoras(historial_previo, capitulo_texto, titulo_contexto, nivel, es_global=False):
    """Analiza de forma macro el texto y devuelve un JSON con las zonas específicas que requieren reescritura."""
    print(f"   🔍 Planificador de Nivel {'2 (Global)' if es_global else '1 (Capítulo)'}: Evaluando fallas de cohesión o notación...")
    
    system_instruction = f"""Eres un Auditor y Editor Académico Principal de nivel {nivel} multidisciplinario.
    Tu único objetivo es leer el borrador de un texto académico, contrastarlo con el historial de la obra y generar un PLAN DE MEJORAS en formato JSON para las zonas que consideres que deben ser rediseñadas o vueltas a redactar.
    
    ZONAS A EVALUAR:
    Identifica las etiquetas '% === INICIO INCISO: id ===' o '% === INICIO PREAMBULO: id ===' presentes en el borrador.
    
    CRITERIOS PARA MARCAR UNA ZONA PARA MEJORA/REESCRITURA:
    1. Si detectas que cambió la terminología técnica, la notación o las convenciones de estilo respecto a los capítulos previos.
    2. Si detectas redundancia cíclica (explicó algo de forma sosa que ya se demostró o expuso antes en el historial).
    3. Si la explicación quedó desconectada o el nivel de rigor conceptual decayó.
    4. Evalúa la adecuación al dominio epistémico: si el manuscrito es conceptual, discursivo o documental (como literatura, artes o derecho) y se forzaron variables algebraicas espurias, ecuaciones o seudo-matematizaciones artificiales, DEBES marcar la zona para reescritura pura. Si la disciplina amerita matemáticas, verifica que las ecuaciones largas no estén forzadas en una sola línea continua y exijan entornos multilínea limpios (`\\begin{{align*}}`).

    ESTRUCTURA EXACTA DE RETORNO (JSON STRICT):
    {{
      "mejoras": [
        {{
          "id": "id_de_la_etiqueta",
          "tipo": "INCISO" o "PREAMBULO",
          "motivo": "Explicación breve de la falla detectada",
          "guia_de_mejora": "Directrices detalladas para reescribir esta sección de forma perfecta siguiendo la disciplina nativa de la obra."
        }}
      ]
    }}
    Si el documento está impecable y no requiere reescritura, devuelve {{"mejoras": []}}."""

    # Aplicamos la ventana deslizante al historial macro
    historial_recortado = recortar_historial(historial_previo)

    user_prompt = f"""
    --- MANUSCRITO / HISTORIAL PREVIO DE REFERENCIA ---
    {historial_recortado if historial_recortado.strip() else "[No hay historial previo]"}
    
    --- BORRADOR DEL TEXTO ACTUAL A AUDITAR ---
    {capitulo_texto}
    
    Analiza el borrador globalmente y genera el JSON con el plan de mejoras:
    """
    
    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite', 
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
            datos = json.loads(respuesta.text.strip())
            return datos.get("mejoras", [])
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"   🚨 CORTACIRCUITOS ACTIVADO en Planificador. Abortando para proteger cuota.")
                raise RuntimeError(f"Fallo crítico decodificando mejoras tras {MAX_RETRIES} intentos: {e}")

            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                print(f"   ⏳ Límite de API en Planificador. Intento {intentos}/{MAX_RETRIES}. Esperando 90s...")
                time.sleep(90)
            else:
                print(f"   ⚠️ Error decodificando mejoras. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s... ({e})")
                time.sleep(15)

def reescribir_zona_con_contexto(historial_previo, capitulo_texto, id_zona, tipo_zona, guia_de_mejora, nivel):
    """Redacta desde cero únicamente el bloque de una zona específica aplicando las directrices del plan."""
    print(f"      🛠  Reescritura Quirúrgica: Rediseñando {tipo_zona.lower()} '{id_zona}'...")
    
    patron = rf"% === INICIO {tipo_zona}: {id_zona} ===(.*?)% === FIN {tipo_zona}: {id_zona} ==="
    match = re.search(patron, capitulo_texto, re.DOTALL)
    version_anterior = match.group(1).strip() if match else ""

    system_instruction = f"""Eres un Catedrático de Élite y Escritor Doctoral de nivel {nivel} multidisciplinario.
    Tu misión es VOLVER A REDACTAR Y REDISEÑAR una sección específica de un libro que fue marcada con fallas estructurales por el auditor jefe.
    
    REGLA INQUEBRANTABLE DE EXTENSIÓN (ANTI-RESUMEN):
    Está ABSOLUTAMENTE PROHIBIDO acortar el texto, omitir pasos, condensar explicaciones o realizar resúmenes. Tu tarea es corregir la notación y mejorar la fluidez analítica MANTENIENDO o INCREMENTANDO el nivel de detalle y la extensión del texto original.

    DIRECTRIZ CAMALEÓNICA (ADAPTACIÓN INTEGRAL Y FLUIDA DE DOMINIO):
    Identifica de forma totalmente autónoma la naturaleza epistémica y la disciplina exacta del manuscrito (ej. Literatura, Medicina, Derecho, Ingeniería, Bellas Artes, Economía, Música, Filosofía, Arquitectura, Ciencias Sociales, etc.). Tienes la obligación inquebrantable de mimetizarte al 100% con la jerga técnica, el tono formal, el estilo expresivo y las convenciones metodológicas naturales de dicha especialidad, sin imponer nunca marcos analíticos artificiales ajenos a ella.
    - Las reglas de visualización matemática son estrictamente condicionales: úsalas de forma explícita únicamente si el tema actual o campo epistémico exige formalismos abstractos, lógica cuantitativa, ecuaciones o derivaciones analíticas/algebraicas.
    - Si el tema es discursivo, conceptual, interpretativo, hermenéutico, descriptivo o clínico, queda ESTRICTAMENTE PROHIBIDO inventar variables lógicas espurias (ej. X, Y), usar expresiones seudo-matemáticas artificiales o forzar bloques de ecuaciones. Escribe con la densidad teórica nativa de la especialidad.

    REGLAS DE VISUALIZACIÓN MATEMÁTICA Y FORMATO (CONDICIONALES AL DOMINIO REQUERIDO):
    - Inline math: usar $...$.
    - Display math: `\\begin{{equation}} ... \\end{{equation}}` o `\\[ ... \\]`.
    - Desarrollo extenso: obligatoriamente `\\begin{{align*}} ... \\end{{align*}}` con saltos de línea `\\\\`.

    REGLA DE COHESIÓN HISTÓRICA:
    Utiliza el manuscrito previo para referenciar directamente resultados ya obtenidos. No vuelvas a derivar lo que ya existe.

    REGLAS DE FORMATO REESCRITURA:
    1. NO uses comandos de estructura raíz o de capítulos (\\chapter, \\section, etc.). Tu salida debe ser texto base puro.
    2. Mantén la cabecera exacta de la sección original en tu razonamiento, pero NO la incluyas en el código LaTeX final.
    3. Devuelve ÚNICAMENTE el código LaTeX puro corregido.

    ESTRUCTURA DE TU RESPUESTA (OBLIGATORIA):
    <razonamiento>
    (Verifica el historial, entiende por qué el texto anterior falló según la guía de mejora, y planifica la reescritura aplicando la Directriz Camaleónica)
    </razonamiento>
    ```latex
    (Tu redacción final corregida en LaTeX puro)
    ```"""

    historial_recortado = recortar_historial(historial_previo)

    user_prompt = f"""
    --- MANUSCRITO DE LA OBRA COMPLETA (HISTORIAL PREVIO RECORTADO) ---
    {historial_recortado if historial_recortado.strip() else "[Primeros capítulos del libro]"}
    
    --- MANUSCRITO COMPLETO DEL CAPÍTULO ACTUAL (BORRADOR) ---
    {capitulo_texto}
    
    --- VERSIÓN ANTERIOR DEFECTUOSA DE ESTA ZONA ---
    {version_anterior}
    
    --- DIRECTRICES CRÍTICAS PARA LA REESCRITURA Y REDISEÑO ---
    {guia_de_mejora}
    
    Reescribe esta zona cumpliendo rigurosamente el filtro anti-resumen:
    """
    
    intentos = 0
    while intentos < MAX_RETRIES:
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
            pensamiento = match_pensamiento.group(1).strip() if match_pensamiento else "No se detectó bloque de razonamiento."
            
            contenido = re.sub(r'<razonamiento>.*?</razonamiento>', '', texto_crudo, flags=re.DOTALL).strip()
            contenido = limpiar_markdown_latex(contenido)
            contenido = limpiar_comandos_estructurales(contenido) # Purga coercitiva de estructuras
            
            return contenido, pensamiento
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"   🚨 CORTACIRCUITOS ACTIVADO en Reescritura. Abortando para proteger cuota.")
                raise RuntimeError(f"Fallo crítico en reescritura quirúrgica tras {MAX_RETRIES} intentos: {e}")

            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                print(f"   ⏳ Límite de API en Escritor Quirúrgico. Intento {intentos}/{MAX_RETRIES}. Esperando 90s...")
                time.sleep(90)
            else:
                print(f"   🚨 Error en reescritura de zona. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s... ({e})")
                time.sleep(15)

def orquestar_generacion(json_path):
    print(f"🚀 Motor de Generación Activado: Arquitectura Quirúrgica Anti-Truncamiento v1.2 (Macro-RAG)...")
    print(f"⚙️  Estado del Editor Nivel 1 (Capítulo): {'ACTIVADO' if ACTIVAR_REVISION_NIVEL_1 else 'DESACTIVADO'}")
    print(f"⚙️  Estado del Editor Nivel 2 (Global): {'ACTIVADO' if ACTIVAR_REVISION_NIVEL_2 else 'DESACTIVADO'}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        estructura = json.load(f)
        
    nivel_libro = estructura['metadata'].get('nivel', 'Universitario')
    nombre_seguro = limpiar_nombre_carpeta(estructura['metadata']['titulo'])
    base_dir = f"libro_{nombre_seguro}"
    chapters_dir = os.path.join(base_dir, "chapters")
    
    os.makedirs("Pensamientos", exist_ok=True)
    ruta_pensamientos = os.path.join("Pensamientos", f"Pensamientos_Generator_{nombre_seguro}.tex")
    
    with open(ruta_pensamientos, 'w', encoding='utf-8') as f_pens:
        f_pens.write(f"\\documentclass[12pt, a4paper]{{article}}\n")
        f_pens.write(f"\\usepackage[utf8]{{inputenc}}\n\\usepackage{{geometry}}\n\\geometry{{margin=2.5cm}}\n")
        f_pens.write(f"\\usepackage{{listings}}\n")
        f_pens.write(f"\\lstset{{breaklines=true, basicstyle=\\ttfamily\\small}}\n")
        f_pens.write(f"\\title{{Bitácora Cognitiva: Generator \\\\ \\large Libro: {nombre_seguro.replace('_', ' ')}\n}}\n")
        f_pens.write(f"\\author{{Registro de Agente Autónomo}}\n\\begin{{document}}\n\\maketitle\n\n")

    linea_de_tiempo = []
    for cap in estructura.get("capitulos", []):
        for sec in cap.get("secciones", []):
            linea_de_tiempo.append(sec["titulo"])
            for subsec in sec.get("subsecciones", []):
                linea_de_tiempo.append(subsec["titulo"])
                for inciso in subsec.get("incisos", []):
                    linea_de_tiempo.append(inciso["titulo"])
                
    indice_temporal = 0
    historial_absoluto_previo = ""  
    
    # -----------------------------------------------------------------
    # FASE 1 Y 2: GENERACIÓN DE BORRADOR Y AUDITORÍA DE NIVEL 1
    # -----------------------------------------------------------------
    for cap in estructura.get("capitulos", []):
        ruta_archivo = os.path.join(chapters_dir, f"{cap['id']}.tex")
        
        # --- LÓGICA DE REANUDACIÓN ---
        if os.path.exists(ruta_archivo):
            with open(ruta_archivo, 'r', encoding='utf-8') as f_tex:
                contenido_existente = f_tex.read()
            
            es_esqueleto = "% El Agente insertará el contenido aquí" in contenido_existente
            tiene_marcas_generadas = "% === INICIO" in contenido_existente
            
            if (not es_esqueleto and tiene_marcas_generadas) or (not es_esqueleto and len(contenido_existente.splitlines()) > 30):
                print(f"\n⏭️ Capítulo ya redactado detectado: {cap['titulo']}. Cargando a la memoria y saltando generación...")
                historial_absoluto_previo += f"\n\n% --- CAPÍTULO FINALIZADO: {cap['titulo']} ---\n\n" + contenido_existente
                
                with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
                    f_pens.write(f"\\section*{{Capítulo: {cap['titulo']} (Reanudado)}}\n")
                    f_pens.write("\\textit{Capítulo generado en una sesión anterior. Cargado exitosamente en la memoria a corto plazo.}\n\n")

                for sec in cap.get("secciones", []):
                    indice_temporal += 1
                    for subsec in sec.get("subsecciones", []):
                        indice_temporal += 1
                        for inciso in subsec.get("incisos", []):
                            indice_temporal += 1
                
                continue 
        
        print(f"\n📖 Redactando Borrador Inicial de Capítulo: {cap['titulo']}")
        
        titulos_secciones = [sec['titulo'] for sec in cap.get("secciones", [])]
        macro_query_capitulo = f"Capítulo: {cap['titulo']}. Temas a tratar: {', '.join(titulos_secciones)}"
        print(f"   🔍 Consultando Cerebro Híbrido para obtener el MACRO-CONTEXTO del capítulo...")
        
        contexto_recuperado = buscar_contexto(macro_query_capitulo, n_results=8)
        
        if contexto_recuperado.strip():
            es_valido = auditar_contexto_rag(macro_query_capitulo, contexto_recuperado)
            if es_valido:
                bloque_contexto_global = f"--- FRAGMENTOS RECUPERADOS Y VERIFICADOS (MACRO-CONTEXTO DEL CAPÍTULO) ---\n{contexto_recuperado}\n"
            else:
                bloque_contexto_global = "--- NOTA DE REDACCIÓN ---\nNo hay bibliografía externa válida o el contexto está contaminado. DEBES UTILIZAR TU CONOCIMIENTO INTERNO AVANZADO para redactar la teoría con máximo rigor académico.\n"
        else:
            bloque_contexto_global = "--- NOTA DE REDACCIÓN ---\nNo hay bibliografía externa válida en la base de datos. DEBES UTILIZAR TU CONOCIMIENTO INTERNO AVANZADO para redactar la teoría con máximo rigor académico.\n"

        texto_del_capitulo = f"\\chapter{{{cap['titulo']}}}\n\n"
        
        with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
            f_pens.write(f"\\section*{{Capítulo: {cap['titulo']}}}\n")

        for sec in cap.get("secciones", []):
            texto_del_capitulo += f"\\section{{{sec['titulo']}}}\n\n"
            
            if sec.get("preambulo"):
                print(f"   🧠 Construyendo preámbulo atomizado...")
                temas_futuros = linea_de_tiempo[indice_temporal + 1 :]
                instruccion_pre = f"Redacta un preámbulo teórico introductorio: {sec['preambulo']}"
                
                texto_del_capitulo += f"% === INICIO PREAMBULO: {sec['id']} ===\n"
                contenido, pensamiento = generar_subseccion_completa(instruccion_pre, nivel_libro, texto_del_capitulo, historial_absoluto_previo, temas_futuros, bloque_contexto_global, es_preambulo=True)
                texto_del_capitulo += contenido
                texto_del_capitulo += f"% === FIN PREAMBULO: {sec['id']} ===\n\n"
                
                with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
                    f_pens.write(f"\\subsection*{{Preámbulo: {sec['titulo']}}}\n\\begin{{lstlisting}}\n{pensamiento}\n\\end{{lstlisting}}\n\n")
                time.sleep(2)
            
            indice_temporal += 1
            
            for subsec in sec.get("subsecciones", []):
                texto_del_capitulo += f"\\subsection{{{subsec['titulo']}}}\n\n"
                indice_temporal += 1
                
                for inciso in subsec.get("incisos", []):
                    print(f"      🔸 Draft Inciso: {inciso['titulo']}")
                    
                    texto_del_capitulo += f"% === INICIO INCISO: {inciso['id']} ===\n"
                    texto_del_capitulo += f"\\subsubsection{{{inciso['titulo']}}}\n\n"
                    
                    temas_futuros = linea_de_tiempo[indice_temporal + 1 :]
                    instruccion_agrupada = ""
                    for i, bloque in enumerate(inciso.get("bloques", [])):
                        instruccion_agrupada += f"Parte {i+1} ({bloque['tipo'].upper()}): {bloque['instruccion']}\n"
                    
                    if instruccion_agrupada:
                        contenido, pensamiento = generar_subseccion_completa(instruccion_agrupada, nivel_libro, texto_del_capitulo, historial_absoluto_previo, temas_futuros, bloque_contexto_global)
                        texto_del_capitulo += contenido
                        
                        with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
                            f_pens.write(f"\\subsection*{{Inciso: {inciso['titulo']}}}\n\\begin{{lstlisting}}\n{pensamiento}\n\\end{{lstlisting}}\n\n")
                        
                    texto_del_capitulo += f"% === FIN INCISO: {inciso['id']} ===\n\n"
                    indice_temporal += 1
                    time.sleep(2)

        if ACTIVAR_REVISION_NIVEL_1:
            plan_mejoras_cap = planificar_mejoras(historial_absoluto_previo, texto_del_capitulo, cap['titulo'], nivel_libro, es_global=False)
            
            if plan_mejoras_cap:
                print(f"   🛡️ Plan de Mejoras aprobado con {len(plan_mejoras_cap)} zonas a rediseñar. Aplicando parches analíticos...")
                for mejora in plan_mejoras_cap:
                    zona_id = mejora["id"]
                    tipo = mejora["tipo"]
                    guia = mejora["guia_de_mejora"]
                    
                    contenido_corregido, pensamiento_correccion = reescribir_zona_con_contexto(historial_absoluto_previo, texto_del_capitulo, zona_id, tipo, guia, nivel_libro)
                    texto_del_capitulo = reemplazar_bloque_quirurgico(texto_del_capitulo, zona_id, contenido_corregido, tipo)
                    
                    with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
                        f_pens.write(f"\\subsection*{{Reescritura (Nivel 1): {zona_id}}}\n\\begin{{lstlisting}}\n{pensamiento_correccion}\n\\end{{lstlisting}}\n\n")
                    time.sleep(2)
            else:
                print("   ✅ Capítulo validado al 100%. No se requirieron reescrituras estructurales.")
        else:
            print("   ⏩ Revisión de Nivel 1 DESACTIVADA por hiperparámetro. Conservando borrador original.")

        with open(ruta_archivo, 'w', encoding='utf-8') as f_tex:
            f_tex.write(texto_del_capitulo)
            
        historial_absoluto_previo += f"\n\n% --- CAPÍTULO FINALIZADO: {cap['titulo']} ---\n\n" + texto_del_capitulo

    # -----------------------------------------------------------------
    # FASE 3: REVISIÓN MAESTRA Y REDISEÑO FINAL GLOBAL (NIVEL 2)
    # -----------------------------------------------------------------
    if ACTIVAR_REVISION_NIVEL_2:
        print("\n🎓 INICIANDO REVISIÓN MAGISTRAL DEL MANUSCRITO COMPLETO (NIVEL 2)...")
        
        manuscrito_completo = ""
        for cap in estructura.get("capitulos", []):
            ruta = os.path.join(chapters_dir, f"{cap['id']}.tex")
            if os.path.exists(ruta):
                with open(ruta, 'r', encoding='utf-8') as f:
                    manuscrito_completo += f"\n% --- MANUSCRITO CAP: {cap['id']} ---\n" + f.read()

        plan_global = planificar_mejoras("", manuscrito_completo, "OBRA_COMPLETA", nivel_libro, es_global=True)
        
        if plan_global:
            print(f"   🌟 El Editor Magistral identificó {len(plan_global)} zonas globales para reajuste armónico final.")
            archivos_afectados = set()
            
            for mejora in plan_global:
                zona_id = mejora["id"]
                tipo = mejora["tipo"]
                guia = mejora["guia_de_mejora"]
                
                contenido_maestro, pensamiento_maestro = reescribir_zona_con_contexto("", manuscrito_completo, zona_id, tipo, guia, nivel_libro)
                
                with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
                    f_pens.write(f"\\section*{{Auditoría Global Magistral}}\n\\subsection*{{Reescritura (Nivel 2): {zona_id}}}\n\\begin{{lstlisting}}\n{pensamiento_maestro}\n\\end{{lstlisting}}\n\n")

                for cap in estructura.get("capitulos", []):
                    ruta = os.path.join(chapters_dir, f"{cap['id']}.tex")
                    if os.path.exists(ruta):
                        with open(ruta, 'r', encoding='utf-8') as f:
                            contenido_archivo = f.read()
                        
                        if f"% === INICIO {tipo}: {zona_id} ===" in contenido_archivo:
                            contenido_archivo_modificado = reemplazar_bloque_quirurgico(contenido_archivo, zona_id, contenido_maestro, tipo)
                            with open(ruta, 'w', encoding='utf-8') as f:
                                f.write(contenido_archivo_modificado)
                            archivos_afectados.add(cap['id'])
                            break
                time.sleep(2)
            print(f"   ✅ Ajustes globales consolidados en los capítulos: {list(archivos_afectados)}")
        else:
            print("   ✅ Manuscrito global aprobado sin fisuras. Armonía teórica perfecta.")
    else:
        print("\n⏩ Revisión Magistral Global (Nivel 2) DESACTIVADA por hiperparámetro.")

    with open(ruta_pensamientos, 'a', encoding='utf-8') as f_pens:
        f_pens.write(f"\n\\end{{document}}\n")

    print("\n🎉 ¡Pipeline de Libros Finalizado! Operación completada bajo las reglas de hiperparámetros actuales.")

if __name__ == "__main__":
    orquestar_generacion("book_structure.json")