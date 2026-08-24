from pathlib import Path
from app.services.static_analyzer import StaticAnalyzer


def test_static_analyzer_detects_business_signals(tmp_path: Path):
    source = tmp_path / "orders.py"
    source.write_text(
        "def checkout(order):\n"
        "    if order.stock < order.quantity:\n"
        "        raise ValueError('stock')\n"
        "    return order\n",
        encoding="utf-8",
    )
    result = StaticAnalyzer().analyze(tmp_path)
    assert result["file_count"] == 1
    assert result["languages"]["Python"] == 1
    assert result["files"][0]["business_rule_candidates"]
