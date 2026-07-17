"""Pydantic schemas for structured agent output.

TradingAgents pattern: Research Manager, Trader, Sentiment Analyst, and
Portfolio Manager use structured output for deterministic, parseable results.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SentimentReport(BaseModel):
    """Sentiment analyst structured output."""

    overall_band: Literal[
        "Bullish", "Mildly Bullish", "Neutral", "Mixed", "Mildly Bearish", "Bearish"
    ] = Field(description="Overall sentiment band")
    overall_score: float = Field(
        ge=0.0, le=10.0, description="Sentiment score 0-10 (10 = max bullish)"
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="Confidence in this assessment"
    )
    narrative: str = Field(description="One-paragraph narrative summary")


class InvestmentPlan(BaseModel):
    """Research Manager output — synthesizes Bull/Bear debate."""

    recommendation: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"] = Field(
        description="Investment recommendation"
    )
    rationale: str = Field(description="Key reasons for the recommendation")
    strategic_actions: list[str] = Field(
        description="2-4 strategic actions to take"
    )


class TradeProposal(BaseModel):
    """Trader output — concrete trading proposal from investment plan."""

    action: Literal["Buy", "Hold", "Sell"] = Field(description="Trading action")
    reasoning: str = Field(description="Trading rationale")
    entry_price: float | None = Field(None, description="Suggested entry price")
    stop_loss: float | None = Field(None, description="Stop-loss level")
    position_sizing: str = Field(description="Position sizing strategy description")


class RiskAssessment(BaseModel):
    """Risk analyst output — risk evaluation of trader proposal."""

    risk_level: Literal["Low", "Medium", "High", "Critical"] = Field(
        description="Overall risk level"
    )
    key_risks: list[str] = Field(description="Key identified risks")
    mitigations: list[str] = Field(description="Risk mitigation suggestions")
    agree_with_trader: bool = Field(description="Whether to agree with trader proposal")


class PortfolioDecision(BaseModel):
    """PM final decision — structured output."""

    action: Literal["BUY", "SELL", "HOLD"] = Field(description="Final trading action")
    target_position_pct: float = Field(
        ge=-100.0, le=100.0, description="Target position percentage"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Decision confidence score"
    )
    time_horizon: str = Field(description="Investment time horizon")
    executive_summary: str = Field(description="One-paragraph executive summary")
    price_target: float | None = Field(None, description="Price target if applicable")
    report: str = Field(description="Full human-readable report in Chinese")
