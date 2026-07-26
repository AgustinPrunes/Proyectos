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