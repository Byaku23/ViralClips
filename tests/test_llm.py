"""El juez de Claude se prueba con un cliente falso: no hace llamadas reales."""
from types import SimpleNamespace

from viralclips import candidates as cm, llm


class FakeMessages:
    def __init__(self, parsed, stop="end_turn"):
        self.parsed, self.stop, self.calls = parsed, stop, []

    def parse(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop, parsed_output=self.parsed)


def fake_client(parsed, stop="end_turn"):
    m = FakeMessages(parsed, stop)
    return SimpleNamespace(messages=m, beta=SimpleNamespace(messages=m)), m


def test_judge_applies_score_title_and_trim(story_words):
    sents = cm.build_sentences(story_words)
    c = cm.Candidate(0, 4, sents[0].start, sents[4].end, "x")
    parsed = llm.Judgements(clips=[llm.ClipJudgement(
        id=0, score=88, first_sentence=0, last_sentence=2, title="Roma no cayó en un día",
        hook="¿Roma cayó en un día?", reason="Buen gancho")])
    client, m = fake_client(parsed)
    assert llm.judge([c], sents, "historia", model="claude-haiku-5-5", client=client, log=lambda *_: None)
    assert c.llm == 88 and c.title.startswith("Roma") and c.last == 2
    assert m.calls[0]["model"] == "claude-haiku-5-5" and "fallbacks" not in m.calls[0]


def test_sonnet_uses_server_side_fallback(story_words):
    sents = cm.build_sentences(story_words)
    c = cm.Candidate(0, 2, sents[0].start, sents[2].end, "x")
    client, m = fake_client(llm.Judgements(clips=[]))
    llm.judge([c], sents, model="claude-sonnet-5-5", client=client, log=lambda *_: None)
    assert m.calls[0]["fallbacks"] == "default"


def test_refusal_keeps_heuristic(story_words):
    sents = cm.build_sentences(story_words)
    c = cm.Candidate(0, 2, sents[0].start, sents[2].end, "x")
    client, _ = fake_client(None, stop="refusal")
    llm.judge([c], sents, client=client, log=lambda *_: None)
    assert c.llm is None


def test_out_of_range_ids_and_indices_are_clamped(story_words):
    sents = cm.build_sentences(story_words)
    c = cm.Candidate(0, 3, sents[0].start, sents[3].end, "x")
    parsed = llm.Judgements(clips=[
        llm.ClipJudgement(id=7, score=99, first_sentence=0, last_sentence=0, title="", hook="", reason=""),
        llm.ClipJudgement(id=0, score=150, first_sentence=-3, last_sentence=40, title="t", hook="h", reason="r"),
    ])
    client, _ = fake_client(parsed)
    llm.judge([c], sents, client=client, log=lambda *_: None)
    assert c.llm == 100 and (c.first, c.last) == (0, 3)
