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