from __future__ import annotations

from math import isfinite

from risk.models import (
    DecisionTarget,
    DecisionTargetExposure,
    RiskStatus,
)
from storage.store import ContextStore


class DecisionTargetExposureResolver:
    def __init__(self, context_store: ContextStore) -> None:
        self._context_store = context_store

    def resolve(self, strategy_id: str) -> DecisionTargetExposure:
        rows = self._context_store.get_decisions(strategy_id, limit=10_000)
        latest: dict[str, dict] = {}
        for row in rows:
            raw_ticker = row.get("ticker")
            ticker = raw_ticker.strip().upper() if isinstance(raw_ticker, str) else ""
            if ticker and ticker not in latest:
                latest[ticker] = row
        if not latest:
            return self._result(
                strategy_id,
                RiskStatus.UNAVAILABLE,
                warnings=("No persisted decision targets are available.",),
            )

        targets: list[DecisionTarget] = []
        warnings: list[str] = []
        invalid = False
        for ticker in sorted(latest):
            row = latest[ticker]
            raw_weight = row.get("target_position_pct")
            if not isinstance(raw_weight, int | float):
                warnings.append(f"{ticker}: target_position_pct is not numeric.")
                invalid = True
                continue
            percentage = float(raw_weight)
            if not isfinite(percentage):
                warnings.append(
                    f"{ticker}: target_position_pct must be between 0 and 100."
                )
                invalid = True
                continue
            targets.append(
                DecisionTarget(
                    decision_id=str(row.get("id") or ""),
                    ticker=ticker,
                    target_position_pct=percentage,
                    weight=percentage / 100,
                    created_at=str(row.get("created_at") or ""),
                )
            )
            if not 0 <= percentage <= 100:
                warnings.append(
                    f"{ticker}: target_position_pct must be between 0 and 100."
                )
                invalid = True
        total = sum(target.weight for target in targets)
        if total > 1:
            warnings.append("Total decision target exposure exceeds 100 percent.")
            invalid = True
        if invalid:
            return self._result(
                strategy_id,
                RiskStatus.INVALID,
                targets=tuple(targets),
                warnings=tuple(warnings),
            )
        if total <= 0:
            return self._result(
                strategy_id,
                RiskStatus.UNAVAILABLE,
                targets=tuple(targets),
                warnings=("All latest decision target exposures are zero.",),
            )
        return self._result(
            strategy_id,
            RiskStatus.COMPLETE,
            targets=tuple(targets),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _result(
        strategy_id: str,
        status: RiskStatus,
        *,
        targets: tuple[DecisionTarget, ...] = (),
        warnings: tuple[str, ...],
    ) -> DecisionTargetExposure:
        weights = {
            target.ticker: target.weight for target in targets if target.weight > 0
        }
        total = sum(weights.values())
        timestamps = tuple(target.created_at for target in targets if target.created_at)
        return DecisionTargetExposure(
            status=status,
            strategy_id=strategy_id,
            as_of=max(timestamps) if timestamps else None,
            decision_ids=tuple(target.decision_id for target in targets),
            decisions=targets,
            weights=weights,
            cash_weight=max(0.0, 1 - total) if status != RiskStatus.INVALID else None,
            gross_exposure=total if status != RiskStatus.INVALID else None,
            warnings=warnings,
        )
