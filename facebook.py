import requests
import json

def publicar_en_facebook(page_access_token, page_id, mensaje, imagen_url="", link_comentario=""):
    """Publica un post en la Página de Facebook, opcionalmente con imagen"""
    print(f"[Facebook] imagen_url recibida: '{imagen_url}'")
    if imagen_url and len(imagen_url) > 10:
        print(f"[Facebook] Intentando publicar con imagen...")
        resultado = _publicar_con_imagen(page_access_token, page_id, mensaje, imagen_url, link_comentario)
        print(f"[Facebook] Resultado con imagen: {resultado}")
        return resultado
    print("[Facebook] Sin imagen valida, publicando solo texto")
    return _publicar_texto(page_access_token, page_id, mensaje, link_comentario)


def _publicar_con_imagen(page_access_token, page_id, mensaje, imagen_url, link_comentario=""):
    """Publica un post con imagen usando el parámetro url de Facebook"""
    try:
        url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
        payload = {
            "message": mensaje,
            "url": imagen_url,
            "access_token": page_access_token,
        }
        resp = requests.post(url, data=payload, timeout=30)
        result = resp.json()
        print(f"[Facebook] photos result: {result}")

        if "id" in result:
            post_id = result["id"]
            post_url = f"https://facebook.com/{post_id.replace('_', '/posts/')}"
            if link_comentario:
                commentar_en_post(page_access_token, post_id, link_comentario)
            return {"exito": True, "post_id": post_id, "url": post_url}
        else:
            error_msg = result.get("error", {}).get("message", "Error desconocido")
            return {"exito": False, "error": error_msg}

    except Exception as e:
        print(f"[Facebook] Error con imagen: {e}")
        return _publicar_texto(page_access_token, page_id, mensaje, link_comentario)


def _publicar_texto(page_access_token, page_id, mensaje, link_comentario=""):
    """Publica un post de solo texto"""
    url = f"https://graph.facebook.com/v21.0/{page_id}/feed"

    payload = {
        "message": mensaje,
        "access_token": page_access_token,
    }

    try:
        resp = requests.post(url, data=payload, timeout=15)
        result = resp.json()

        if "id" in result:
            post_id = result["id"]
            post_url = f"https://facebook.com/{post_id.replace('_', '/posts/')}"
            if link_comentario:
                commentar_en_post(page_access_token, post_id, link_comentario)
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
