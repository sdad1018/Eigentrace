import pytest
from eigentrace import score, compare, EigenTrace

DIRECT = [
    "Inflation occurs when money supply grows faster than economic output.",
    "Yes. Earth is an oblate spheroid confirmed by satellite imagery.",
    "Stocks outperform most assets over long horizons but carry volatility.",
]

HEDGED = [
    "Inflation is a complex phenomenon that various experts study differently.",
    "Many perspectives exist on this question and context matters significantly.",
    "It may be worth considering consulting a professional about your situation.",
]

def test_direct_scores_higher_than_hedged():
    for d, h in zip(DIRECT, HEDGED):
        md = score(d)
        mh = score(h)
        assert md.directness_score > mh.directness_score

def test_direct_status():
    for text in DIRECT:
        m = score(text)
        assert m.status in ("DIRECT", "UNKNOWN")

def test_hedged_status():
    for text in HEDGED:
        m = score(text)
        assert m.status in ("HEDGED", "UNKNOWN")

def test_hedge_density_ordering():
    for d, h in zip(DIRECT, HEDGED):
        md = score(d)
        mh = score(h)
        assert md.hedge_density < mh.hedge_density

def test_compare_winner():
    result = compare(DIRECT[0], HEDGED[0])
    assert result["winner"] == "a"
    assert result["delta"] > 0

def test_compare_with_reference():
    reference = "Inflation is caused by excess money supply relative to goods."
    result = compare(DIRECT[0], HEDGED[0], reference=reference)
    assert result["winner"] == "a"

def test_eigentrace_stateful():
    tracer = EigenTrace(reference=DIRECT[0])
    m_direct = tracer.score(DIRECT[1])
    m_hedged = tracer.score(HEDGED[0])
    assert m_direct.directness_score > m_hedged.directness_score

def test_metrics_fields():
    m = score(DIRECT[0])
    assert 0.0 <= m.directness_score <= 1.0
    assert 0.0 <= m.hedge_density <= 1.0
    assert m.status in ("DIRECT", "HEDGED", "UNKNOWN")
    assert isinstance(m.pos_tags, list)
    assert len(m.pos_tags) > 0

def test_empty_text():
    m = score("")
    assert m is not None
    assert 0.0 <= m.directness_score <= 1.0

def test_short_text():
    m = score("Yes.")
    assert m is not None

def test_verbose_direct_vs_concise_hedged():
    verbose_direct = (
        "When we examine the root causes of inflation carefully, "
        "we find that the primary driver is an expansion of the money supply "
        "that outpaces real economic growth. Central banks respond by "
        "increasing interest rates, which makes borrowing more expensive."
    )
    concise_hedged = "Inflation may have various causes. Experts suggest monetary factors could play a role."
    mv = score(verbose_direct)
    mc = score(concise_hedged)
    assert mv.directness_score > mc.directness_score

def test_signal_score():
    pytest.importorskip("torch")
    from eigentrace import signal_score
    result = signal_score(DIRECT[0], DIRECT[0])
    assert result.logos_loss < 0.01
    assert result.status in ("COHERENT", "FLAT", "INCOHERENT")

def test_signal_different_texts():
    pytest.importorskip("torch")
    from eigentrace import signal_score
    same = signal_score(DIRECT[0], DIRECT[0])
    diff = signal_score(DIRECT[0], HEDGED[0])
    assert diff.logos_loss > same.logos_loss
