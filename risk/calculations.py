from __future__ import annotations

import numpy as np

from risk.models import ConcentrationResult, CorrelationResult, RiskStatus


def common_dates(
    closes_by_ticker: dict[str, dict[str, float]], lookback_days: int
) -> tuple[str, ...]:
    if not closes_by_ticker or any(not closes for closes in closes_by_ticker.values()):
        return ()
    common = set.intersection(*(set(closes) for closes in closes_by_ticker.values()))
    return tuple(sorted(common)[-lookback_days:])


def simple_returns(closes: dict[str, float], dates: tuple[str, ...]) -> np.ndarray:
    values = np.asarray([closes[day] for day in dates], dtype=float)
    return values[1:] / values[:-1] - 1


def correlation(ticker_returns: dict[str, np.ndarray]) -> CorrelationResult:
    labels = tuple(sorted(ticker_returns))
    if len(labels) == 1:
        return CorrelationResult(
            status=RiskStatus.UNAVAILABLE,
            labels=labels,
            matrix=((1.0,),),
            warnings=("Correlation requires at least two tickers.",),
        )
    matrix: list[list[float | None]] = []
    has_null = False
    for row_index, row_label in enumerate(labels):
        row: list[float | None] = []
        for column_index, column_label in enumerate(labels):
            if row_index == column_index:
                row.append(1.0)
                continue
            left = ticker_returns[row_label]
            right = ticker_returns[column_label]
            if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
                row.append(None)
                has_null = True
            else:
                row.append(float(np.corrcoef(left, right)[0, 1]))
        matrix.append(row)
    return CorrelationResult(
        status=RiskStatus.PARTIAL if has_null else RiskStatus.COMPLETE,
        labels=labels,
        matrix=tuple(tuple(row) for row in matrix),
        warnings=("Some correlations are unavailable.",) if has_null else (),
    )


def concentration(weights: dict[str, float]) -> ConcentrationResult:
    if not weights:
        return ConcentrationResult(
            weights={}, herfindahl_index=0, largest_label=None, largest_weight=0
        )
    largest = max(weights, key=weights.__getitem__)
    return ConcentrationResult(
        weights=weights,
        herfindahl_index=sum(weight * weight for weight in weights.values()),
        largest_label=largest,
        largest_weight=weights[largest],
    )


def unavailable_correlation(labels: tuple[str, ...]) -> CorrelationResult:
    return CorrelationResult(
        status=RiskStatus.UNAVAILABLE,
        labels=labels,
        matrix=tuple(
            tuple(1.0 if row == column else None for column in labels) for row in labels
        ),
        warnings=("Correlation is unavailable without common return samples.",),
    )
