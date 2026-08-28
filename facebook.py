import requests
import json
import tempfile
import os


def publicar_en_facebook(page_access_token, page_id, mensaje, imagen_url="", link_comentario=""):
    """Publica un post en la Página de Facebook, opcionalmente con imagen"""
    if imagen_url:
        return _publicar_con_imagen(page_access_token, page_id, mensaje, imagen_url, link_comentario)
    return _publicar_texto(page_access_token, page_id, mensaje, link_comentario)


def _publicar_con_imagen(page_access_token, page_id, mensaje, imagen_url, link_comentario=""):
    """Publica un post con imagen descargada"""
    tmp_path = None
    try:
        img_resp = requests.get(imagen_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        img_resp.raise_for_status()

        ext = ".jpg"
        if "png" in img_resp.headers.get("content-type", ""):
            ext = ".png"

        tmp_path = os.path.join(tempfile.gettempdir(), f"fb_post{ext}")
        with open(tmp_path, "wb") as f:
            f.write(img_resp.content)

        url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
        with open(tmp_path, "rb") as img_file:
            payload = {
                "message": mensaje,
                "access_token": page_access_token,
            }
            resp = requests.post(url, data=payload, files={"source": img_file}, timeout=30)

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
        print(f"[Facebook] Error con imagen: {e}")
        return _publicar_texto(page_access_token, page_id, mensaje, link_comentario)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


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
