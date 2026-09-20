from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChartMarker:
    date: str
    price: float
    text: str


@dataclass
class EdgeResult:
    code: str
    name: str
    direction: str
    category: str
    status: str
    strength: float
    score: float
    explanation: str
    raw_values: Dict[str, Any] = field(default_factory=dict)
    markers: List[ChartMarker] = field(default_factory=list)

    def to_dict(self):
        result = asdict(self)
        result["markers"] = [asdict(marker) for marker in self.markers]
        return result


@dataclass
class ScanResult:
    symbol: str
    scan_date: str
    status: str
    long_score: float
    short_score: float
    net_score: float
    long_count: int
    short_count: int
    close: float
    entry_low: Optional[float]
    entry_high: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    risk_reward: Optional[float]
    edges: List[EdgeResult]

