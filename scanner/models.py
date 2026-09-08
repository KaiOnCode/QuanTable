from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel, ConfigDict, model_validator


class ScanField(StrEnum):
    PRICE = "price"
    CHANGE_PCT = "change_pct"
    VOLUME = "volume"
    RSI14 = "rsi14"
    SMA20 = "sma20"
    SMA50 = "sma50"
    PE_RATIO = "pe_ratio"
    PB_RATIO = "pb_ratio"
    MARKET_CAP = "market_cap"
    SECTOR = "sector"


class ScanOperator(StrEnum):
    LESS_THAN = "<"
    GREATER_THAN = ">"
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN_OR_EQUAL = ">="
    EQUAL = "=="
    BETWEEN = "between"


class UniverseSource(StrEnum):
    MARKET_STORE = "market_store"
    STRATEGY = "strategy"
    WATCHLIST = "watchlist"


NUMERIC_FIELDS = frozenset(ScanField) - frozenset({ScanField.SECTOR})


class ScanCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: ScanField
    operator: ScanOperator
    value: float | str
    value2: float | str | None = None

    @model_validator(mode="after")
    def validate_semantics(self) -> ScanCondition:
        if self.field == ScanField.SECTOR:
            if self.operator != ScanOperator.EQUAL or not isinstance(self.value, str):
                raise ValueError("sector only supports string equality")
            if self.value2 is not None:
                raise ValueError("sector does not accept value2")
            return self
        if self.field not in NUMERIC_FIELDS or not isinstance(self.value, float):
            raise ValueError("numeric fields require a finite numeric value")
        if not isfinite(self.value):
            raise ValueError("numeric values must be finite")
        if self.field == ScanField.RSI14 and not 0 <= self.value <= 100:
            raise ValueError("rsi14 values must be between 0 and 100")
        if self.operator == ScanOperator.BETWEEN:
            if not isinstance(self.value2, float) or not isfinite(self.value2):
                raise ValueError("between requires a finite value2")
            if self.value > self.value2:
                raise ValueError("between lower bound must not exceed upper bound")
            if self.field == ScanField.RSI14 and not 0 <= self.value2 <= 100:
                raise ValueError("rsi14 values must be between 0 and 100")
        elif self.value2 is not None:
            raise ValueError("value2 is only valid for between")
        return self

    def display(self) -> str:
        if self.operator == ScanOperator.BETWEEN:
            return f"{self.field.value} between {self.value} and {self.value2}"
        return f"{self.field.value} {self.operator.value} {self.value}"


class SnapshotValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | str | None
    unit: str
    currency: str | None
    source: str | None
    as_of: str | None


class ScannerSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    price: SnapshotValue
    change_pct: SnapshotValue
    volume: SnapshotValue
    rsi14: SnapshotValue
    sma20: SnapshotValue
    sma50: SnapshotValue
    pe_ratio: SnapshotValue
    pb_ratio: SnapshotValue
    market_cap: SnapshotValue
    sector: SnapshotValue

    def value_for(self, field: ScanField) -> SnapshotValue:
        match field:
            case ScanField.PRICE:
                return self.price
            case ScanField.CHANGE_PCT:
                return self.change_pct
            case ScanField.VOLUME:
                return self.volume
            case ScanField.RSI14:
                return self.rsi14
            case ScanField.SMA20:
                return self.sma20
            case ScanField.SMA50:
                return self.sma50
            case ScanField.PE_RATIO:
                return self.pe_ratio
            case ScanField.PB_RATIO:
                return self.pb_ratio
            case ScanField.MARKET_CAP:
                return self.market_cap
            case ScanField.SECTOR:
                return self.sector


class TrackedTicker(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    provenance: tuple[UniverseSource, ...]


class ScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    match_score: float
    matched_conditions: tuple[ScanCondition, ...]
    snapshot: ScannerSnapshot
    provenance: tuple[UniverseSource, ...]
    source_dates: dict[str, str]


class ScanResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    universe: tuple[TrackedTicker, ...]
    results: tuple[ScanResult, ...]
    scanned_count: int
    matched_count: int
    missing_data_count: int
    warnings: tuple[str, ...]
    scanned_at: datetime
