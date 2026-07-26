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