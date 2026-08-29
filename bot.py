import os
import sys
import json
import time
import hashlib
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from gemini import redactar_con_ia, generar_post_facebook
from sheets import publicar_en_sheet
from facebook import publicar_en_facebook, buscar_imagen_og

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ==================== CONFIGURACION ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SEEN_FILE = os.path.join(BASE_DIR, "seen_news.json")
PENDING_FILE = os.path.join(BASE_DIR, "pending_news.json")

def load_config():
    env_token = os.environ.get("TELEGRAM_TOKEN")
    if env_token:
        fuentes_raw = os.environ.get("FUENTES_ACTIVAS", "")
        fuentes = [f.strip() for f in fuentes_raw.split(",") if f.strip()] if fuentes_raw else list(SCRAPERS.keys())
        return {
            "telegram_token": env_token,
            "telegram_chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "gemini_api_key": os.environ["GEMINI_API_KEY"],
            "apps_script_url": os.environ["APPS_SCRIPT_URL"],
            "intervalo_minutos": int(os.environ.get("INTERVALO_MINUTOS", "30")),
            "fuentes_activas": fuentes,
            "facebook_app_id": os.environ.get("FACEBOOK_APP_ID", ""),
            "facebook_app_secret": os.environ.get("FACEBOOK_APP_SECRET", ""),
            "facebook_page_token": os.environ.get("FACEBOOK_PAGE_TOKEN", ""),
            "facebook_page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_seen(context=None):
    if context and "seen" in context.bot_data:
        return context.bot_data["seen"]
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if context:
                context.bot_data["seen"] = data
            return data
    return {}

def save_seen(seen, context=None):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)
    if context:
        context.bot_data["seen"] = seen

def load_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_pending(pending):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

def find_nearby_image(tag):
    """Busca una imagen en el tag o en sus padres cercanos"""
    img = tag.select_one("img[src]")
    if img:
        src = img.get("src", "") or img.get("data-src", "")
        if src and "scorecardresearch" not in src and "pixel" not in src and len(src) > 10:
            return src
    parent = tag.parent
    for _ in range(4):
        if not parent:
            break
        img = parent.select_one("img[src]")
        if img:
            src = img.get("src", "") or img.get("data-src", "")
            if src and "scorecardresearch" not in src and "pixel" not in src and len(src) > 10:
                return src
        parent = parent.parent
    return ""

def make_id(title, url):
    raw = f"{title}|{url}"
    return hashlib.md5(raw.encode()).hexdigest()

def slugify(text):
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = text.replace(" ", "-")
    text = "".join(c for c in text if c.isalnum() or c == "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")

# ==================== SCRAPERS ====================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

