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