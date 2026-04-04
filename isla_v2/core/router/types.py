from dataclasses import dataclass
from typing import Optional


@dataclass
class RouteDecision:
    route: str
    reason: str
    namespace: Optional[str] = None
    key: Optional[str] = None
    exact_text: Optional[str] = None
