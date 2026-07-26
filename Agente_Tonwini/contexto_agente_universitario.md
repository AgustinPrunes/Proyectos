==================================================
ARQUITECTURA DEL AGENTE AUTÓNOMO UNIVERSITARIO
==================================================

📁 ESTRUCTURA DE DIRECTORIOS:

📦 [Proyecto Raíz]/
    📄 book_structure.json
    📄 build_vector_db.py
    📄 check_models.py
    📄 compilar_guia.py
    📄 compilar_libro.py
    📄 compiler_service.py
    📄 conocimiento_grafo.json
    📄 contexto_agente_universitario.md
    📄 context_packer.py
    📄 generator_agent.py
    📄 guia_builder.py
    📄 guide_parser.py
    📄 guide_structure.json
    📄 llm_corrector.py
    📄 ocr_transcriber.py
    📄 orchestrator.py
    📄 solver_agent.py
    📄 syllabus_parser.py
    📄 temario_bruto.txt
    📄 temario_builder.py
    📄 temas_guia.txt
    📄 Tonwini.py
    📄 Tonwini_setup.py
    📄 ver_modelos.py
    📂 bibliografia/ (Contenido omitido)
    📂 bibliografia_escaneada/ (Contenido omitido)
    📂 chroma_db/ (Contenido omitido)
    📂 compendio_preguntas/ (Contenido omitido)
    📂 Errores/ (Contenido omitido)
    📂 guias_in/ (Contenido omitido)
    📂 guias_out/ (Contenido omitido)
    📂 PDFs_guias/ (Contenido omitido)
    📂 PDFs_libros/ (Contenido omitido)
    📂 Pensamientos/ (Contenido omitido)
    📂 syllabus/ (Contenido omitido)
    📂 template_base/
    📂 venv/ (Contenido omitido)
    📂 __pycache__/ (Contenido omitido)

==================================================
CÓDIGO FUENTE DE LOS ARCHIVOS
==================================================

