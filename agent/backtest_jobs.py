from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, timedelta
from os import getenv
from collections.abc import Callable
from typing import Final, Literal, Protocol, runtime_checkable
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent.backtest_errors import BacktestDecisionError
from agent.backtest_policy import (
    BacktestMode,
    BacktestRunSpec,
    ExperimentalAgentPolicy,
    StrategyEligibilityError,
    freeze_backtest_run_spec,
)
from agent.backtest_policy_executor import (
    BacktestRunDecisionExecutor,
    ExperimentalDecisionAdapter,
)
from broker.backtest_data import (
    BacktestDataError,
    BacktestDatasetPreparer,
    HistoricalPriceLoader,
)
from broker.backtest_runner import (
    BacktestInsufficientHistoryError,
    BacktestRunObserver,
    BacktestRunner,
)
from broker.config import BrokerConfig
from broker.views import (
    BacktestEndPositionView,
    BacktestConfigView,
    BacktestDecisionView,
    BacktestNoTradeReasonView,
    BacktestOrderEvidenceView,
    BacktestProgressView,
    BacktestProvenanceView,
    BacktestResultView,
    BacktestSeriesPointView,
    ClosedTradeView,
    PerformanceMetricsView,
    TradeView,
)
from dataflow.store import MarketDataStore
from dataflow.history import DataServiceHistoryLoader
from storage.backtest_snapshot import (
    CanonicalSnapshotEnvelope,
    decode_canonical_snapshot,
)
from storage.store import (
    BacktestDecisionEvidence,
    BacktestInputSnapshotContent,
    BacktestInputSnapshotRecord,
    BacktestJobRecord,
    ContextStore,
)

type BacktestJobStatus = Literal["pending", "running", "completed", "failed"]
type BacktestJobErrorCode = Literal[
    "agent_failed",
    "backtest_failed",
    "execution_failed",
    "interrupted",
    "market_data_unavailable",
    "storage_corrupt",
    "decision_context_invalid",
    "decision_policy_invalid",
    "decision_transient_exhausted",
    "provider_failed",
    "decision_schema_invalid",
    "insufficient_history",
]

_SESSION_TIMESTAMP: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00:00Z$")
_SESSION_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")
_MAX_FROZEN_SNAPSHOT_BYTES: Final = 16 * 1024 * 1024
_FROZEN_SNAPSHOT_PROVENANCE_KEYS: Final = frozenset(
    {
        "actions",
        "auto_adjust",
        "corporate_actions_mode",
        "date_from",
        "date_to",
        "end_exclusive",
        "interval",
        "library_version",
        "lookback_days",
        "provider",
        "provider_buffer_days",
        "provider_end_semantics",
        "provider_timezone",
        "row_adjustment_modes",
        "ticker",
        "timezone_normalization",
        "warmup_bars",
    }
)


class BacktestRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    strategy_id: str = Field(min_length=1, max_length=128)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    date_from: date
    date_to: date
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    benchmark: str = Field(default="SPY", pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    mode: BacktestMode = BacktestMode.DETERMINISTIC

    @model_validator(mode="after")
    def ordered_date_window(self) -> BacktestRequest:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class BacktestJobError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: BacktestJobErrorCode
    stage: str | None = Field(default=None, max_length=64)
    decision_date: str | None = Field(default=None, max_length=64)
    attempt: int | None = Field(default=None, ge=1)
    message: str


class BacktestJobAcceptedResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    status: Literal["pending"] = "pending"
    contract_version: Literal[1] = 1


class BacktestSnapshotEvidenceView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    compressed_bytes: int = Field(ge=0)
    uncompressed_bytes: int = Field(ge=0)


class BacktestJobResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Literal["completed", "completed_no_trades"]
    warnings: list[str] = Field(default_factory=list)
    no_trade_reasons: list[BacktestNoTradeReasonView] = Field(default_factory=list)
    metrics: PerformanceMetricsView
    equity: list[BacktestSeriesPointView] = Field(default_factory=list)
    orders: list[BacktestOrderEvidenceView] = Field(default_factory=list)
    fills: list[TradeView] = Field(default_factory=list)
    closed_trades: list[ClosedTradeView] = Field(default_factory=list)
    end_position: BacktestEndPositionView
    snapshot: BacktestSnapshotEvidenceView | None = None
    provenance: BacktestProvenanceView


class BacktestJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    status: BacktestJobStatus
    request: BacktestRequest | None = None
    config: BacktestConfigView | None = None
    progress: BacktestProgressView = Field(default_factory=BacktestProgressView)
    decisions: list[BacktestDecisionView] = Field(default_factory=list)
    result: BacktestJobResult | None = None
    error: BacktestJobError | None = None
    created_at: str
    updated_at: str


class BacktestJobRunner(Protocol):
    def run(self, spec: BacktestRunSpec) -> BacktestResultView: ...


@runtime_checkable
class ObservabilityAwareBacktestJobRunner(Protocol):
    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView: ...


@runtime_checkable
class SnapshotReplayAwareBacktestJobRunner(Protocol):
    def run(self, spec: BacktestRunSpec) -> BacktestResultView: ...

    def run_replay_with_observability(
        self,
        spec: BacktestRunSpec,
        snapshot: BacktestInputSnapshotRecord,
        observer: BacktestRunObserver,
    ) -> BacktestResultView: ...


@dataclass(frozen=True, slots=True)
class BacktestReplayInput:
    spec: BacktestRunSpec
    snapshot: BacktestInputSnapshotRecord


class BacktestReplayUnavailableError(RuntimeError):
    pass


class _DiscardingBacktestRunObserver:
    def __init__(self) -> None:
        self.input_snapshot_hash: str | None = None

    def bind_input_snapshot(
        self, target: pd.DataFrame, benchmark: pd.DataFrame
    ) -> None:
        self.input_snapshot_hash = _canonical_input_snapshot(
            target, benchmark
        ).content_hash

    def record_progress(self, progress: BacktestProgressView) -> None:
        del progress

    def begin_decision(
        self, sequence: int, decision_date: str, policy_hash: str
    ) -> None:
        del sequence, decision_date, policy_hash

    def record_decision(self, decision: BacktestDecisionView) -> None:
        del decision

    def record_execution(self, sequence: int, execution_date: str) -> None:
        del sequence, execution_date


class ActiveBacktestJobRunner:
    def __init__(
        self,
        market_store: MarketDataStore | None = None,
        history_loader: HistoricalPriceLoader | None = None,
        experimental_adapter: ExperimentalDecisionAdapter | None = None,
    ) -> None:
        self._market_store = market_store or MarketDataStore()
        self._history_loader = history_loader or DataServiceHistoryLoader(
            self._market_store
        )
        self._experimental_adapter = experimental_adapter

    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        return self.run_with_observability(spec, _DiscardingBacktestRunObserver())

    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        dataset = BacktestDatasetPreparer(
            self._market_store,
            history_loader=self._history_loader,
        ).prepare(
            ticker=spec.ticker,
            benchmark_symbol=spec.benchmark,
            date_from=spec.date_from.isoformat(),
            date_to=spec.date_to.isoformat(),
            warmup_bars=spec.policy.required_lookback_bars,
        )
        return self._run_dataset(
            spec,
            observer,
            target=dataset.target,
            benchmark=dataset.benchmark,
            target_history=dataset.target_history,
            benchmark_history=dataset.benchmark_history,
            warmup_bar_count=dataset.warmup_bar_count,
        )

    def run_replay_with_observability(
        self,
        spec: BacktestRunSpec,
        snapshot: BacktestInputSnapshotRecord,
        observer: BacktestRunObserver,
    ) -> BacktestResultView:
        target_history, benchmark_history = _replay_snapshot_frames(snapshot, spec)
        target = target_history.loc[
            spec.date_from.isoformat() : spec.date_to.isoformat()
        ].copy()
        benchmark = benchmark_history.loc[
            spec.date_from.isoformat() : spec.date_to.isoformat()
        ].copy()
        if target.empty:
            raise BacktestDataError("frozen backtest snapshot has no target window")
        data_provenance = target_history.attrs.get("backtest_data_provenance")
        if not isinstance(data_provenance, dict):
            raise BacktestDataError("frozen backtest snapshot has no data provenance")
        warmup_bar_count = data_provenance.get("warmup_bars")
        if (
            not isinstance(warmup_bar_count, int)
            or isinstance(warmup_bar_count, bool)
            or warmup_bar_count < 0
        ):
            raise BacktestDataError(
                "frozen backtest snapshot has invalid data provenance"
            )
        return self._run_dataset(
            spec,
            observer,
            target=target,
            benchmark=benchmark,
            target_history=target_history,
            benchmark_history=benchmark_history,
            warmup_bar_count=warmup_bar_count,
        )

    def _run_dataset(
        self,
        spec: BacktestRunSpec,
        observer: BacktestRunObserver,
        *,
        target: pd.DataFrame,
        benchmark: pd.DataFrame,
        target_history: pd.DataFrame,
        benchmark_history: pd.DataFrame,
        warmup_bar_count: int,
    ) -> BacktestResultView:
        data_provenance = target_history.attrs.get("backtest_data_provenance")
        if not isinstance(data_provenance, dict):
            raise BacktestDataError("frozen backtest snapshot has no data provenance")
        runner = BacktestRunner(
            BrokerConfig(**spec.broker_config.model_dump()),
            decision_executor=BacktestRunDecisionExecutor(
                spec, experimental_adapter=self._experimental_adapter
            ),
        )
        result = runner.run(
            spec.ticker,
            target,
            spec.date_from.isoformat(),
            spec.date_to.isoformat(),
            benchmark_df=benchmark,
            benchmark_symbol=spec.benchmark,
            frequency=spec.run_frequency,
            strategy_id=spec.strategy_id,
            policy_hash=spec.policy_hash,
            observer=observer,
            history_df=target_history,
            snapshot_benchmark_df=benchmark_history,
        ).view
        warnings = [
            *result.warnings,
            "max_drawdown_limit_not_enforced",
            "capacity_model_not_modeled",
            "provider_adjusted_prices_are_synthetic",
            *_sample_size_warnings(
                evaluation_bar_count=len(target),
                closed_trade_count=len(result.closed_trades),
            ),
        ]
        if spec.mode is BacktestMode.AGENT_EXPERIMENT:
            warnings.append("experimental_provider_dependent_result")
        if not result.closed_trades:
            warnings.append("completed_with_no_trades_not_trusted_performance")
        warnings = list(dict.fromkeys(warnings))
        data_snapshot_hash = getattr(observer, "input_snapshot_hash", None)
        if not isinstance(data_snapshot_hash, str) or not _SHA256_HEX.fullmatch(
            data_snapshot_hash
        ):
            raise BacktestObservabilityError()
        config = BacktestConfigView(
            ticker=spec.ticker,
            start_date=spec.date_from.isoformat(),
            end_date=spec.date_to.isoformat(),
            frequency=spec.run_frequency,
            benchmark_symbol=spec.benchmark,
            strategy_id=spec.strategy_id,
            engine_version=spec.engine_version,
            mode=spec.mode.value,
            agent_model=(
                spec.policy.policy.model
                if isinstance(spec.policy.policy, ExperimentalAgentPolicy)
                else None
            ),
            strategy_snapshot_hash=spec.strategy_snapshot_hash,
            policy_hash=spec.policy_hash,
            data_snapshot_hash=data_snapshot_hash,
            strategy_execution_frequency=spec.strategy_execution_frequency,
            run_frequency=spec.run_frequency,
            initial_capital=spec.broker_config.initial_cash,
            commission_rate=spec.broker_config.commission_rate,
            commission_bps=spec.broker_config.commission_rate * 10_000,
            slippage_rate=spec.broker_config.slippage_rate,
            slippage_bps=spec.broker_config.slippage_rate * 10_000,
            execution_timing=spec.broker_config.execution_timing,
            max_position_pct=spec.broker_config.max_position_pct,
            allow_short=spec.broker_config.allow_short,
            max_drawdown_limit_pct=spec.max_drawdown_limit_pct,
            max_drawdown_limit_enforced=spec.max_drawdown_limit_enforced,
            data_provider=str(data_provenance["provider"]),
            data_provider_version=str(data_provenance["library_version"]),
            data_interval="1d",
            data_auto_adjust=True,
            data_actions=False,
            data_end_exclusive=(spec.date_to + timedelta(days=1)).isoformat(),
            data_lookback_days=int(data_provenance["lookback_days"]),
            data_provider_buffer_days=100,
            data_provider_end_semantics="exclusive",
            data_provider_timezone=str(data_provenance["provider_timezone"]),
            data_timezone_normalization=("exchange_session_date_to_UTC_midnight"),
            warmup_bars=warmup_bar_count,
            risk_free_rate=0.0,
            periods_per_year=252,
            evaluation_bar_count=len(target),
            sample_first_date=str(target.index[0])[:10],
            sample_last_date=str(target.index[-1])[:10],
        )
        finalized_result = result.model_copy(
            update={
                "outcome": (
                    "completed" if result.closed_trades else "completed_no_trades"
                ),
                "config": config,
                "warnings": warnings,
            }
        )
        return _with_bound_result_provenance(
            spec,
            finalized_result,
            data_snapshot_hash=data_snapshot_hash,
        )


def _frozen_snapshot_payload(
    snapshot: BacktestInputSnapshotRecord,
) -> dict[str, object]:
    if (
        snapshot.schema_version != 1
        or snapshot.codec != "gzip-json-v1"
        or snapshot.compressed_bytes != len(snapshot.payload)
        or snapshot.uncompressed_bytes < 0
        or snapshot.uncompressed_bytes > _MAX_FROZEN_SNAPSHOT_BYTES
        or _SHA256_HEX.fullmatch(snapshot.content_hash) is None
    ):
        raise BacktestDataError("frozen backtest snapshot is invalid")
    try:
        canonical = decode_canonical_snapshot(
            CanonicalSnapshotEnvelope(
                payload=snapshot.payload,
                compressed_bytes=snapshot.compressed_bytes,
                uncompressed_bytes=snapshot.uncompressed_bytes,
                content_hash=snapshot.content_hash,
                maximum_uncompressed_bytes=_MAX_FROZEN_SNAPSHOT_BYTES,
            )
        )
        payload = json.loads(canonical)
    except (
        RuntimeError,
        json.JSONDecodeError,
    ) as error:
        raise BacktestDataError("frozen backtest snapshot is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise BacktestDataError("frozen backtest snapshot is invalid")
    return payload


def _replay_snapshot_frames(
    snapshot: BacktestInputSnapshotRecord,
    spec: BacktestRunSpec,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = _frozen_snapshot_payload(snapshot)
    target = _replay_snapshot_frame(payload.get("target"))
    benchmark = _replay_snapshot_frame(payload.get("benchmark"), allow_empty=True)
    if (
        len(target) != snapshot.row_count_target
        or len(benchmark) != snapshot.row_count_benchmark
    ):
        raise BacktestDataError("frozen backtest snapshot is invalid")
    provenance = payload.get("data_provenance")
    if not isinstance(provenance, dict):
        raise BacktestDataError("frozen backtest snapshot has no data provenance")
    for name, frame in (("target", target), ("benchmark", benchmark)):
        value = _validated_replay_snapshot_provenance(
            provenance.get(name),
            spec=spec,
            ticker=spec.ticker if name == "target" else spec.benchmark,
            allow_missing_adjustment_modes=frame.empty,
        )
        frame.attrs["backtest_data_provenance"] = {
            key: item for key, item in value.items() if key != "row_adjustment_modes"
        }
        modes = value.get("row_adjustment_modes")
        if isinstance(modes, list) and all(isinstance(mode, str) for mode in modes):
            frame.attrs["adjustment_modes"] = tuple(modes)
    evaluation_start = pd.Timestamp(spec.date_from, tz="UTC")
    evaluation_end = pd.Timestamp(spec.date_to, tz="UTC")
    requested_warmup = spec.policy.required_lookback_bars
    for frame in (target, benchmark):
        if (frame.index > evaluation_end).any() or int(
            (frame.index < evaluation_start).sum()
        ) > requested_warmup:
            raise BacktestDataError("frozen backtest snapshot is invalid")
    evaluation_target = target.loc[evaluation_start:evaluation_end]
    evaluation_benchmark = benchmark.loc[evaluation_start:evaluation_end]
    if evaluation_target.empty:
        raise BacktestDataError("frozen backtest snapshot has no target window")
    if evaluation_target.index.intersection(evaluation_benchmark.index).empty:
        raise BacktestDataError(
            "frozen backtest snapshot has no overlapping benchmark session"
        )
    return target, benchmark


def _validated_replay_snapshot_provenance(
    value: object,
    *,
    spec: BacktestRunSpec,
    ticker: str,
    allow_missing_adjustment_modes: bool,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    keys = set(value)
    missing_adjustment_modes = _FROZEN_SNAPSHOT_PROVENANCE_KEYS - {
        "row_adjustment_modes"
    }
    if keys != _FROZEN_SNAPSHOT_PROVENANCE_KEYS and not (
        allow_missing_adjustment_modes and keys == missing_adjustment_modes
    ):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    string_keys = keys - {
        "actions",
        "auto_adjust",
        "lookback_days",
        "provider_buffer_days",
        "row_adjustment_modes",
        "warmup_bars",
    }
    if any(not isinstance(value[key], str) for key in string_keys):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    integer_keys = {"lookback_days", "provider_buffer_days", "warmup_bars"}
    if any(
        not isinstance(value[key], int) or isinstance(value[key], bool)
        for key in integer_keys
    ):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    if not isinstance(value["actions"], bool) or not isinstance(
        value["auto_adjust"], bool
    ):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    expected_contract: dict[str, str | int | bool] = {
        "provider": "yfinance",
        "ticker": ticker,
        "date_from": spec.date_from.isoformat(),
        "date_to": spec.date_to.isoformat(),
        "end_exclusive": (spec.date_to + timedelta(days=1)).isoformat(),
        "provider_buffer_days": 100,
        "interval": "1d",
        "auto_adjust": True,
        "actions": False,
        "warmup_bars": spec.policy.required_lookback_bars,
        "corporate_actions_mode": "provider_adjusted_prices",
        "provider_end_semantics": "exclusive",
        "timezone_normalization": "exchange_session_date_to_UTC_midnight",
    }
    if any(value[key] != expected for key, expected in expected_contract.items()):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    if (
        value["lookback_days"] < 0
        or value["provider_buffer_days"] < 0
        or value["warmup_bars"] < 0
    ):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    modes = value.get("row_adjustment_modes")
    if modes is None and allow_missing_adjustment_modes:
        return value
    if not isinstance(modes, list) or any(not isinstance(mode, str) for mode in modes):
        raise BacktestDataError("frozen backtest snapshot has invalid data provenance")
    return value


def _snapshot_content(
    snapshot: BacktestInputSnapshotRecord,
) -> BacktestInputSnapshotContent:
    return BacktestInputSnapshotContent(
        content_hash=snapshot.content_hash,
        payload=snapshot.payload,
        uncompressed_bytes=snapshot.uncompressed_bytes,
        row_count_target=snapshot.row_count_target,
        row_count_benchmark=snapshot.row_count_benchmark,
    )


def _replay_snapshot_frame(value: object, *, allow_empty: bool = False) -> pd.DataFrame:
    if not isinstance(value, dict):
        raise BacktestDataError("frozen backtest snapshot is invalid")
    columns = value.get("columns")
    rows = value.get("rows")
    expected_columns = ["Open", "High", "Low", "Close", "Volume"]
    if columns != expected_columns or not isinstance(rows, list):
        raise BacktestDataError("frozen backtest snapshot is invalid")
    dates: list[str] = []
    values: list[list[float]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(expected_columns) + 1:
            raise BacktestDataError("frozen backtest snapshot is invalid")
        session_date, *raw_values = row
        if (
            not isinstance(session_date, str)
            or _SESSION_DATE.fullmatch(session_date) is None
            or not all(
                isinstance(raw, str | int | float) and not isinstance(raw, bool)
                for raw in raw_values
            )
        ):
            raise BacktestDataError("frozen backtest snapshot is invalid")
        try:
            numeric_values = [float(raw) for raw in raw_values]
            parsed_date = date.fromisoformat(session_date)
        except (TypeError, ValueError) as error:
            raise BacktestDataError("frozen backtest snapshot is invalid") from error
        if parsed_date.isoformat() != session_date or not all(
            math.isfinite(number) for number in numeric_values
        ):
            raise BacktestDataError("frozen backtest snapshot is invalid")
        open_price, high, low, close, volume = numeric_values
        if (
            min(open_price, high, low, close) <= 0
            or volume < 0
            or low > min(open_price, close)
            or max(open_price, close) > high
        ):
            raise BacktestDataError("frozen backtest snapshot is invalid")
        dates.append(session_date)
        values.append(numeric_values)
    frame = pd.DataFrame(
        values,
        columns=pd.Index(expected_columns),
        index=pd.DatetimeIndex(pd.to_datetime(dates, format="%Y-%m-%d", utc=True)),
    )
    if (
        (frame.empty and not allow_empty)
        or not frame.index.is_unique
        or not frame.index.is_monotonic_increasing
    ):
        raise BacktestDataError("frozen backtest snapshot is invalid")
    return frame


def _sample_size_warnings(
    *, evaluation_bar_count: int, closed_trade_count: int
) -> list[str]:
    warnings: list[str] = []
    if evaluation_bar_count < 63:
        warnings.append("insufficient_evaluation_bars_lt_63")
    if evaluation_bar_count < 252:
        warnings.append("insufficient_evaluation_bars_lt_252")
    if closed_trade_count < 30:
        warnings.append("insufficient_closed_trades_lt_30")
    return warnings


def _canonical_economic_result_hash(
    spec: BacktestRunSpec,
    result: BacktestResultView,
    *,
    data_snapshot_hash: str,
) -> str:
    config_fields = {
        "ticker",
        "start_date",
        "end_date",
        "run_frequency",
        "benchmark_symbol",
        "mode",
        "initial_capital",
        "commission_rate",
        "slippage_rate",
        "execution_timing",
        "max_position_pct",
        "allow_short",
        "provider_adjustment_mode",
        "corporate_actions_mode",
        "data_provider",
        "data_provider_version",
        "data_interval",
        "data_auto_adjust",
        "data_actions",
        "data_end_exclusive",
        "data_lookback_days",
        "data_provider_buffer_days",
        "data_provider_end_semantics",
        "data_provider_timezone",
        "data_timezone_normalization",
        "warmup_bars",
        "risk_free_rate",
        "periods_per_year",
        "max_drawdown_limit_pct",
        "max_drawdown_limit_enforced",
        "evaluation_bar_count",
        "sample_first_date",
        "sample_last_date",
    }
    decision_fields = {
        "sequence",
        "signal_date",
        "execution_date",
        "status",
        "target_position_pct",
        "confidence",
        "action",
        "feature_hash",
        "error_code",
    }
    order_fields = {
        "status",
        "signal_date",
        "execution_date",
        "reason",
        "ticker",
        "side",
        "quantity",
        "order_type",
        "limit_price",
    }
    fill_fields = {
        "timestamp",
        "ticker",
        "side",
        "quantity",
        "price",
        "fee",
        "slippage",
        "trade_value",
        "realized_pnl",
        "cash_after",
        "equity_after",
        "shares_after",
        "avg_cost_after",
    }
    closed_trade_fields = {
        "entry_at",
        "exit_at",
        "ticker",
        "quantity",
        "entry_vwap",
        "exit_vwap",
        "average_cost_basis",
        "net_realized_pnl",
        "fees",
        "slippage",
        "holding_period_trading_days",
    }
    canonical = {
        "canonicalization_version": "backtest-economic-result/v1",
        "run_contract_version": spec.contract_version,
        "engine_version": spec.engine_version,
        "policy_hash": spec.policy_hash,
        "strategy_snapshot_hash": spec.strategy_snapshot_hash,
        "data_snapshot_hash": data_snapshot_hash,
        "economic_result": {
            "config": result.config.model_dump(mode="json", include=config_fields),
            "outcome": result.outcome,
            "warnings": result.warnings,
            "no_trade_reasons": [
                reason.model_dump(mode="json", include={"code", "count"})
                for reason in result.no_trade_reasons
            ],
            "metrics": result.summary.model_dump(mode="json"),
            "equity": [point.model_dump(mode="json") for point in result.series],
            "decisions": [
                decision.model_dump(mode="json", include=decision_fields)
                for decision in result.decisions
            ],
            "orders": [
                order.model_dump(mode="json", include=order_fields)
                for order in result.orders
            ],
            "fills": [
                execution.model_dump(mode="json", include=fill_fields)
                for execution in result.executions
            ],
            "closed_trades": [
                closed_trade.model_dump(mode="json", include=closed_trade_fields)
                for closed_trade in result.closed_trades
            ],
            "end_position": result.end_position.model_dump(
                mode="json",
                include={
                    "ticker",
                    "shares",
                    "market_value",
                    "average_cost_basis",
                    "unrealized_pnl",
                    "liquidated_at_end",
                },
            ),
        },
    }
    encoded = json.dumps(
        canonical,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _with_bound_result_provenance(
    spec: BacktestRunSpec,
    result: BacktestResultView,
    *,
    data_snapshot_hash: str,
) -> BacktestResultView:
    canonical_result_hash = _canonical_economic_result_hash(
        spec,
        result,
        data_snapshot_hash=data_snapshot_hash,
    )
    return result.model_copy(
        update={
            "provenance": BacktestProvenanceView(
                strategy_snapshot_hash=spec.strategy_snapshot_hash,
                policy_hash=spec.policy_hash,
                data_snapshot_hash=data_snapshot_hash,
                canonical_result_hash=canonical_result_hash,
            )
        }
    )


@dataclass(frozen=True, slots=True)
class _PendingBacktestDecision:
    sequence: int
    decision_date: str
    policy_hash: str


class BacktestObservabilityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _SafeDecisionFailure:
    code: BacktestJobErrorCode
    stage: str | None
    decision_date: str | None
    attempt: int
    message: str


class _JobObservabilitySink:
    def __init__(self, store: ContextStore, job_id: str, policy_hash: str) -> None:
        self._store = store
        self._job_id = job_id
        self._policy_hash = policy_hash
        self._pending: _PendingBacktestDecision | None = None
        self.input_snapshot_hash: str | None = None

    def bind_input_snapshot(
        self, target: pd.DataFrame, benchmark: pd.DataFrame
    ) -> None:
        snapshot = _canonical_input_snapshot(target, benchmark)
        self._store.bind_backtest_input_snapshot(self._job_id, snapshot)
        self.input_snapshot_hash = snapshot.content_hash

    def record_progress(self, progress: BacktestProgressView) -> None:
        self._store.update_backtest_job_progress(
            self._job_id,
            progress.model_copy(
                update={
                    "current_decision_date": _safe_session_timestamp(
                        progress.current_decision_date
                    )
                }
            ).model_dump_json(),
        )

    def begin_decision(
        self, sequence: int, decision_date: str, policy_hash: str
    ) -> None:
        del policy_hash
        safe_decision_date = _safe_session_timestamp(decision_date)
        if safe_decision_date is None:
            raise BacktestObservabilityError()
        self._pending = _PendingBacktestDecision(
            sequence=sequence,
            decision_date=safe_decision_date,
            policy_hash=self._policy_hash,
        )

    def record_decision(self, decision: BacktestDecisionView) -> None:
        pending = self._pending
        if pending is None:
            raise BacktestObservabilityError()
        self._store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id=self._job_id,
                sequence=pending.sequence,
                signal_date=pending.decision_date,
                execution_date=_safe_session_timestamp(decision.execution_date),
                status=decision.status,
                attempts=decision.attempts,
                target_position_pct=decision.target_position_pct,
                confidence=decision.confidence,
                action=decision.action,
                rationale=decision.rationale,
                feature_hash=_safe_sha256(decision.feature_hash),
                policy_hash=pending.policy_hash,
                error_code=None,
                error_stage=None,
            )
        )
        self._pending = None

    def record_execution(self, sequence: int, execution_date: str) -> None:
        safe_execution_date = _safe_session_timestamp(execution_date)
        if safe_execution_date is None:
            raise BacktestObservabilityError()
        updated = self._store.update_backtest_decision_execution(
            self._job_id, sequence, safe_execution_date
        )
        if not updated:
            raise BacktestObservabilityError()

    def record_failure(self, error: BacktestDecisionError) -> None:
        pending = self._pending
        if pending is None:
            return
        safe_failure = _safe_decision_failure(error)
        self._store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id=self._job_id,
                sequence=pending.sequence,
                signal_date=pending.decision_date,
                execution_date=None,
                status="failed",
                attempts=safe_failure.attempt,
                target_position_pct=None,
                confidence=None,
                action=None,
                rationale=None,
                feature_hash=None,
                policy_hash=pending.policy_hash,
                error_code=safe_failure.code,
                error_stage=safe_failure.stage,
            )
        )
        self._pending = None


def _canonical_input_snapshot(
    target: pd.DataFrame, benchmark: pd.DataFrame
) -> BacktestInputSnapshotContent:
    expected_columns = ["Open", "High", "Low", "Close", "Volume"]
    if (
        list(target.columns) != expected_columns
        or list(benchmark.columns) != expected_columns
    ):
        raise BacktestDataError("backtest input snapshot requires canonical OHLCV")
    payload: dict[str, object] = {
        "benchmark": json.loads(_canonical_frame_json(benchmark)),
        "schema_version": 1,
        "target": json.loads(_canonical_frame_json(target)),
    }
    target_provenance = _canonical_data_provenance(target)
    benchmark_provenance = _canonical_data_provenance(benchmark)
    if target_provenance is not None and benchmark_provenance is not None:
        payload["data_provenance"] = {
            "target": target_provenance,
            "benchmark": benchmark_provenance,
        }
    canonical_bytes = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical_bytes).hexdigest(),
        payload=gzip.compress(canonical_bytes, mtime=0),
        uncompressed_bytes=len(canonical_bytes),
        row_count_target=len(target),
        row_count_benchmark=len(benchmark),
    )


