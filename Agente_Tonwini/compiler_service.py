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