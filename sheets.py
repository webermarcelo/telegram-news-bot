import requests
import json
from datetime import datetime


def publicar_en_sheet(apps_script_url, titulo, texto, imagen_url=""):
    """Publica una nota en Google Sheet via Apps Script"""
    fecha = datetime.now().strftime("%d/%m/%Y")

    payload = {
        "titulo": titulo,
        "fecha": fecha,
        "imagen": imagen_url,
        "texto": texto
    }

    try:
        resp = requests.post(
            apps_script_url,
            data=json.dumps(payload),
            headers={"Content-Type": "text/plain"},
            timeout=15
        )
        resp.raise_for_status()

        resultado = resp.json()
        return {"exito": True, "mensaje": resultado.get("message", "Publicado")}

    except Exception as e:
        print(f"[Sheets] Error: {e}")
        return {"exito": False, "error": str(e)}
