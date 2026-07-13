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
    BacktestConfigView,
    BacktestDecisionView,
    BacktestProgressView,
    BacktestProvenanceView,
    BacktestResultView,
)
from dataflow.store import MarketDataStore
from dataflow.history import DataServiceHistoryLoader
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
_SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")


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


class BacktestJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_id: str
    status: BacktestJobStatus
    result: BacktestResultView | None = None
    error: BacktestJobError | None = None
    progress: BacktestProgressView = Field(default_factory=BacktestProgressView)
    decisions: list[BacktestDecisionView] = Field(default_factory=list)
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str


class BacktestJobRunner(Protocol):
    def run(self, spec: BacktestRunSpec) -> BacktestResultView: ...


@runtime_checkable
class ObservabilityAwareBacktestJobRunner(Protocol):
    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
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
        runner = BacktestRunner(
            BrokerConfig(**spec.broker_config.model_dump()),
            decision_executor=BacktestRunDecisionExecutor(
                spec, experimental_adapter=self._experimental_adapter
            ),
        )
        result = runner.run(
            spec.ticker,
            dataset.target,
            spec.date_from.isoformat(),
            spec.date_to.isoformat(),
            benchmark_df=dataset.benchmark,
            benchmark_symbol=spec.benchmark,
            frequency=spec.run_frequency,
            strategy_id=spec.strategy_id,
            policy_hash=spec.policy_hash,
            observer=observer,
            history_df=dataset.target_history,
            snapshot_benchmark_df=dataset.benchmark_history,
        ).view
        warnings = [
            *result.warnings,
            "max_drawdown_limit_not_enforced",
            "capacity_model_not_modeled",
            "provider_adjusted_prices_are_synthetic",
            *_sample_size_warnings(
                evaluation_bar_count=len(dataset.target),
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
        canonical_result_hash = _canonical_economic_result_hash(
            spec, result, data_snapshot_hash=data_snapshot_hash
        )
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
            data_provider=str(
                dataset.target_history.attrs["backtest_data_provenance"]["provider"]
            ),
            data_provider_version=str(
                dataset.target_history.attrs["backtest_data_provenance"][
                    "library_version"
                ]
            ),
            data_interval="1d",
            data_auto_adjust=True,
            data_actions=False,
            data_end_exclusive=(spec.date_to + timedelta(days=1)).isoformat(),
            data_lookback_days=int(
                dataset.target_history.attrs["backtest_data_provenance"][
                    "lookback_days"
                ]
            ),
            data_provider_buffer_days=100,
            data_provider_end_semantics="exclusive",
            data_provider_timezone=str(
                dataset.target_history.attrs["backtest_data_provenance"][
                    "provider_timezone"
                ]
            ),
            data_timezone_normalization=("exchange_session_date_to_UTC_midnight"),
            warmup_bars=dataset.warmup_bar_count,
            risk_free_rate=0.0,
            periods_per_year=252,
            evaluation_bar_count=len(dataset.target),
            sample_first_date=str(dataset.target.index[0])[:10],
            sample_last_date=str(dataset.target.index[-1])[:10],
        )
        return result.model_copy(
            update={
                "outcome": (
                    "completed" if result.closed_trades else "completed_no_trades"
                ),
                "config": config,
                "warnings": warnings,
                "provenance": BacktestProvenanceView(
                    strategy_snapshot_hash=spec.strategy_snapshot_hash,
                    policy_hash=spec.policy_hash,
                    data_snapshot_hash=data_snapshot_hash,
                    canonical_result_hash=canonical_result_hash,
                ),
            }
        )


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
    data_snapshot_hash: str | None = None,
) -> str:
    payload = result.model_dump(mode="json", exclude={"provenance"})
    for record_type in ("trades", "executions", "closed_trades"):
        for record in payload.get(record_type, []):
            if isinstance(record, dict):
                for operational_field in (
                    "order_id",
                    "account_id",
                    "session_id",
                    "decision_id",
                ):
                    record.pop(operational_field, None)
    config = payload.get("config")
    if isinstance(config, dict):
        config.pop("account_id", None)
    for order in payload.get("orders", []):
        if isinstance(order, dict):
            order.pop("order_id", None)
    canonical = {
        "engine_version": spec.engine_version,
        "policy_hash": spec.policy_hash,
        "strategy_snapshot_hash": spec.strategy_snapshot_hash,
        "data_snapshot_hash": data_snapshot_hash or result.config.data_snapshot_hash,
        "economic_result": payload,
    }
    encoded = json.dumps(
        canonical,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


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
        runner: BacktestJobRunner | ObservabilityAwareBacktestJobRunner,
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

    def create(self, request: BacktestRequest) -> BacktestJobResponse:
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
        response = self.get(job_id)
        if response is None:
            raise RuntimeError("backtest job disappeared after creation")
        return response

    def _supports_structured_output(self, strategy: dict[str, object]) -> bool:
        capability = self._structured_output_supported
        if isinstance(capability, bool):
            return capability
        model = strategy.get("agent_model")
        return capability(model if isinstance(model, str) else "")

    def get(self, job_id: str) -> BacktestJobResponse | None:
        job = self._store.get_backtest_job(job_id)
        return _to_response(job, self._store) if job is not None else None

    def replay(self, job_id: str) -> BacktestReplayInput:
        job = self._store.get_backtest_job(job_id)
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
        snapshot = self._store.get_backtest_input_snapshot(job.input_snapshot_hash)
        if snapshot is None:
            raise BacktestReplayUnavailableError(
                "frozen backtest replay is unavailable"
            )
        return BacktestReplayInput(spec=spec, snapshot=snapshot)

    def trades_csv(self, job_id: str) -> str | None:
        job = self.get(job_id)
        if job is None or job.status != "completed" or job.result is None:
            return None
        output = io.StringIO(newline="")
        fields = (
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
        )
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for trade in job.result.trades:
            writer.writerow(
                {
                    "timestamp": trade.timestamp.isoformat(),
                    "ticker": trade.ticker,
                    "side": trade.side,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "fee": trade.fee,
                    "slippage": trade.slippage,
                    "trade_value": trade.trade_value,
                    "realized_pnl": trade.realized_pnl,
                    "cash_after": trade.cash_after,
                    "equity_after": trade.equity_after,
                }
            )
        return output.getvalue()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    def _run_job(self, job_id: str, spec: BacktestRunSpec) -> None:
        if not self._store.mark_backtest_job_running(job_id):
            return
        observer = _JobObservabilitySink(self._store, job_id, spec.policy_hash)
        try:
            if isinstance(self._runner, ObservabilityAwareBacktestJobRunner):
                result = self._runner.run_with_observability(spec, observer)
            else:
                result = self._runner.run(spec)
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
        except Exception:  # noqa: BLE001
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="backtest_failed", stage="runner", message="Backtest failed"
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


def _to_response(job: BacktestJobRecord, store: ContextStore) -> BacktestJobResponse:
    result = None
    error = None
    progress = _backtest_progress_from_json(job.progress_json)
    decisions = [
        BacktestDecisionView(
            sequence=decision.sequence,
            signal_date=decision.signal_date,
            execution_date=decision.execution_date,
            status=decision.status,
            attempts=decision.attempts,
            target_position_pct=decision.target_position_pct,
            confidence=decision.confidence,
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
        for decision in store.get_backtest_decisions(job.id)
    ]
    match job.status:
        case "completed":
            if job.result_json is None:
                error = BacktestJobError(
                    code="storage_corrupt", message="Backtest result is unavailable"
                )
            else:
                try:
                    result = BacktestResultView.model_validate_json(job.result_json)
                    if job.contract_version == 0:
                        result = result.model_copy(
                            update={
                                "warnings": [
                                    *result.warnings,
                                    "legacy_result_unverified",
                                ]
                            }
                        )
                except ValidationError:
                    error = BacktestJobError(
                        code="storage_corrupt", message="Backtest result is unavailable"
                    )
        case "failed":
            if job.error_json is not None:
                try:
                    error = BacktestJobError.model_validate_json(job.error_json)
                except ValidationError:
                    error = BacktestJobError(
                        code="storage_corrupt",
                        message="Backtest failure is unavailable",
                    )
        case "pending" | "running":
            pass
    return BacktestJobResponse(
        backtest_id=job.id,
        status=job.status,
        result=result,
        error=error,
        progress=progress,
        decisions=decisions,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


def _backtest_progress_from_json(progress_json: str | None) -> BacktestProgressView:
    if progress_json is None:
        return BacktestProgressView()
    try:
        return BacktestProgressView.model_validate_json(progress_json)
    except ValidationError:
        return BacktestProgressView()