def scrape_vandal():
    noticias = []
    try:
        resp = requests.get("https://vandal.elespanol.com/noticias", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.select_one("#pestana_noticias")
        if not container:
            container = soup
        for a in container.select("a[href*='/noticia/']")[:15]:
            url = a.get("href", "")
            if not url.startswith("http"):
                url = "https://vandal.elespanol.com" + url
            title = a.get_text(strip=True)
            img = a.select_one("img")
            imagen = ""
            if img:
                imagen = img.get("src", "") or img.get("data-src", "")
            if title and len(title) > 10:
                noticias.append({"titulo": title, "url": url, "fuente": "Vandal", "resumen": "", "fecha": "", "imagen": imagen})
    except Exception as e:
        print(f"[Vandal] Error: {e}")
    return noticias

def scrape_tierragamer():
    noticias = []
    try:
        resp = requests.get(
            "https://tierragamer.com/wp-json/wp/v2/posts?categories=5&per_page=10&_embed",
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            for post in resp.json():
                title = post.get("title", {}).get("rendered", "")
                link = post.get("link", "")
                media = post.get("_embedded", {}).get("wp:featuredmedia", [])
                imagen = media[0].get("source_url", "") if media else ""
                import html as html_mod
                title = html_mod.unescape(title)
                if title:
                    noticias.append({"titulo": title, "url": link, "fuente": "TierraGamer", "resumen": "", "fecha": "", "imagen": imagen})
    except Exception as e:
        print(f"[TierraGamer] Error: {e}")
    return noticias

def scrape_eurogamer():
    noticias = []
    try:
        resp = requests.get("https://www.eurogamer.es/news", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article.archive__item")[:10]:
            title_tag = article.select_one("h2.archive__title a")
            desc_tag = article.select_one("div.archive__strapline")
            date_tag = article.select_one("time.archive__date")
            if title_tag:
                title = title_tag.get_text(strip=True)
                url = title_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.eurogamer.es" + url
                resumen = desc_tag.get_text(strip=True)[:200] if desc_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                noticias.append({"titulo": title, "url": url, "fuente": "Eurogamer", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[Eurogamer] Error: {e}")
    return noticias

def scrape_3djuegos():
    noticias = []
    try:
        resp = requests.get("https://www.3djuegos.com/noticias/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .article-card, .news-item")[:10]:
            link_tag = article.select_one("a[href*='/noticias/']")
            title_tag = article.select_one("h2, h3, .title")
            desc_tag = article.select_one("p, .description, .excerpt")
            date_tag = article.select_one("time, .date, span[class*='date']")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.3djuegos.com" + url
                resumen = desc_tag.get_text(strip=True)[:200] if desc_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 10:
                    noticias.append({"titulo": title, "url": url, "fuente": "3DJuegos", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[3DJuegos] Error: {e}")
    return noticias

def scrape_ign():
    noticias = []
    try:
        resp = requests.get("https://www.ign.com/articles", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href*='/articles/']")[:15]:
            url = a.get("href", "")
            if not url.startswith("http"):
                url = "https://www.ign.com" + url
            title = a.get_text(strip=True)
            img = a.select_one("img")
            imagen = ""
            if img:
                imagen = img.get("src", "") or img.get("data-src", "")
                if imagen and not imagen.startswith("http"):
                    imagen = "https://www.ign.com" + imagen
            if title and len(title) > 10:
                noticias.append({"titulo": title, "url": url, "fuente": "IGN", "resumen": "", "fecha": "", "imagen": imagen})
    except Exception as e:
        print(f"[IGN] Error: {e}")
    return noticias

# ==================== SCRAPERS: EFEMERIDES ====================

KEYWORDS_EFEMERIDES = [
    "cine", "película", "pelicula", "serie", "televisión", "television",
    "videojuego", "consola", "nintendo", "playstation", "atari", "sega",
    "disco", "álbum", "album", "canción", "cancion", "banda", "música",
    "actor", "actriz", "director", "tecnología", "tecnologia",
    "computadora", "ordenador", "internet", "software", "hardware",
    "msx", "amiga", "commodore", "amstrad", "spectrum", "dos",
    "windows", "apple", "macintosh", "sony", "microsoft",
    "marvel", "dc", "comics", "cómic", "comic", "manga", "anime",
    "radio", "tv", "canal", "emisora", "programa",
    "deportes", "fútbol", "futbol", "basket", "tenis", "f1",
    "olimpiadas", "mundial", "copa",
    "moda", "tendencia", "moda retro",
    "juguete", "juguete", "figura", "action figure",
]

WIKI_HEADERS = {
    "User-Agent": "MillennialsArBot/1.0 (https://millennials.ar; contact@millennials.ar)",
    "Accept": "application/json",
}

def scrape_wikipedia_efemerides():
    """Busca efemerides del dia en Wikipedia API, filtradas por relevancia cultural"""
    noticias = []
    try:
        from datetime import datetime as dt_now
        now = dt_now.now()
        month = f"{now.month:02d}"
        day = f"{now.day:02d}"

        url = f"https://es.wikipedia.org/api/rest_v1/feed/onthisday/all/{month}/{day}"
        resp = requests.get(url, headers=WIKI_HEADERS, timeout=15)
        if resp.status_code != 200:
            return noticias

        data = resp.json()
        year_actual = now.year

        eventos = data.get("events", []) + data.get("selected", [])

        for evento in eventos:
            year = evento.get("year", 0)
            text = evento.get("text", "")

            if not text or not year:
                continue

            texto_lower = text.lower()
            relevante = any(kw in texto_lower for kw in KEYWORDS_EFEMERIDES)

            if not relevante:
                continue

            diff = year_actual - year
            if diff < 10:
                continue

            pages = evento.get("pages", [])
            wiki_url = ""
            if pages:
                wiki_url = pages[0].get("content_urls", {}).get("desktop", {}).get("page", "")
                if not wiki_url:
                    wiki_url = f"https://es.wikipedia.org/wiki/{pages[0].get('title', '').replace(' ', '_')}"

            titulo = f"{year}: {text[:80]}"
            if len(text) > 80:
                titulo += "..."

            noticias.append({
                "titulo": titulo,
                "url": wiki_url or f"https://es.wikipedia.org/api/rest_v1/feed/onthisday/all/{month}/{day}",
                "fuente": "Wikipedia",
                "resumen": text,
                "fecha": f"{year}-01-01",
                "imagen": "",
            })

        nacimientos = data.get("births", [])
        for nac in nacimientos[:10]:
            year = nac.get("year", 0)
            text = nac.get("text", "")
            if not text or not year:
                continue
            texto_lower = text.lower()
            relevante = any(kw in texto_lower for kw in KEYWORDS_EFEMERIDES)
            if not relevante:
                continue
            pages = nac.get("pages", [])
            wiki_url = ""
            if pages:
                wiki_url = pages[0].get("content_urls", {}).get("desktop", {}).get("page", "")
            titulo = f"Nacimiento {year}: {text[:70]}"
            noticias.append({
                "titulo": titulo,
                "url": wiki_url or "",
                "fuente": "Wikipedia",
                "resumen": text,
                "fecha": f"{year}-01-01",
                "imagen": "",
            })

    except Exception as e:
        print(f"[Wikipedia Efemerides] Error: {e}")
    return noticias

# ==================== SCRAPERS: CULTURA POP RETRO ====================

def scrape_nostalgiapop():
    noticias = []
    try:
        resp = requests.get("https://www.nostalgiapop.es", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .post")[:10]:
            link_tag = article.select_one("a[href]")
            title_tag = article.select_one("h2, h3, .entry-title, .post-title")
            date_tag = article.select_one("time, .entry-date, .post-date")
            excerpt_tag = article.select_one(".entry-summary, .excerpt, p")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.nostalgiapop.es" + url
                resumen = excerpt_tag.get_text(strip=True)[:200] if excerpt_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 5:
                    noticias.append({"titulo": title, "url": url, "fuente": "NostalgiaPop", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[NostalgiaPop] Error: {e}")
    return noticias

def scrape_decada80():
    noticias = []
    try:
        resp = requests.get("https://www.decada80.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .post, .entry")[:10]:
            link_tag = article.select_one("a[href]")
            title_tag = article.select_one("h2, h3, .entry-title, .post-title")
            date_tag = article.select_one("time, .entry-date, .post-date")
            excerpt_tag = article.select_one(".entry-summary, .excerpt, p")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.decada80.com" + url
                resumen = excerpt_tag.get_text(strip=True)[:200] if excerpt_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 5:
                    noticias.append({"titulo": title, "url": url, "fuente": "Decada80", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[Decada80] Error: {e}")
    return noticias

def scrape_retroconsolas():
    noticias = []
    try:
        resp = requests.get("https://retroconsolas.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .post, .entry")[:10]:
            link_tag = article.select_one("a[href]")
            title_tag = article.select_one("h2, h3, .entry-title, .post-title")
            date_tag = article.select_one("time, .entry-date, .post-date")
            excerpt_tag = article.select_one(".entry-summary, .excerpt, p")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://retroconsolas.com" + url
                resumen = excerpt_tag.get_text(strip=True)[:200] if excerpt_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 5:
                    noticias.append({"titulo": title, "url": url, "fuente": "RetroConsolas", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[RetroConsolas] Error: {e}")
    return noticias

def scrape_pulsayjuega():
    noticias = []
    try:
        resp = requests.get("https://pulsayjuega.blog", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .post, .entry")[:10]:
            link_tag = article.select_one("a[href]")
            title_tag = article.select_one("h2, h3, .entry-title, .post-title")
            date_tag = article.select_one("time, .entry-date, .post-date")
            excerpt_tag = article.select_one(".entry-summary, .excerpt, p")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://pulsayjuega.blog" + url
                resumen = excerpt_tag.get_text(strip=True)[:200] if excerpt_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 5:
                    noticias.append({"titulo": title, "url": url, "fuente": "Pulsa y Juega", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[Pulsa y Juega] Error: {e}")
    return noticias

def scrape_rebobina80():
    noticias = []
    try:
        resp = requests.get("https://rebobinalos80.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .post, .entry")[:10]:
            link_tag = article.select_one("a[href]")
            title_tag = article.select_one("h2, h3, .entry-title, .post-title")
            date_tag = article.select_one("time, .entry-date, .post-date")
            excerpt_tag = article.select_one(".entry-summary, .excerpt, p")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://rebobinalos80.com" + url
                resumen = excerpt_tag.get_text(strip=True)[:200] if excerpt_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 5:
                    noticias.append({"titulo": title, "url": url, "fuente": "Rebobina los 80", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[Rebobina los 80] Error: {e}")
    return noticias

def scrape_elnostalgico():
    noticias = []
    try:
        resp = requests.get("https://www.elnostalgico.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .post, .entry")[:10]:
            link_tag = article.select_one("a[href]")
            title_tag = article.select_one("h2, h3, .entry-title, .post-title")
            date_tag = article.select_one("time, .entry-date, .post-date")
            excerpt_tag = article.select_one(".entry-summary, .excerpt, p")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.elnostalgico.com" + url
                resumen = excerpt_tag.get_text(strip=True)[:200] if excerpt_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                imagen = find_nearby_image(article)
                if title and len(title) > 5:
                    noticias.append({"titulo": title, "url": url, "fuente": "El Nostalgico", "resumen": resumen, "fecha": fecha, "imagen": imagen})
    except Exception as e:
        print(f"[El Nostalgico] Error: {e}")
    return noticias

SCRAPERS = {
    "Vandal": scrape_vandal,
    "Eurogamer": scrape_eurogamer,
    "3DJuegos": scrape_3djuegos,
    "IGN": scrape_ign,
    "TierraGamer": scrape_tierragamer,
    "Wikipedia Efemerides": scrape_wikipedia_efemerides,
    "NostalgiaPop": scrape_nostalgiapop,
    "Decada80": scrape_decada80,
    "RetroConsolas": scrape_retroconsolas,
    "Pulsa y Juega": scrape_pulsayjuega,
    "Rebobina los 80": scrape_rebobina80,
    "El Nostalgico": scrape_elnostalgico,
}

# ==================== HANDLERS DEL BOT ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot de Noticias Millennials.ar\n\n"
        "Comandos:\n"
        "/noticias - Noticias nuevas (ultimas)\n"
        "/buscar - Buscar por tiempo (24h, 12h, 6h, 3h, 1h)\n"
        "/publicar - Ver noticias pendientes\n"
        "/stats - Estadisticas"
    )

async def cmd_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("24 horas", callback_data="filtro:24h"),
            InlineKeyboardButton("12 horas", callback_data="filtro:12h"),
        ],
        [
            InlineKeyboardButton("6 horas", callback_data="filtro:6h"),
            InlineKeyboardButton("3 horas", callback_data="filtro:3h"),
        ],
        [
            InlineKeyboardButton("1 hora", callback_data="filtro:1h"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("¿Cuantas horas hacia atras queres buscar?", reply_markup=reply_markup)

async def cmd_noticias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    seen = load_seen(context)
    chat_id = update.effective_chat.id

    await update.message.reply_text("Buscando noticias...")

    activas = config.get("fuentes_activas", list(SCRAPERS.keys()))
    total_nuevas = 0

    for nombre in activas:
        if nombre not in SCRAPERS:
            continue
        try:
            noticias = SCRAPERS[nombre]()
            for noticia in noticias[:3]:
                nid = make_id(noticia["titulo"], noticia["url"])
                if nid not in seen:
                    keyboard = [
                        [
                            InlineKeyboardButton("Redactar con IA", callback_data=f"redactar:{nid}"),
                            InlineKeyboardButton("Siguiente", callback_data=f"siguiente:{nid}"),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    fecha_str = ""
                    if noticia.get("fecha"):
                        try:
                            if "T" in noticia["fecha"]:
                                dt = datetime.fromisoformat(noticia["fecha"].replace("Z", "+00:00"))
                                fecha_str = dt.strftime("%d/%m/%Y")
                            else:
                                fecha_str = noticia["fecha"][:10]
                        except:
                            pass

                    msg = (
                        f"[{noticia['fuente']}]"
                        + (f"\nFecha: {fecha_str}" if fecha_str else "")
                        + f"\n\n{noticia['titulo']}"
                    )
                    if noticia.get("resumen"):
                        msg += f"\n\n{noticia['resumen']}"

                    await context.bot.send_message(
                        chat_id=chat_id, text=msg, reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                    total_nuevas += 1

                    seen[nid] = {
                        "titulo": noticia["titulo"],
                        "fuente": noticia["fuente"],
                        "url": noticia["url"],
                        "resumen": noticia.get("resumen", ""),
                        "fecha": noticia.get("fecha", ""),
                    }
                    time.sleep(1)
        except Exception as e:
            print(f"Error {nombre}: {e}")

    save_seen(seen, context)
    if total_nuevas == 0:
        await update.message.reply_text("No hay noticias nuevas por el momento.")
    else:
        await update.message.reply_text(f"Se encontraron {total_nuevas} noticias nuevas.")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seen = load_seen(context)
    pending = load_pending()
    await update.message.reply_text(
        f"Estadisticas:\n\n"
        f"Noticias procesadas: {len(seen)}\n"
        f"Pendientes de publicar: {len(pending)}"
    )

async def cmd_publicar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = load_pending()
    if not pending:
        await update.message.reply_text("No hay noticias pendientes de publicar.")
        return

    await update.message.reply_text(f"Tenés {len(pending)} noticias pendientes. Usá /noticias para buscar nuevas.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    config = load_config()

    data = query.data
    chat_id = query.message.chat.id

    if data.startswith("filtro:"):
        horas = int(data.split(":")[1].replace("h", ""))
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text=f"Buscando noticias de las ultimas {horas} horas...")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=horas)
        activas = config.get("fuentes_activas", list(SCRAPERS.keys()))
        total = 0

        for nombre in activas:
            if nombre not in SCRAPERS:
                continue
            try:
                noticias = SCRAPERS[nombre]()
                for noticia in noticias:
                    fecha_ok = True
                    if noticia.get("fecha"):
                        try:
                            if "T" in noticia["fecha"]:
                                dt = datetime.fromisoformat(noticia["fecha"].replace("Z", "+00:00"))
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                fecha_ok = dt >= cutoff
                            else:
                                fecha_ok = True
                        except:
                            fecha_ok = True

                    if not fecha_ok:
                        continue

                    nid = make_id(noticia["titulo"], noticia["url"])
                    keyboard = [
                        [
                            InlineKeyboardButton("Redactar con IA", callback_data=f"redactar:{nid}"),
                            InlineKeyboardButton("Siguiente", callback_data=f"siguiente:{nid}"),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    fecha_str = ""
                    if noticia.get("fecha"):
                        try:
                            if "T" in noticia["fecha"]:
                                dt = datetime.fromisoformat(noticia["fecha"].replace("Z", "+00:00"))
                                fecha_str = dt.strftime("%d/%m/%Y %H:%M")
                            else:
                                fecha_str = noticia["fecha"][:16]
                        except:
                            pass

                    msg = (
                        f"[{noticia['fuente']}]"
                        + (f"\nFecha: {fecha_str}" if fecha_str else "")
                        + f"\n\n{noticia['titulo']}"
                    )
                    if noticia.get("resumen"):
                        msg += f"\n\n{noticia['resumen']}"

                    await context.bot.send_message(
                        chat_id=chat_id, text=msg, reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                    total += 1

                    seen[nid] = {
                        "titulo": noticia["titulo"],
                        "fuente": noticia["fuente"],
                        "url": noticia["url"],
                        "resumen": noticia.get("resumen", ""),
                        "fecha": noticia.get("fecha", ""),
                    }
                    time.sleep(1)
            except Exception as e:
                print(f"Error {nombre}: {e}")

        save_seen(seen, context)
        if total == 0:
            await context.bot.send_message(chat_id=chat_id, text="No se encontraron noticias en ese rango de tiempo.")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"Se encontraron {total} noticias.")

    elif data.startswith("siguiente:"):
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="Noticia skipeada.")

    elif data.startswith("redactar:"):
        nid = data.split(":", 1)[1]
        seen = load_seen(context)

        if nid not in seen:
            all_news = context.bot_data.get("all_news", {})
            if nid in all_news:
                seen[nid] = all_news[nid]

        if nid not in seen:
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=chat_id, text="Noticia no encontrada.")
            return

        noticia = seen[nid]
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="Redactando con IA... Esperá un momento.")

        resultado = redactar_con_ia(
            api_key=config["gemini_api_key"],
            titulo=noticia["titulo"],
            fuente=noticia.get("fuente", ""),
            resumen=noticia.get("resumen", ""),
            url=noticia.get("url", ""),
        )

        pending = load_pending()
        preview_id = make_id(resultado["titulo"], str(time.time()))
        pending[preview_id] = {
            "titulo_ia": resultado["titulo"],
            "texto_ia": resultado["texto"],
            "titulo_original": noticia["titulo"],
            "fuente": noticia.get("fuente", ""),
            "url_original": noticia.get("url", ""),
            "imagen": noticia.get("imagen", ""),
        }
        save_pending(pending)

        texto_preview = resultado["texto"]
        if len(texto_preview) > 800:
            texto_preview = texto_preview[:800] + "..."

        keyboard = [
            [
                InlineKeyboardButton("Publicar", callback_data=f"publicar:{preview_id}"),
                InlineKeyboardButton("Editar titulo", callback_data=f"editar:{preview_id}"),
            ],
            [
                InlineKeyboardButton("Cancelar", callback_data=f"cancelar:{preview_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = (
            f"VISTA PREVIA:\n\n"
            f"Titulo: {resultado['titulo']}\n\n"
            f"{texto_preview}\n\n"
            f"Original: {noticia['titulo']}"
        )
        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=reply_markup)

    elif data.startswith("publicar:"):
        pid = data.split(":", 1)[1]
        pending = load_pending()

        if pid not in pending:
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=chat_id, text="Publicacion no encontrada.")
            return

        item = pending[pid]
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Enviame la URL de la imagen para la nota.\n"
                 "Si no queres imagen, escribi 'skip'."
        )

        context.user_data["pending_publish"] = pid

    elif data.startswith("editar:"):
        pid = data.split(":", 1)[1]
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Escribi el nuevo titulo para la nota:"
        )
        context.user_data["pending_edit"] = pid

    elif data.startswith("cancelar:"):
        pid = data.split(":", 1)[1]
        pending = load_pending()
        if pid in pending:
            del pending[pid]
            save_pending(pending)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="Publicacion cancelada.")

    elif data == "fb_publicar":
        await query.edit_message_reply_markup(reply_markup=None)
        fb_data = context.user_data.pop("facebook_publish", None)
        link_millennials = context.user_data.pop("pending_link", None)

        if not fb_data:
            await context.bot.send_message(chat_id=chat_id, text="Error: datos de Facebook no encontrados.")
            return

        imagen_url = fb_data.get("imagen", "")
        print(f"[Bot] fb_publicar imagen from fb_data: '{imagen_url}'", flush=True)

        if not imagen_url:
            all_news = context.bot_data.get("all_news", {})
            for nid, n in all_news.items():
                if n.get("titulo") == fb_data.get("titulo"):
                    imagen_url = n.get("imagen", "")
                    print(f"[Bot] imagen from all_news: '{imagen_url}'", flush=True)
                    break

        if not imagen_url:
            url_original = fb_data.get("url_original", "")
            if not url_original:
                pending = load_pending()
                for pid, item in pending.items():
                    if item.get("titulo_ia") == fb_data.get("titulo"):
                        url_original = item.get("url_original", "")
                        break
            if url_original:
                print(f"[Bot] Buscando og:image de: {url_original}", flush=True)
                imagen_url = buscar_imagen_og(url_original)

        print(f"[Bot] imagen_url final para Facebook: '{imagen_url}'", flush=True)

        config = load_config()
        resultado = publicar_en_facebook(
            page_access_token=config["facebook_page_token"],
            page_id=config["facebook_page_id"],
            mensaje=fb_data["texto"],
            imagen_url=imagen_url,
            link_comentario=link_millennials or "",
        )

        if resultado["exito"]:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Publicado en Facebook!\n\n{resultado['url']}"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Error al publicar en Facebook: {resultado.get('error', 'desconocido')}"
            )

    elif data == "fb_cancelar":
        await query.edit_message_reply_markup(reply_markup=None)
        context.user_data.pop("facebook_publish", None)
        context.user_data.pop("pending_link", None)
        await context.bot.send_message(chat_id=chat_id, text="Publicacion en Facebook cancelada.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    config = load_config()

    if "pending_publish" in context.user_data:
        pid = context.user_data.pop("pending_publish")
        pending = load_pending()

        if pid not in pending:
            await update.message.reply_text("Error: publicacion no encontrada.")
            return

        item = pending[pid]
        imagen_url = "" if text.lower() == "skip" else text

        resultado = publicar_en_sheet(
            apps_script_url=config["apps_script_url"],
            titulo=item["titulo_ia"],
            texto=item["texto_ia"],
            imagen_url=imagen_url,
        )

        if resultado["exito"]:
            fb_token = config.get("facebook_page_token", "")
            if fb_token:
                fb_result = generar_post_facebook(
                    api_key=config["gemini_api_key"],
                    titulo=item["titulo_ia"],
                    resumen=item.get("resumen", ""),
                )
                fb_texto = fb_result["texto"]

                imagen_noticia = item.get("imagen", "")
                if not imagen_noticia:
                    all_news = context.bot_data.get("all_news", {})
                    for nid, n in all_news.items():
                        if n.get("titulo") == item.get("titulo_original"):
                            imagen_noticia = n.get("imagen", "")
                            break

                context.user_data["facebook_publish"] = {
                    "titulo": item["titulo_ia"],
                    "texto": fb_texto,
                    "imagen": imagen_noticia,
                    "url_original": item.get("url_original", ""),
                }

                img_info = f"\n(Con imagen adjunta)" if imagen_noticia else ""
                await update.message.reply_text(
                    f"Publicado en tu web!\n\n"
                    f"Titulo: {item['titulo_ia']}\n\n"
                    f"La nota ya deberia estar visible en millennials.ar\n\n"
                    f"---\n\n"
                    f"Post para Facebook:\n\n"
                    f"{fb_texto}{img_info}\n\n"
                    f"---\n\n"
                    f"Link generado: https://millennials.ar/noticias/{slugify(item['titulo_ia'])}/\n\n"
                    f"Publicar?"
                )
            else:
                await update.message.reply_text(
                    f"Publicado en tu web!\n\n"
                    f"Titulo: {item['titulo_ia']}\n\n"
                    f"La nota ya deberia estar visible en millennials.ar"
                )
        else:
            await update.message.reply_text(f"Error al publicar: {resultado.get('error', 'desconocido')}")

        del pending[pid]
        save_pending(pending)

    elif "pending_edit" in context.user_data:
        pid = context.user_data.pop("pending_edit")
        pending = load_pending()

        if pid not in pending:
            await update.message.reply_text("Error: publicacion no encontrada.")
            return

        pending[pid]["titulo_ia"] = text
        save_pending(pending)

        item = pending[pid]
        texto_preview = item["texto_ia"]
        if len(texto_preview) > 800:
            texto_preview = texto_preview[:800] + "..."

        keyboard = [
            [
                InlineKeyboardButton("Publicar", callback_data=f"publicar:{pid}"),
                InlineKeyboardButton("Editar titulo", callback_data=f"editar:{pid}"),
            ],
            [
                InlineKeyboardButton("Cancelar", callback_data=f"cancelar:{pid}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = (
            f"VISTA PREVIA (titulo editado):\n\n"
            f"Titulo: {text}\n\n"
            f"{texto_preview}"
        )
        await update.message.reply_text(msg, reply_markup=reply_markup)

    elif "facebook_publish" in context.user_data and "pending_link" not in context.user_data:
        fb_data = context.user_data["facebook_publish"]
        slug = slugify(fb_data["titulo"])
        link_millennials = f"https://millennials.ar/noticias/{slug}/"

        context.user_data["pending_link"] = link_millennials

        keyboard = [
            [
                InlineKeyboardButton("Publicar en Facebook", callback_data="fb_publicar"),
                InlineKeyboardButton("Cancelar", callback_data="fb_cancelar"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        imagen_info = ""
        if fb_data.get("imagen"):
            imagen_info = "\n(Se publica con imagen adjunta)"

        msg = (
            f"Vista previa del post de Facebook:\n\n"
            f"{fb_data['texto']}\n\n"
            f"---"
            f"{imagen_info}\n"
            f"\nLink en comentario: {link_millennials}\n\n"
            f"Publicar?"
        )
        await update.message.reply_text(msg, reply_markup=reply_markup)

# ==================== BACKGROUND CHECK ====================

async def periodic_check(app: Application):
    config = load_config()
    intervalo = config.get("intervalo_minutos", 30)
    chat_id = config["telegram_chat_id"]
    bot = app.bot

    while True:
        await asyncio.sleep(intervalo * 60)

        seen = load_seen(app)
        activas = config.get("fuentes_activas", list(SCRAPERS.keys()))
        total_nuevas = 0

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Revision automatica...")

        for nombre in activas:
            if nombre not in SCRAPERS:
                continue
            try:
                noticias = SCRAPERS[nombre]()
                for noticia in noticias[:3]:
                    nid = make_id(noticia["titulo"], noticia["url"])
                    if nid not in seen:
                        keyboard = [
                            [
                                InlineKeyboardButton("Redactar con IA", callback_data=f"redactar:{nid}"),
                                InlineKeyboardButton("Siguiente", callback_data=f"siguiente:{nid}"),
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        fecha_str = ""
                        if noticia.get("fecha"):
                            try:
                                if "T" in noticia["fecha"]:
                                    dt = datetime.fromisoformat(noticia["fecha"].replace("Z", "+00:00"))
                                    fecha_str = dt.strftime("%d/%m/%Y")
                                else:
                                    fecha_str = noticia["fecha"][:10]
                            except:
                                pass

                        msg = (
                            f"[{noticia['fuente']}]"
                            + (f"\nFecha: {fecha_str}" if fecha_str else "")
                            + f"\n\n{noticia['titulo']}"
                        )
                        if noticia.get("resumen"):
                            msg += f"\n\n{noticia['resumen']}"

                        await bot.send_message(
                            chat_id=chat_id, text=msg, reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        total_nuevas += 1

                    seen[nid] = {
                        "titulo": noticia["titulo"],
                        "fuente": noticia["fuente"],
                        "url": noticia["url"],
                        "resumen": noticia.get("resumen", ""),
                        "fecha": noticia.get("fecha", ""),
                        "imagen": noticia.get("imagen", ""),
                    }
                    if "all_news" not in app.bot_data:
                        app.bot_data["all_news"] = {}
                    app.bot_data["all_news"][nid] = seen[nid]
                    time.sleep(1)
            except Exception as e:
                print(f"Error {nombre}: {e}")

        save_seen(seen, app)
        if total_nuevas > 0:
            print(f"  Nuevas: {total_nuevas}")

# ==================== MAIN ====================

def main():
    config = load_config()

    app = Application.builder().token(config["telegram_token"]).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("noticias", cmd_noticias))
    app.add_handler(CommandHandler("buscar", cmd_buscar))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("publicar", cmd_publicar))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_once(periodic_check, when=5)

    print("=" * 50)
    print("  BOT DE NOTICIAS - MILLENNIALS.AR")
    print("=" * 50)
    print(f"  Fuentes: {config.get('fuentes_activas', 'Todas')}")
    print(f"  Intervalo: {config.get('intervalo_minutos', 30)} min")
    print("=" * 50)
    print("  Ctrl+C para detener")
    print("=" * 50)

    app.run_polling()

if __name__ == "__main__":
    main()
