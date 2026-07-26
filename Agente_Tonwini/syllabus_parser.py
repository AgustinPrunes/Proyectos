import os
import json
import time
import re
from pypdf import PdfReader
from google import genai
from google.genai import types
from dotenv import load_dotenv

# =========================================================================
# HIPERPARÁMETROS DE SEGURIDAD Y CONFIGURACIÓN (RC 1.0)
# =========================================================================
MAX_RETRIES = 5  # Cortacircuitos anti-drenaje de tokens y prevención de bucles infinitos
EXTENSIONES_PERMITIDAS = {'.pdf', '.txt'} # Lista Blanca de Ingesta
# =========================================================================

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")
client = genai.Client(api_key=api_key)

def leer_pdf_syllabus(carpeta="syllabus"):
    if not os.path.exists(carpeta):
        os.makedirs(carpeta)
        print(f"⚠️ Carpeta '{carpeta}' creada. Coloca el programa ahí.")
        return None

    # BLINDAJE: Filtro estricto contra archivos ocultos y validación por Lista Blanca
    archivos_validos = []
    for f in os.listdir(carpeta):
        if f.startswith('.'):
            continue
        _, extension = os.path.splitext(f.lower())
        if extension in EXTENSIONES_PERMITIDAS:
            archivos_validos.append(f)

    if not archivos_validos:
        print(f"⚠️ No hay archivos válidos (.pdf, .txt) en '{carpeta}'.")
        return None

    ruta_archivo = os.path.join(carpeta, archivos_validos[0])
    print(f"📄 Analizando programa: {archivos_validos[0]}...")
    
    texto_completo = ""
    try:
        if ruta_archivo.endswith('.pdf'):
            lector = PdfReader(ruta_archivo)
            for pagina in lector.pages:
                texto_extraido = pagina.extract_text()
                if texto_extraido:
                    texto_completo += texto_extraido + "\n"
        elif ruta_archivo.endswith('.txt'):
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                texto_completo = f.read()
                
        return texto_completo
    except Exception as e:
        print(f"🚨 Error al leer el documento: {e}")
        return None

def sanear_y_cargar_json(texto_crudo):
    """
    Función determinista para sanear el JSON eliminando bloques markdown y
    escapando las barras invertidas huérfanas de LaTeX que rompen json.loads().
    """
    contenido = texto_crudo.strip()
    contenido = re.sub(r'^```json', '', contenido, flags=re.IGNORECASE)
    contenido = re.sub(r'```$', '', contenido).strip()
    contenido = re.sub(r'^```', '', contenido).strip()
    
    try:
        return json.loads(contenido)
    except json.JSONDecodeError:
        print("   🛡️ JSON malformado detectado (Posibles barras de LaTeX). Aplicando saneamiento Regex...")
        contenido_rescatado = re.sub(r'\\(?!([ntrbf"/\\]|u[0-9a-fA-F]{4}))', r'\\\\', contenido)
        try:
            return json.loads(contenido_rescatado)
        except Exception as e:
            print(f"   🚨 Error crítico: El JSON es irrecuperable de forma automatizada. Detalle: {e}")
            return None

