from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time


@dataclass(slots=True)
class SavingsReport:
    original_tokens: int
    refined_tokens: int
    pass1_savings: int
    pass2_savings: int
    pass3_savings: int
    elapsed_ms: float
    turn: int
    session_id: str = ""
    timestamp: float = field(default_factory=time)

    @property
    def total_savings(self) -> int:
        return max(0, self.original_tokens - self.refined_tokens)

    @property
    def savings_pct(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return (self.total_savings / self.original_tokens) * 100

    @property
    def estimated_cost_saved_usd(self) -> float:
        return (self.total_savings / 1_000_000) * 3.0

    def to_console(self) -> str:
        return "\n".join(
            [
                f"┌─ SESSION SIFT SAVINGS REPORT ─ Turn {self.turn} "
                + "─" * 28,
                (
                    f"│  Original: {self.original_tokens:,} tokens -> "
                    f"Refined: {self.refined_tokens:,} tokens"
                ),
                (
                    f"│  Saved:    {self.total_savings:,} tokens "
                    f"({self.savings_pct:.1f}%)"
                ),
                f"│  Pass 1 (Structural): {self.pass1_savings:,}",
                f"│  Pass 2 (Temporal):   {self.pass2_savings:,}",
                f"│  Pass 3 (Semantic):   {self.pass3_savings:,}",
                f"│  Cost saved: ~${self.estimated_cost_saved_usd:.4f} USD",
                f"│  Latency: {self.elapsed_ms:.1f}ms",
                "└" + "─" * 58,
            ]
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["total_savings"] = self.total_savings
        data["savings_pct"] = self.savings_pct
        data["estimated_cost_saved_usd"] = self.estimated_cost_saved_usd
        return data
