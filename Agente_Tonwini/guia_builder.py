import os
import json
import time
import re
import chromadb
import networkx as nx
from google import genai
from google.genai import types
from dotenv import load_dotenv

# =========================================================================
# HIPERPARÁMETROS DE SEGURIDAD Y CONFIGURACIÓN (RC 1.0)
# =========================================================================
MAX_RETRIES = 5  # Cortacircuitos anti-drenaje de tokens y prevención de bucles infinitos
# =========================================================================

# Cargar variables de entorno
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")
client = genai.Client(api_key=api_key)

# =========================================================================
# CATÁLOGO DE MODALIDADES DE GUÍAS (100% MULTIDISCIPLINARIAS)
# =========================================================================
PROMPTS_MODALIDADES = {
    "socratica_guiada": (
        "Diseña una 'Guía Socrática / Guiada'. El objetivo es construir conocimiento procedimental paso a paso. "
        "El enunciado plantea la situación base. Los incisos (a, b, c) deben seguir una progresión lineal estricta: "
        "a) Identificar variables/conceptos clave, b) Modelar o formular la interacción simple, y c) Calcular o analizar un escenario de cambio. Evita saltos creativos masivos."
    ),
    "evaluacion_hardcore": (
        "Diseña un 'Taller de Evaluación Hardcore (Examen)'. El objetivo es evaluar el dominio absoluto. "
        "Plantea problemas de sistemas compuestos, con condiciones de borde estrictas o variables ocultas. "
        "Los incisos deben exigir demostraciones directas complejas, optimización o deducción analítica profunda desde los primeros principios."
    ),
    "laboratorio_frontera": (
        "Diseña un 'Laboratorio Conceptual / Casos de Frontera'. "
        "Plantea escenarios donde los modelos tradicionales o fórmulas estándar fallan, entran en conflicto o rompen simetrías. "
        "Los incisos deben exigir al alumno que diagnostique por qué falla el modelo base y que proponga/calcule correcciones argumentadas."
    ),
    "diagnostico_resolucion": (
        "Diseña un 'Compendio de Diagnóstico y Resolución'. "
        "Se entrega un caso con fallos o patologías (un sistema colapsado, un paciente con síntomas cruzados, etc.). "
        "Los incisos deben seguir esta lógica: a) Aislar analíticamente la causa raíz, b) Proponer y modelar un algoritmo de corrección, c) Predecir el comportamiento posterior del sistema."
    ),
    "ensayo_cruzado": (
        "Diseña un 'Taller Interconectado de Ensayo Cruzado'. El objetivo es forzar el pensamiento sistémico. "
        "Cada problema debe obligar a unir dos disciplinas o ramas de la materia distintas. "
        "Los incisos deben prohibir explícitamente resolver usando una sola herramienta: el resultado analítico del inciso 'a' debe ser la entrada obligatoria del marco teórico del inciso 'b'."
    ),
    "demostraciones_formales": (
        "Diseña una 'Guía de Demostraciones Formales / Derivación Paso a Paso'. "
        "El enunciado principal NO debe plantear un caso numérico, sino un teorema, un axioma central o un postulado final que deba ser demostrado. "
        "Los incisos deben guiar la demostración teórica: a) Plantear condiciones iniciales o leyes base, b) Desarrollar el paso algebraico o lógico intermedio clave, c) Concluir formalmente la derivación."
    ),
    "modelado_simplificado": (
        "Diseña una guía de 'Ejercicios de Modelado Simplificado / Toy Models'. "
        "El enunciado debe plantear un escenario de la vida real extremadamente complejo y caótico. "
        "Los incisos pedirán: a) Identificar y justificar qué variables o efectos ignorar para hacer el problema analíticamente resoluble, b) Construir matemáticamente/lógicamente el modelo simplificado, c) Resolver dicho modelo."
    ),
    "comparacion_analitica": (
        "Diseña una 'Guía de Comparación Analítica (Sistema A vs. Sistema B)'. "
        "El enunciado presenta dos sistemas, mecanismos o escenarios alternativos competitivos. "
        "Los incisos deben estructurarse así: a) Analizar/calcular el estado final del Sistema A, b) Analizar/calcular el estado final del Sistema B, c) Comparar y justificar cuantitativa o lógicamente cuál es más eficiente/estable bajo un criterio dado."
    ),
    "analisis_sensibilidad": (
        "Diseña un 'Taller de Análisis de Sensibilidad y Perturbaciones'. "
        "El enunciado describe un sistema dinámico o teórico en perfecto estado base o equilibrio. "
        "Los incisos exigen: a) Calcular las condiciones del estado base, b) Introducir una perturbación exógena específica y calcular el nuevo estado, c) Analizar la tasa de desviación o impacto relativo del cambio."
    ),
    "datos_faltantes": (
        "Diseña una 'Guía de Casos Prácticos con Datos Faltantes'. "
        "El enunciado plantea un problema técnico, pero omite deliberada y explícitamente ciertas constantes o datos iniciales cruciales para su resolución. "
        "Los incisos deben obligar a: a) Declarar y justify profesionalmente qué supuestos de aproximación o valores (órdenes de magnitud) asumirá el alumno, b) Resolver el modelo utilizando sus propios supuestos, c) Criticar los límites de validez de su respuesta."
    )
}

