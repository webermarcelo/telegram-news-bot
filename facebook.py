import requests
import json


def publicar_en_facebook(page_access_token, page_id, mensaje, link=""):
    """Publica un post en la Página de Facebook"""
    url = f"https://graph.facebook.com/v21.0/{page_id}/feed"

    print(f"[Facebook] Page ID: {page_id}")
    print(f"[Facebook] Token length: {len(page_access_token)}")
    print(f"[Facebook] Token start: {page_access_token[:20]}...")

    payload = {
        "message": mensaje,
        "access_token": page_access_token,
    }

    try:
        resp = requests.post(url, data=payload, timeout=15)
        result = resp.json()

        print(f"[Facebook] Response: {result}")

        if "id" in result:
            post_id = result["id"]
            post_url = f"https://facebook.com/{post_id.replace('_', '/posts/')}"

            if link:
                commentar_en_post(page_access_token, post_id, link)

            return {"exito": True, "post_id": post_id, "url": post_url}
        else:
            error_msg = result.get("error", {}).get("message", "Error desconocido")
            return {"exito": False, "error": error_msg}

    except Exception as e:
        print(f"[Facebook] Error: {e}")
        return {"exito": False, "error": str(e)}


def commentar_en_post(page_access_token, post_id, mensaje):
    """Publica un comentario en un post de Facebook"""
    url = f"https://graph.facebook.com/v21.0/{post_id}/comments"

    payload = {
        "message": mensaje,
        "access_token": page_access_token,
    }

    try:
        resp = requests.post(url, data=payload, timeout=15)
        result = resp.json()
        return "id" in result
    except Exception as e:
        print(f"[Facebook] Error comment: {e}")
        return False
