import pytest

from viralclips.models import Word


def make_words(sentences, gap=0.4, wps=2.5):
    """Palabras sintéticas con tiempos: cada frase dura len(palabras)/wps segundos."""
    words, t = [], 0.0
    for s in sentences:
        for tok in s.split():
            words.append(Word(tok, round(t, 3), round(t + 1 / wps * 0.9, 3)))
            t += 1 / wps
        t += gap
    return words


@pytest.fixture
def story_words():
    sents = [
        "¿Sabías que Roma nunca cayó en un solo día?",
        "Durante siglos fue la ciudad más poderosa del mundo conocido.",
        "Hablemos del clima, que era templado y bastante estable en general.",
        "Los campesinos sembraban trigo y cebada en sus campos.",
        "Y aquí viene lo increíble: el último emperador era un niño.",
        "En 476 fue depuesto y nadie nombró a otro emperador.",
        "Así terminó, en silencio, el imperio más famoso de la historia.",
        "Las calzadas tenían varias capas de piedra y grava.",
    ] * 3
    return make_words(sents)
