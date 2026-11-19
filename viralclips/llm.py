"""Claude como juez de viralidad.

Haiku puntúa muchos candidatos por muy poco dinero; Sonnet vuelve a juzgar solo los
mejores para afinar el puntaje, el título y el gancho.
"""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from .models import Candidate, Sentence

JUDGE_MODEL = "claude-haiku-5-5"
REFINE_MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = """Eres editor de shorts verticales (YouTube Shorts, TikTok, Reels) y decides qué fragmentos de un video largo funcionarían como clips independientes.

Para cada fragmento recibes sus frases numeradas. Califica de 0 a 100 qué tan probable es que el clip retenga y se comparta, con esta rúbrica:
- Gancho (35 %): las primeras 1-2 frases despiertan curiosidad, sorpresa o tensión sin necesidad de contexto.
- Se entiende solo (25 %): alguien que no vio el video entiende de qué se habla.
- Remate (20 %): termina con una conclusión, revelación o frase redonda, no a mitad de una idea.
- Emoción o valor (10 %): asombro, humor, polémica, dato memorable o aprendizaje claro.
- Encaje con el nicho del canal (10 %).

Puedes recortar el fragmento eligiendo la primera y la última frase que conviene conservar (índices dentro del fragmento, empezando en 0), por ejemplo para quitar una frase de relleno al inicio. No inventes frases. Sé exigente: un 80 o más es un clip que publicarías sin dudar; la mayoría de fragmentos deberían quedar por debajo de 60.

Escribe el título (máximo 60 caracteres) y el texto del gancho en el idioma del video."""


class ClipJudgement(BaseModel):
    id: int = Field(description="El id del fragmento tal como se recibió")
    score: int = Field(description="Puntaje de viralidad de 0 a 100")
    first_sentence: int = Field(description="Índice de la primera frase a conservar dentro del fragmento")
    last_sentence: int = Field(description="Índice de la última frase a conservar dentro del fragmento")
    title: str = Field(description="Título corto para el short")
    hook: str = Field(description="Texto de gancho para mostrar en pantalla en los primeros segundos")
    reason: str = Field(description="Una frase explicando el puntaje")


class Judgements(BaseModel):
    clips: list[ClipJudgement]


def _render_batch(batch: list[Candidate], sentences: list[Sentence]) -> str:
    parts = []
    for i, c in enumerate(batch):
        lines = [f'<fragmento id="{i}" duracion="{c.duration:.0f}s">']
        for k, idx in enumerate(range(c.first, c.last + 1)):
            lines.append(f"[{k}] {sentences[idx].text}")
        lines.append("</fragmento>")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _chunks(items: list[Candidate], size: int) -> Iterable[list[Candidate]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _call(client, model: str, niche: str, body: str) -> Judgements | None:
    messages = [{
        "role": "user",
        "content": f"Nicho del canal: {niche or 'general'}\n\nFragmentos:\n\n{body}\n\n"
                   "Devuelve un juicio por cada fragmento.",
    }]
    common = dict(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=messages,
        output_format=Judgements,
        output_config={"effort": "low"},
    )
    if model.startswith("claude-sonnet-5-5"):
        # Si un clasificador de seguridad rechaza por error, el servidor reintenta con otro modelo.
        response = client.beta.messages.parse(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **common
        )
    else:
        response = client.messages.parse(**common)
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output


def judge(
    candidates: list[Candidate],
    sentences: list[Sentence],
    niche: str = "",
    model: str = JUDGE_MODEL,
    batch_size: int = 12,
    client=None,
    log=print,
) -> bool:
    """Rellena `llm`, `title`, `hook`, `reason` y recorta first/last según el juicio de Claude."""
    if not candidates:
        return True
    import anthropic

    if client is None:
        client = anthropic.Anthropic()

    for n, batch in enumerate(_chunks(candidates, batch_size), start=1):
        log(f"  Claude ({model}) juzgando lote {n} de {-(-len(candidates) // batch_size)}...")
        try:
            result = _call(client, model, niche, _render_batch(batch, sentences))
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            log(f"  Claude no aceptó las credenciales ({e.__class__.__name__}); sigo solo con señales. "
                "Configura ANTHROPIC_API_KEY para usar la IA.")
            return False
        except TypeError as e:
            if "authentication" not in str(e).lower():
                raise
            log("  No hay credenciales de Claude; sigo solo con señales. "
                "Configura ANTHROPIC_API_KEY para usar la IA.")
            return False
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            log(f"  Falló la llamada a Claude ({e.__class__.__name__}); este lote queda con puntaje heurístico.")
            continue
        if result is None:
            log("  Claude rechazó este lote; se mantiene el puntaje heurístico.")
            continue
        for j in result.clips:
            if not 0 <= j.id < len(batch):
                continue
            c = batch[j.id]
            span = c.last - c.first
            lo = min(max(j.first_sentence, 0), span)
            hi = min(max(j.last_sentence, lo), span)
            new_first, new_last = c.first + lo, c.first + hi
            if (new_first, new_last) != (c.first, c.last):
                trimmed_dur = sentences[new_last].end - sentences[new_first].start
                if trimmed_dur >= 10:  # no aceptar recortes que dejen un clip ridículo
                    c.first, c.last = new_first, new_last
                    c.start, c.end = sentences[new_first].start, sentences[new_last].end
                    c.text = " ".join(s.text for s in sentences[new_first : new_last + 1])
            c.llm = float(max(0, min(100, j.score)))
            c.title = j.title.strip()
            c.hook = j.hook.strip()
            c.reason = j.reason.strip()
    return True
