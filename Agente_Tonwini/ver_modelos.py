import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("🔍 Buscando los nombres exactos en la API...\n")
for m in client.models.list():
    if 'pro' in m.name.lower():
        print(f"Nombre en Interfaz: {m.display_name}")
        print(f"-> STRING PARA TU CÓDIGO: '{m.name}'\n")