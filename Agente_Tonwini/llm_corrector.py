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