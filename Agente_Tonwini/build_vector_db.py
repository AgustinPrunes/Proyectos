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