def _canonical_data_provenance(frame: pd.DataFrame) -> dict[str, object] | None:
    raw = frame.attrs.get("backtest_data_provenance")
    if not isinstance(raw, dict):
        return None
    keys = (
        "actions",
        "auto_adjust",
        "corporate_actions_mode",
        "date_from",
        "date_to",
        "end_exclusive",
        "interval",
        "library_version",
        "lookback_days",
        "provider",
        "provider_buffer_days",
        "provider_end_semantics",
        "provider_timezone",
        "ticker",
        "timezone_normalization",
        "warmup_bars",
    )
    safe: dict[str, object] = {}
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str | int | bool):
            safe[key] = value
    modes = frame.attrs.get("adjustment_modes")
    if isinstance(modes, tuple):
        safe["row_adjustment_modes"] = sorted({str(mode) for mode in modes})
    return safe


def _safe_session_timestamp(value: str | None) -> str | None:
    if value is None or _SESSION_TIMESTAMP.fullmatch(value) is None:
        return None
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return None
    return value


def _safe_sha256(value: str | None) -> str | None:
    return value if value is not None and _SHA256_HEX.fullmatch(value) else None


def _safe_decision_failure(error: BacktestDecisionError) -> _SafeDecisionFailure:
    code = _safe_decision_error_code(error.code)
    return _SafeDecisionFailure(
        code=code,
        stage=_safe_decision_error_stage(error.stage),
        decision_date=_safe_session_timestamp(error.decision_date),
        attempt=_safe_decision_attempt(error.attempt),
        message=_safe_decision_error_message(code),
    )