def detectar_modo_automatico(temas_crudos):
    """Motor analítico preliminar. Infiere el tipo de guía óptima según los temas."""
    print("   🕵️‍♂️ No se detectó hiperparámetro explícito. Analizando semántica para Auto-Detección de Guía...")
    
    claves_disponibles = ", ".join(list(PROMPTS_MODALIDADES.keys()))
    
    system_instruction = f"""Eres un Enrutador Analítico de Diseño de Evaluaciones.
    Tu única tarea es leer una lista de temas a evaluar y decidir cuál es el MEJOR formato de guía de ejercicios para ellos.
    
    Opciones estrictas permitidas: [{claves_disponibles}]
    
    REGLA: Devuelve ÚNICAMENTE el nombre de la clave exacta, sin comillas ni explicaciones.
    (Ej: Si son temas muy aplicados usa 'modelado_simplificado' o 'diagnostico_resolucion'. Si es teoría dura usa 'demostraciones_formales'. Si no hay contexto claro, usa 'socratica_guiada')."""
    
    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=f"Temas a evaluar:\n{temas_crudos}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                )
            )
            modo_inferido = respuesta.text.strip().lower()
            if modo_inferido in PROMPTS_MODALIDADES:
                return modo_inferido
            return "socratica_guiada"
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo en auto-detección tras {MAX_RETRIES} intentos. Usando fallback.")
                return "socratica_guiada"
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"      ⏳ Límite de API. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"      🔥 Servidor saturado. Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"      ⚠️ Falló auto-detección ({e}). Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)

def buscar_contexto(query, n_results=4):
    """Consulta el Cerebro Híbrido (Vectorial + Semántico)."""
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
                    conexiones.append(f"[{origen}] --({rel})--> [{nodo}]")

            if conexiones:
                conexiones_unicas = list(set(conexiones))[:30] 
                texto_grafo = "\n".join(conexiones_unicas)
    except Exception:
        pass

    contexto_final = ""
    if texto_vectorial:
        contexto_final += "--- FRAGMENTOS DE LA BIBLIOGRAFÍA (Fórmulas y Teoría) ---\n" + texto_vectorial + "\n\n"
    if texto_grafo:
        contexto_final += "--- MAPA LÓGICO DEL GRAFO (Cruces conceptuales) ---\n" + texto_grafo + "\n\n"
        
    return contexto_final.strip()

def auditar_contexto_rag(temas, contexto_bruto):
    """Agente Portero: Verifica si el contexto recuperado pertenece a la disciplina solicitada."""
    if not contexto_bruto.strip():
        return False
        
    print("   🛡️ Agente Portero: Auditando relevancia del contexto recuperado...")
    system_instruction = """Eres un Juez Auditor de Contexto Estricto.
    Tu única tarea es leer los temas solicitados y el contexto recuperado de una base de datos.
    Debes evaluar si el contexto pertenece EXACTAMENTE a la misma disciplina que los temas y si es útil.
    Si el contexto es irrelevante, confuso, o pertenece a otra rama/disciplina distinta a la de los temas, DEBES rechazarlo.
    Responde ÚNICAMENTE con la palabra 'APROBADO' o 'RECHAZADO' sin comillas ni explicaciones adicionales."""
    
    user_prompt = f"TEMAS SOLICITADOS:\n{temas}\n\nCONTEXTO RECUPERADO:\n{contexto_bruto}"
    
    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0, 
                )
            )
            decision = respuesta.text.strip().upper()
            if "APROBADO" in decision:
                print("      ✅ Veredicto: APROBADO. El contexto es relevante.")
                return True
            else:
                print("      ❌ Veredicto: RECHAZADO. El contexto no concuerda. Se descartará.")
                return False
                
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo en Agente Portero tras {MAX_RETRIES} intentos. Rechazando contexto.")
                return False
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"      ⏳ Límite de API en Portero. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"      🔥 Servidor saturado (503). Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"      ⚠️ Error en el Agente Portero ({e}). Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)

