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