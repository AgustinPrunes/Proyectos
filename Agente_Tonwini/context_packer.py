import os

def generar_contexto(archivo_salida="contexto_agente_universitario.md"):
    # Extensiones de los archivos cuyo código fuente SÍ queremos leer
    extensiones_validas = ['.py', '.json', '.txt', '.md']
    
    # Carpetas que queremos MOSTRAR en el árbol, pero NO leer su contenido
    carpetas_excluidas = [
        '.git', '__pycache__', '.venv', 'venv', 
        'chroma_db', 'bibliografia', 'bibliografia_escaneada', 
        'Pensamientos', 'guias_out', 'syllabus',
        'compendio_preguntas', 'guias_in',
        'Errores', 'PDFs_guias',
        'PDFs_libros'
    ]
    
    # Archivos específicos que no queremos leer (ej. el json del grafo que será enorme)
    archivos_excluidos = ['.env', 'conocimiento_grafo.json', 'contexto_agente_universitario.md', 'book_structure.json',
        'guide_structure.json', 'temario_bruto.txt',
        'temas_guia.txt']

    with open(archivo_salida, 'w', encoding='utf-8') as out:
        out.write("==================================================\n")
        out.write("ARQUITECTURA DEL AGENTE AUTÓNOMO UNIVERSITARIO\n")
        out.write("==================================================\n\n")
        
        # 1. DIBUJAR EL ÁRBOL DE CARPETAS
        out.write("📁 ESTRUCTURA DE DIRECTORIOS:\n\n")
        for root, dirs, files in os.walk('.'):
            level = root.replace('.', '').count(os.sep)
            indent = ' ' * 4 * level
            basename = os.path.basename(root)
            
            if level == 0:
                out.write("📦 [Proyecto Raíz]/\n")
            else:
                if basename in carpetas_excluidas:
                    out.write(f"{indent}📂 {basename}/ (Contenido omitido)\n")
                    dirs[:] = []  # Le decimos a os.walk que no entre a esta carpeta
                    continue
                else:
                    out.write(f"{indent}📂 {basename}/\n")
            
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                if any(f.endswith(ext) for ext in extensiones_validas):
                    out.write(f"{subindent}📄 {f}\n")
                    
        out.write("\n==================================================\n")
        out.write("CÓDIGO FUENTE DE LOS ARCHIVOS\n")
        out.write("==================================================\n\n")

        # 2. LEER Y PEGAR EL CÓDIGO
        for root, dirs, files in os.walk('.'):
            # Filtramos las carpetas para no entrar a las excluidas al buscar código
            dirs[:] = [d for d in dirs if d not in carpetas_excluidas]
            
            for file in files:
                if file in archivos_excluidos:
                    continue
                    
                if any(file.endswith(ext) for ext in extensiones_validas):
                    ruta_completa = os.path.join(root, file)
                    try:
                        with open(ruta_completa, 'r', encoding='utf-8') as f_in:
                            contenido = f_in.read()
                            
                        out.write(f"==================================================\n")
                        out.write(f"📄 ARCHIVO: {file}\n")
                        out.write(f"Ruta: {ruta_completa}\n")
                        out.write(f"==================================================\n")
                        out.write(f"```python\n{contenido}\n```\n\n")
                    except Exception as e:
                        out.write(f"⚠️ Error leyendo {file}: {str(e)}\n\n")

    print(f"✅ Empaquetado completado: {archivo_salida}")

if __name__ == "__main__":
    generar_contexto()