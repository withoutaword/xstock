from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_settings
from src.edges import build_scan_result, evaluate_edges
from src.indicators import add_indicators
from src.provider import generate_demo_prices


def test_all_reference_edges_are_present():
    settings = load_settings()
    prices = generate_demo_prices(["TEST", "SPY"], days=520)
    frame = add_indicators(prices["TEST"], prices["SPY"])
    edges = evaluate_edges(frame, settings)
    codes = {edge.code for edge in edges}
    assert {"L1", "L2", "L3", "L4", "L5", "L6", "S1", "S2", "S3", "S4", "S5", "S6"} <= codes


def test_scores_are_bounded_and_result_is_explainable():
    settings = load_settings()
    prices = generate_demo_prices(["TEST", "SPY"], days=520)
    frame = add_indicators(prices["TEST"], prices["SPY"])
    edges = evaluate_edges(frame, settings)
    result = build_scan_result("TEST", frame, edges, settings)
    assert 0 <= result.long_score <= 100
    assert 0 <= result.short_score <= 100
    assert result.edges
    assert all(edge.explanation for edge in result.edges)