def fragmentar_texto_inteligente(texto, max_words=1200):
    """
    Divide el texto buscando primero Módulos/Unidades, y como fallback usa agrupación de párrafos.
    Garantiza que la IA no sufra truncamiento por exceso de salida.
    """
    # 1. Intentar fragmentar por "### MÓDULO" (Ruta automática del temario_builder)
    if "### MÓDULO" in texto:
        fragmentos = re.split(r'(?=### MÓDULO)', texto)
        return [f.strip() for f in fragmentos if f.strip()]
    
    # 2. Intentar fragmentar por "UNIDAD" o "CAPÍTULO" si es un PDF externo estándar
    if re.search(r'\n\s*(UNIDAD|CAP[IÍ]TULO)\s+\d+', texto, re.IGNORECASE):
        fragmentos = re.split(r'(?=\n\s*(?:UNIDAD|CAP[IÍ]TULO)\s+\d+)', texto, flags=re.IGNORECASE)
        chunks = []
        chunk_actual = ""
        for f in fragmentos:
            if len(chunk_actual.split()) + len(f.split()) > max_words and chunk_actual:
                chunks.append(chunk_actual.strip())
                chunk_actual = f
            else:
                chunk_actual += "\n\n" + f
        if chunk_actual.strip():
            chunks.append(chunk_actual.strip())
        return chunks

    # 3. Fallback universal (Para PDFs caóticos): Agrupación por párrafos
    parrafos = texto.split('\n\n')
    chunks = []
    chunk_actual = ""
    
    for p in parrafos:
        if len(chunk_actual.split()) + len(p.split()) > max_words and chunk_actual:
            chunks.append(chunk_actual.strip())
            chunk_actual = p + "\n\n"
        else:
            chunk_actual += p + "\n\n"
    
    if chunk_actual.strip():
        chunks.append(chunk_actual.strip())
        
    return chunks

def generar_esqueleto_base(texto_fragmento):
    """Fase 1: Extrae solo Capítulos y Secciones principales de un fragmento de texto."""
    
    system_instruction = """Eres un Arquitecto Académico. Tu tarea es extraer la estructura MACRO de un fragmento de un programa de curso.
    Genera un JSON estrictamente con la metadata, capítulos y secciones presentes en el fragmento. No incluyas subsecciones aún.
    
    REGLA CRÍTICA DE SÍNTESIS DE TÍTULOS (ANTI-DESBORDE LATEX):
    Para los campos "titulo" (tanto de capítulos como de secciones), DEBES inventar o sintetizar un título ultra-corto, elegante y académico (MÁXIMO 5 a 6 palabras).
    Si el temario original tiene una descripción kilométrica, extrae solo el núcleo conceptual para el campo "titulo".
    
    Para cada sección, redacta su 'preambulo' teórico profundo, aquí SÍ debes extenderte y capturar la esencia descriptiva del temario.
    
    ESTRUCTURA EXIGIDA:
    {
      "metadata": {
        "titulo": "Título Inferred",
        "autor": "Autor Extraído o Genérico",
        "nivel": "Nivel Extraído o Genérico"
      },
      "capitulos": [
        {
          "id": "cap_01",
          "numero": 1,
          "titulo": "Nombre Corto del Capítulo",
          "secciones": [
            {
              "id": "sec_1_1",
              "titulo": "Nombre Corto de Sección",
              "preambulo": "Preámbulo introductorio extenso basado en la descripción original del temario..."
            }
          ]
        }
      ]
    }
    """

    user_prompt = f"Genera el esqueleto base para el siguiente fragmento del programa:\n\n{texto_fragmento}"

    # =========================================================================
    # BÓVEDA DE RESILIENCIA (Bucle Controlado Anti-Drenaje)
    # =========================================================================
    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                    response_mime_type="application/json" 
                )
            )
            
            datos_saneados = sanear_y_cargar_json(respuesta.text.strip())
            if datos_saneados:
                return datos_saneados
            else:
                intentos += 1
                if intentos >= MAX_RETRIES:
                    print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo irrecuperable de JSON en Esqueleto Base tras {MAX_RETRIES} intentos.")
                    return None
                print(f"   ⚠️ Reintentando generación de esqueleto base debido a JSON irrecuperable. Intento {intentos}/{MAX_RETRIES}...")
                time.sleep(5)
                
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico de red en Esqueleto Base tras {MAX_RETRIES} intentos.")
                return None
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"   ⏳ Límite de API en Esqueleto Base. Intento {intentos}/{MAX_RETRIES}. Esperando 60s antes de reintentar...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"   🔥 Servidor de Google saturado (503). Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"   🚨 Error de red detectado: {e}. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)
    return None

