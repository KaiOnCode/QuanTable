from __future__ import annotations

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from os import getenv
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent.backtest_adapter import BacktestDecisionAdapter, BacktestDecisionError
from broker.backtest_data import (
    BacktestDataError,
    BacktestDataService,
    BacktestDatasetPreparer,
    HistoricalPriceLoader,
)
from broker.backtest_runner import BacktestAgent, BacktestRunner
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.views import BacktestResultView
from dataflow.store import MarketDataStore
from dataflow.history import DataServiceHistoryLoader
from storage.store import BacktestJobRecord, ContextStore

type BacktestJobStatus = Literal["pending", "running", "completed", "failed"]


class BacktestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str = Field(min_length=1, max_length=128)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    date_from: date
    date_to: date
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    benchmark: str = Field(default="SPY", pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")

    @model_validator(mode="after")
    def ordered_date_window(self) -> BacktestRequest:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class BacktestJobError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal[
        "agent_failed",
        "backtest_failed",
        "interrupted",
        "market_data_unavailable",
        "storage_corrupt",
    ]
    message: str


class BacktestJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    backtest_id: str
    status: BacktestJobStatus
    result: BacktestResultView | None = None
    error: BacktestJobError | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str


class BacktestJobRunner(Protocol):
    def run(self, request: BacktestRequest) -> BacktestResultView: ...


class _ScopedBacktestAgent:
    def __init__(
        self,
        *,
        as_of: str,
        broker: MockBrokerEngine,
        market_store: MarketDataStore,
    ) -> None:
        self._adapter = BacktestDecisionAdapter(
            data_service=BacktestDataService(as_of=as_of, market_store=market_store),
            broker=broker,
        )

    def run(
        self,
        ticker: str,
        *,
        date: str,
        as_of: str,
        current_position_pct: float,
        execution_enabled: bool,
        strategy_id: str,
        account_id: str,
        session_id: str,
    ) -> dict:
        return dict(
            self._adapter.run(
                ticker,
                date=date,
                as_of=as_of,
                current_position_pct=current_position_pct,
                execution_enabled=execution_enabled,
                strategy_id=strategy_id,
                account_id=account_id,
                session_id=session_id,
            )
        )


class ActiveBacktestJobRunner:
    def __init__(
        self,
        market_store: MarketDataStore | None = None,
        history_loader: HistoricalPriceLoader | None = None,
    ) -> None:
        self._market_store = market_store or MarketDataStore()
        self._history_loader = history_loader or DataServiceHistoryLoader(
            self._market_store
        )

    def run(self, request: BacktestRequest) -> BacktestResultView:
        dataset = BacktestDatasetPreparer(
            self._market_store,
            history_loader=self._history_loader,
        ).prepare(
            ticker=request.ticker,
            benchmark_symbol=request.benchmark,
            date_from=request.date_from.isoformat(),
            date_to=request.date_to.isoformat(),
        )
        runner = BacktestRunner(
            BrokerConfig(),
            scoped_agent_factory=self._scoped_agent_factory,
        )
        return runner.run(
            request.ticker,
            dataset.target,
            request.date_from.isoformat(),
            request.date_to.isoformat(),
            benchmark_df=dataset.benchmark,
            benchmark_symbol=request.benchmark,
            frequency=request.frequency,
            strategy_id=request.strategy_id,
        ).view

    def _scoped_agent_factory(
        self, as_of: str, broker: MockBrokerEngine
    ) -> BacktestAgent:
        return _ScopedBacktestAgent(
            as_of=as_of,
            broker=broker,
            market_store=self._market_store,
        )


class BacktestJobService:
    def __init__(
        self,
        *,
        store: ContextStore,
        runner: BacktestJobRunner,
        llm_available: bool = True,
        max_workers: int = 2,
    ) -> None:
        self._store = store
        self._runner = runner
        self._llm_available = llm_available
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="backtest-job",
        )

    @property
    def can_start(self) -> bool:
        return self._llm_available

    def create(self, request: BacktestRequest) -> BacktestJobResponse:
        job_id = uuid4().hex
        self._store.create_backtest_job(job_id, request.model_dump_json())
        self._executor.submit(self._run_job, job_id, request)
        response = self.get(job_id)
        if response is None:
            raise RuntimeError("backtest job disappeared after creation")
        return response

    def get(self, job_id: str) -> BacktestJobResponse | None:
        job = self._store.get_backtest_job(job_id)
        return _to_response(job) if job is not None else None

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

    def _run_job(self, job_id: str, request: BacktestRequest) -> None:
        if not self._store.mark_backtest_job_running(job_id):
            return
        try:
            result = self._runner.run(request)
        except BacktestDataError:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="market_data_unavailable",
                    message=(
                        "Historical market data is unavailable for "
                        f"{request.ticker} and {request.benchmark} in the requested window."
                    ),
                ).model_dump_json(),
            )
            return
        except BacktestDecisionError:
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="agent_failed",
                    message=(
                        "The backtest agent could not produce a valid structured decision."
                    ),
                ).model_dump_json(),
            )
            return
        except Exception:  # noqa: BLE001
            self._store.fail_backtest_job(
                job_id,
                BacktestJobError(
                    code="backtest_failed", message="Backtest failed"
                ).model_dump_json(),
            )
            return
        self._store.complete_backtest_job(job_id, result.model_dump_json())


def default_backtest_job_service(store: ContextStore) -> BacktestJobService:
    return BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(),
        llm_available=bool(getenv("OPENAI_API_KEY")),
    )


def _to_response(job: BacktestJobRecord) -> BacktestJobResponse:
    result = None
    error = None
    match job.status:
        case "completed":
            if job.result_json is None:
                error = BacktestJobError(
                    code="storage_corrupt", message="Backtest result is unavailable"
                )
            else:
                try:
                    result = BacktestResultView.model_validate_json(job.result_json)
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
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )
