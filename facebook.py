import requests
import json


def publicar_en_facebook(page_access_token, page_id, mensaje, link=""):
    """Publica un post en la Página de Facebook"""
    url = f"https://graph.facebook.com/v21.0/{page_id}/feed"

    payload = {
        "message": mensaje,
        "access_token": page_access_token,
    }
    if link:
        payload["link"] = link

    try:
        resp = requests.post(url, data=payload, timeout=15)
        result = resp.json()

        if "id" in result:
            post_id = result["id"]
            post_url = f"https://facebook.com/{post_id.replace('_', '/posts/')}"
            return {"exito": True, "post_id": post_id, "url": post_url}
        else:
            error_msg = result.get("error", {}).get("message", "Error desconocido")
            return {"exito": False, "error": error_msg}

    except Exception as e:
        print(f"[Facebook] Error: {e}")
        return {"exito": False, "error": str(e)}