def construir_guia():
    print("🚀 Iniciando el Constructor de Guías Hiperparametrizado (Builder con Bucle Actor-Crítico)...")
    
    ruta_entrada = "temas_guia.txt"
    if not os.path.exists(ruta_entrada):
        print(f"🚨 Error: No se encontró '{ruta_entrada}'. Créalo y añade los temas.")
        return

    with open(ruta_entrada, "r", encoding="utf-8") as f:
        temario_crudo = f.read()

    # 1. Parsear Metadatos y Texto Limpio
    match_modo = re.search(r'(?:MODO|MODO_GUIA)\s*:\s*([a-zA-Z0-9_]+)', temario_crudo, re.IGNORECASE)
    
    lineas_limpias = [
        l for l in temario_crudo.splitlines() 
        if not (l.strip().upper().startswith("MODO:") or l.strip().upper().startswith("MODO_GUIA:") or l.strip() == "===" or l.strip() == "---")
    ]
    temas_finales = "\n".join(lineas_limpias).strip()
    if not temas_finales:
        temas_finales = temario_crudo.strip()

    # 2. Asignación del Modo (Explícito o Auto-Detectado)
    if match_modo:
        modo_guia = match_modo.group(1).strip().lower()
        print(f"🧠 Catedrático: Modo explícito detectado en cabecera [{modo_guia.upper()}].")
    else:
        modo_guia = detectar_modo_automatico(temas_finales)
        print(f"🧠 Catedrático: Modo auto-asignado por IA [{modo_guia.upper()}].")

    # 3. Recuperación y Auditoría del Contexto
    contexto_crudo = buscar_contexto(temas_finales)
    contexto_validado = ""
    
    if contexto_crudo:
        es_valido = auditar_contexto_rag(temas_finales, contexto_crudo)
        if es_valido:
            contexto_validado = f"--- FRAGMENTOS RECUPERADOS Y VERIFICADOS ---\n{contexto_crudo}\n"
    
    instruccion_pedagogica = PROMPTS_MODALIDADES.get(modo_guia, PROMPTS_MODALIDADES["socratica_guiada"])

    # 4. Construcción de los Prompts Dinámicos (Actor y Crítico)
    system_instruction_actor = f"""Eres un Catedrático Universitario de nivel avanzado y Diseñador de Evaluaciones. Tienes la capacidad de adaptar tu experiencia a cualquier disciplina.
    Tu objetivo es diseñar una guía de ejercicios de alto rigor académico y entregarla en código LaTeX puro, completo y compilable.

    DIRECTRIZ CAMALEÓNICA (NATURALIDAD DE DOMINIO INQUEBRANTABLE):
    Adapta el tono, el vocabulario y la estructura ORGÁNICAMENTE a la disciplina:
    - Si es HUMANIDADES, CIENCIAS SOCIALES, FILOSOFÍA o DERECHO: Diseña preguntas de análisis crítico, desarrollo de ensayos, casos de estudio o interrogación dialéctica. ESTRICTAMENTE PROHIBIDO usar verbos de ciencias exactas ("Calcule", "Demuestre matemáticamente") o inventar variables lógicas absurdas (X, Y) para fenómenos sociales. Que suene a un seminario real de lectura y debate. (El uso de términos como "sistemas", "variables cualitativas", "dinámicas" o "modelos" está permitido y es riguroso).
    - Si es CIENCIAS EXACTAS, INGENIERÍA o MATEMÁTICA: Diseña problemas rigurosos de cálculo, derivación y demostración formal.

    DIRECTRIZ CRÍTICA DE CONOCIMIENTO:
    Si se te proporciona un bloque de 'FRAGMENTOS RECUPERADOS Y VERIFICADOS', utilízalo como base para redactar los enunciados. 
    Si ese bloque NO aparece, confía exclusivamente en tu propio conocimiento interno avanzado para diseñar ejercicios inmaculados.

    INSTRUCCIÓN PEDAGÓGICA (MODO DE GUÍA APLICADO):
    {instruccion_pedagogica}

    REGLAS DE FORMATO LATEX Y COMPATIBILIDAD CON PARSER (INQUEBRANTABLES):
    1. DOCUMENTO INDEPENDIENTE: DEBES generar la estructura completa (\\documentclass{{article}}, paquetes, \\begin{{document}} y \\end{{document}}).
    2. SECCIONES DE PROBLEMAS: El parser requiere que los problemas se dividan usando EXACTAMENTE `\\section*{{...}}`. El texto en llaves debe ser un título descriptivo (Ej: `\\section*{{Análisis de Cohesión Social}}`). JAMÁS uses "Problema 1", "Ejercicio 2". Luego va el enunciado.
    3. INCISOS OBLIGATORIOS: CADA problema DEBE incluir un desglose en incisos utilizando el entorno `\\begin{{enumerate}}` y `\\item`.
    4. NOTACIÓN: Toda variable o término técnico matemático (si aplica al dominio) debe ir en modo matemático estricto ($...$ o \\[...\\]).

    ESTRUCTURA DE TU RESPUESTA (OBLIGATORIA E INQUEBRANTABLE):
    Incluso si estás respondiendo a una crítica de un intento anterior, NUNCA omitas ni cambies el formato de estas etiquetas XML:
    <tema_compendio>
    (Nombre corto de la disciplina, SÓLO minúsculas y guiones bajos. Ej: sociologia_clasica)
    </tema_compendio>
    <diseno_pedagogico>
    (Analiza la disciplina del temario, define el tono adecuado evitando seudo-matematización si es humanidades, y planifica cómo los problemas cumplirán con el modo solicitado).
    </diseno_pedagogico>
    ```latex
    (Código LaTeX completo y compilable).
    ```
    """

    system_instruction_critico = """Eres un Auditor de Calidad Académica y Evaluador de Exámenes.
    Tu trabajo es auditar la guía propuesta por el Catedrático y asegurar que cumple con la Directriz Camaleónica y el Formato Estructural.
    
    CRITERIOS DE RECHAZO (SEVERIDAD ALTA):
    1. SESGO ROBÓTICO O SEUDO-MATEMATIZACIÓN ABSURDA: Si la materia es Humanidades/Ciencias Sociales y el autor intentó forzar ecuaciones matemáticas explícitas, cálculos abstractos (ej: calcular límites morales) o forzar álgebra en conceptos discursivos, RECHÁZALO. 
    ATENCIÓN (REGLA ANTI-PARANOIA): ES TOTALMENTE VÁLIDO en disciplinas sociales usar terminología académica formal como "variables cualitativas", "modelo teórico", "dinámicas", "sistema cerrado" o "umbral crítico". NO rechaces la guía por el uso de estos términos técnicos. Solo penaliza la aplicación ridícula o literal de matemáticas de ingeniería sobre letras.
    2. FORMATO ROTO: Si faltan los \\section*{...} con títulos descriptivos (es decir, si dice "Problema 1" en vez de un título conceptual), o si los incisos no usan \\begin{enumerate}, RECHÁZALO.
    
    FORMATO DE RESPUESTA OBLIGATORIO (JSON STRICT):
    {
        "estado": "APROBADO" o "RECHAZADO",
        "motivo": "Explicación muy breve de qué falló o por qué se aprueba",
        "critica_constructiva": "Si es RECHAZADO, dale instrucciones exactas al autor de cómo arreglar el tono o el formato. Si es APROBADO, déjalo vacío."
    }
    """

    user_prompt = f"""
    Diseña una guía de ejercicios basándote ESTRICTAMENTE en los siguientes temas y requerimientos:
    
    TEMAS SOLICITADOS:
    {temas_finales}
    
    {contexto_validado}
    """

    max_intentos = 3 # Límite LÓGICO de revisiones Actor-Crítico
    intento_actual = 1
    intentos_red = 0 # Límite de RED (Cortacircuitos)
    
    historial_criticas = ""
    bitacora_acumulada = ""
    latex_final = ""
    tema_detectado = "compendio_general"
    pensamiento = ""

    while intento_actual <= max_intentos:
        print(f"   ⚙️  Generando Borrador de la Guía (Intento {intento_actual}/{max_intentos})...")
        
        try:
            # --- TURNO DEL ACTOR ---
            prompt_actual = user_prompt
            if historial_criticas:
                prompt_actual += f"\n\n--- CRÍTICA DEL AUDITOR AL INTENTO ANTERIOR ---\n{historial_criticas}\nCorrige tu respuesta basándote ESTRICTAMENTE en esta crítica. REGLA INQUEBRANTABLE: DEBES INCLUIR OBLIGATORIAMENTE LAS ETIQUETAS XML <tema_compendio> y <diseno_pedagogico> en tu nueva respuesta o el sistema fallará."

            respuesta_actor = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=prompt_actual,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction_actor,
                    temperature=0.3
                )
            )
            
            texto_crudo = respuesta_actor.text.strip()
            
            # Extracción segura de etiquetas XML para la Bitácora
            match_tema = re.search(r'<tema_compendio>(.*?)</tema_compendio>', texto_crudo, re.DOTALL | re.IGNORECASE)
            tema_detectado = match_tema.group(1).strip().replace(" ", "_").lower() if match_tema else "compendio_general"
            tema_detectado = re.sub(r'[^a-z0-9_]', '', tema_detectado)

            match_pensamiento = re.search(r'<diseno_pedagogico>(.*?)</diseno_pedagogico>', texto_crudo, re.DOTALL | re.IGNORECASE)
            pensamiento = match_pensamiento.group(1).strip() if match_pensamiento else "No se detectó bloque de diseño."
            
            bitacora_acumulada += f"=== INTENTO {intento_actual} ===\nCATEDRÁTICO (Razonamiento / Diseño):\n{pensamiento}\n\n"
            
            # Limpieza del LaTeX
            contenido_limpio = re.sub(r'<tema_compendio>.*?</tema_compendio>', '', texto_crudo, flags=re.DOTALL)
            contenido_limpio = re.sub(r'<diseno_pedagogico>.*?</diseno_pedagogico>', '', contenido_limpio, flags=re.DOTALL).strip()
            
            marca_inicio = chr(96) * 3 + 'latex'
            marca_fin = chr(96) * 3
            if contenido_limpio.startswith(marca_inicio): contenido_limpio = contenido_limpio[len(marca_inicio):]
            if contenido_limpio.endswith(marca_fin): contenido_limpio = contenido_limpio[:-len(marca_fin)]
            if contenido_limpio.startswith(chr(96)*3): contenido_limpio = contenido_limpio[3:] 
            
            latex_final = contenido_limpio.strip()

            # --- TURNO DEL CRÍTICO ---
            print(f"   🕵️‍♂️  El Auditor está revisando la naturalidad y el formato de la guía...")
            
            prompt_evaluacion = f"TEMARIO ORIGINAL:\n{temas_finales}\n\nDISEÑO PEDAGÓGICO DEL AUTOR:\n{pensamiento}\n\nGUÍA PROPUESTA:\n{latex_final}"
            
            respuesta_critico = client.models.generate_content(
                model='gemini-3.1-flash-lite', 
                contents=prompt_evaluacion,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction_critico,
                    temperature=0.1,
                    response_mime_type="application/json" 
                )
            )
            
            # Resetear contador de red en caso de éxito en ambas llamadas
            intentos_red = 0
            
            try:
                evaluacion = json.loads(respuesta_critico.text.strip())
                estado = evaluacion.get("estado", "")
                motivo = evaluacion.get("motivo", "")
                
                bitacora_acumulada += f"AUDITOR (Veredicto: {estado}):\nMotivo: {motivo}\nFeedback: {evaluacion.get('critica_constructiva', 'N/A')}\n\n"
                
                if estado == "APROBADO":
                    print(f"      ✅ ¡Guía Aprobada! La naturalidad y estructura son óptimas. ({motivo})")
                    break
                else:
                    print(f"      ❌ Guía Rechazada por el Auditor. Motivo: {motivo}")
                    historial_criticas = evaluacion.get("critica_constructiva", "Ajusta el tono al dominio correcto y revisa el formato.")
                    
                intento_actual += 1
                time.sleep(3)
                
            except json.JSONDecodeError:
                print("      ⚠️ Error decodificando el veredicto del auditor. Aprobando por seguridad...")
                bitacora_acumulada += "AUDITOR: Fallo JSON. Aprobado por fallback.\n\n"
                break
                
        except Exception as e:
            intentos_red += 1
            if intentos_red >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico de red en el Builder tras {MAX_RETRIES} intentos.")
                break # Rompe el bucle para intentar rescatar el borrador generado
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"      ⏳ Límite de API en Builder. Intento de red {intentos_red}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"      🔥 Servidor saturado (503). Intento de red {intentos_red}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"      🚨 Error de red detectado: {e}. Intento de red {intentos_red}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)
            
            # Usar 'continue' asegura que NO incrementamos 'intento_actual', repitiendo la misma iteración lógica
            continue

    if not latex_final:
        print("\n❌ Abortando: No se pudo generar ningún contenido debido a errores críticos de red o cuota.")
        return

    if intento_actual > max_intentos or intentos_red >= MAX_RETRIES:
        if intentos_red >= MAX_RETRIES:
             print("   ⚠️ Bucle abortado por fallos críticos de red. Rescatando el último borrador generado.")
             bitacora_acumulada += f"=== CORTACIRCUITOS ===\nAbortado tras {MAX_RETRIES} fallos de red.\n"
        else:
             print("   ⚠️ Se agotaron los intentos lógicos. Guardando el último borrador (podría tener observaciones del Crítico).")
             bitacora_acumulada += "=== FIN DEL BUCLE ===\nAdvertencia: Límite de correcciones alcanzado.\n"

    try:
        # Guardado en guias_in
        os.makedirs("guias_in", exist_ok=True)
        nombre_base = "guia_generada"
        ruta_guia = os.path.join("guias_in", f"{nombre_base}.tex")
        with open(ruta_guia, "w", encoding="utf-8") as f:
            f.write(latex_final)
        print(f"\n✅ Guía generada y guardada exitosamente en '{ruta_guia}'")

        # Guardado Acumulativo (Compendio)
        os.makedirs("compendio_preguntas", exist_ok=True)
        ruta_compendio = os.path.join("compendio_preguntas", f"{tema_detectado}.tex")
        
        match_body = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', latex_final, re.DOTALL)
        body_to_append = match_body.group(1).strip() if match_body else latex_final
        
        with open(ruta_compendio, "a", encoding="utf-8") as f:
            f.write(f"\n\n% === NUEVA GENERACIÓN ({modo_guia.upper()}): {time.strftime('%Y-%m-%d %H:%M')} ===\n")
            f.write(body_to_append)
            f.write(f"\n% =========================================================\n")
        print(f"📚 Preguntas añadidas al compendio de la materia: '{ruta_compendio}'")

        # Guardado de Bitácora Cognitiva
        os.makedirs("Pensamientos", exist_ok=True)
        ruta_pensamientos = os.path.join("Pensamientos", f"Pensamientos_Builder_{nombre_base}.tex")
        
        with open(ruta_pensamientos, 'w', encoding='utf-8') as f_pens:
            f_pens.write(f"\\documentclass[12pt, a4paper]{{article}}\n")
            f_pens.write(f"\\usepackage[utf8]{{inputenc}}\n\\usepackage{{geometry}}\n\\geometry{{margin=2.5cm}}\n")
            f_pens.write(f"\\usepackage{{listings}}\n")
            f_pens.write(f"\\lstset{{breaklines=true, basicstyle=\\ttfamily\\small}}\n")
            f_pens.write(f"\\title{{Bitácora Cognitiva: Builder \\\\ \\large Tema: {tema_detectado} \\\\ Modo: {modo_guia.replace('_', ' ').title()}}}\n")
            f_pens.write(f"\\author{{Registro de Agente Autónomo}}\n\\begin{{document}}\n\\maketitle\n\n")
            f_pens.write(f"\\section*{{Trazas del Bucle Actor-Crítico}}\n")
            f_pens.write(f"\\begin{{lstlisting}}\n")
            f_pens.write(bitacora_acumulada)
            f_pens.write(f"\n\\end{{lstlisting}}\n")
            f_pens.write(f"\n\\end{{document}}\n")
        
        print(f"🧠 Bitácora cognitiva guardada en '{ruta_pensamientos}'")
        print("\n🚀 Siguiente paso: Ejecuta 'python guide_parser.py' para estructurarla en JSON.")

    except Exception as e:
        print(f"🚨 Error durante el proceso de guardado de archivos: {e}")

if __name__ == "__main__":
    construir_guia()