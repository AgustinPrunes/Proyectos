import os
import requests
from dotenv import load_dotenv

# Cargamos tu clave
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("🚨 No se encontró la API Key.")
    exit()

print("🔍 Consultando a Google los modelos disponibles para tu cuenta...")

# Hacemos la llamada directa a la API
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
respuesta = requests.get(url)

if respuesta.status_code == 200:
    datos = respuesta.json()
    print("\n✅ MODELOS DISPONIBLES PARA GENERAR TEXTO:")
    print("-" * 50)
    for modelo in datos.get('models', []):
        # Filtramos solo los modelos que sirven para generar contenido
        if 'generateContent' in modelo.get('supportedGenerationMethods', []):
            # Limpiamos el prefijo 'models/' para que veas el string exacto
            nombre_limpio = modelo['name'].replace('models/', '')
            print(nombre_limpio)
    print("-" * 50)
else:
    print(f"🚨 Error al consultar la API: {respuesta.status_code}")
    print(respuesta.text)