def _safe_decision_error_code(value: str) -> BacktestJobErrorCode:
    match value:
        case "agent_failed":
            return "agent_failed"
        case "decision_context_invalid":
            return "decision_context_invalid"
        case "decision_policy_invalid":
            return "decision_policy_invalid"
        case "decision_transient_exhausted":
            return "decision_transient_exhausted"
        case "provider_failed":
            return "provider_failed"
        case "decision_schema_invalid":
            return "decision_schema_invalid"
        case _:
            return "backtest_failed"


def _safe_decision_error_stage(value: str) -> str | None:
    return (
        value
        if value
        in {
            "agent_execution",
            "context",
            "policy",
            "provider",
            "transient",
            "structured_output",
            "tool_call",
            "tool_payload",
        }
        else None
    )


def _safe_decision_attempt(value: int) -> int:
    return value if value >= 1 else 1


def _safe_decision_error_message(code: BacktestJobErrorCode) -> str:
    match code:
        case "agent_failed":
            return "Backtest agent execution failed"
        case "decision_context_invalid":
            return "Backtest decision context is unavailable"
        case "decision_policy_invalid":
            return "Backtest decision violates the frozen policy"
        case "decision_transient_exhausted":
            return "Backtest decision provider remained unavailable"
        case "provider_failed":
            return "Backtest decision provider failed"
        case "decision_schema_invalid":
            return "Backtest decision could not be validated"
        case _:
            return "Backtest failed"