def expandir_seccion(capitulo_titulo, seccion_titulo, texto_syllabus):
    """Fase 2: Por cada sección, genera un desglose exhaustivo de sus incisos y bloques."""
    
    system_instruction = """Eres un Arquitecto Académico de élite. 
    Tu tarea es aplicar FRAGMENTACIÓN ATÓMICA Y MAPEO 1:1 EXHAUSTIVO a una sección específica de un temario, estructurándola para cualquier disciplina universitaria.
    
    CRÍTICA DE COMPORTAMIENTO PASADO: Antes creabas UNA SOLA subsección que repetía exactamente el nombre de la Sección principal. ESTO ESTÁ ESTRICTAMENTE PROHIBIDO.
    
    REGLAS DE ORO:
    1. MAPEO 1:1: Si el texto de la Sección contiene una lista de conceptos (enumerados o separados por comas), DEBES crear una "subseccion" INDEPENDIENTE por CADA UNO de esos conceptos. No asumas ni agrupes.
    2. INCISOS SECUENCIALES: Dentro de cada subsección, crea múltiples "incisos" que representen el desarrollo progresivo del tema (ej. Contexto Inicial, Planteamiento Principal, Análisis Detallado/Desglose, Ejemplos Prácticos).
    3. NO RESUMAS LA INFORMACIÓN: Conserva toda la riqueza de la descripción original.
    
    REGLA CRÍTICA DE TÍTULOS ULTRA-CORTOS (ANTI-DESBORDE LATEX):
    Para TODOS los campos "titulo" (tanto de subsecciones como de incisos), DEBES sintetizar un título ultra-corto, elegante y académico (MÁXIMO 5 a 6 palabras).
    TODA la oración descriptiva kilométrica original del temario DEBE ser desplazada íntegramente al campo "instruccion" dentro de los "bloques". ESTÁ ESTRICTAMENTE PROHIBIDO colocar descripciones largas en los campos "titulo".
    
    ESTRUCTURA EXIGIDA (Retorna SOLO este objeto JSON):
    {
      "subsecciones": [
        {
          "id": "subsec_generado_1",
          "titulo": "Concepto Breve Extraído",
          "incisos": [
            {
              "id": "inciso_generado_1_1",
              "titulo": "Fase Inicial Corta",
              "bloques": [
                {"tipo": "exposicion", "instruccion": "[AQUÍ VA LA DESCRIPCIÓN KILOMÉTRICA] Explicación académica profunda y completa de toda la descripción del temario..."}
              ]
            },
            {
              "id": "inciso_generado_1_2",
              "titulo": "Desarrollo Corto",
              "bloques": [
                {"tipo": "desarrollo", "instruccion": "[AQUÍ VA LA DESCRIPCIÓN KILOMÉTRICA] Desarrollo analítico y exhaustivo paso a paso de..."}
              ]
            }
          ]
        }
      ]
    }
    """

    user_prompt = f"""
    TEMARIO COMPLETO DE REFERENCIA:
    {texto_syllabus}
    
    TAREA:
    Busca en el temario la parte que corresponde al Capítulo '{capitulo_titulo}', Sección '{seccion_titulo}'.
    Desglosa OBLIGATORIAMENTE todos los puntos, enumeraciones o conceptos clave contenidos en esa sección, creando una 'subseccion' distinta para cada uno de ellos, respetando la regla de títulos ultra-cortos.
    """

    # =========================================================================
    # BÓVEDA DE RESILIENCIA (Bucle Controlado Anti-Drenaje)
    # =========================================================================
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
            
            datos_saneados = sanear_y_cargar_json(respuesta.text.strip())
            if datos_saneados is not None and "subsecciones" in datos_saneados:
                return datos_saneados.get("subsecciones", [])
            else:
                intentos += 1
                if intentos >= MAX_RETRIES:
                    print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo irrecuperable de JSON expandiendo '{seccion_titulo}' tras {MAX_RETRIES} intentos.")
                    return []
                print(f"   ⚠️ Reintentando expansión de '{seccion_titulo}' debido a JSON irrecuperable. Intento {intentos}/{MAX_RETRIES}...")
                time.sleep(5)
                
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico de red expandiendo '{seccion_titulo}' tras {MAX_RETRIES} intentos.")
                return []
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"   ⏳ Límite de API en Expansión de Sección. Intento {intentos}/{MAX_RETRIES}. Esperando 60s antes de reintentar...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"   🔥 Servidor de Google saturado (503). Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"   🚨 Error de red detectado: {e}. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)
    return []

