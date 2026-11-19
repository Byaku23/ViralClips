from viralclips import candidates as cm
from viralclips.models import Word


def test_build_sentences_splits_on_punctuation_and_gaps():
    words = [Word("Hola.", 0, 0.4), Word("Esto", 0.5, 0.8), Word("sigue", 0.9, 1.2),
             Word("aquí", 3.0, 3.3)]  # silencio largo antes de "aquí"
    sents = cm.build_sentences(words)
    assert [s.text for s in sents] == ["Hola.", "Esto sigue", "aquí"]


def test_sliding_candidates_respect_duration(story_words):
    sents = cm.build_sentences(story_words)
    cands = cm.sliding_candidates(sents, min_len=10, max_len=20)
    assert cands
    assert all(10 <= c.duration <= 20 for c in cands)


def test_coverage_covers_everything_without_overlap(story_words):
    sents = cm.build_sentences(story_words)
    segs = cm.coverage_segments(sents, target=15, min_len=8, max_len=25)
    assert segs[0].first == 0 and segs[-1].last == len(sents) - 1
    for a, b in zip(segs, segs[1:]):
        assert b.first == a.last + 1
    assert all(s.duration <= 25 * 1.3 for s in segs)


def test_nms_drops_overlaps():
    a = cm.Candidate(0, 1, 0, 30, "a", score=90)
    b = cm.Candidate(0, 1, 5, 35, "b", score=80)  # se solapa casi entero con a
    c = cm.Candidate(2, 3, 40, 70, "c", score=70)
    kept = cm.non_max_suppression([b, c, a])
    assert [k.text for k in kept] == ["a", "c"]