def _canonical_frame_json(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    rows = [
        [
            str(index)[:10],
            *[_canonical_decimal(float(row[column])) for column in frame.columns],
        ]
        for index, row in frame.iterrows()
    ]
    return json.dumps(
        {"columns": columns, "rows": rows},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_decimal(value: float) -> str:
    if not math.isfinite(value):
        raise BacktestDataError("backtest input snapshot requires finite OHLCV values")
    normalized = format(Decimal(str(value)).normalize(), "f")
    return "0" if normalized in {"", "-0"} else normalized


class BacktestJobService:
    def __init__(
        self,
        *,
        store: ContextStore,
        runner: (
            BacktestJobRunner
            | ObservabilityAwareBacktestJobRunner
            | SnapshotReplayAwareBacktestJobRunner
        ),
        llm_available: bool = True,
        structured_output_supported: bool | Callable[[str], bool] = True,
        strategy_resolver: Callable[[str], dict[str, object] | None] | None = None,
        max_workers: int = 2,
    ) -> None:
        self._store = store
        self._runner = runner
        self._llm_available = llm_available
        self._structured_output_supported = structured_output_supported
        self._strategy_resolver = strategy_resolver or store.get_strategy
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="backtest-job",
        )

    def create(self, request: BacktestRequest) -> BacktestJobAcceptedResponse:
        strategy = self._strategy_resolver(request.strategy_id)
        if strategy is None:
            raise StrategyEligibilityError(
                "strategy_not_found", "Strategy not found", http_status=404
            )
        spec = freeze_backtest_run_spec(
            request,
            strategy,
            llm_available=self._llm_available,
            structured_output_supported=self._supports_structured_output(strategy),
        )
        job_id = uuid4().hex
        self._store.create_backtest_job(
            job_id, request.model_dump_json(), spec.model_dump_json()
        )
        self._executor.submit(self._run_job, job_id, spec)
        return BacktestJobAcceptedResponse(id=job_id)

    def _supports_structured_output(self, strategy: dict[str, object]) -> bool:
        capability = self._structured_output_supported
        if isinstance(capability, bool):
            return capability
        model = strategy.get("agent_model")
        return capability(model if isinstance(model, str) else "")

    def get(self, job_id: str) -> BacktestJobResponse | None:
        try:
            job = self._store.get_backtest_job(job_id)
        except RuntimeError:
            return _storage_corrupt_response(job_id)
        return _to_response(job, self._store) if job is not None else None

    def replay(self, job_id: str) -> BacktestReplayInput:
        try:
            job = self._store.get_backtest_job(job_id)
        except RuntimeError as error:
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            ) from error
        if (
            job is None
            or job.contract_version != 1
            or job.run_spec_json is None
            or job.input_snapshot_hash is None
        ):
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            )
        try:
            spec = BacktestRunSpec.model_validate_json(job.run_spec_json)
        except ValidationError as error:
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            ) from error
        if not _request_matches_spec(job.request_json, spec):
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            )
        try:
            snapshot = self._store.get_backtest_input_snapshot(job.input_snapshot_hash)
        except RuntimeError as error:
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            ) from error
        if snapshot is None:
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            )
        if snapshot.schema_version != 1 or snapshot.codec != "gzip-json-v1":
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            )
        try:
            _replay_snapshot_frames(snapshot, spec)
        except BacktestDataError as error:
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            ) from error
        return BacktestReplayInput(spec=spec, snapshot=snapshot)

    def create_replay(self, job_id: str) -> BacktestJobAcceptedResponse:
        replay = self.replay(job_id)
        replay_id = uuid4().hex
        request = BacktestRequest(
            strategy_id=replay.spec.strategy_id,
            ticker=replay.spec.ticker,
            date_from=replay.spec.date_from,
            date_to=replay.spec.date_to,
            frequency=replay.spec.run_frequency,
            benchmark=replay.spec.benchmark,
            mode=replay.spec.mode,
        )
        self._store.create_backtest_job(
            replay_id,
            request.model_dump_json(),
            replay.spec.model_dump_json(),
        )
        self._executor.submit(self._run_replay_job, replay_id, replay)
        return BacktestJobAcceptedResponse(id=replay_id)

    def trades_csv(self, job_id: str) -> str | None:
        result = self._completed_export_result(job_id)
        if result is None:
            return None
        output = io.StringIO(newline="")
        fields = (
            "date",
            "ticker",
            "side",
            "quantity",
            "price",
            "realized_pl",
            "equity_after",
        )
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for trade in result.fills:
            writer.writerow(
                {
                    "date": trade.timestamp.date().isoformat(),
                    "ticker": trade.ticker,
                    "side": trade.side,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "realized_pl": trade.realized_pnl,
                    "equity_after": trade.equity_after,
                }
            )
        return output.getvalue()

    def closed_trades_csv(self, job_id: str) -> str | None:
        result = self._completed_export_result(job_id)
        if result is None:
            return None
        output = io.StringIO(newline="")
        fields = (
            "entry_date",
            "exit_date",
            "ticker",
            "quantity",
            "entry_vwap",
            "exit_vwap",
            "net_realized_pl",
            "fees",
            "slippage",
            "holding_period_trading_days",
        )
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for trade in result.closed_trades:
            writer.writerow(
                {
                    "entry_date": trade.entry_at.date().isoformat(),
                    "exit_date": trade.exit_at.date().isoformat(),
                    "ticker": trade.ticker,
                    "quantity": trade.quantity,
                    "entry_vwap": trade.entry_vwap,
                    "exit_vwap": trade.exit_vwap,
                    "net_realized_pl": trade.net_realized_pnl,
                    "fees": trade.fees,
                    "slippage": trade.slippage,
                    "holding_period_trading_days": trade.holding_period_trading_days,
                }
            )
        return output.getvalue()

    def decisions_csv(self, job_id: str) -> str | None:
        rows = self._decision_export_rows(job_id)
        if rows is None:
            return None
        output = io.StringIO(newline="")
        fields = (
            "sequence",
            "signal_date",
            "execution_date",
            "status",
            "target_position_pct",
            "confidence",
            "action",
            "rationale",
            "attempts",
            "error_code",
        )
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow([row[field] for field in fields])
        return output.getvalue()

    def decisions_json(self, job_id: str) -> str | None:
        rows = self._decision_export_rows(job_id)
        if rows is None:
            return None
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    def _completed_export_result(self, job_id: str) -> BacktestJobResult | None:
        job = self.get(job_id)
        if job is None or job.status != "completed":
            return None
        return job.result

    def _decision_export_rows(
        self, job_id: str
    ) -> list[dict[str, object | None]] | None:
        job = self.get(job_id)
        if job is None or job.status != "completed" or job.result is None:
            return None
        return [
            {
                "sequence": decision.sequence,
                "signal_date": decision.signal_date,
                "execution_date": decision.execution_date,
                "status": decision.status,
                "target_position_pct": decision.target_position_pct,
                "confidence": decision.confidence,
                "action": decision.action,
                "rationale": decision.rationale,
                "attempts": decision.attempts,
                "error_code": decision.error_code,
            }
            for decision in job.decisions
        ]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    def _run_job(self, job_id: str, spec: BacktestRunSpec) -> None:
        def execute(observer: _JobObservabilitySink) -> BacktestResultView:
            if isinstance(self._runner, ObservabilityAwareBacktestJobRunner):
                return self._runner.run_with_observability(spec, observer)
            return self._runner.run(spec)

        self._run_persisted_job(job_id, spec, execute)

    def _run_replay_job(self, job_id: str, replay: BacktestReplayInput) -> None:
        def execute(observer: _JobObservabilitySink) -> BacktestResultView:
            self._store.bind_backtest_input_snapshot(
                job_id, _snapshot_content(replay.snapshot)
            )
            if not isinstance(self._runner, SnapshotReplayAwareBacktestJobRunner):
                raise BacktestReplayUnavailableError(
                    "frozen backtest replay is unavailable"
                )
            return self._runner.run_replay_with_observability(
                replay.spec, replay.snapshot, observer
            )

        self._run_persisted_job(job_id, replay.spec, execute)

    def _run_persisted_job(
        self,
        job_id: str,
        spec: BacktestRunSpec,
        execute: Callable[[_JobObservabilitySink], BacktestResultView],
    ) -> None:
        if not self._store.mark_backtest_job_running(job_id):
            return
        observer = _JobObservabilitySink(self._store, job_id, spec.policy_hash)
        try:
            result = execute(observer)
        except BacktestDataError:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="market_data_unavailable",
                    stage="data",
                    message=(
                        "Historical market data is unavailable for "
                        f"{spec.ticker} and {spec.benchmark} in the requested window."
                    ),
                ).model_dump_json(),
            )
            return
        except BacktestInsufficientHistoryError:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="insufficient_history",
                    stage="data",
                    message="Historical data is insufficient for the frozen policy",
                ).model_dump_json(exclude_none=True),
            )
            return
        except BacktestDecisionError as error:
            safe_failure = _safe_decision_failure(error)
            try:
                observer.record_failure(error)
            except Exception:  # noqa: BLE001
                self._store.fail_backtest_job(
                    job_id,
                    BacktestJobError(
                        code="backtest_failed",
                        stage="persistence",
                        message="Backtest evidence could not be persisted",
                    ).model_dump_json(exclude_none=True),
                )
                return
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code=safe_failure.code,
                    stage=safe_failure.stage,
                    decision_date=safe_failure.decision_date,
                    attempt=safe_failure.attempt,
                    message=safe_failure.message,
                ).model_dump_json(exclude_none=True),
            )
            return
        except BacktestObservabilityError:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="backtest_failed",
                    stage="persistence",
                    message="Backtest evidence could not be persisted",
                ).model_dump_json(exclude_none=True),
            )
            return
        except BacktestReplayUnavailableError:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="storage_corrupt",
                    stage="replay",
                    message="Frozen backtest replay is unavailable",
                ).model_dump_json(exclude_none=True),
            )
            return
        except Exception:  # noqa: BLE001
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="execution_failed",
                    stage="execution",
                    message="Backtest execution failed",
                ).model_dump_json(exclude_none=True),
            )
            return
        completed_job = self._store.get_backtest_job(job_id)
        if completed_job is None or completed_job.input_snapshot_hash is None:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="backtest_failed",
                    stage="snapshot",
                    message="Backtest input snapshot is unavailable",
                ).model_dump_json(exclude_none=True),
            )
            return
        try:
            snapshot = self._store.get_backtest_input_snapshot(
                completed_job.input_snapshot_hash
            )
            if snapshot is None:
                raise BacktestDataError("frozen backtest snapshot is invalid")
            target_history, _ = _replay_snapshot_frames(snapshot, spec)
        except (BacktestDataError, RuntimeError):
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="backtest_failed",
                    stage="snapshot",
                    message="Backtest input snapshot is unavailable",
                ).model_dump_json(exclude_none=True),
            )
            return
        stored_decisions = _stored_backtest_decisions(self._store, job_id)
        if stored_decisions is None:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="backtest_failed",
                    stage="persistence",
                    message="Backtest evidence could not be persisted",
                ).model_dump_json(exclude_none=True),
            )
            return
        result = result.model_copy(
            update={
                "config": result.config.model_copy(
                    update=_snapshot_bound_config(
                        spec,
                        target_history,
                        data_snapshot_hash=completed_job.input_snapshot_hash,
                        account_id=result.config.account_id,
                    ).model_dump()
                ),
                "decisions": stored_decisions,
            }
        )
        result = _with_bound_result_provenance(
            spec,
            result,
            data_snapshot_hash=completed_job.input_snapshot_hash,
        )
        self._store.complete_backtest_job(job_id, result.model_dump_json())


