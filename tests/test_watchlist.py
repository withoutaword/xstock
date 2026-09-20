from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.watchlist import add_to_watchlist, load_watchlist, parse_symbols, remove_from_watchlist


def test_parse_symbols_supports_common_separators():
    assert parse_symbols("mu, sndk\nDELL intc;GOOG") == ["MU", "SNDK", "DELL", "INTC", "GOOG"]


def test_parse_symbols_rejects_invalid_input():
    with pytest.raises(ValueError):
        parse_symbols("NVDA,$BAD")


def test_watchlist_add_and_remove(tmp_path):
    path = tmp_path / "watchlist.csv"
    add_to_watchlist(path, ["MU", "DELL", "MU"])
    assert load_watchlist(path).symbol.tolist() == ["DELL", "MU"]
    remove_from_watchlist(path, ["MU"])
    assert load_watchlist(path).symbol.tolist() == ["DELL"]

