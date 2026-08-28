from google import genai

ESTILO_PROMPT = """Sos el redactor del blog Millennials.ar. Reescribi la siguiente noticia en el estilo del sitio.

ESTRUCTURA DE UNA NOTA DEL BLOG:
- Parrafo 1: Hook nostalgico que enganche al lector ("¿Se acuerdan de cuando...?", "Un dia como hoy...", "Si tuviste una PS1, sabes de que hablamos...")
- Parrafo 2: Contexto de la noticia explicada de forma simple
- Parrafo 3: Detalles de la noticia
- Parrafo 4: Cierre con reflexion, meme o frase iconica

REGLAS:
- Tono conversacional argentino, usa "vos" (nunca "tu")
- Referencias a cultura argentina: Telefe, Canal 13, Magic Kids, videoclubs, VHS
- Extension: 150-250 palabras
- No uses marcadores como ** o * en el texto
- NO copies comentarios, fechas de comentarios, ni metadatos de la pagina original
- SOLO escribe el titulo y el texto de la nota

IMPORTANTE: Respondi EXACTAMENTE en este formato (sin comillas, sin markdown):

Titulo: [el titulo aqui]
Texto: [el texto aqui]

NOTICIA A REESCRIBIR:
Titulo: {titulo}
Resumen: {resumen}"""


def redactar_con_ia(api_key, titulo, fuente, resumen="", url=""):
    """Usa Gemini para reescribir una noticia en el estilo del blog"""
    try:
        client = genai.Client(api_key=api_key)

        # Limpiar resumen de basura
        resumen_limpio = resumen
        for basura in ["comentarios", "opinar", "Compartir", "Twitter", "Facebook"]:
            if basura in resumen_limpio:
                resumen_limpio = resumen_limpio.split(basura)[0].strip()

        prompt = ESTILO_PROMPT.format(
            titulo=titulo,
            resumen=resumen_limpio or titulo
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )
        texto_generado = response.text.strip()

        # Parsear titulo y texto
        titulo_final = titulo
        texto_final = ""

        lineas = texto_generado.split("\n")
        capture_texto = False

        for linea in lineas:
            linea_limpia = linea.strip()
            if linea_limpia.lower().startswith("titulo:"):
                titulo_final = linea_limpia.split(":", 1)[1].strip()
            elif linea_limpia.lower().startswith("texto:"):
                texto_final = linea_limpia.split(":", 1)[1].strip()
                capture_texto = True
            elif capture_texto and linea_limpia:
                texto_final += "\n\n" + linea_limpia

        # Si no se pudo parsear, usar todo el texto
        if not texto_final or len(texto_final) < 30:
            texto_final = texto_generado
            # Intentar limpiar
            if "titulo:" in texto_generado.lower():
                parts = texto_generado.lower().split("texto:")
                if len(parts) > 1:
                    texto_final = parts[1].strip()

        # Quitar comillas sobrantes
        texto_final = texto_final.strip('"').strip("'")

        return {
            "titulo": titulo_final,
            "texto": texto_final,
            "exito": True
        }

    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return {
            "titulo": titulo,
            "texto": resumen or "Error al generar el texto con IA",
            "exito": False,
            "error": str(e)
        }
