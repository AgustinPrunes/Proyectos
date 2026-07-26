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