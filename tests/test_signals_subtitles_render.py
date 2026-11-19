from viralclips import candidates as cm, ingest, render, signals, subtitles
from viralclips.models import Word


def test_hook_sentence_scores_higher_than_filler(story_words):
    sents = cm.build_sentences(story_words)
    hook = cm.Candidate(0, 1, sents[0].start, sents[1].end, sents[0].text + " " + sents[1].text)
    filler = cm.Candidate(2, 3, sents[2].start, sents[3].end, sents[2].text + " " + sents[3].text)
    sh, sf = signals.text_signals(hook, sents), signals.text_signals(filler, sents)
    assert sh["gancho_inicio"] > sf["gancho_inicio"]


def test_heatmap_average_and_missing():
    hm = [{"start_time": 0, "end_time": 10, "value": 0.2}, {"start_time": 10, "end_time": 20, "value": 1.0}]
    assert abs(signals.heatmap_score(hm, 5, 15) - 0.6) < 1e-9
    assert signals.heatmap_score([], 0, 10) is None


def test_heuristic_redistributes_without_retention():
    full = {k: 1.0 for k in signals.WEIGHTS}
    no_ret = {k: 1.0 for k in signals.WEIGHTS if k != "retencion"}
    assert signals.heuristic_score(full) == 100
    assert signals.heuristic_score(no_ret) == 100


def test_ass_highlights_one_word_per_event_and_is_relative():
    words = [Word("hola", 10.0, 10.3), Word("mundo", 10.4, 10.8), Word("{raro}", 10.9, 11.2)]
    ass = subtitles.build_ass(words, 10.0, 12.0, hook="Mira esto")
    events = [l for l in ass.splitlines() if l.startswith("Dialogue: 0")]
    assert len(events) == 3
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.40")
    assert all(e.count("\\c&H0000E6FF&") == 1 for e in events)
    assert "{raro}" not in ass and "(RARO)" in ass  # llaves escapadas
    assert "MIRA ESTO" in ass


def test_srt_format():
    words = [Word("uno", 1.0, 1.5), Word("dos.", 1.6, 2.0)]
    srt = subtitles.build_srt(words, 1.0, 3.0)
    assert "00:00:00,000 --> 00:00:01,000" in srt


def test_filters_for_each_framing(tmp_path):
    ass = tmp_path / "a b.ass"
    crop = render.build_filter(1920, 1080, "recorte", 0.9, None)
    assert "crop=606:1080:1314:0" in crop  # pegado al borde derecho sin salirse
    fit = render.build_filter(1920, 1080, "ajuste", None, ass)
    assert "gblur" in fit and fit.endswith("[v]") and "ass='" in fit
    vertical = render.build_filter(1080, 1920, "recorte", None, None)
    assert "pad=1080:1920" in vertical


def test_normalize_cloud_urls():
    assert ingest.normalize_url("https://www.dropbox.com/s/abc/v.mp4?dl=0").endswith("dl=1")
    yt = "https://youtu.be/xyz"
    assert ingest.normalize_url(yt) == yt
    assert ingest.is_url("https://drive.google.com/file/d/1/view")
    assert not ingest.is_url("C:/videos/a.mp4")
