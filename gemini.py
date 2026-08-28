from google import genai

ESTILO_PROMPT = """Sos el redactor del blog Millennials.ar, un sitio de noticias de gaming y cultura pop para argentinos de 30+.

Escribi la siguiente noticia como una nota informativa y profesional.

ESTRUCTURA:
- Parrafo de entrada: Presentá la noticia de forma clara y directa. Contá qué pasó, quiénes están involucrados y por qué importa.
- Parrafo de contexto: Explicá el trasfondo. Qué es el juego/empresa/tema, cómo se relaciona con lo que ya se sabe.
- Parrafo de detalles: Datos concretos: fechas, cifras, nombres, declaraciones relevantes.
- Cierre: Una reflexión breve, una pregunta al lector, o una conexión con algo que el público de Millennials.ar pueda valorar. Solo si queda natural, podés meter una referencia sutil a la cultura pop argentina (Magic Kids, videoclubs, VHS, etc.) pero no es obligatorio y no fuerces si no va.

REGLAS:
- Tono periodístico argentino, informal pero profesional
- Usá "vos" (nunca "tu")
- Sé informativo primero, entretenido después
- No empieces todas las notas con la misma frase ni con preguntas retóricas forzadas
- Coherencia: que cada parrafo fluya naturalmente al siguiente
- Extension: 180-280 palabras
- No uses marcadores como ** o * en el texto
- NO copies comentarios, fechas de comentarios, ni metadatos de la pagina original
- SOLO escribe el titulo y el texto de la nota

IMPORTANTE: Respondi EXACTAMENTE en este formato (sin comillas, sin markdown):

Titulo: [el titulo aqui]
Texto: [el texto aqui]

NOTICIA A REESCRIBIR:
Titulo: {titulo}
Resumen: {resumen}"""

FB_POST_PROMPT = """Sos el community manager de Millennials.ar en Facebook. Generá un post para redes sociales basado en esta nota.

El post tiene que:
- Tener entre 2 y 4 oraciones
- Resumir la noticia de forma atractiva
- Generar curiosidad para que la gente quiera leer la nota completa
- Tono cercano y argentino, pero profesional
- NO poner links en el post (el link va en el primer comentario)
- NO usar hashtags
- Empezar de forma variada, no siempre igual

Ejemplos de buenos posts:
- "Según confirmó la empresa, el nuevo título llegará antes de lo esperado. Los fans ya están reaccionando en las redes."
- "La noticia que muchos esperaban se hizo oficial hoy. Acá te contamos los detalles."

Respondi SOLO el texto del post, sin formato adicional.

NOTICIA:
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


def generar_post_facebook(api_key, titulo, resumen=""):
    """Genera un post resumido para Facebook usando Gemini"""
    try:
        client = genai.Client(api_key=api_key)

        resumen_limpio = resumen
        for basura in ["comentarios", "opinar", "Compartir", "Twitter", "Facebook"]:
            if basura in resumen_limpio:
                resumen_limpio = resumen_limpio.split(basura)[0].strip()

        prompt = FB_POST_PROMPT.format(
            titulo=titulo,
            resumen=resumen_limpio or titulo
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )

        texto = response.text.strip().strip('"').strip("'")
        return {"texto": texto, "exito": True}

    except Exception as e:
        print(f"[Gemini] Error post Facebook: {e}")
        return {"texto": titulo, "exito": False, "error": str(e)}
