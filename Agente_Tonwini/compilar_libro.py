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