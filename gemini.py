from google import genai

ESTILO_PROMPT = """Sos el redactor del blog Millennials.ar, especializado en cultura pop, videojuegos, cine y tecnología de los 90 y 2000 para argentinos de 30+.

Redactá la siguiente noticia como una nota periodística completa y fiel a la fuente.

VERACIDAD (regla máxima):
- Usá ÚNICAMENTE la información que aparece en el resumen provisto. No inventes especificaciones, fechas, cifras, nombres ni tramas.
- Si la información es rumor o filtración, aclaralo explícitamente ("según fuentes", "se rumora", "aún no confirmado").
- No mezcles con información de tu conocimiento general. Si algo no está en la fuente, no lo menciones.
- Respetá la temporalidad: la noticia es de HOY, no mezcles con eventos pasados a menos que la fuente lo mencione.

ESTRUCTURA (3 a 4 párrafos):
- Parrafo 1: Entrada clara con el hecho principal. Qué pasó, quiénes involucrados, por qué importa.
- Parrafo 2: Contexto o antecedentes relevantes SOLO si la fuente los provee.
- Parrafo 3: Datos concretos: fechas, cifras, declaraciones, especificaciones de la fuente.
- Parrafo 4 (opcional): Cierre con implicancias o lo que se espera a futuro.

TONO Y ESTILO:
- Periodístico argentino, fluido y equilibrado.
- La nostalgia debe sentirse orgánica: relacioná con la memoria de los 90/2000 sin forzar ni caer en infantilismos.
- Evitá vocabulario clínico/académico y también sensacionalismo o clickbait.
- NO uses muletillas de IA como "En este contexto", "Es importante destacar", "Vale la pena mencionar", "No podemos dejar de lado".
- Redactá en voz activa, oraciones directas.
- Usá "vos" (nunca "tu").
- NO termines con preguntas.

REGLAS DE FORMATO:
- NO uses marcadores como ** o * en el texto.
- NO copies comentarios, metadatos ni fechas de comentarios de la página original.
- Extensión: 250-400 palabras.

FORMATO DE RESPUESTA (exacto, sin comillas ni markdown):

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
