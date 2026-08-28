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

from gemini import redactar_con_ia
from sheets import publicar_en_sheet

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
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

def load_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_pending(pending):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

def make_id(title, url):
    raw = f"{title}|{url}"
    return hashlib.md5(raw.encode()).hexdigest()

# ==================== SCRAPERS ====================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

def scrape_vandal():
    noticias = []
    try:
        resp = requests.get("https://vandal.elespanol.com/noticias", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article.noticia, div.noticia, .news-item, .article-card")[:10]:
            title_tag = article.select_one("h2, h3, .title, a")
            link_tag = article.select_one("a[href]")
            desc_tag = article.select_one("p, .description, .excerpt, .summary")
            date_tag = article.select_one("time, .date, .time, span[class*='date']")
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://vandal.elespanol.com" + url
                resumen = desc_tag.get_text(strip=True)[:200] if desc_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                noticias.append({"titulo": title, "url": url, "fuente": "Vandal", "resumen": resumen, "fecha": fecha})
        if not noticias:
            for a in soup.select("a[href*='/noticias/']")[:10]:
                title = a.get_text(strip=True)
                url = a.get("href", "")
                if title and len(title) > 15:
                    if not url.startswith("http"):
                        url = "https://vandal.elespanol.com" + url
                    noticias.append({"titulo": title, "url": url, "fuente": "Vandal", "resumen": "", "fecha": ""})
    except Exception as e:
        print(f"[Vandal] Error: {e}")
    return noticias

def scrape_timeextension():
    noticias = []
    try:
        resp = requests.get("https://www.timeextension.com/news", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .article-item, .news-item")[:10]:
            title_tag = article.select_one("h2, h3, .title, a")
            link_tag = article.select_one("a[href]")
            desc_tag = article.select_one("p, .description, .excerpt, .summary")
            date_tag = article.select_one("time, .date, span[class*='date']")
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.timeextension.com" + url
                resumen = desc_tag.get_text(strip=True)[:200] if desc_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                noticias.append({"titulo": title, "url": url, "fuente": "TimeExtension", "resumen": resumen, "fecha": fecha})
    except Exception as e:
        print(f"[TimeExtension] Error: {e}")
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
                noticias.append({"titulo": title, "url": url, "fuente": "Eurogamer", "resumen": resumen, "fecha": fecha})
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
                if title and len(title) > 10:
                    noticias.append({"titulo": title, "url": url, "fuente": "3DJuegos", "resumen": resumen, "fecha": fecha})
    except Exception as e:
        print(f"[3DJuegos] Error: {e}")
    return noticias

def scrape_ign():
    noticias = []
    try:
        resp = requests.get("https://latam.ign.com/noticias", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article, .article-item, div[class*='article']")[:10]:
            link_tag = article.select_one("a[href*='noticias']") if article.name != "a" else article
            title_tag = article.select_one("h2, h3, .title, span")
            desc_tag = article.select_one("p, .description, .excerpt")
            date_tag = article.select_one("time, .date, span[class*='date']")
            if link_tag:
                title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                url = link_tag.get("href", "")
                if not url.startswith("http"):
                    url = "https://latam.ign.com" + url
                resumen = desc_tag.get_text(strip=True)[:200] if desc_tag else ""
                fecha = ""
                if date_tag:
                    fecha = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
                if title and len(title) > 10:
                    noticias.append({"titulo": title, "url": url, "fuente": "IGN", "resumen": resumen, "fecha": fecha})
    except Exception as e:
        print(f"[IGN] Error: {e}")
    return noticias

SCRAPERS = {
    "Vandal": scrape_vandal,
    "TimeExtension": scrape_timeextension,
    "Eurogamer": scrape_eurogamer,
    "3DJuegos": scrape_3djuegos,
    "IGN": scrape_ign,
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
    seen = load_seen()
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

    save_seen(seen)
    if total_nuevas == 0:
        await update.message.reply_text("No hay noticias nuevas por el momento.")
    else:
        await update.message.reply_text(f"Se encontraron {total_nuevas} noticias nuevas.")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seen = load_seen()
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

        save_seen(seen)
        if total == 0:
            await context.bot.send_message(chat_id=chat_id, text="No se encontraron noticias en ese rango de tiempo.")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"Se encontraron {total} noticias.")

    elif data.startswith("siguiente:"):
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="Noticia skipeada.")

    elif data.startswith("redactar:"):
        nid = data.split(":", 1)[1]
        seen = load_seen()

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

# ==================== BACKGROUND CHECK ====================

async def periodic_check(app: Application):
    config = load_config()
    intervalo = config.get("intervalo_minutos", 30)
    chat_id = config["telegram_chat_id"]
    bot = app.bot

    while True:
        await asyncio.sleep(intervalo * 60)

        seen = load_seen()
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
                        }
                        time.sleep(1)
            except Exception as e:
                print(f"Error {nombre}: {e}")

        save_seen(seen)
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