def generar_json_desde_syllabus(texto_syllabus):
    try:
        # Paso 1: Fragmentación y consolidación del esqueleto maestro
        chunks = fragmentar_texto_inteligente(texto_syllabus)
        print(f"🧩 Texto original fragmentado en {len(chunks)} bloques para evitar truncamiento cognitivo.")
        
        esqueleto_maestro = {"metadata": {}, "capitulos": []}
        
        for i, chunk in enumerate(chunks):
            print(f"🧠 [Fase 1/2] Extrayendo estructura del bloque {i+1}/{len(chunks)}...")
            esqueleto_parcial = generar_esqueleto_base(chunk)
            
            if esqueleto_parcial:
                # Conservar la metadata del primer bloque válido
                if not esqueleto_maestro["metadata"] and "metadata" in esqueleto_parcial:
                    esqueleto_maestro["metadata"] = esqueleto_parcial["metadata"]
                
                if "capitulos" in esqueleto_parcial:
                    esqueleto_maestro["capitulos"].extend(esqueleto_parcial["capitulos"])
            else:
                print(f"⚠️ Advertencia: No se pudo extraer estructura del bloque {i+1}. Omitiendo y continuando...")
                
        if not esqueleto_maestro["capitulos"]:
            print("🚨 Error: No se pudo generar ningún capítulo válido desde los bloques. Abortando expansión.")
            return None
            
        # Re-indexación geométrica para asegurar el correcto acoplamiento en orchestrator.py
        for idx_cap, cap in enumerate(esqueleto_maestro["capitulos"]):
            cap["numero"] = idx_cap + 1
            cap["id"] = f"cap_{idx_cap + 1:02d}"
            for idx_sec, sec in enumerate(cap.get("secciones", [])):
                sec["id"] = f"{cap['id']}_sec_{idx_sec + 1}"
        
        total_secciones = sum(len(cap.get("secciones", [])) for cap in esqueleto_maestro.get("capitulos", []))
        print(f"\n🔍 [Fase 2/2] Se consolidó un esqueleto maestro con {len(esqueleto_maestro['capitulos'])} capítulos y {total_secciones} secciones.")
        print("🚀 Iniciando expansión profunda iterativa...")
        
        # Paso 2: Iterar y poblar las subsecciones
        contador = 1
        for cap in esqueleto_maestro.get("capitulos", []):
            for sec in cap.get("secciones", []):
                print(f"   ⚙️ Expandiendo [{contador}/{total_secciones}]: {sec['titulo']}")
                
                subsecciones_detalladas = expandir_seccion(cap['titulo'], sec['titulo'], texto_syllabus)
                
                # Ajuste de IDs atómicos
                for idx_sub, sub in enumerate(subsecciones_detalladas):
                    sub['id'] = f"{sec['id']}_{idx_sub+1}"
                    for idx_inc, inciso in enumerate(sub.get('incisos', [])):
                        inciso['id'] = f"{sub['id']}_i{idx_inc+1}"
                        
                sec["subsecciones"] = subsecciones_detalladas
                
                contador += 1
                time.sleep(2) 
                
        return json.dumps(esqueleto_maestro, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"🚨 Error catastrófico en la orquestación del JSON: {e}")
        return None

if __name__ == "__main__":
    texto = leer_pdf_syllabus()
    if texto:
        json_generado = generar_json_desde_syllabus(texto)
        if json_generado:
            with open("book_structure.json", "w", encoding="utf-8") as f:
                f.write(json_generado)
            print("\n✅ 'book_structure.json' generado exitosamente con estrategia Multi-Llamada y semántica general blindada.")