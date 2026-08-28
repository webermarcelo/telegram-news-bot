import requests
from bs4 import BeautifulSoup


def publicar_en_facebook(page_access_token, page_id, mensaje, imagen_url="", link_comentario=""):
    """Publica un post en la Página de Facebook, opcionalmente con imagen"""
    print(f"[Facebook] imagen_url recibida: '{imagen_url}'", flush=True)
    if imagen_url and len(imagen_url) > 10:
        print(f"[Facebook] Publicando con imagen...", flush=True)
        resultado = _publicar_con_imagen(page_access_token, page_id, mensaje, imagen_url, link_comentario)
        print(f"[Facebook] Resultado: {resultado}", flush=True)
        return resultado
    print("[Facebook] Sin imagen, publicando solo texto", flush=True)
    return _publicar_texto(page_access_token, page_id, mensaje, link_comentario)


def buscar_imagen_og(url_noticia):
    """Busca og:image en la URL original de la noticia como fallback"""
    try:
        resp = requests.get(url_noticia, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og = soup.select_one("meta[property='og:image']")
            if og and og.get("content"):
                print(f"[Facebook] og:image encontrada: {og['content'][:80]}", flush=True)
                return og["content"]
    except Exception as e:
        print(f"[Facebook] Error buscan og:image: {e}", flush=True)
    return ""


def _publicar_con_imagen(page_access_token, page_id, mensaje, imagen_url, link_comentario=""):
    """Publica un post con imagen usando el parametro url de Facebook"""
    try:
        url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
        payload = {
            "message": mensaje,
            "url": imagen_url,
            "access_token": page_access_token,
        }
        resp = requests.post(url, data=payload, timeout=30)
        result = resp.json()
        print(f"[Facebook] photos response: {result}", flush=True)

        if "id" in result:
            post_id = result["id"]
            post_url = f"https://facebook.com/{post_id.replace('_', '/posts/')}"
            if link_comentario:
                commentar_en_post(page_access_token, post_id, link_comentario)
            return {"exito": True, "post_id": post_id, "url": post_url}
        else:
            error_msg = result.get("error", {}).get("message", "Error desconocido")
            print(f"[Facebook] API error: {error_msg}", flush=True)
            return {"exito": False, "error": error_msg}

    except Exception as e:
        print(f"[Facebook] Excepcion con imagen: {e}", flush=True)
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
        print(f"[Facebook] Error: {e}", flush=True)
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
        print(f"[Facebook] Error comment: {e}", flush=True)
        return False
