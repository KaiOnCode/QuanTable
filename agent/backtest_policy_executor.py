from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from os import getenv
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.backtest_errors import BacktestDecisionError
from agent.backtest_policy import BacktestPolicySnapshot, ExperimentalAgentPolicy
from agent.backtest_policy import BacktestMode, BacktestRunSpec
from broker.backtest_runner import BacktestTargetDecision
from storage.strategy_policy import MomentumPolicy, SmaCrossoverPolicy


class PointInTimeFeatureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of: str
    closes: tuple[float, ...]

    @property
    def feature_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal["BUY", "SELL", "HOLD"]
    target_position_pct: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)
    feature_hash: str
    attempts: int = Field(ge=1, le=3)


class PositionTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal["BUY", "SELL", "HOLD"]
    delta_position_pct: float
    order_required: bool


def derive_position_transition(
    current_position_pct: float,
    target_position_pct: float,
    *,
    max_position_pct: float,
) -> PositionTransition:
    if not all(
        math.isfinite(value)
        for value in (current_position_pct, target_position_pct, max_position_pct)
    ):
        raise ValueError("position percentages must be finite")
    if current_position_pct < 0 or target_position_pct < 0:
        raise ValueError("backtest targets are long-only")
    if target_position_pct > max_position_pct:
        raise ValueError("target exceeds Strategy maximum position")
    delta = target_position_pct - current_position_pct
    if math.isclose(delta, 0.0, abs_tol=1e-9):
        return PositionTransition(
            action="HOLD", delta_position_pct=0.0, order_required=False
        )
    return PositionTransition(
        action="BUY" if delta > 0 else "SELL",
        delta_position_pct=delta,
        order_required=True,
    )


class BacktestPolicyExecutor:
    def __init__(self, snapshot: BacktestPolicySnapshot) -> None:
        if isinstance(snapshot.policy, ExperimentalAgentPolicy):
            raise ValueError("deterministic executor requires a quant policy")
        self._snapshot = snapshot

    def decide(
        self,
        features: PointInTimeFeatureSnapshot,
        *,
        current_position_pct: float,
    ) -> PolicyDecision:
        policy = self._snapshot.policy
        match policy:
            case MomentumPolicy():
                target, rationale = self._momentum_target(
                    policy, features, current_position_pct
                )
            case SmaCrossoverPolicy():
                target, rationale = self._sma_target(policy, features)
            case _:
                raise AssertionError("unreachable policy variant")
        transition = derive_position_transition(
            current_position_pct,
            target,
            max_position_pct=policy.target_position_pct * 100,
        )
        return PolicyDecision(
            action=transition.action,
            target_position_pct=target,
            confidence=1.0,
            rationale=rationale,
            feature_hash=features.feature_hash,
            attempts=1,
        )

    @staticmethod
    def _momentum_target(
        policy: MomentumPolicy,
        features: PointInTimeFeatureSnapshot,
        current_position_pct: float,
    ) -> tuple[float, str]:
        required = policy.lookback_bars + 1
        if len(features.closes) < required:
            raise ValueError("momentum features are not ready")
        base = features.closes[-required]
        if base <= 0:
            raise ValueError("momentum base close must be positive")
        momentum = features.closes[-1] / base - 1
        if momentum >= policy.entry_threshold:
            return policy.target_position_pct * 100, "momentum_entry"
        if momentum <= policy.exit_threshold:
            return 0.0, "momentum_exit"
        return min(current_position_pct, policy.target_position_pct * 100), (
            "momentum_hold_band"
        )

    @staticmethod
    def _sma_target(
        policy: SmaCrossoverPolicy, features: PointInTimeFeatureSnapshot
    ) -> tuple[float, str]:
        if len(features.closes) < policy.slow_window:
            raise ValueError("SMA features are not ready")
        fast = sum(features.closes[-policy.fast_window :]) / policy.fast_window
        slow = sum(features.closes[-policy.slow_window :]) / policy.slow_window
        if fast > slow:
            return policy.target_position_pct * 100, "sma_fast_above_slow"
        return 0.0, "sma_fast_not_above_slow"


class ExperimentalDecisionInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    features: PointInTimeFeatureSnapshot
    current_position_pct: float = Field(ge=0, le=100)
    max_position_pct: float = Field(gt=0, le=100)
    strategy_name: str
    strategy_description: str
    beliefs: tuple[str, ...]
    max_drawdown_limit_pct: float = Field(gt=0, le=100)
    model: str
    mode: Literal["agent_experiment"]


class ExperimentalStructuredDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_position_pct: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class ExperimentalDecisionProvider(Protocol):
    def decide(
        self, decision_input: ExperimentalDecisionInput, *, repair: bool
    ) -> Mapping[str, object]: ...


class ProviderTransientError(RuntimeError):
    pass


class ProviderPermanentError(RuntimeError):
    pass


class OpenAIStructuredDecisionProvider:
    def __init__(
        self,
        model: str,
        *,
        client_factory: Callable[[], object] | None = None,
    ) -> None:
        self._model = model
        self._client_factory = client_factory

    def decide(
        self, decision_input: ExperimentalDecisionInput, *, repair: bool
    ) -> Mapping[str, object]:
        from openai import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            OpenAI,
            RateLimitError,
        )

        client = (
            self._client_factory()
            if self._client_factory is not None
            else OpenAI(
                api_key=getenv("OPENAI_API_KEY") or "",
                base_url=getenv("OPENAI_API_BASE") or None,
            )
        )
        instruction = (
            "Return one long-only target position decision from the supplied "
            "point-in-time JSON. Never use information after features.as_of."
        )
        if repair:
            instruction += " Repair the prior schema failure and obey every bound."
        try:
            openai_client = cast(OpenAI, client)
            response = openai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": instruction},
                    {
                        "role": "user",
                        "content": decision_input.model_dump_json(),
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "backtest_target_position",
                        "strict": True,
                        "schema": ExperimentalStructuredDecision.model_json_schema(),
                    },
                },
                temperature=0,
            )
        except (APIConnectionError, APITimeoutError, RateLimitError) as error:
            raise ProviderTransientError from error
        except APIError as error:
            raise ProviderPermanentError from error
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            raise ProviderPermanentError("structured provider returned no choices")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise ProviderPermanentError("structured provider returned no message")
        content = getattr(message, "content", None)
        if not content:
            return {}
        if not isinstance(content, str):
            raise ProviderPermanentError("structured provider returned invalid content")
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class ExperimentalDecisionAdapter:
    def __init__(
        self,
        provider: ExperimentalDecisionProvider,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider = provider
        self._sleeper = sleeper

    def decide(
        self,
        policy: BacktestPolicySnapshot,
        decision_input: ExperimentalDecisionInput,
    ) -> PolicyDecision:
        if not isinstance(policy.policy, ExperimentalAgentPolicy):
            raise ValueError("experimental adapter requires an agent policy")
        schema_repair_used = False
        attempt = 0
        while attempt < 3:
            attempt += 1
            try:
                raw = self._provider.decide(decision_input, repair=schema_repair_used)
                structured = ExperimentalStructuredDecision.model_validate(raw)
            except ProviderTransientError as error:
                if attempt >= 3:
                    raise BacktestDecisionError(
                        code="decision_transient_exhausted",
                        stage="transient",
                        decision_date=decision_input.features.as_of,
                        attempt=attempt,
                    ) from error
                self._sleeper(0.25 * (2 ** (attempt - 1)))
                continue
            except ValidationError as error:
                if schema_repair_used or attempt >= 3:
                    raise BacktestDecisionError(
                        code="decision_schema_invalid",
                        stage="structured_output",
                        decision_date=decision_input.features.as_of,
                        attempt=attempt,
                    ) from error
                schema_repair_used = True
                continue
            except ProviderPermanentError as error:
                raise BacktestDecisionError(
                    code="provider_failed",
                    stage="provider",
                    decision_date=decision_input.features.as_of,
                    attempt=attempt,
                ) from error
            try:
                transition = derive_position_transition(
                    decision_input.current_position_pct,
                    structured.target_position_pct,
                    max_position_pct=decision_input.max_position_pct,
                )
            except ValueError as error:
                raise BacktestDecisionError(
                    code="decision_policy_invalid",
                    stage="policy",
                    decision_date=decision_input.features.as_of,
                    attempt=attempt,
                ) from error
            return PolicyDecision(
                action=transition.action,
                target_position_pct=structured.target_position_pct,
                confidence=structured.confidence,
                rationale=structured.rationale,
                feature_hash=decision_input.features.feature_hash,
                attempts=attempt,
            )
        raise AssertionError("bounded retry loop exhausted")


class BacktestRunDecisionExecutor:
    def __init__(
        self,
        spec: BacktestRunSpec,
        *,
        experimental_adapter: ExperimentalDecisionAdapter | None = None,
    ) -> None:
        self._spec = spec
        self._deterministic = (
            BacktestPolicyExecutor(spec.policy)
            if spec.mode is BacktestMode.DETERMINISTIC
            else None
        )
        self._deterministic_target_position_pct = 0.0
        if spec.mode is BacktestMode.AGENT_EXPERIMENT:
            policy = spec.policy.policy
            if not isinstance(policy, ExperimentalAgentPolicy):
                raise ValueError("experimental run requires an agent policy")
            self._experimental = experimental_adapter or ExperimentalDecisionAdapter(
                OpenAIStructuredDecisionProvider(policy.model)
            )
        else:
            self._experimental = None

    @property
    def minimum_close_count(self) -> int:
        policy = self._spec.policy.policy
        match policy:
            case MomentumPolicy(lookback_bars=lookback):
                return lookback + 1
            case SmaCrossoverPolicy(slow_window=window):
                return window
            case ExperimentalAgentPolicy():
                return 1
        raise AssertionError("unreachable policy variant")

    def reset_for_run(self) -> None:
        self._deterministic_target_position_pct = 0.0

    def decide(
        self,
        ticker: str,
        *,
        as_of: str,
        closes: tuple[float, ...],
        current_position_pct: float,
    ) -> BacktestTargetDecision:
        features = PointInTimeFeatureSnapshot(ticker=ticker, as_of=as_of, closes=closes)
        if self._deterministic is not None:
            decision = self._deterministic.decide(
                features,
                current_position_pct=self._deterministic_target_position_pct,
            )
            self._deterministic_target_position_pct = decision.target_position_pct
            action = derive_position_transition(
                current_position_pct,
                decision.target_position_pct,
                max_position_pct=self._spec.broker_config.max_position_pct * 100,
            ).action
        else:
            if self._experimental is None:
                raise AssertionError("experimental adapter is unavailable")
            policy = self._spec.policy.policy
            if not isinstance(policy, ExperimentalAgentPolicy):
                raise AssertionError("experimental policy is unavailable")
            decision = self._experimental.decide(
                self._spec.policy,
                ExperimentalDecisionInput(
                    ticker=ticker,
                    features=features,
                    current_position_pct=current_position_pct,
                    max_position_pct=self._spec.broker_config.max_position_pct * 100,
                    strategy_name=self._spec.strategy_name,
                    strategy_description=self._spec.strategy_description,
                    beliefs=self._spec.strategy_beliefs,
                    max_drawdown_limit_pct=self._spec.max_drawdown_limit_pct * 100,
                    model=policy.model,
                    mode="agent_experiment",
                ),
            )
            action = decision.action
        return BacktestTargetDecision(
            action=action,
            target_position_pct=decision.target_position_pct,
            confidence=decision.confidence,
            rationale=decision.rationale,
            feature_hash=decision.feature_hash,
            attempts=decision.attempts,
        )