==================================================
📄 ARCHIVO: build_vector_db.py
Ruta: .\build_vector_db.py
==================================================
```python
import os
import json
import re
import time
import shutil
import uuid
import PyPDF2
import networkx as nx
import chromadb
from google import genai
from google.genai import types
from dotenv import load_dotenv

# =========================================================================
# HIPERPARÁMETROS DE SEGURIDAD Y CONFIGURACIÓN
# =========================================================================
MAX_RETRIES = 5  # Cortacircuitos anti-drenaje de tokens
EXTENSIONES_PERMITIDAS = {'.pdf', '.txt', '.tex', '.md'} # Lista Blanca de Ingesta
# =========================================================================

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")
client = genai.Client(api_key=api_key)

def extraer_texto_pdf(ruta_pdf):
    texto = ""
    try:
        with open(ruta_pdf, 'rb') as f:
            lector = PyPDF2.PdfReader(f)
            for pagina in lector.pages:
                extraido = pagina.extract_text()
                if extraido:
                    texto += extraido + "\n"
    except Exception as e:
        print(f"❌ Error leyendo PDF {ruta_pdf}: {e}")
    return texto

def dividir_en_chunks(texto, max_words=400):
    palabras = texto.split()
    chunks = []
    for i in range(0, len(palabras), max_words):
        chunk = " ".join(palabras[i:i + max_words])
        chunks.append(chunk)
    return chunks

def extraer_grafo_con_llm(chunk, chunk_id, archivo_origen):
    system_instruction = """Eres un experto analista de datos y grafos de conocimiento.
    Tu tarea es leer el fragmento de texto proporcionado y extraer los conceptos clave (nodos) y las relaciones entre ellos (aristas).
    Debes devolver ÚNICAMENTE un JSON válido con la siguiente estructura exacta:
    {
      "nodos": ["Concepto A", "Concepto B"],
      "aristas": [
         {"origen": "Concepto A", "destino": "Concepto B", "relacion": "depende de"}
      ]
    }
    Si el fragmento no contiene información conceptual útil, devuelve las listas vacías: {"nodos": [], "aristas": []}."""

    user_prompt = f"FRAGMENTO DE TEXTO (Archivo: {archivo_origen}):\n{chunk}"

    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            texto_json = response.text.strip()
            # Limpieza básica por si el LLM inyecta bloques markdown ignorando el mime_type
            if texto_json.startswith("```json"):
                texto_json = texto_json[7:]
            if texto_json.endswith("```"):
                texto_json = texto_json[:-3]
                
            datos = json.loads(texto_json.strip())
            return datos.get("nodos", []), datos.get("aristas", [])

        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS: Fallo extrayendo grafo tras {MAX_RETRIES} intentos. Saltando fragmento para evitar bucle.")
                return [], [] 
            
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                print(f"      ⏳ Límite de API en Grafo. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
            else:
                print(f"      ⚠️ Error decodificando grafo. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)

def procesar_bibliografia():
    directorio_biblio = "bibliografia"
    directorio_escaneada = "bibliografia_escaneada"
    ruta_grafo = "conocimiento_grafo.json"

    os.makedirs(directorio_biblio, exist_ok=True)
    os.makedirs(directorio_escaneada, exist_ok=True)

    cliente_chroma = chromadb.PersistentClient(path="chroma_db")
    coleccion = cliente_chroma.get_or_create_collection(name="conocimiento_fisica")

    if os.path.exists(ruta_grafo):
        try:
            with open(ruta_grafo, 'r', encoding='utf-8') as f:
                datos_grafo = json.load(f)
                G = nx.node_link_graph(datos_grafo)
        except Exception:
            G = nx.DiGraph()
    else:
        G = nx.DiGraph()

    archivos = os.listdir(directorio_biblio)
    if not archivos:
        print(f"⚠️ La carpeta '{directorio_biblio}' está vacía. No hay datos para ingerir.")
        return

    print(f"🚀 Iniciando Pipeline de Ingesta (Cerebro Híbrido)...")

    for archivo in archivos:
        # 1. BLINDAJE: Evitar lectura de .gitkeep, .DS_Store o cualquier archivo oculto
        if archivo.startswith('.'):
            continue
            
        # 2. BLINDAJE: Filtro de Lista Blanca Estricta
        _, extension = os.path.splitext(archivo.lower())
        if extension not in EXTENSIONES_PERMITIDAS:
            print(f"   ⏭️ Ignorando archivo no soportado por Lista Blanca: {archivo}")
            continue

        ruta_archivo = os.path.join(directorio_biblio, archivo)
        print(f"\n📄 Procesando: {archivo}...")

        texto_completo = ""
        if extension == ".pdf":
            texto_completo = extraer_texto_pdf(ruta_archivo)
            texto_limpio = re.sub(r'\s+', '', texto_completo)
            
            if len(texto_limpio) < 50:
                print(f"   ⚠️ PDF escaneado o vacío detectado. Moviendo a '{directorio_escaneada}' para OCR...")
                try:
                    shutil.move(ruta_archivo, os.path.join(directorio_escaneada, archivo))
                except Exception as e:
                    print(f"   ❌ Error moviendo archivo a OCR: {e}")
                continue
        else:
            # 3. BLINDAJE: Prevención de lectura de binarios falsificados
            try:
                with open(ruta_archivo, "r", encoding="utf-8") as f:
                    texto_completo = f.read()
            except UnicodeDecodeError:
                print(f"   ❌ Error de codificación leyendo {archivo}. El archivo está corrupto o es un binario disfrazado.")
                continue

        if not texto_completo.strip():
            print(f"   ⚠️ El archivo {archivo} no contiene texto procesable.")
            continue

        chunks = dividir_en_chunks(texto_completo, max_words=400)
        print(f"   🧩 Dividido en {len(chunks)} fragmentos atómicos. Inyectando en Cerebro Híbrido...")

        # Transacciones Atómicas (Sección preservada intacta)
        exito_total = True
        temp_nodos = []
        temp_aristas = []
        temp_docs = []
        temp_metadatas = []
        temp_ids = []

        for idx, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            
            temp_docs.append(chunk)
            temp_metadatas.append({"origen": archivo, "chunk_index": idx})
            temp_ids.append(chunk_id)

            print(f"      🧠 LLM: Extrayendo topología de grafo para fragmento {idx+1}/{len(chunks)}...")
            nodos, aristas = extraer_grafo_con_llm(chunk, chunk_id, archivo)
            
            temp_nodos.extend(nodos)
            temp_aristas.extend(aristas)
            
            time.sleep(2)

        if exito_total:
            try:
                if temp_docs:
                    coleccion.add(
                        documents=temp_docs,
                        metadatas=temp_metadatas,
                        ids=temp_ids
                    )
                
                for nodo in temp_nodos:
                    G.add_node(nodo)
                for arista in temp_aristas:
                    origen = arista.get("origen")
                    destino = arista.get("destino")
                    relacion = arista.get("relacion", "se relaciona con")
                    if origen and destino:
                        G.add_edge(origen, destino, relacion=relacion)
                        
                datos_grafo = nx.node_link_data(G)
                with open(ruta_grafo, 'w', encoding='utf-8') as f:
                    json.dump(datos_grafo, f, ensure_ascii=False, indent=4)
                    
                print(f"   ✅ Archivo '{archivo}' asimilado exitosamente en BD Vectorial y Grafo.")
            except Exception as e:
                print(f"   ❌ Error Crítico al realizar commit en bases de datos para '{archivo}': {e}")
        else:
            print(f"   ⚠️ Fallo procesando '{archivo}'. Transacción atómica abortada para no corromper la BD.")

    print("\n🏆 ¡PIPELINE DE INGESTA COMPLETADO! Cerebro Híbrido actualizado.")

if __name__ == "__main__":
    procesar_bibliografia()
```

==================================================
📄 ARCHIVO: check_models.py
Ruta: .\check_models.py
==================================================
```python
import os
import requests
from dotenv import load_dotenv

# Cargamos tu clave
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("🚨 No se encontró la API Key.")
    exit()

print("🔍 Consultando a Google los modelos disponibles para tu cuenta...")

# Hacemos la llamada directa a la API
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
respuesta = requests.get(url)

if respuesta.status_code == 200:
    datos = respuesta.json()
    print("\n✅ MODELOS DISPONIBLES PARA GENERAR TEXTO:")
    print("-" * 50)
    for modelo in datos.get('models', []):
        # Filtramos solo los modelos que sirven para generar contenido
        if 'generateContent' in modelo.get('supportedGenerationMethods', []):
            # Limpiamos el prefijo 'models/' para que veas el string exacto
            nombre_limpio = modelo['name'].replace('models/', '')
            print(nombre_limpio)
    print("-" * 50)
else:
    print(f"🚨 Error al consultar la API: {respuesta.status_code}")
    print(respuesta.text)
```

==================================================
📄 ARCHIVO: compilar_guia.py
Ruta: .\compilar_guia.py
==================================================
```python
import os
import json
import subprocess
import time
import re
from pypdf import PdfWriter

# =========================================================================
# HIPERPARÁMETROS DE COMPILACIÓN Y CARPETAS
# =========================================================================
MAX_RETRIES = 5
CARPETA_IN = "guias_in"
CARPETA_OUT = "guias_out"
CARPETA_PDFS = "PDFs_guias"

def limpiar_nombre_carpeta(texto):
    texto_limpio = re.sub(r'[^a-zA-Z0-9]', '_', texto)
    texto_limpio = re.sub(r'_+', '_', texto_limpio)
    return texto_limpio.strip('_')

def obtener_archivo_mas_reciente(carpeta, extension):
    """
    Escanea la carpeta y devuelve la ruta del archivo con la extensión dada
    que haya sido modificado/creado más recientemente.
    """
    if not os.path.exists(carpeta):
        return None
        
    archivos = [os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.endswith(extension)]
    if not archivos:
        return None
        
    # max() con key=os.path.getmtime nos asegura obtener el archivo más "fresco"
    archivo_reciente = max(archivos, key=os.path.getmtime)
    return archivo_reciente

def ejecutar_curacion_llm(ruta_tex, log_path):
    """
    Invoca al agente de auto-curación de forma segura leyendo el error
    y pasándolo directamente a la función 'aplicar_correccion' de tu llm_corrector.
    """
    try:
        import llm_corrector
        
        # Leemos el contenido del error para pasárselo a la IA
        mensaje_error = ""
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                mensaje_error = f.read()
                
        # Llamamos a la función correcta de tu script
        if hasattr(llm_corrector, 'aplicar_correccion'):
            llm_corrector.aplicar_correccion(ruta_tex, mensaje_error)
        else:
            print("   ⚠️ Error de integración: llm_corrector.py no tiene la función 'aplicar_correccion'.")
            
    except Exception as e:
        print(f"   🚨 Error crítico al intentar ejecutar el corrector LLM: {e}")

def compilar_latex_con_blindaje(ruta_tex):
    """
    Motor Inmortal de Compilación: Si pdflatex arroja un error de sintaxis,
    captura el log e invoca al LLM Crítico para repararlo en un bucle cerrado.
    """
    print(f"\n⚙️ Iniciando compilación blindada de: {ruta_tex}")
    directorio = os.path.dirname(ruta_tex)
    archivo_tex = os.path.basename(ruta_tex)
    nombre_base = os.path.splitext(archivo_tex)[0]
    ruta_pdf = os.path.join(directorio, f"{nombre_base}.pdf")
    
    intentos = 0
    while intentos < MAX_RETRIES:
        print(f"   ▶️ Intento de compilación {intentos + 1}/{MAX_RETRIES}...")
        
        # Limpieza quirúrgica de archivos residuales para evitar falsos errores de caché
        for ext in ['.aux', '.log', '.out']:
            res = os.path.join(directorio, f"{nombre_base}{ext}")
            if os.path.exists(res):
                try:
                    os.remove(res)
                except Exception:
                    pass
                
        proceso = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", archivo_tex],
            cwd=directorio,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if proceso.returncode == 0 and os.path.exists(ruta_pdf):
            print(f"   ✅ Compilación exitosa: {ruta_pdf}")
            return ruta_pdf
            
        print(f"   ❌ Error de sintaxis LaTeX detectado en {archivo_tex}.")
        log_path = os.path.join(directorio, f"{nombre_base}_error.log")
        
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(proceso.stdout)
            if proceso.stderr:
                f.write("\n" + proceso.stderr)
        
        print("   🛠️ Invocando al agente crítico (llm_corrector.py) para reparar el código...")
        ejecutar_curacion_llm(ruta_tex, log_path)
        
        intentos += 1
        time.sleep(2) # Pausa estratégica para dar respiro a los I/O del disco
        
    print(f"🚨 CORTACIRCUITOS ACTIVADO: No se pudo compilar {ruta_tex} tras {MAX_RETRIES} intentos.")
    return None

def limpiar_archivos_residuales():
    """
    Elimina los archivos auxiliares de compilación (.aux, .log, .out, _error.log)
    y los PDFs intermedios creados en guias_in y guias_out, dejando intactos únicamente los .tex.
    """
    print("\n🧹 Limpiando archivos auxiliares e intermedios...")
    carpetas = [CARPETA_IN, CARPETA_OUT]
    
    for carpeta in carpetas:
        if os.path.exists(carpeta):
            for archivo in os.listdir(carpeta):
                # Mantener intactos los archivos .tex y borrar residuos de compilación y PDFs intermedios
                if not archivo.endswith('.tex'):
                    if archivo.endswith(('.aux', '.log', '.out', '_error.log', '.pdf')):
                        ruta_archivo = os.path.join(carpeta, archivo)
                        try:
                            os.remove(ruta_archivo)
                            print(f"   🗑️ Eliminado: {ruta_archivo}")
                        except Exception as e:
                            print(f"   ⚠️ No se pudo eliminar {ruta_archivo}: {e}")

def orquestar_fusion_guias(json_path="guide_structure.json"):
    print("🚀 Motor de Fusión y Curación de Guías (Pipeline de Práctica)...")
    
    # Aseguramos la existencia del ecosistema de salida
    if not os.path.exists(CARPETA_PDFS):
        os.makedirs(CARPETA_PDFS)
        print(f"📁 Directorio base '{CARPETA_PDFS}/' creado exitosamente.")
        
    # Intentamos obtener un título base (útil para nombrar el archivo final)
    titulo_base = "Guia_Generica"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                estructura = json.load(f)
                titulo_bruto = estructura.get('metadata', {}).get('titulo', 'Guia_Generica')
                titulo_base = limpiar_nombre_carpeta(titulo_bruto)
        except Exception:
            pass
    
    print(f"\n🔍 Buscando piezas orgánicas más recientes...")
    
    pdf_enunciado = None
    pdf_resolucion = None
    
    # =========================================================================
    # FASE 1: PROCESAR ENUNCIADO (guias_in) - BÚSQUEDA DEL MÁS RECIENTE
    # =========================================================================
    ruta_pdf_in_reciente = obtener_archivo_mas_reciente(CARPETA_IN, ".pdf")
    ruta_tex_in_reciente = obtener_archivo_mas_reciente(CARPETA_IN, ".tex")
    
    # Prioridad: Si hay un PDF reciente (subida manual) y un TEX reciente, comparamos tiempos. 
    # Por defecto, asumiremos que si hay un .tex fresco, vino del Builder automático.
    if ruta_tex_in_reciente:
        # Validar si el PDF no es aún MÁS reciente (ej. usuario reemplazó el PDF manual)
        if ruta_pdf_in_reciente and os.path.getmtime(ruta_pdf_in_reciente) > os.path.getmtime(ruta_tex_in_reciente):
            print(f"   📄 Vía Manual Detectada: PDF de enunciado más reciente en {ruta_pdf_in_reciente}")
            pdf_enunciado = ruta_pdf_in_reciente
        else:
            print(f"   📄 Vía Automática Detectada: LaTeX de enunciado más reciente es {ruta_tex_in_reciente}. Procediendo a compilar...")
            pdf_enunciado = compilar_latex_con_blindaje(ruta_tex_in_reciente)
    elif ruta_pdf_in_reciente:
        print(f"   📄 Vía Manual Detectada: PDF de enunciado más reciente en {ruta_pdf_in_reciente}")
        pdf_enunciado = ruta_pdf_in_reciente
    else:
        print(f"   ⚠️ No se encontró PDF ni TEX base de enunciado en {CARPETA_IN}.")

    # =========================================================================
    # FASE 2: PROCESAR RESOLUCIÓN (guias_out) - BÚSQUEDA DEL MÁS RECIENTE
    # =========================================================================
    ruta_tex_out_reciente = obtener_archivo_mas_reciente(CARPETA_OUT, ".tex")
    
    if ruta_tex_out_reciente:
        print(f"   📝 LaTeX de resolución más reciente detectado: {ruta_tex_out_reciente}. Procediendo a compilar...")
        pdf_resolucion = compilar_latex_con_blindaje(ruta_tex_out_reciente)
    else:
        print(f"   ⚠️ No se encontró ningún archivo LaTeX resuelto en {CARPETA_OUT}.")

    # =========================================================================
    # FASE 3: FUSIÓN MAESTRA Y EMPAQUETADO FINAL
    # =========================================================================
    print("\n🔗 Iniciando ensamblaje topológico de la Guía Completa...")
    if pdf_enunciado or pdf_resolucion:
        merger = PdfWriter()
        
        try:
            if pdf_enunciado:
                merger.append(pdf_enunciado)
                print("   ➕ [1/2] Enunciado base añadido al índice del documento final.")
                
            if pdf_resolucion:
                merger.append(pdf_resolucion)
                print("   ➕ [2/2] Pauta de resolución (Solver) acoplada al final del documento.")
                
            ruta_final = os.path.join(CARPETA_PDFS, f"{titulo_base}_Guia_Completa.pdf")
            merger.write(ruta_final)
            merger.close()
            print(f"✅ ¡ÉXITO ABSOLUTO! Guía unificada y compilada correctamente en:\n   -> {ruta_final}")
            
            # Limpieza post-compilación
            limpiar_archivos_residuales()
            
        except Exception as e:
            print(f"🚨 Error crítico durante la fusión de PDFs mediante pypdf: {e}")
    else:
        print("❌ Operación abortada por el orquestador: No se lograron generar o encontrar los PDFs básicos para la fusión.")

if __name__ == "__main__":
    orquestar_fusion_guias()
```

==================================================
📄 ARCHIVO: compilar_libro.py
Ruta: .\compilar_libro.py
==================================================
```python
import os
import subprocess
import time
import re
import shutil

# =========================================================================
# HIPERPARÁMETROS DE COMPILACIÓN Y CARPETAS
# =========================================================================
MAX_RETRIES = 5
CARPETA_PDFS_LIBROS = "PDFs_libros"

def limpiar_nombre_carpeta(texto):
    texto_limpio = re.sub(r'[^a-zA-Z0-9]', '_', texto)
    texto_limpio = re.sub(r'_+', '_', texto_limpio)
    return texto_limpio.strip('_')

def ejecutar_curacion_llm(ruta_tex, log_path):
    """
    Invoca al agente de auto-curación de forma segura.
    Intenta importar la función de llm_corrector, y si falla la firma exacta,
    lo ejecuta como un subproceso de consola.
    """
    try:
        import llm_corrector
        if hasattr(llm_corrector, 'corregir_error_latex'):
            llm_corrector.corregir_error_latex(ruta_tex, log_path)
        elif hasattr(llm_corrector, 'corregir_latex'):
            llm_corrector.corregir_latex(ruta_tex, log_path)
        else:
            subprocess.run(["python", "llm_corrector.py", ruta_tex, log_path], check=False)
    except ImportError:
        subprocess.run(["python", "llm_corrector.py", ruta_tex, log_path], check=False)

def compilar_latex_con_blindaje(directorio_base, archivo_main):
    """
    Motor Inmortal de Compilación para Libros: Si pdflatex arroja un error de sintaxis,
    captura el log e invoca al LLM Crítico para repararlo en un bucle cerrado.
    """
    ruta_tex = os.path.join(directorio_base, archivo_main)
    print(f"\n⚙️ Iniciando compilación blindada del libro maestro: {ruta_tex}")
    
    nombre_base = os.path.splitext(archivo_main)[0]
    ruta_pdf = os.path.join(directorio_base, f"{nombre_base}.pdf")
    
    intentos = 0
    while intentos < MAX_RETRIES:
        print(f"   ▶️ Intento de compilación {intentos + 1}/{MAX_RETRIES}...")
        
        # Limpieza quirúrgica de archivos residuales para evitar falsos errores de caché
        # Se incluyen extensiones de índice (toc, lof, lot) vitales en los libros
        for ext in ['.aux', '.log', '.out', '.toc', '.lof', '.lot']:
            res = os.path.join(directorio_base, f"{nombre_base}{ext}")
            if os.path.exists(res):
                try:
                    os.remove(res)
                except Exception:
                    pass
                
        # Compilación doble obligatoria en libros para indexar el Table of Contents (TOC)
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", archivo_main],
            cwd=directorio_base,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        proceso_final = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", archivo_main],
            cwd=directorio_base,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if proceso_final.returncode == 0 and os.path.exists(ruta_pdf):
            print(f"   ✅ Compilación exitosa: {ruta_pdf}")
            return ruta_pdf
            
        print(f"   ❌ Error de sintaxis LaTeX detectado en el libro.")
        log_path = os.path.join(directorio_base, f"{nombre_base}_error.log")
        
        # Guardar log de errores para análisis forense del Agente Corrector
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(proceso_final.stdout)
            if proceso_final.stderr:
                f.write("\n" + proceso_final.stderr)
        
        print("   🛠️ Invocando al agente crítico (llm_corrector.py) para reparar el código...")
        ejecutar_curacion_llm(ruta_tex, log_path)
        
        intentos += 1
        time.sleep(2) 
        
    print(f"🚨 CORTACIRCUITOS ACTIVADO: No se pudo compilar el libro tras {MAX_RETRIES} intentos.")
    return None

def obtener_libros_compilables():
    """
    Escanea la raíz buscando carpetas de libros válidos (libro_*) que contengan main.tex.
    Retorna una lista ordenada desde el modificado más recientemente hasta el más antiguo.
    """
    libros = []
    for elemento in os.listdir("."):
        if os.path.isdir(elemento) and elemento.startswith("libro_"):
            ruta_main = os.path.join(elemento, "main.tex")
            if os.path.exists(ruta_main):
                # Usamos el tiempo de modificación del main.tex como ancla cronológica
                tiempo_mod = os.path.getmtime(ruta_main)
                libros.append((elemento, tiempo_mod))
                
    # Ordenar por tiempo de modificación descendente (el más reciente primero)
    libros_ordenados = sorted(libros, key=lambda x: x[1], reverse=True)
    return [libro[0] for libro in libros_ordenados]

def empaquetar_libro():
    print("🚀 Motor de Compilación y Empaquetado de Libros (Pipeline de Teoría)...")
    
    if not os.path.exists(CARPETA_PDFS_LIBROS):
        os.makedirs(CARPETA_PDFS_LIBROS)
        print(f"📁 Directorio base '{CARPETA_PDFS_LIBROS}/' creado exitosamente.")
        
    libros_disponibles = obtener_libros_compilables()
    
    if not libros_disponibles:
        print("🚨 Error: No se encontraron carpetas de libros válidos (con archivo main.tex) en el directorio raíz.")
        return

    print("\n📚 LIBROS DISPONIBLES PARA COMPILAR:")
    for i, libro in enumerate(libros_disponibles):
        marca = " ⭐ (Más reciente - Opción por defecto automática)" if i == 0 else ""
        # Limpiar nombre para la vista del usuario
        nombre_vista = libro.replace("libro_", "").replace("_", " ")
        print(f"  [{i}] {nombre_vista}{marca}")

    # Interruptor Híbrido: Espera la entrada del usuario (o la inyección del orquestador)
    try:
        seleccion = input("\nIntroduce el número del libro a compilar: ").strip()
        indice = int(seleccion)
        if 0 <= indice < len(libros_disponibles):
            directorio_libro = libros_disponibles[indice]
        else:
            print("❌ Selección fuera de rango. Abortando.")
            return
    except ValueError:
        print("❌ Entrada no válida. Debes ingresar un número. Abortando.")
        return
    except EOFError:
        # Fallback de seguridad por si falla la inyección de consola en ciertos SO
        print("\n⚠️ No se detectó entrada de consola. Seleccionando [0] por defecto.")
        directorio_libro = libros_disponibles[0]

    titulo_limpio = directorio_libro.replace("libro_", "")
    archivo_main = "main.tex"
    
    print(f"\n📚 Procediendo a compilar el libro estructural: {titulo_limpio.replace('_', ' ')}")
    ruta_pdf_generado = compilar_latex_con_blindaje(directorio_libro, archivo_main)
    
    # =========================================================================
    # FASE FINAL: EMPAQUETADO EN LA CARPETA OBJETIVO
    # =========================================================================
    if ruta_pdf_generado and os.path.exists(ruta_pdf_generado):
        ruta_final = os.path.join(CARPETA_PDFS_LIBROS, f"{titulo_limpio}.pdf")
        
        try:
            shutil.copy2(ruta_pdf_generado, ruta_final)
            print(f"\n✅ ¡ÉXITO ABSOLUTO! Libro compilado y empaquetado correctamente en:\n   -> {ruta_final}")
        except Exception as e:
            print(f"🚨 Error crítico al trasladar el PDF final hacia la carpeta de empaquetado: {e}")
    else:
        print("\n❌ Operación abortada por el orquestador: Falló la compilación del libro. Revisa los logs de error.")

if __name__ == "__main__":
    empaquetar_libro()
```

==================================================
📄 ARCHIVO: compiler_service.py
Ruta: .\compiler_service.py
==================================================
```python
import subprocess
import os

def compilar_latex(directorio_trabajo, archivo_principal="main.tex"):
    print(f"⚙️ Iniciando compilación de {archivo_principal}...")
    
    # -interaction=nonstopmode evita que el compilador se quede esperando si hay un error
    # -halt-on-error detiene el proceso al primer fallo crítico
    comando = [
        "pdflatex", 
        "-interaction=nonstopmode", 
        "-halt-on-error",
        archivo_principal
    ]
    
    try:
        # Ejecutamos el comando asegurándonos de estar en la carpeta correcta
        resultado = subprocess.run(
            comando, 
            cwd=directorio_trabajo, 
            capture_output=True, 
            text=True
        )
        
        if resultado.returncode == 0:
            print("✅ Compilación exitosa. PDF generado.")
            return True
        else:
            print("❌ Error de sintaxis detectado. Analizando log...")
            analizar_log_error(directorio_trabajo, archivo_principal)
            return False
            
    except FileNotFoundError:
        print("🚨 CRÍTICO: No se encontró 'pdflatex' en tu sistema.")
        print("Asegúrate de tener instalado MiKTeX o TeX Live en Windows y que estén agregados al PATH.")
        return False

def analizar_log_error(directorio_trabajo, archivo_principal):
    # El archivo .log siempre tiene el mismo nombre que el .tex principal
    nombre_base = os.path.splitext(archivo_principal)[0]
    ruta_log = os.path.join(directorio_trabajo, f"{nombre_base}.log")
    
    if not os.path.exists(ruta_log):
        print("No se generó ningún archivo .log.")
        return
        
    print("\n--- EXTRACTO DEL ERROR PARA EL AGENTE ---")
    with open(ruta_log, 'r', encoding='utf-8', errors='ignore') as f:
        lineas = f.readlines()
        for i, linea in enumerate(lineas):
            # LaTeX marca los errores críticos empezando la línea con "!"
            if linea.startswith("!"):
                # Capturamos el error y las siguientes 4 líneas de contexto
                contexto_error = "".join(lineas[i:i+5])
                print(contexto_error.strip())
                break
    print("-----------------------------------------\n")

if __name__ == "__main__":
    # Definimos la ruta absoluta hacia nuestra carpeta de plantilla
    ruta_template = os.path.join(os.getcwd(), "template_base")
    
    # Ejecutamos la función
    compilar_latex(ruta_template)
```

==================================================
📄 ARCHIVO: context_packer.py
Ruta: .\context_packer.py
==================================================
```python
import os

def generar_contexto(archivo_salida="contexto_agente_universitario.md"):
    # Extensiones de los archivos cuyo código fuente SÍ queremos leer
    extensiones_validas = ['.py', '.json', '.txt', '.md']
    
    # Carpetas que queremos MOSTRAR en el árbol, pero NO leer su contenido
    carpetas_excluidas = [
        '.git', '__pycache__', '.venv', 'venv', 
        'chroma_db', 'bibliografia', 'bibliografia_escaneada', 
        'Pensamientos', 'guias_out', 'syllabus',
        'compendio_preguntas', 'guias_in',
        'Errores', 'PDFs_guias',
        'PDFs_libros'
    ]
    
    # Archivos específicos que no queremos leer (ej. el json del grafo que será enorme)
    archivos_excluidos = ['.env', 'conocimiento_grafo.json', 'contexto_agente_universitario.md', 'book_structure.json',
        'guide_structure.json', 'temario_bruto.txt',
        'temas_guia.txt']

    with open(archivo_salida, 'w', encoding='utf-8') as out:
        out.write("==================================================\n")
        out.write("ARQUITECTURA DEL AGENTE AUTÓNOMO UNIVERSITARIO\n")
        out.write("==================================================\n\n")
        
        # 1. DIBUJAR EL ÁRBOL DE CARPETAS
        out.write("📁 ESTRUCTURA DE DIRECTORIOS:\n\n")
        for root, dirs, files in os.walk('.'):
            level = root.replace('.', '').count(os.sep)
            indent = ' ' * 4 * level
            basename = os.path.basename(root)
            
            if level == 0:
                out.write("📦 [Proyecto Raíz]/\n")
            else:
                if basename in carpetas_excluidas:
                    out.write(f"{indent}📂 {basename}/ (Contenido omitido)\n")
                    dirs[:] = []  # Le decimos a os.walk que no entre a esta carpeta
                    continue
                else:
                    out.write(f"{indent}📂 {basename}/\n")
            
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                if any(f.endswith(ext) for ext in extensiones_validas):
                    out.write(f"{subindent}📄 {f}\n")
                    
        out.write("\n==================================================\n")
        out.write("CÓDIGO FUENTE DE LOS ARCHIVOS\n")
        out.write("==================================================\n\n")

        # 2. LEER Y PEGAR EL CÓDIGO
        for root, dirs, files in os.walk('.'):
            # Filtramos las carpetas para no entrar a las excluidas al buscar código
            dirs[:] = [d for d in dirs if d not in carpetas_excluidas]
            
            for file in files:
                if file in archivos_excluidos:
                    continue
                    
                if any(file.endswith(ext) for ext in extensiones_validas):
                    ruta_completa = os.path.join(root, file)
                    try:
                        with open(ruta_completa, 'r', encoding='utf-8') as f_in:
                            contenido = f_in.read()
                            
                        out.write(f"==================================================\n")
                        out.write(f"📄 ARCHIVO: {file}\n")
                        out.write(f"Ruta: {ruta_completa}\n")
                        out.write(f"==================================================\n")
                        out.write(f"```python\n{contenido}\n```\n\n")
                    except Exception as e:
                        out.write(f"⚠️ Error leyendo {file}: {str(e)}\n\n")

    print(f"✅ Empaquetado completado: {archivo_salida}")

if __name__ == "__main__":
    generar_contexto()
```

==================================================
📄 ARCHIVO: generator_agent.py
Ruta: .\generator_agent.py
==================================================
```python
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
ACTIVAR_REVISION_NIVEL_2 = True

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

    user_prompt = f"""
    --- HISTORIAL DE CAPÍTULOS ANTERIORES (TEXTO EXACTO) ---
    {texto_absolute_previo if texto_absolute_previo.strip() else "[Este es el primer capítulo del libro]"}
    
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
                print(f"   ⏳ Límite de API alcanzado. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
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

    user_prompt = f"""
    --- MANUSCRITO / HISTORIAL PREVIO DE REFERENCIA ---
    {historial_previo if historial_previo.strip() else "[No hay historial previo]"}
    
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
                print(f"   ⏳ Límite de API en Planificador. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
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

    user_prompt = f"""
    --- MANUSCRITO DE LA OBRA COMPLETA (HISTORIAL PREVIO) ---
    {historial_previo if historial_previo.strip() else "[Primeros capítulos del libro]"}
    
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
                print(f"   ⏳ Límite de API en Escritor Quirúrgico. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
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
```

==================================================
📄 ARCHIVO: guia_builder.py
Ruta: .\guia_builder.py
==================================================
```python
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
```

==================================================
📄 ARCHIVO: guide_parser.py
Ruta: .\guide_parser.py
==================================================
```python
import os
import json
import re
import time
import sys
from pypdf import PdfReader
from google import genai
from google.genai import types
from dotenv import load_dotenv

# =========================================================================
# HIPERPARÁMETROS DE SEGURIDAD Y CONFIGURACIÓN (RC 1.0)
# =========================================================================
MAX_RETRIES = 5  # Cortacircuitos anti-drenaje de tokens
EXTENSIONES_PERMITIDAS = {'.pdf', '.tex', '.txt'} # Lista Blanca de Ingesta
# =========================================================================

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")
client = genai.Client(api_key=api_key)

def leer_pdf_guia(carpeta="guias_in"):
    if not os.path.exists(carpeta):
        os.makedirs(carpeta)
        print(f"⚠️ Carpeta '{carpeta}' creada. Coloca tus guías (.pdf, .tex o .txt) ahí.")
        return None, None

    # BLINDAJE: Filtro estricto contra archivos ocultos y validación por Lista Blanca
    archivos_validos = []
    for f in os.listdir(carpeta):
        if f.startswith('.'):
            continue
        _, extension = os.path.splitext(f.lower())
        if extension in EXTENSIONES_PERMITIDAS:
            archivos_validos.append(f)

    if not archivos_validos:
        print(f"⚠️ No hay archivos válidos (.pdf, .tex, .txt) en '{carpeta}'.")
        return None, None

    ruta_archivo = os.path.join(carpeta, archivos_validos[0])
    nombre_archivo = archivos_validos[0]
    print(f"📄 Extrayendo texto de la guía: {nombre_archivo}...")
    
    texto_completo = ""
    try:
        # Lógica dividida según el tipo de archivo
        if ruta_archivo.endswith('.pdf'):
            lector = PdfReader(ruta_archivo)
            for pagina in lector.pages:
                texto_extraido = pagina.extract_text()
                if texto_extraido:
                    texto_completo += texto_extraido + "\n"
                    
        elif ruta_archivo.endswith('.tex') or ruta_archivo.endswith('.txt'):
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                texto_completo = f.read()
                
        return texto_completo, nombre_archivo
        
    except Exception as e:
        print(f"🚨 Error al leer el documento: {e}")
        return None, None

def estructurar_guia_json(texto_guia, nombre_archivo):
    print("🧠 Analizando la guía: detectando jerarquía de problemas e incisos (Modo Universal)...")

    system_instruction = """Eres un Analista Académico de Élite, capaz de procesar documentos de cualquier disciplina.
    Tu objetivo es leer el texto crudo de una guía de estudio o examen (que puede ser LaTeX puro o un PDF externo escaneado con formato caótico) y extraer los problemas estructurándolos jerárquicamente.
    
    REGLA DE ADAPTACIÓN UNIVERSAL (COMPATIBILIDAD EXTERNA):
    Un "Problema" puede estar etiquetado de mil formas dependiendo del profesor: "1.", "Problema 1", "I.", "\\section*{...}", o simplemente viñetas. Debes usar tu inteligencia para deducir dónde empieza y termina un problema independiente.
    
    REGLA DE JERARQUÍA ESTRICTA (CONTEXTO + INCISOS):
    1. La mayoría de los problemas tienen un "contexto_base" (la situación principal, el sistema, la historia).
    2. Luego, el problema se divide en "sub_items" o preguntas (a, b, c, i, ii, etc.).
    3. DEBES extraer el "contexto_base" en su propio campo, y poner todos los incisos asociados dentro de su respectivo array "sub_items". NO repitas el contexto dentro de las preguntas de los incisos.
    4. Si un problema es directo (ej: "¿Qué es la mitosis?") y NO tiene incisos a, b, c, pon la pregunta entera en "contexto_base" y deja el array de "sub_items" vacío.
    
    REGLA DE LIMPIEZA ESTRUCTURAL Y FLUIDEZ DE TEXTO (CRÍTICA):
    Si el texto de entrada es código LaTeX o OCR sucio, limpia TODOS los comandos estructurales residuales (como \\begin{enumerate}, \\item, \\section*, \\noindent, saltos de línea rotos) para que el texto sea natural y coherente.

    REGLA DE FORMATO MATEMÁTICO OBLIGATORIO ($):
    Asegúrate rigurosamente de que CADA variable matemática, símbolo, ecuación o número con unidades esté correctamente encapsulado en formato matemático de LaTeX ($...$ o \\[...\\]).

    REGLA DE ESCAPE DE CARACTERES LATEX EN JSON (INQUEBRANTABLE):
    DEBES ESCAPAR TODAS las barras invertidas de los comandos LaTeX utilizando doble barra (ejemplo: \\\\hbar, \\\\exp, \\\\theta, \\\\frac). Si omites la doble barra, el JSON se corromperá.

    ESTRUCTURA JSON ESPERADA (Retorna SOLO el JSON):
    {
      "metadata": {
        "titulo": "Título inferido o extraído de la materia",
        "archivo_origen": "Nombre del archivo"
      },
      "items": [
        {
          "id": "prob_1",
          "contexto_base": "Texto que plantea la situación o sistema principal. Si no hay incisos, pon la pregunta directa aquí.",
          "sub_items": [
            {
              "id_letra": "a",
              "pregunta": "¿Qué ocurre si la temperatura aumenta?"
            },
            {
              "id_letra": "b",
              "pregunta": "Calcule la velocidad final."
            }
          ]
        }
      ]
    }
    """

    user_prompt = f"Aquí está el texto bruto de la guía. Recuerda escapar TODAS las barras de LaTeX con doble barra (\\\\). Archivo: {nombre_archivo}\n\n{texto_guia}"

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
            return respuesta.text.strip()
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico de red en el Parser tras {MAX_RETRIES} intentos.")
                return None
                
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"   ⏳ Límite de API en Parser. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"   🔥 Servidor saturado (503). Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"   🚨 Error de red detectado: {e}. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s...")
                time.sleep(15)
    return None

def sanear_y_cargar_json(texto_crudo):
    contenido = texto_crudo.strip()
    contenido = re.sub(r'^```json', '', contenido, flags=re.IGNORECASE)
    contenido = re.sub(r'```$', '', contenido).strip()
    contenido = re.sub(r'^```', '', contenido).strip()
    
    try:
        return json.loads(contenido)
    except json.JSONDecodeError:
        print("   🛡️ JSON malformado detectado. Aplicando saneamiento Regex Quirúrgico...")
        # REGEX QUIRÚRGICA: Ignora las barras que YA son dobles (?<!\\) y repara solo las huérfanas.
        contenido_rescatado = re.sub(r'(?<!\\)\\(?![\\/"bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', contenido)
        try:
            return json.loads(contenido_rescatado)
        except Exception as e:
            print(f"   🚨 Error crítico: El JSON es irrecuperable de forma automatizada. Detalle: {e}")
            return None

if __name__ == "__main__":
    resultado = leer_pdf_guia()
    if resultado and resultado[0]:
        texto, nombre_archivo = resultado
        json_generado = estructurar_guia_json(texto, nombre_archivo)
        
        if json_generado:
            datos_jerarquicos = sanear_y_cargar_json(json_generado)
            
            if datos_jerarquicos and "items" in datos_jerarquicos:
                print("✅ Estructura jerárquica original validada con éxito.")
                
                json_listo = json.dumps(datos_jerarquicos, indent=2, ensure_ascii=False)
                
                with open("guide_structure.json", "w", encoding="utf-8") as f:
                    f.write(json_listo)
                print("✅ 'guide_structure.json' generado preservando la lógica nativa del solver.")
            else:
                print("❌ Abortando: No se pudo procesar la jerarquía JSON debido a un formato corrupto o falta de la clave 'items'.")
                sys.exit(1)
        else:
            print("❌ Abortando: La IA no pudo generar el JSON (Límite de reintentos alcanzado).")
            sys.exit(1)
    else:
        print("❌ Abortando: No se pudo leer el archivo original o el directorio está vacío.")
        sys.exit(1)
```

==================================================
📄 ARCHIVO: llm_corrector.py
Ruta: .\llm_corrector.py
==================================================
```python
import os
import re
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Cargar las variables de entorno
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY en el entorno.")

# Inicializar cliente de la nueva SDK
client = genai.Client(api_key=api_key)

def limpiar_markdown_latex(texto):
    """Limpia los bloques de formato markdown que el LLM suele añadir."""
    contenido = texto.strip()
    marca_inicio = chr(96) * 3 + 'latex'
    marca_fin = chr(96) * 3
    if contenido.startswith(marca_inicio):
        contenido = contenido[len(marca_inicio):]
    if contenido.endswith(marca_fin):
        contenido = contenido[:-len(marca_fin)]
    if contenido.startswith(chr(96)*3):
        contenido = contenido[3:]
    return contenido.strip()

def aislar_bloque_quirurgico(contenido_completo, numero_linea):
    """
    Rastrea hacia arriba desde el número de línea del error para encontrar
    el bloque atómico exacto (INCISO o PREAMBULO) que contiene la falla.
    Retorna: (tipo_bloque, id_bloque, contenido_aislado, patron_regex) o None si falla.
    """
    if not numero_linea:
        return None, None, None, None

    lineas = contenido_completo.split('\n')
    
    # Validar que la línea esté dentro del rango
    if numero_linea < 1 or numero_linea > len(lineas):
        return None, None, None, None

    tipo_bloque = None
    id_bloque = None

    # Escanear hacia atrás desde la línea del error para encontrar el INICIO del bloque
    for i in range(numero_linea - 1, -1, -1):
        linea = lineas[i]
        match_inicio = re.search(r'% === INICIO (INCISO|PREAMBULO): (.*?) ===', linea)
        if match_inicio:
            tipo_bloque = match_inicio.group(1)
            id_bloque = match_inicio.group(2)
            break
        # Si topamos con un FIN antes de un INICIO al mirar hacia arriba, 
        # significa que el error ocurrió entre bloques (fuera del tejido atómico).
        if re.search(r'% === FIN (INCISO|PREAMBULO):', linea):
            return None, None, None, None

    if not id_bloque:
        return None, None, None, None

    # Extraer el contenido exacto del bloque usando expresiones regulares
    patron = rf"% === INICIO {tipo_bloque}: {id_bloque} ===(.*?)% === FIN {tipo_bloque}: {id_bloque} ==="
    match_bloque = re.search(patron, contenido_completo, re.DOTALL)
    
    if match_bloque:
        return tipo_bloque, id_bloque, match_bloque.group(1).strip(), patron
        
    return None, None, None, None

def aplicar_correccion(ruta_archivo, mensaje_error, numero_linea=None):
    """
    Lee un archivo .tex defectuoso, aísla la zona del error y utiliza Gemini
    para corregir la sintaxis de LaTeX, protegiendo la extensión y la disciplina.
    """
    if not os.path.exists(ruta_archivo):
        print(f"      ⚠️ Agente Corrector: El archivo {ruta_archivo} no existe.")
        return False

    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        contenido_completo = f.read()

    # Intentar aislamiento quirúrgico
    tipo_bloque, id_bloque, bloque_texto, patron_regex = aislar_bloque_quirurgico(contenido_completo, numero_linea)
    es_quirurgico = (tipo_bloque is not None)

    if es_quirurgico:
        print(f"      🧠 Agente Corrector: Error localizado quirúrgicamente en el {tipo_bloque} '{id_bloque}' (Línea aprox: {numero_linea}).")
        fragmento_a_corregir = bloque_texto
        instruccion_contexto = "CÓDIGO AFECTADO (Fragmento Aislado Quirúrgicamente)"
    else:
        if numero_linea:
            print(f"      ⚠️ Agente Corrector: El error en la línea {numero_linea} es estructural o no pertenece a un inciso. Aplicando Curación Global (Fallback)...")
        else:
            print(f"      ⚠️ Agente Corrector: No se proporcionó número de línea. Aplicando Curación Global (Fallback)...")
        fragmento_a_corregir = contenido_completo
        instruccion_contexto = "CÓDIGO COMPLETO DEL CAPÍTULO"

    system_instruction = """Eres un Ingeniero Experto en LaTeX y Auditor de Control de Calidad Académica multidisciplinario.
    Tu única tarea es analizar un log de error devuelto por 'pdflatex' y arreglar la sintaxis defectuosa en el código proporcionado.

    REGLA 1 (ANTI-RESUMEN INQUEBRANTABLE):
    Tienes ESTRICTAMENTE PROHIBIDO acortar el texto, resumir conceptos o eliminar párrafos válidos. Tu intervención debe ser exclusivamente sintáctica (cerrar llaves `}`, arreglar entornos `\begin...\end` huérfanos, corregir tabulaciones o escapar caracteres reservados como `&`, `%`, `$`). El contenido narrativo debe mantenerse INTACTO.

    REGLA 2 (DIRECTRIZ CAMALEÓNICA):
    Analiza el fragmento y respeta su naturaleza disciplinaria. Si el texto aborda humanidades o ciencias sociales, no inyectes entornos algebraicos para arreglar el formato. Si aborda física o matemáticas, asegúrate de que las ecuaciones respeten entornos formales (ej. `\\begin{align*}`).

    REGLA 3 (CERO EXPLICACIONES):
    Devuelve ÚNICAMENTE el código LaTeX corregido, listo para ser compilado. No saludes, no incluyas bloques de markdown (```latex) al principio ni al final, y no expliques qué reparaste.
    """

    user_prompt = f"""
    MENSAJE DE ERROR DEL COMPILADOR (pdflatex):
    {mensaje_error}

    --- {instruccion_contexto} ---
    {fragmento_a_corregir}
    -------------------------------------------
    
    Analiza la falla, aplica la corrección manteniendo el 100% de la integridad narrativa y devuelve exclusivamente el código LaTeX reparado.
    """

    while True:
        try:
            print("      🤖 Agente Corrector: Analizando la falla con Gemini...")
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0 # Determinismo máximo para arreglar código
                )
            )
            
            codigo_reparado = limpiar_markdown_latex(response.text)
            
            # Reintegrar el código reparado al archivo original
            if es_quirurgico:
                nuevo_bloque = f"% === INICIO {tipo_bloque}: {id_bloque} ===\n{codigo_reparado}\n% === FIN {tipo_bloque}: {id_bloque} ==="
                # Usar lambda para evitar problemas si el código contiene '\g' o similares
                contenido_final = re.sub(patron_regex, lambda _: nuevo_bloque, contenido_completo, flags=re.DOTALL)
            else:
                contenido_final = codigo_reparado
                
            # Sobreescribir el archivo de manera segura
            with open(ruta_archivo, 'w', encoding='utf-8') as f:
                f.write(contenido_final)
                
            print(f"      ✅ Agente Corrector: Tejido {'quirúrgico' if es_quirurgico else 'global'} reparado con éxito y sobreescrito.")
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                print("      ⏳ Agente Corrector: Límite de API alcanzado. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg:
                print("      🔥 Agente Corrector: Servidor saturado (503). Esperando 15s...")
                time.sleep(15)
            else:
                print(f"      🚨 Error inesperado en el Agente Corrector: {e}. Reintentando en 15s...")
                time.sleep(15)

if __name__ == "__main__":
    # Script diseñado para ser importado como módulo, pero con soporte de prueba local.
    print("Módulo de curación LaTeX cargado.")
```

==================================================
📄 ARCHIVO: ocr_transcriber.py
Ruta: .\ocr_transcriber.py
==================================================
```python
import os
import time
from google import genai
from google.genai import types
import fitz  # PyMuPDF
from dotenv import load_dotenv

# =========================================================================
# HIPERPARÁMETROS DE SEGURIDAD Y CONFIGURACIÓN
# =========================================================================
MAX_RETRIES = 5  # Cortacircuitos anti-drenaje de tokens
EXTENSIONES_PERMITIDAS = {'.pdf'} # Lista Blanca (El OCR solo lee PDFs)
# =========================================================================

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")

# Inicializar cliente de la nueva SDK
client = genai.Client(api_key=api_key)

def procesar_imagen_con_llm(image_bytes, num_pagina, nombre_archivo):
    system_instruction = """Eres un experto en transcripción de documentos académicos y reconocimiento óptico de caracteres (OCR) avanzado.
    Tu tarea es transcribir el texto de la imagen proporcionada con precisión absoluta.
    Reglas inquebrantables:
    1. Transcribe todo el texto manteniendo la estructura de párrafos original.
    2. Convierte todas las ecuaciones, fórmulas matemáticas y símbolos a código LaTeX puro.
    3. Si hay diagramas o gráficos, descríbelos brevemente entre corchetes [Diagrama: breve descripción].
    4. No omitas información, no resumas y no agregues comentarios externos tuyos."""

    user_prompt = f"Transcribe la página {num_pagina} del documento '{nombre_archivo}'."

    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            imagen_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type='image/jpeg'
            )

            response = client.models.generate_content(
                model='gemini-3.1-flash-lite', 
                contents=[imagen_part, user_prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        )
                    ]
                )
            )
            return response.text.strip() + "\n\n"
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS: Fallo OCR tras {MAX_RETRIES} intentos en página {num_pagina}.")
                return f"\n[ERROR DE TRANSCRIPCIÓN: No se pudo procesar la página {num_pagina} debido a un fallo persistente del servidor]\n\n"
            
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg:
                print(f"      ⏳ Límite de API en OCR. Intento {intentos}/{MAX_RETRIES}. Esperando 60s...")
                time.sleep(60)
            elif "503" in error_msg or "unavailable" in error_msg:
                print(f"      🔥 Servidor saturado (503). Intento {intentos}/{MAX_RETRIES}. Esperando 15s...")
                time.sleep(15)
            else:
                print(f"      ⚠️ Error OCR. Intento {intentos}/{MAX_RETRIES}. Reintentando en 15s... ({e})")
                time.sleep(15)

def transcribir_escaneados():
    directorio_entrada = "bibliografia_escaneada"
    directorio_salida = "bibliografia"

    os.makedirs(directorio_entrada, exist_ok=True)
    os.makedirs(directorio_salida, exist_ok=True)

    archivos = os.listdir(directorio_entrada)
    
    if not archivos:
        # print(f"✅ La carpeta '{directorio_entrada}' está vacía. OCR en reposo.") # Removido para mantener tu silencio original en consola si está vacía
        return

    print("🚀 Despertando Agente de Visión Artificial (OCR)...")

    for archivo in archivos:
        # 1. BLINDAJE: Ignorar archivos ocultos y .gitkeep
        if archivo.startswith('.'):
            continue
            
        # 2. BLINDAJE: Lista Blanca Estricta
        _, extension = os.path.splitext(archivo.lower())
        if extension not in EXTENSIONES_PERMITIDAS:
            print(f"   ⏭️ Ignorando archivo no soportado por OCR: {archivo}")
            continue

        ruta_pdf = os.path.join(directorio_entrada, archivo)
        nombre_base = os.path.splitext(archivo)[0]
        archivo_txt_salida = os.path.join(directorio_salida, f"{nombre_base}.txt")

        print(f"\n👁️  Analizando visualmente: {archivo}")
        texto_completo = ""

        try:
            documento = fitz.open(ruta_pdf)
            total_paginas = len(documento)
            
            for num_pagina in range(total_paginas):
                print(f"   📸 Escaneando página {num_pagina + 1}/{total_paginas}...")
                pagina = documento.load_page(num_pagina)
                
                # Renderizar página a imagen (pixmap) en alta resolución
                pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2))
                image_bytes = pix.tobytes("jpeg")

                transcripcion = procesar_imagen_con_llm(image_bytes, num_pagina + 1, archivo)
                texto_completo += f"--- PÁGINA {num_pagina + 1} ---\n{transcripcion}"
                
                time.sleep(2) # Respetar cuotas de visión multimodal
                
            documento.close()
            
            # Guardar el .txt en la carpeta principal de bibliografía
            with open(archivo_txt_salida, 'w', encoding='utf-8') as f:
                f.write(texto_completo)
                
            print(f"   ✅ Transcripción completa. Guardado como '{archivo_txt_salida}'.")
            
            # Limpieza: Eliminar el PDF original de la carpeta de escaneados
            os.remove(ruta_pdf)
            print(f"   🧹 Archivo original '{archivo}' procesado y purgado de la cola.")
            
        except Exception as e:
            print(f"   ❌ Error crítico abriendo o procesando el PDF '{archivo}': {e}")

    print("\n🏆 ¡PIPELINE OCR COMPLETADO! Los textos transcritos están listos para la ingesta.")

if __name__ == "__main__":
    transcribir_escaneados()
```

==================================================
📄 ARCHIVO: orchestrator.py
Ruta: .\orchestrator.py
==================================================
```python
import os
import json
import re

def limpiar_nombre_carpeta(texto):
    texto_limpio = re.sub(r'[^a-zA-Z0-9]', '_', texto)
    texto_limpio = re.sub(r'_+', '_', texto_limpio)
    return texto_limpio.strip('_')

def construir_esqueleto(json_path):
    print(f"🏗️ Iniciando la construcción del esqueleto jerárquico desde {json_path}...")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as file:
            estructura = json.load(file)
    except FileNotFoundError:
        print(f"🚨 Error: No se encontró el archivo {json_path}")
        return

    titulo_libro = estructura['metadata'].get('titulo', 'Libro_Generico')
    nombre_seguro = limpiar_nombre_carpeta(titulo_libro)
    base_dir = f"libro_{nombre_seguro}"
    
    chapters_dir = os.path.join(base_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)
    
    main_tex_path = os.path.join(base_dir, "main.tex")
    
    main_tex_content = f"""\\documentclass[12pt, a4paper, openany]{{book}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath, amssymb, physics}}
\\usepackage{{hyperref}}

\\title{{{estructura['metadata']['titulo']}}}
\\author{{{estructura['metadata']['autor']}}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle
\\tableofcontents

"""

    for cap in estructura.get("capitulos", []):
        id_cap = cap["id"]
        titulo_cap = cap["titulo"]
        ruta_archivo = os.path.join(chapters_dir, f"{id_cap}.tex")
        
        main_tex_content += f"\\include{{chapters/{id_cap}}}\n"
        
        with open(ruta_archivo, 'w', encoding='utf-8') as f:
            f.write(f"% Este archivo fue generado automáticamente\n")
            f.write(f"\\chapter{{{titulo_cap}}}\n\n")
            
            for sec in cap.get("secciones", []):
                f.write(f"\\section{{{sec['titulo']}}}\n")
                if sec.get("preambulo"):
                    f.write(f"% --- Preámbulo de sección: {sec['id']} ---\n\n")
                
                for subsec in sec.get("subsecciones", []):
                    f.write(f"\\subsection{{{subsec['titulo']}}}\n")
                    
                    # --- NUEVO NIVEL: INCISOS (Fragmentación Atómica) ---
                    for inciso in subsec.get("incisos", []):
                        f.write(f"\\subsubsection{{{inciso['titulo']}}}\n")
                        f.write(f"% El Agente insertará el contenido aquí para: {inciso.get('id', 'inciso')}\n\n")
            
        print(f"✅ Creado/Actualizado: {ruta_archivo}")

    main_tex_content += "\n\\end{document}\n"
    
    with open(main_tex_path, 'w', encoding='utf-8') as f:
        f.write(main_tex_content)
        
    print("🚀 ¡Esqueleto de 4 niveles construido exitosamente!")

if __name__ == "__main__":
    construir_esqueleto("book_structure.json")
```

==================================================
📄 ARCHIVO: solver_agent.py
Ruta: .\solver_agent.py
==================================================
```python
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
            datos = json.loads(respuesta.text.strip())
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
        
    titulo_guia = limpiar_nombre_carpeta(estructura['metadata']['titulo'])
    titulo_real = estructura['metadata'].get('titulo', 'Guía de Ejercicios')
    
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
```

==================================================
📄 ARCHIVO: syllabus_parser.py
Ruta: .\syllabus_parser.py
==================================================
```python
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
```

==================================================
📄 ARCHIVO: temario_builder.py
Ruta: .\temario_builder.py
==================================================
```python
import os
import time
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

# =========================================================================
# HIPERPARÁMETROS DE SEGURIDAD Y CONFIGURACIÓN (RC 1.0)
# =========================================================================
MAX_RETRIES = 5  # Cortacircuitos anti-drenaje de tokens y prevención de bucles infinitos
# =========================================================================

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY en el entorno.")

client = genai.Client(api_key=api_key)

def leer_hiperparametros(archivo="temario_bruto.txt"):
    if not os.path.exists(archivo):
        print(f"🚨 Error: No se encontró '{archivo}'. Ejecuta Tonwini_setup.py primero.")
        return None, None
    
    with open(archivo, "r", encoding="utf-8") as f:
        contenido = f.read()
        
    partes = contenido.split("===")
    if len(partes) < 2:
        return contenido, [contenido]
        
    metadata = partes[0].strip()
    cuerpo = partes[1].strip()
    
    directrices_finales = metadata + "\n"
    temas_principales = []
    
    lineas = cuerpo.split('\n')
    leyendo_directrices = True
    
    for linea in lineas:
        lin_strip = linea.strip()
        if not lin_strip:
            continue
            
        # Aislar las líneas de metadatos o títulos genéricos para que no sean "temas"
        if "DIRECTRICES" in lin_strip.upper() or "ESTRUCTURA" in lin_strip.upper():
            if leyendo_directrices:
                directrices_finales += lin_strip + "\n"
            continue
            
        # Detectar temas principales (I., II., 1. Tema, Módulo 1, Capítulo 1)
        es_tema_principal = re.match(r'^(I{1,3}|IV|V|VI{0,3}|IX|X)\b\.', lin_strip) or \
                            re.match(r'^\d+\.\s+[A-ZÁÉÍÓÚ]', lin_strip) or \
                            re.match(r'^(M[OÓ]DULO|CAP[IÍ]TULO)\s*\d+', lin_strip, re.IGNORECASE)
                            
        # Detectar si es un subtema numérico (ej: 1.1, 1.2, 3.4) para IGNORARLO aquí
        es_subtema = re.match(r'^\d+\.\d+', lin_strip)
        
        if es_tema_principal:
            leyendo_directrices = False
            temas_principales.append(lin_strip)
        elif not es_subtema and leyendo_directrices:
            # Sigue siendo parte del párrafo de directrices
            directrices_finales += lin_strip + "\n"
            
    # Fallback de seguridad: si el usuario solo puso palabras sueltas sin números ni viñetas
    if not temas_principales:
        for linea in lineas:
            lin_strip = linea.strip()
            if lin_strip and not "DIRECTRICES" in lin_strip.upper() and not "ESTRUCTURA" in lin_strip.upper():
                temas_principales.append(lin_strip)
                
    return directrices_finales.strip(), temas_principales

def generar_temario(tema, directrices, historial_previo=""):
    print(f"\n🧠 Estructurando módulo base para: {tema}...")
    
    bloque_memoria = ""
    if historial_previo:
        bloque_memoria = f"""
--- HISTORIAL DE MÓDULOS ANTERIORES (CONTEXTO MACRO) ---
{historial_previo}
REGLA ANTI-REDUNDANCIA (CRÍTICA): NO repitas conceptos, subtemas ni introducciones históricas que ya se hayan abarcado en los módulos anteriores. Mantén una progresión lineal estricta hacia las nuevas fronteras de este tema específico.
--------------------------------------------------------
"""

    system_instruction = f"""Eres un Arquitecto Académico de Élite.
    Tu misión es generar la estructura MACRO de un programa analítico (Syllabus) basándote ESTRICTAMENTE en las siguientes directrices:
    
    {directrices}
    {bloque_memoria}
    
    REGLAS DE FORMATO Y COMPORTAMIENTO:
    1. Genera un programa estructurado en 'Capítulos' y 'Secciones' solo para este tema.
    2. REGLA CRÍTICA DE HUMILDAD Y COHESIÓN: Sé riguroso y objetivo. No extiendas la estructura de forma artificial ni inventes temas que no vengan al caso o que solapen con módulos pasados o futuros. Mantenlo enfocado, directo y secuencial.
    3. NO generes subsecciones o incisos todavía. Solo la estructura principal.
    4. Proporciona una muy breve descripción del enfoque general de este módulo antes de listar los capítulos.
    """
    
    user_prompt = f"Genera la estructura de capítulos y secciones principales EXCLUSIVAMENTE para el siguiente tema/concepto: {tema}"
    
    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2
                )
            )
            return respuesta.text.strip()
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico de red generando temario tras {MAX_RETRIES} intentos.")
                return None
            time.sleep(15)
    return None

def expandir_capitulo(capitulo_texto, directrices, historial_previo=""):
    print("   ⚙️ Expandiendo detalles descriptivos del módulo...")
    
    bloque_memoria = ""
    if historial_previo:
        bloque_memoria = f"""
--- HISTORIAL DE MÓDULOS ANTERIORES (CONTEXTO MACRO) ---
{historial_previo}
REGLA ANTI-SPOILER Y ANTI-ECO: Asume plenamente que el estudiante ya domina todo lo expuesto en el historial. ESTÁ ESTRICTAMENTE PROHIBIDO volver a explicar o mencionar con profundidad esos conceptos. Avanza directamente con el nuevo desarrollo analítico.
--------------------------------------------------------
"""

    system_instruction = f"""Eres el mismo Arquitecto Académico de Élite.
    Tu misión ahora es tomar la estructura MACRO previamente generada y enriquecerla con descripciones académicas para cada sección, respetando estas directrices:
    
    {directrices}
    {bloque_memoria}
    
    REGLAS VITALES Y ESTRICTAS:
    1. Para cada Sección identificada, redacta un párrafo descriptivo que detalle los conceptos o enfoques teóricos que se abordarán.
    2. PROHIBIDO EL RELLENO ARTIFICIAL Y LA REDUNDANCIA: Si el tema se explica perfectamente con rigor en un párrafo claro y directo, NO agregues información ética, histórica o filosófica irrelevante solo para extender el texto. Sé objetivo, humilde y estrictamente al grano. No recapitules.
    3. Devuelve la estructura completa del módulo, pero ahora enriquecida con estas descripciones ajustadas y precisas.
    """
    
    user_prompt = f"Aquí está la estructura base generada. Expándela con descripciones rigurosas y directas por cada sección, sin solapar información previa:\n\n{capitulo_texto}"
    
    intentos = 0
    while intentos < MAX_RETRIES:
        try:
            respuesta = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2 # Bajamos la temperatura para que sea más determinista y menos "creativo"
                )
            )
            return respuesta.text.strip()
            
        except Exception as e:
            intentos += 1
            if intentos >= MAX_RETRIES:
                print(f"      🚨 CORTACIRCUITOS ACTIVADO: Fallo crítico expandiendo capítulo tras {MAX_RETRIES} intentos.")
                return None
            time.sleep(15)
    return None

def main():
    directrices, temas = leer_hiperparametros()
    if not directrices or not temas:
        print("❌ Operación abortada: Faltan hiperparámetros o temas a procesar.")
        return
        
    carpeta_salida = "syllabus"
    if not os.path.exists(carpeta_salida):
        os.makedirs(carpeta_salida)
        
    print(f"🚀 Iniciando construcción de Syllabus ({len(temas)} módulos reales detectados)...")
    
    texto_final_completo = f"PROGRAMA ANALÍTICO COMPLETO\n===========================\n\nDIRECTRICES APLICADAS:\n{directrices.strip()}\n\n"
    historial_modulos = "" # Memoria de estado para evitar solapamientos
    
    for i, tema in enumerate(temas, 1):
        print(f"\n--- Procesando Módulo {i}/{len(temas)}: {tema} ---")
        
        esqueleto = generar_temario(tema, directrices, historial_modulos)
        if not esqueleto:
            print(f"🚨 Error: No se pudo generar la estructura para '{tema}'. Saltando al siguiente...")
            continue
            
        time.sleep(2)
        
        modulo_expandido = expandir_capitulo(esqueleto, directrices, historial_modulos)
        if not modulo_expandido:
            print(f"🚨 Error: No se pudo expandir el módulo '{tema}'. Guardando solo estructura básica...")
            texto_final_completo += f"\n\n### MÓDULO {i}: {tema}\n{esqueleto}\n"
            historial_modulos += f"### MÓDULO {i}: {tema}\n{esqueleto}\n\n"
            continue
            
        texto_final_completo += f"\n\n### MÓDULO {i}: {tema}\n{modulo_expandido}\n"
        historial_modulos += f"### MÓDULO {i}: {tema}\n{modulo_expandido}\n\n"
        
        print(f"✅ Módulo '{tema}' construido y expandido exitosamente.")
        time.sleep(2) 
        
    ruta_archivo_salida = os.path.join(carpeta_salida, "programa_generado.txt")
    with open(ruta_archivo_salida, "w", encoding="utf-8") as f:
        f.write(texto_final_completo)
        
    print(f"\n🏁 ¡Construcción finalizada! El programa completo ha sido guardado en: '{ruta_archivo_salida}'")
    print("   Siguiente paso recomendado: Ejecutar 'syllabus_parser.py' para estructurar este documento.")

if __name__ == "__main__":
    main()
```

==================================================
📄 ARCHIVO: Tonwini.py
Ruta: .\Tonwini.py
==================================================
```python
import os
import sys
import subprocess
import time
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

# =====================================================================
# CONFIGURACIÓN DE IA FORENSE PARA ANÁLISIS DE ERRORES
# =====================================================================
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

def obtener_modificacion_archivo(ruta_archivo):
    """Devuelve el timestamp de la última modificación del archivo."""
    return os.path.getmtime(ruta_archivo) if os.path.exists(ruta_archivo) else 0

def analizar_error_con_llm(script_name, error_log):
    """Consulta a Gemini para analizar la causa del fallo del script."""
    if not api_key:
        return "No se pudo generar análisis detallado porque no hay GEMINI_API_KEY en el entorno."
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Eres el Arquitecto de Software Principal de este sistema.
        El script '{script_name}' de mi Agente Autónomo Universitario ha fallado con un error fatal.
        
        Aquí tienes el log completo del sistema (stdout y stderr fusionados) devuelto por la consola:
        {error_log}
        
        Por favor, analiza este error y responde de forma concisa:
        1. ¿Qué línea o módulo falló exactamente?
        2. ¿Cuál es la causa subyacente (ej. fallo de API, problema de sintaxis, JSON roto)?
        3. ¿Cómo se soluciona rápidamente para continuar la ejecución?
        """
        respuesta = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        return respuesta.text
    except Exception as e:
        return f"Error secundario: La IA no pudo procesar el reporte de error. Detalle: {e}"

def manejar_error_fatal(script_name, error_traceback):
    """Crea la carpeta Errores, genera el reporte y detiene el orquestador."""
    os.makedirs("Errores", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_error = os.path.join("Errores", f"Fallo_{script_name.replace('.py', '')}_{timestamp}.txt")
    
    print(f"\n🚨 [CRÍTICO] El script '{script_name}' experimentó un fallo fatal.")
    print(f"🤖 Solicitando análisis forense a la IA sobre el Log Completo...")
    
    analisis = analizar_error_con_llm(script_name, error_traceback)
    
    with open(archivo_error, "w", encoding="utf-8") as f:
        f.write(f"=== REPORTE DE ERROR FATAL ===\n")
        f.write(f"Script Afectado: {script_name}\n")
        f.write(f"Marca de Tiempo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"--- 1. LOG COMPLETO DEL SISTEMA (STDOUT + STDERR) ---\n")
        f.write(error_traceback + "\n\n")
        f.write(f"--- 2. ANÁLISIS Y DIAGNÓSTICO DE LA IA ---\n")
        f.write(analisis)
        
    print(f"📄 Reporte forense generado y guardado en: {archivo_error}")
    print("❌ Abortando Pipeline maestro para prevenir corrupción de datos.")
    sys.exit(1)

def ejecutar_paso(script_name, es_interactivo=False, auto_input=None):
    """Ejecuta un script atrapando TODO el output para la IA Forense sin perder la vista en tiempo real."""
    print(f"\n" + "="*65)
    print(f"🚀 INICIANDO MÓDULO: {script_name}")
    print("="*65 + "\n")
    
    if es_interactivo:
        # Tonwini_setup requiere input() del usuario, dejamos todo estándar
        proceso = subprocess.run([sys.executable, script_name])
        if proceso.returncode != 0:
            print(f"🚨 Error durante la configuración inicial en {script_name}.")
            sys.exit(1)
    else:
        # BLINDAJE DE CODIFICACIÓN: Forzamos UTF-8 en el entorno del subproceso 
        # para que emojis y matemáticas no colapsen el Pipe.
        entorno_blindado = os.environ.copy()
        entorno_blindado["PYTHONIOENCODING"] = "utf-8"

        # Configuramos stdin solo si necesitamos inyectar una respuesta automática
        stdin_config = subprocess.PIPE if auto_input is not None else None

        # MAGIA ARQUITECTÓNICA: Usamos Popen con la bandera '-u' (unbuffered) y STDOUT para fusionar canales.
        proceso = subprocess.Popen(
            [sys.executable, "-u", script_name], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            stdin=stdin_config,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=entorno_blindado  # Aplicamos el escudo aquí
        )
        
        # Inyectamos el input automático de inmediato (ej: "0" para compilar todo)
        if auto_input is not None:
            proceso.stdin.write(auto_input + "\n")
            proceso.stdin.flush()
            proceso.stdin.close()  # Cerramos stdin para que el subproceso no se quede esperando más datos
        
        salida_completa = ""
        # Leemos línea por línea en tiempo real
        for linea in proceso.stdout:
            sys.stdout.write(linea)
            sys.stdout.flush()
            salida_completa += linea
        
        proceso.wait()
        
        # Si hubo un crash (returncode != 0), mandamos TODA la salida acumulada a la IA Forense
        if proceso.returncode != 0:
            manejar_error_fatal(script_name, salida_completa)

def main():
    print("=========================================================")
    print("🌟 ORQUESTADOR MAESTRO TONWINI - AGENTE AUTÓNOMO 🌟")
    print("=========================================================\n")
    
    # 1. Vigilar los archivos de decisión antes del setup
    mtime_libro_antes = obtener_modificacion_archivo("temario_bruto.txt")
    mtime_guia_antes = obtener_modificacion_archivo("temas_guia.txt")
    
    # 2. Iniciar la Capa Meta-Cognitiva
    ejecutar_paso("Tonwini_setup.py", es_interactivo=True)
    
    # 3. Detectar la decisión del usuario viendo qué archivo es más nuevo
    mtime_libro_despues = obtener_modificacion_archivo("temario_bruto.txt")
    mtime_guia_despues = obtener_modificacion_archivo("temas_guia.txt")
    
    ruta_elegida = None
    if mtime_libro_despues > mtime_libro_antes:
        ruta_elegida = "LIBRO"
    elif mtime_guia_despues > mtime_guia_antes:
        ruta_elegida = "GUIA"
    else:
        print("\n⚠️ No se detectaron actualizaciones en los hiperparámetros.")
        print("Es posible que el setup se haya cancelado. Terminando Orquestador.")
        sys.exit(0)
        
    # 4. Enrutamiento del Pipeline
    if ruta_elegida == "LIBRO":
        print("\n📚 RUTA DETECTADA: INICIANDO PIPELINE DE TEORÍA (LIBROS)...")
        time.sleep(1)
        ejecutar_paso("temario_builder.py")
        ejecutar_paso("syllabus_parser.py")
        ejecutar_paso("orchestrator.py")
        ejecutar_paso("generator_agent.py")
        # Inyección automática del "0" para compilar todo el libro de una vez
        ejecutar_paso("compilar_libro.py", auto_input="0")
        print("\n🏆 ¡PIPELINE DE LIBRO COMPLETADO CON ÉXITO! El sistema ha descansado.")
        
    elif ruta_elegida == "GUIA":
        print("\n📝 RUTA DETECTADA: INICIANDO PIPELINE DE PRÁCTICA (GUÍAS)...")
        time.sleep(1)
        ejecutar_paso("guia_builder.py")
        ejecutar_paso("guide_parser.py")
        ejecutar_paso("solver_agent.py")
        # Añadido el paso de compilación para la ruta de guías
        ejecutar_paso("compilar_guia.py")
        print("\n🏆 ¡PIPELINE DE GUÍAS COMPLETADO CON ÉXITO! El sistema ha descansado.")

if __name__ == "__main__":
    main()
```

==================================================
📄 ARCHIVO: Tonwini_setup.py
Ruta: .\Tonwini_setup.py
==================================================
```python
import os
import sys
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("🚨 CRÍTICO: No se encontró GEMINI_API_KEY.")
client = genai.Client(api_key=api_key)

# =========================================================================
# CATÁLOGOS MULTIDISCIPLINARIOS (LENGUAJE 100% AGNÓSTICO Y ESTRUCTURAL)
# =========================================================================

MODOS_LIBRO = {
    "1": ("academico_clasico", "Progresión Pedagógica: Fundamentos base -> Herramientas de análisis -> Aplicaciones simples -> Sistemas complejos."),
    "2": ("tratado_evolutivo", "Enfoque Histórico: Estado primitivo del problema -> Crisis del modelo anterior -> El punto de inflexión -> Síntesis moderna."),
    "3": ("manual_procedimental", "Enfoque de Resolución/Aplicado: Identificación de la anomalía -> Análisis de variables -> Protocolo de resolución paso a paso -> Prevención de fallos."),
    "4": ("compendio_dialectico", "Debate de Paradigmas: Fenómeno base -> Modelo A (argumentos) -> Modelo B (críticas) -> Estado actual de la disputa."),
    "5": ("divulgacion_estructurada", "Textos de Accesibilidad (Crash Course): Analogías base -> Mapa conceptual -> Implicancias reales (aislando jerga densa y formalismos iniciales)."),
    "6": ("estado_del_arte", "Fronteras del Conocimiento: Omite introducciones. Ataca directamente los límites teóricos actuales, problemas abiertos y desarrollos recientes."),
    "7": ("fichas_conceptuales", "Diccionario Analítico: Definiciones cortas y aisladas. Principio nuclear -> Contexto de uso inmediato -> Límites de validez o excepciones."),
    "8": ("ensayo_interconexion", "Síntesis Sistémica: Toma conceptos aparentemente inconexos y centra la redacción puramente en cómo interactúan formando un ecosistema.")
}

MODOS_GUIA = {
    "1": ("socratica_guiada", "[Dificultad: Baja-Media] Progresión lineal: Identificar elementos clave -> Modelar la interacción -> Analizar un escenario de cambio."),
    "2": ("evaluacion_hardcore", "[Dificultad: Alta/Examen] Evaluación profunda: Sistemas de múltiples variables y desarrollo deductivo estricto desde los primeros principios."),
    "3": ("laboratorio_frontera", "[Dificultad: Muy Alta/Nivel Experto] Casos de Ruptura: Escenarios donde el modelo estándar o las reglas base entran en conflicto; exige evaluar y proponer correcciones argumentadas."),
    "4": ("diagnostico_resolucion", "[Dificultad: Media-Alta] Enfoque Operativo: Aislar analíticamente la causa raíz de un fallo o vacío -> Proponer protocolo de corrección -> Predecir comportamiento."),
    "5": ("ensayo_cruzado", "[Dificultad: Alta] Pensamiento Sistémico: Obliga a usar el resultado analítico de una rama teórica como entrada obligatoria para aplicar las herramientas de otra rama."),
    "6": ("demostraciones_formales", "[Dificultad: Alta] Lógica Pura: Derivación estructural paso a paso de principios, normativas o leyes fundamentales de la materia."),
    "7": ("modelado_simplificado", "[Dificultad: Media] Capacidad de Abstracción: Aprender a justificar qué variables de un problema complejo de la realidad se deben ignorar para hacerlo resoluble."),
    "8": ("comparacion_analitica", "[Dificultad: Media-Alta] Toma de Decisiones: Evaluar Sistema/Escenario A -> Evaluar Sistema/Escenario B -> Justificar lógicamente cuál es más eficiente o adecuado."),
    "9": ("analisis_sensibilidad", "[Dificultad: Alta] Perturbaciones: Definir estado base en equilibrio -> Introducir un factor o desviación externa -> Analizar el impacto de dicho cambio."),
    "10": ("datos_faltantes", "[Dificultad: Muy Alta] Casos Profesionales Reales: El problema omite deliberadamente información vital; exige al alumno asumir premisas lógicas, justificarlas y resolver.")
}

def limpiar_consola():
    os.system('cls' if os.name == 'nt' else 'clear')

def optimizar_temas_con_llm(temas_crudos, nivel_academico, tipo_documento, nombre_modo):
    """
    Usa el LLM para pulir los temas crudos y redactar directrices de autor 
    sin sesgos de disciplina.
    """
    print("\n🧠 Tonwini Profiler: Procesando tu solicitud y generando directrices hiperparametrizadas...")
    
    system_instruction = f"""Eres el Perfilador Meta-Cognitivo (Capa 0) del Agente Tonwini.
    El usuario quiere crear un(a) {tipo_documento} de nivel '{nivel_academico}' usando el formato estructural '{nombre_modo}'.
    Te dará una lista cruda de temas o ideas vagas.
    
    Tu tarea:
    1. Organiza y limpia esa lista de temas para que se vea rigurosa y estructurada. No inventes temas que se alejen de la idea original.
    2. Redacta un pequeño párrafo al inicio llamado 'DIRECTRICES DEL AUTOR'. Aquí debes explicarle al agente redactor cómo debe tratar estos temas para cumplir con el nivel {nivel_academico}. 
    CRÍTICO: Usa lenguaje 100% multidisciplinario. Tus directrices deben ser igual de válidas si los temas son sobre Filosofía, Derecho, Biología celular o Ingeniería Aeroespacial.
    
    Devuelve solo el texto plano, sin formato Markdown alrededor, listo para ser guardado en un archivo .txt.
    """
    
    try:
        respuesta = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=f"Temas crudos provistos por el usuario:\n{temas_crudos}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
            )
        )
        return respuesta.text.strip()
    except Exception as e:
        print(f"⚠️ Error en la optimización con LLM ({e}). Se guardarán los temas crudos.")
        return temas_crudos

def main():
    limpiar_consola()
    print("="*85)
    print(" 🤖 AGENTE TONWINI - CAPA META-COGNITIVA ORQUESTADORA (SETUP V1.0)")
    print("="*85)
    
    # 1. Elegir Pipeline
    print("\n¿Qué tipo de material académico deseas estructurar hoy?")
    print("  [1] Libro Teórico (Pipeline de Teoría)")
    print("  [2] Guía de Ejercicios / Prácticas (Pipeline de Práctica)")
    
    while True:
        opcion_pipeline = input("\nSelecciona (1 o 2): ").strip()
        if opcion_pipeline in ["1", "2"]:
            break
        print("❌ Opción inválida.")

    # 2. Elegir Formato
    limpiar_consola()
    if opcion_pipeline == "1":
        tipo_documento = "Libro Teórico"
        archivo_salida = "temario_bruto.txt"
        etiqueta_modo = "MODO_TEXTO"
        catalogo = MODOS_LIBRO
        print(f"📖 CONFIGURANDO LIBRO TEÓRICO\n")
    else:
        tipo_documento = "Guía de Ejercicios"
        archivo_salida = "temas_guia.txt"
        etiqueta_modo = "MODO_GUIA"
        catalogo = MODOS_GUIA
        print(f"📝 CONFIGURANDO GUÍA DE EJERCICIOS\n")

    print("Selecciona el formato documental (Enfoque Analítico Estructural):")
    for key, (nombre, desc) in catalogo.items():
        print(f"  [{key}] {nombre.replace('_', ' ').title()}")
        print(f"      ↳ {desc}\n")

    while True:
        opcion_modo = input(f"Selecciona (1-{len(catalogo)}): ").strip()
        if opcion_modo in catalogo:
            modo_seleccionado = catalogo[opcion_modo][0]
            break
        print("❌ Opción inválida.")

    # 3. Nivel Académico
    limpiar_consola()
    print(f"🎓 Formato seleccionado: {modo_seleccionado.upper()}")
    print("\nDefine el nivel académico o profundidad de la obra:")
    print("(Ej: Pregrado, Bachillerato, Nivel Doctoral, Divulgación General, Cátedra Avanzada)")
    nivel_academico = input("> ").strip()
    if not nivel_academico:
        nivel_academico = "Universitario General"

    # 4. Temas Crudos
    print("\n✍️  Escribe los temas que deseas tratar (pueden ser conceptos sueltos, un párrafo vago o separados por comas):")
    temas_crudos = input("> ").strip()
    if not temas_crudos:
        print("⚠️ No ingresaste temas. Cerrando setup.")
        sys.exit()

    # 5. Optimización LLM
    contenido_optimizado = optimizar_temas_con_llm(temas_crudos, nivel_academico, tipo_documento, modo_seleccionado)

    # 6. Empaquetado y Guardado
    contenido_final = f"{etiqueta_modo}: {modo_seleccionado}\n"
    contenido_final += "===\n"
    contenido_final += contenido_optimizado

    with open(archivo_salida, "w", encoding="utf-8") as f:
        f.write(contenido_final)

    limpiar_consola()
    print("✅ ¡SETUP COMPLETADO CON ÉXITO!")
    print(f"El archivo '{archivo_salida}' ha sido generado e hiperparametrizado.\n")
    print("CONTENIDO GENERADO:")
    print("-" * 60)
    print(contenido_final)
    print("-" * 60)
    
    if opcion_pipeline == "1":
        print("\n🚀 Próximo paso: Ejecuta 'python temario_builder.py' para expandir el programa.")
    else:
        print("\n🚀 Próximo paso: Ejecuta 'python guia_builder.py' para que el Catedrático diseñe la evaluación.")

if __name__ == "__main__":
    main()
```

==================================================
📄 ARCHIVO: ver_modelos.py
Ruta: .\ver_modelos.py
==================================================
```python
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("🔍 Buscando los nombres exactos en la API...\n")
for m in client.models.list():
    if 'pro' in m.name.lower():
        print(f"Nombre en Interfaz: {m.display_name}")
        print(f"-> STRING PARA TU CÓDIGO: '{m.name}'\n")
```