def default_backtest_job_service(store: ContextStore) -> BacktestJobService:
    return BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(),
        llm_available=bool(getenv("OPENAI_API_KEY")),
        structured_output_supported=_configured_structured_output_supported,
    )


def _configured_structured_output_supported(model: str) -> bool:
    base_url = (getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").lower()
    if not base_url.startswith("https://api.openai.com/"):
        return False
    return model.lower().startswith(("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4"))


def _verified_completed_result(
    job: BacktestJobRecord,
    store: ContextStore,
    decisions: list[BacktestDecisionView],
) -> tuple[BacktestResultView, BacktestInputSnapshotRecord | None] | None:
    if job.result_json is None:
        return None
    try:
        result = BacktestResultView.model_validate_json(job.result_json)
    except ValidationError:
        return None
    if job.contract_version == 0:
        return (
            result.model_copy(
                update={
                    "warnings": [*result.warnings, "legacy_result_unverified"],
                }
            ),
            None,
        )
    if (
        job.contract_version != 1
        or job.run_spec_json is None
        or job.input_snapshot_hash is None
    ):
        return None
    try:
        snapshot = store.get_backtest_input_snapshot(job.input_snapshot_hash)
    except RuntimeError:
        return None
    if snapshot is None:
        return None
    try:
        spec = BacktestRunSpec.model_validate_json(job.run_spec_json)
        target_history, _ = _replay_snapshot_frames(snapshot, spec)
    except (BacktestDataError, ValidationError):
        return None
    if not _request_matches_spec(job.request_json, spec):
        return None
    expected_config = _snapshot_bound_config(
        spec,
        target_history,
        data_snapshot_hash=snapshot.content_hash,
        account_id=result.config.account_id,
    )
    if result.config != expected_config:
        return None
    if (
        result.provenance.strategy_snapshot_hash != spec.strategy_snapshot_hash
        or result.provenance.policy_hash != spec.policy_hash
        or result.provenance.data_snapshot_hash != job.input_snapshot_hash
    ):
        return None
    if result.decisions != decisions:
        return None
    try:
        canonical_result_hash = _canonical_economic_result_hash(
            spec,
            result,
            data_snapshot_hash=job.input_snapshot_hash,
        )
    except (TypeError, ValueError):
        return None
    if canonical_result_hash != result.provenance.canonical_result_hash:
        return None
    return result, snapshot


def _storage_corrupt_response(job_id: str) -> BacktestJobResponse:
    return BacktestJobResponse(
        id=job_id,
        status="failed",
        progress=BacktestProgressView(),
        decisions=[],
        error=BacktestJobError(
            code="storage_corrupt", message="Backtest result is unavailable"
        ),
        created_at="",
        updated_at="",
    )


def _to_response(job: BacktestJobRecord, store: ContextStore) -> BacktestJobResponse:
    request = _backtest_request_from_json(job.request_json)
    config = _backtest_config_from_spec_json(job.run_spec_json)
    result: BacktestJobResult | None = None
    error: BacktestJobError | None = None
    status: BacktestJobStatus = job.status
    progress = _backtest_progress_from_json(job.progress_json)
    stored_decisions = _stored_backtest_decisions(store, job.id)
    decisions = stored_decisions or []
    if stored_decisions is None:
        status = "failed"
        error = BacktestJobError(
            code="storage_corrupt", message="Backtest result is unavailable"
        )
    else:
        match job.status:
            case "completed":
                verified = _verified_completed_result(job, store, stored_decisions)
                if verified is None:
                    status = "failed"
                    decisions = []
                    error = BacktestJobError(
                        code="storage_corrupt", message="Backtest result is unavailable"
                    )
                else:
                    persisted_result, snapshot = verified
                    config = persisted_result.config
                    result = _public_backtest_result(persisted_result, snapshot)
            case "failed":
                if job.error_json is not None:
                    try:
                        error = BacktestJobError.model_validate_json(job.error_json)
                    except ValidationError:
                        error = BacktestJobError(
                            code="storage_corrupt",
                            message="Backtest failure is unavailable",
                        )
                else:
                    error = BacktestJobError(
                        code="storage_corrupt",
                        message="Backtest failure is unavailable",
                    )
            case "pending" | "running":
                pass
    return BacktestJobResponse(
        id=job.id,
        status=status,
        request=request,
        config=config,
        progress=progress,
        decisions=decisions,
        result=result,
        error=error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _stored_backtest_decisions(
    store: ContextStore, job_id: str
) -> list[BacktestDecisionView] | None:
    try:
        return [
            BacktestDecisionView(
                sequence=decision.sequence,
                signal_date=decision.signal_date,
                execution_date=decision.execution_date,
                status=decision.status,
                attempts=decision.attempts,
                target_position_pct=decision.target_position_pct,
                confidence=decision.confidence,
                action=decision.action,
                rationale=decision.rationale,
                feature_hash=decision.feature_hash,
                policy_hash=decision.policy_hash,
                error_code=(
                    _safe_decision_error_code(decision.error_code)
                    if decision.error_code is not None
                    else None
                ),
                error_stage=(
                    _safe_decision_error_stage(decision.error_stage)
                    if decision.error_stage is not None
                    else None
                ),
            )
            for decision in store.get_backtest_decisions(job_id)
        ]
    except (RuntimeError, ValueError, ValidationError):
        return None


def _backtest_request_from_json(request_json: str) -> BacktestRequest | None:
    try:
        return BacktestRequest.model_validate_json(request_json)
    except ValidationError:
        return None


def _request_matches_spec(request_json: str, spec: BacktestRunSpec) -> bool:
    try:
        request = BacktestRequest.model_validate_json(request_json)
    except ValidationError:
        return False
    return request == BacktestRequest(
        strategy_id=spec.strategy_id,
        ticker=spec.ticker,
        date_from=spec.date_from,
        date_to=spec.date_to,
        frequency=spec.run_frequency,
        benchmark=spec.benchmark,
        mode=spec.mode,
    )


def _snapshot_bound_config(
    spec: BacktestRunSpec,
    target_history: pd.DataFrame,
    *,
    data_snapshot_hash: str,
    account_id: str,
) -> BacktestConfigView:
    provenance = target_history.attrs.get("backtest_data_provenance")
    if not isinstance(provenance, dict):
        raise BacktestDataError("frozen backtest snapshot has no data provenance")
    target = target_history.loc[spec.date_from.isoformat() : spec.date_to.isoformat()]
    if target.empty:
        raise BacktestDataError("frozen backtest snapshot has no target window")
    return BacktestConfigView(
        ticker=spec.ticker,
        start_date=spec.date_from.isoformat(),
        end_date=spec.date_to.isoformat(),
        frequency=spec.run_frequency,
        benchmark_symbol=spec.benchmark,
        strategy_id=spec.strategy_id,
        account_id=account_id,
        mode=spec.mode.value,
        agent_model=(
            spec.policy.policy.model
            if isinstance(spec.policy.policy, ExperimentalAgentPolicy)
            else None
        ),
        strategy_snapshot_hash=spec.strategy_snapshot_hash,
        policy_hash=spec.policy_hash,
        data_snapshot_hash=data_snapshot_hash,
        engine_version=spec.engine_version,
        strategy_execution_frequency=spec.strategy_execution_frequency,
        run_frequency=spec.run_frequency,
        initial_capital=spec.broker_config.initial_cash,
        commission_rate=spec.broker_config.commission_rate,
        commission_bps=spec.broker_config.commission_rate * 10_000,
        slippage_rate=spec.broker_config.slippage_rate,
        slippage_bps=spec.broker_config.slippage_rate * 10_000,
        execution_timing=spec.broker_config.execution_timing,
        max_position_pct=spec.broker_config.max_position_pct,
        allow_short=spec.broker_config.allow_short,
        provider_adjustment_mode="auto_adjusted_prices_v1",
        corporate_actions_mode=str(provenance["corporate_actions_mode"]),
        data_provider=str(provenance["provider"]),
        data_provider_version=str(provenance["library_version"]),
        data_interval="1d",
        data_auto_adjust=bool(provenance["auto_adjust"]),
        data_actions=bool(provenance["actions"]),
        data_end_exclusive=str(provenance["end_exclusive"]),
        data_lookback_days=int(provenance["lookback_days"]),
        data_provider_buffer_days=int(provenance["provider_buffer_days"]),
        data_provider_end_semantics="exclusive",
        data_provider_timezone=str(provenance["provider_timezone"]),
        data_timezone_normalization="exchange_session_date_to_UTC_midnight",
        warmup_bars=int(provenance["warmup_bars"]),
        risk_free_rate=0.0,
        periods_per_year=252,
        max_drawdown_limit_pct=spec.max_drawdown_limit_pct,
        max_drawdown_limit_enforced=spec.max_drawdown_limit_enforced,
        evaluation_bar_count=len(target),
        sample_first_date=str(target.index[0])[:10],
        sample_last_date=str(target.index[-1])[:10],
    )


def _backtest_config_from_spec_json(
    run_spec_json: str | None,
) -> BacktestConfigView | None:
    if run_spec_json is None:
        return None
    try:
        spec = BacktestRunSpec.model_validate_json(run_spec_json)
    except ValidationError:
        return None
    return BacktestConfigView(
        ticker=spec.ticker,
        start_date=spec.date_from.isoformat(),
        end_date=spec.date_to.isoformat(),
        benchmark_symbol=spec.benchmark,
        frequency=spec.run_frequency,
        strategy_id=spec.strategy_id,
        engine_version=spec.engine_version,
        mode=spec.mode.value,
        agent_model=(
            spec.policy.policy.model
            if isinstance(spec.policy.policy, ExperimentalAgentPolicy)
            else None
        ),
        strategy_snapshot_hash=spec.strategy_snapshot_hash,
        policy_hash=spec.policy_hash,
        strategy_execution_frequency=spec.strategy_execution_frequency,
        run_frequency=spec.run_frequency,
        initial_capital=spec.broker_config.initial_cash,
        commission_rate=spec.broker_config.commission_rate,
        commission_bps=spec.broker_config.commission_rate * 10_000,
        slippage_rate=spec.broker_config.slippage_rate,
        slippage_bps=spec.broker_config.slippage_rate * 10_000,
        execution_timing=spec.broker_config.execution_timing,
        max_position_pct=spec.broker_config.max_position_pct,
        allow_short=spec.broker_config.allow_short,
        max_drawdown_limit_pct=spec.max_drawdown_limit_pct,
        max_drawdown_limit_enforced=spec.max_drawdown_limit_enforced,
    )


def _public_backtest_result(
    result: BacktestResultView,
    snapshot: BacktestInputSnapshotRecord | None,
) -> BacktestJobResult:
    return BacktestJobResult(
        outcome=result.outcome,
        warnings=result.warnings,
        no_trade_reasons=result.no_trade_reasons,
        metrics=result.summary,
        equity=result.series,
        orders=result.orders,
        fills=result.executions,
        closed_trades=result.closed_trades,
        end_position=result.end_position,
        snapshot=(
            BacktestSnapshotEvidenceView(
                compressed_bytes=snapshot.compressed_bytes,
                uncompressed_bytes=snapshot.uncompressed_bytes,
            )
            if snapshot is not None
            else None
        ),
        provenance=result.provenance,
    )


def _backtest_progress_from_json(progress_json: str | None) -> BacktestProgressView:
    if progress_json is None:
        return BacktestProgressView()
    try:
        return BacktestProgressView.model_validate_json(progress_json)
    except ValidationError:
        return BacktestProgressView()
