import os
import json
import re

def limpiar_nombre_carpeta(texto):
    texto_limpio = re.sub(r'[^a-zA-Z0-9]', '_', texto)
    texto_limpio = re.sub(r'_+', '_', texto_limpio)
    return texto_limpio.strip('_')

def construir_esqueleto(json_path):
    print(f"🏗️ Iniciando la construcción del esqueleto jerárquico desde {json_path}...")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as file:
            estructura = json.load(file)
    except FileNotFoundError:
        print(f"🚨 Error: No se encontró el archivo {json_path}")
        return

    titulo_libro = estructura['metadata'].get('titulo', 'Libro_Generico')
    nombre_seguro = limpiar_nombre_carpeta(titulo_libro)
    base_dir = f"libro_{nombre_seguro}"
    
    chapters_dir = os.path.join(base_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)
    
    main_tex_path = os.path.join(base_dir, "main.tex")
    
    main_tex_content = f"""\\documentclass[12pt, a4paper, openany]{{book}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath, amssymb, physics}}
\\usepackage{{hyperref}}

\\title{{{estructura['metadata']['titulo']}}}
\\author{{{estructura['metadata']['autor']}}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle
\\tableofcontents

"""

    for cap in estructura.get("capitulos", []):
        id_cap = cap["id"]
        titulo_cap = cap["titulo"]
        ruta_archivo = os.path.join(chapters_dir, f"{id_cap}.tex")
        
        main_tex_content += f"\\include{{chapters/{id_cap}}}\n"
        
        with open(ruta_archivo, 'w', encoding='utf-8') as f:
            f.write(f"% Este archivo fue generado automáticamente\n")
            f.write(f"\\chapter{{{titulo_cap}}}\n\n")
            
            for sec in cap.get("secciones", []):
                f.write(f"\\section{{{sec['titulo']}}}\n")
                if sec.get("preambulo"):
                    f.write(f"% --- Preámbulo de sección: {sec['id']} ---\n\n")
                
                for subsec in sec.get("subsecciones", []):
                    f.write(f"\\subsection{{{subsec['titulo']}}}\n")
                    
                    # --- NUEVO NIVEL: INCISOS (Fragmentación Atómica) ---
                    for inciso in subsec.get("incisos", []):
                        f.write(f"\\subsubsection{{{inciso['titulo']}}}\n")
                        f.write(f"% El Agente insertará el contenido aquí para: {inciso.get('id', 'inciso')}\n\n")
            
        print(f"✅ Creado/Actualizado: {ruta_archivo}")

    main_tex_content += "\n\\end{document}\n"
    
    with open(main_tex_path, 'w', encoding='utf-8') as f:
        f.write(main_tex_content)
        
    print("🚀 ¡Esqueleto de 4 niveles construido exitosamente!")

if __name__ == "__main__":
    construir_esqueleto("book_structure.json")