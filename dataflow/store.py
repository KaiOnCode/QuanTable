"""MarketDataStore — structured SQLite storage for market data.

Separates raw market data (OHLCV, fundamentals, news) from operational
data (sessions, decisions — handled by storage/store.py).

Design principles:
- (ticker, date) compound keys for natural dedup
- Point-in-time safe: all data has an as_of_date, no look-ahead
- Source attribution: every row tracks where it came from and when it was fetched
- FTS5 full-text search on news for semantic queries
- Data freshness tracking: know when each ticker's data was last updated
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "market_data.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class InvalidOHLCVDateError(ValueError):
    value: str

    def __str__(self) -> str:
        return f"OHLCV date must be an ISO trading date: {self.value!r}"


def _parse_ohlcv_date(row: dict) -> str:
    raw_value = row.get("date", row.get("ts", ""))
    value = str(raw_value)[:10]
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise InvalidOHLCVDateError(value) from error
    if parsed.isoformat() != value:
        raise InvalidOHLCVDateError(value)
    return value


class MarketDataStore:
    """SQLite storage for OHLCV, fundamentals, and news data.

    Usage:
        store = MarketDataStore()
        store.upsert_ohlcv("AAPL", ohlcv_rows)
        store.upsert_fundamentals("AAPL", "2024-03-15", fundamentals_dict)
        store.add_news_articles("AAPL", news_list)
        bars = store.get_ohlcv("AAPL", "2024-01-01", "2024-06-01")
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Schema ──────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as db:
            db.executescript("""
                -- OHLCV daily bars
                CREATE TABLE IF NOT EXISTS ohlcv (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    volume REAL,
                    source TEXT DEFAULT 'yfinance',
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (ticker, date)
                );
                CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker ON ohlcv(ticker);
                CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON ohlcv(date);

                -- Fundamentals snapshots (point-in-time)
                CREATE TABLE IF NOT EXISTS fundamentals (
                    ticker TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    pe REAL, pb REAL, ps REAL, eps REAL,
                    market_cap REAL,
                    gross_margin REAL, op_margin REAL, profit_margin REAL,
                    roe REAL, dividend_yield REAL,
                    revenue_growth REAL, eps_growth REAL,
                    raw_json TEXT DEFAULT '{}',
                    source TEXT DEFAULT 'yfinance',
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (ticker, as_of_date)
                );
                CREATE INDEX IF NOT EXISTS idx_fund_ticker ON fundamentals(ticker);
                """)
            db.execute(
                "DELETE FROM ohlcv WHERE date(date) IS NULL OR date(date) != date"
            )
            # Migrations: add columns that may not exist in older DBs
            # Must run outside executescript — if column already exists, silently skip
            for col in ("roe", "dividend_yield", "profit_margin"):
                try:
                    db.execute(f"ALTER TABLE fundamentals ADD COLUMN {col} REAL")
                except Exception:
                    pass  # column already exists
            db.executescript("""
                -- News articles
                CREATE TABLE IF NOT EXISTS news (
                    id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    source_name TEXT DEFAULT '',
                    url TEXT DEFAULT '',
                    published_at TEXT NOT NULL,
                    sentiment_score REAL,
                    fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_news_ticker ON news(ticker);
                CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at);

                -- FTS5 full-text search on news
                CREATE VIRTUAL TABLE IF NOT EXISTS news_fts USING fts5(
                    ticker, title, summary, content='news', content_rowid='rowid'
                );
                -- Triggers to keep FTS in sync
                CREATE TRIGGER IF NOT EXISTS news_fts_insert AFTER INSERT ON news BEGIN
                    INSERT INTO news_fts(rowid, ticker, title, summary)
                    VALUES (new.rowid, new.ticker, new.title, new.summary);
                END;
                CREATE TRIGGER IF NOT EXISTS news_fts_delete AFTER DELETE ON news BEGIN
                    INSERT INTO news_fts(news_fts, rowid, ticker, title, summary)
                    VALUES ('delete', old.rowid, old.ticker, old.title, old.summary);
                END;

                -- Data freshness tracker
                CREATE TABLE IF NOT EXISTS data_freshness (
                    ticker TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    last_fetched_at TEXT NOT NULL,
                    last_success_at TEXT,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    PRIMARY KEY (ticker, data_type)
                );

                -- Ticker metadata from YFinance info (one-time fetch, immutable)
                CREATE TABLE IF NOT EXISTS ticker_meta (
                    ticker TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    short_name TEXT DEFAULT '',
                    sector TEXT DEFAULT '',
                    industry TEXT DEFAULT '',
                    market TEXT DEFAULT '',
                    exchange TEXT DEFAULT '',
                    currency TEXT DEFAULT '',
                    country TEXT DEFAULT '',
                    fetched_at TEXT NOT NULL
                );
            """)

    # ── OHLCV ───────────────────────────────────────────────

    def upsert_ohlcv(
        self,
        ticker: str,
        rows: list[dict],
        source: str = "yfinance",
    ) -> int:
        """Insert or replace OHLCV rows. Returns count of rows written.

        Each row must have: date, open, high, low, close (volume optional).
        """
        now = _now()
        count = 0
        with self._conn() as db:
            for row in rows:
                db.execute(
                    """INSERT OR REPLACE INTO ohlcv
                       (ticker, date, open, high, low, close, volume, source, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ticker.upper(),
                        _parse_ohlcv_date(row),
                        row.get("open", row.get("o")),
                        row.get("high", row.get("h")),
                        row.get("low", row.get("l")),
                        row.get("close", row.get("c")),
                        row.get("volume", row.get("v")),
                        source,
                        now,
                    ),
                )
                count += 1
        self._touch_freshness(ticker, "ohlcv", success=True)
        return count

    def get_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str | None = None,
    ) -> list[dict]:
        """Get OHLCV bars in date range. Returns list of dicts sorted by date."""
        if end_date is None:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with self._conn() as db:
            rows = db.execute(
                """SELECT date, open, high, low, close, volume, source
                   FROM ohlcv
                   WHERE ticker = ? AND date >= ? AND date <= ?
                   ORDER BY date ASC""",
                (ticker.upper(), start_date, end_date),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_date(self, ticker: str) -> str | None:
        """Get the most recent date we have OHLCV data for."""
        with self._conn() as db:
            row = db.execute(
                "SELECT MAX(date) FROM ohlcv WHERE ticker = ?",
                (ticker.upper(),),
            ).fetchone()
        return row[0] if row and row[0] else None

    def list_known_tickers(self) -> list[str]:
        """Return the sorted distinct ticker union already present in cached tables."""
        with self._conn() as db:
            rows = db.execute(
                """SELECT ticker FROM ohlcv
                   UNION
                   SELECT ticker FROM fundamentals
                   UNION
                   SELECT ticker FROM ticker_meta
                   ORDER BY ticker ASC"""
            ).fetchall()
        return [str(row["ticker"]) for row in rows]

    # ── Fundamentals ────────────────────────────────────────

    def upsert_fundamentals(
        self,
        ticker: str,
        as_of_date: str,
        data: dict,
        source: str = "yfinance",
    ) -> None:
        """Store a fundamentals snapshot for a given date."""
        now = _now()
        ttm = data.get("ttm", {})
        growth = data.get("growth", {})
        with self._conn() as db:
            db.execute(
                """INSERT OR REPLACE INTO fundamentals
                   (ticker, as_of_date, pe, pb, ps, eps, market_cap,
                    gross_margin, op_margin, profit_margin,
                    roe, dividend_yield,
                    revenue_growth, eps_growth,
                    raw_json, source, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticker.upper(),
                    as_of_date[:10],
                    ttm.get("pe"),
                    ttm.get("pb"),
                    ttm.get("ps"),
                    ttm.get("eps"),
                    ttm.get("market_cap"),
                    ttm.get("gross_margin"),
                    ttm.get("op_margin"),
                    ttm.get("profit_margin"),
                    ttm.get("roe"),
                    ttm.get("dividend_yield"),
                    growth.get("rev_yoy"),
                    growth.get("eps_yoy"),
                    json.dumps(data, ensure_ascii=False),
                    source,
                    now,
                ),
            )
        self._touch_freshness(ticker, "fundamentals", success=True)

    def get_fundamentals(
        self,
        ticker: str,
        as_of_date: str | None = None,
    ) -> dict | None:
        """Get the most recent fundamentals snapshot. If as_of_date is given,
        get the snapshot closest to (but not after) that date (PIT-safe)."""
        with self._conn() as db:
            if as_of_date:
                row = db.execute(
                    """SELECT * FROM fundamentals
                       WHERE ticker = ? AND as_of_date <= ?
                       ORDER BY as_of_date DESC LIMIT 1""",
                    (ticker.upper(), as_of_date[:10]),
                ).fetchone()
            else:
                row = db.execute(
                    """SELECT * FROM fundamentals
                       WHERE ticker = ?
                       ORDER BY as_of_date DESC LIMIT 1""",
                    (ticker.upper(),),
                ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["raw_json"] = json.loads(d.get("raw_json", "{}"))
        return d

    # ── News ────────────────────────────────────────────────

    def add_news_articles(
        self,
        ticker: str,
        articles: list[dict],
    ) -> int:
        """Insert news articles with dedup by URL. Returns count of new articles."""
        now = _now()
        count = 0
        with self._conn() as db:
            for article in articles:
                article_id = article.get("id") or str(uuid.uuid4())
                url = article.get("url", "")
                # Skip if this URL already exists (dedup)
                if url:
                    existing = db.execute(
                        "SELECT 1 FROM news WHERE url = ? LIMIT 1", (url,)
                    ).fetchone()
                    if existing:
                        continue
                try:
                    db.execute(
                        """INSERT INTO news
                           (id, ticker, title, summary, source_name, url,
                            published_at, sentiment_score, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            article_id,
                            ticker.upper(),
                            article.get("title", ""),
                            article.get("summary", ""),
                            article.get("source", ""),
                            url,
                            article.get("published_at", now),
                            article.get("sentiment_score"),
                            now,
                        ),
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    continue  # duplicate id, skip
        self._touch_freshness(ticker, "news", success=True)
        return count

    def search_news(
        self,
        query: str,
        ticker: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search news articles. Returns ranked results."""
        with self._conn() as db:
            if ticker:
                rows = db.execute(
                    """SELECT n.* FROM news n
                       JOIN news_fts fts ON n.rowid = fts.rowid
                       WHERE news_fts MATCH ?
                       AND n.ticker = ?
                       ORDER BY rank LIMIT ?""",
                    (query, ticker.upper(), limit),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT n.* FROM news n
                       JOIN news_fts fts ON n.rowid = fts.rowid
                       WHERE news_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (query, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_news(
        self,
        ticker: str,
        window_days: int = 7,
    ) -> list[dict]:
        """Get recent news for a ticker."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime(
            "%Y-%m-%d"
        )
        with self._conn() as db:
            rows = db.execute(
                """SELECT * FROM news
                   WHERE ticker = ? AND published_at >= ?
                   ORDER BY published_at DESC LIMIT 50""",
                (ticker.upper(), cutoff),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_news_as_of(
        self,
        ticker: str,
        start_date: str,
        as_of_date: str,
    ) -> list[dict]:
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM news WHERE ticker = ? AND published_at >= ? "
                "AND published_at <= ? ORDER BY published_at DESC LIMIT 50",
                (
                    ticker.upper(),
                    start_date[:10],
                    as_of_date[:10] + "T23:59:59Z",
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    # ── Freshness ───────────────────────────────────────────

    def _touch_freshness(self, ticker: str, data_type: str, success: bool) -> None:
        now = _now()
        with self._conn() as db:
            if success:
                db.execute(
                    """INSERT OR REPLACE INTO data_freshness
                       (ticker, data_type, last_fetched_at, last_success_at, error_count, last_error)
                       VALUES (?, ?, ?, ?, 0, NULL)""",
                    (ticker.upper(), data_type, now, now),
                )
            else:
                db.execute(
                    """INSERT INTO data_freshness
                       (ticker, data_type, last_fetched_at, error_count)
                       VALUES (?, ?, ?, 1)
                       ON CONFLICT(ticker, data_type) DO UPDATE SET
                       last_fetched_at = excluded.last_fetched_at,
                       error_count = data_freshness.error_count + 1""",
                    (ticker.upper(), data_type, now),
                )

    def mark_error(self, ticker: str, data_type: str, error_msg: str) -> None:
        """Record a fetch failure for monitoring."""
        now = _now()
        with self._conn() as db:
            db.execute(
                """INSERT INTO data_freshness
                   (ticker, data_type, last_fetched_at, error_count, last_error)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(ticker, data_type) DO UPDATE SET
                   last_fetched_at = excluded.last_fetched_at,
                   error_count = data_freshness.error_count + 1,
                   last_error = excluded.last_error""",
                (ticker.upper(), data_type, now, error_msg),
            )

    def get_stale_tickers(self, data_type: str, max_age_hours: int = 24) -> list[str]:
        """Return tickers whose data is older than max_age_hours.
        Used by the DataCollector to prioritize refreshes."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        ).isoformat()
        with self._conn() as db:
            rows = db.execute(
                """SELECT ticker FROM data_freshness
                   WHERE data_type = ? AND last_success_at < ?
                   ORDER BY last_success_at ASC""",
                (data_type, cutoff),
            ).fetchall()
        return [r[0] for r in rows]

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return summary stats about stored data volume."""
        with self._conn() as db:
            ohlcv_count = db.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
            ohlcv_tickers = db.execute(
                "SELECT COUNT(DISTINCT ticker) FROM ohlcv"
            ).fetchone()[0]
            fund_count = db.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
            news_count = db.execute("SELECT COUNT(*) FROM news").fetchone()[0]
            latest_bar = db.execute("SELECT MAX(date) FROM ohlcv").fetchone()[0]
        return {
            "ohlcv_bars": ohlcv_count,
            "ohlcv_tickers": ohlcv_tickers,
            "fundamentals_snapshots": fund_count,
            "news_articles": news_count,
            "latest_ohlcv_date": latest_bar,
            "db_path": str(self.db_path),
            "db_size_mb": round(self.db_path.stat().st_size / (1024 * 1024), 2)
            if self.db_path.exists()
            else 0,
        }

    # ── Ticker Metadata ──────────────────────────────────────

    def upsert_ticker_meta(self, ticker: str, **fields: str) -> None:
        """Store metadata for a ticker. Accepts: name, short_name, sector,
        industry, market, exchange, currency, country. One-time fetch."""
        now = _now()
        cols = [
            "ticker",
            "name",
            "short_name",
            "sector",
            "industry",
            "market",
            "exchange",
            "currency",
            "country",
            "fetched_at",
        ]
        vals = [ticker.upper()] + [fields.get(c, "") for c in cols[1:-1]] + [now]
        with self._conn() as db:
            db.execute(
                f"INSERT OR REPLACE INTO ticker_meta ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                vals,
            )

    def get_ticker_meta(self, ticker: str) -> dict | None:
        """Get metadata for a ticker."""
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM ticker_meta WHERE ticker = ?", (ticker.upper(),)
            ).fetchone()
        return dict(row) if row else None

    def get_ticker_meta_batch(self, tickers: list[str]) -> dict[str, dict]:
        """Get metadata for multiple tickers at once."""
        if not tickers:
            return {}
        placeholders = ",".join("?" for _ in tickers)
        with self._conn() as db:
            rows = db.execute(
                f"SELECT * FROM ticker_meta WHERE ticker IN ({placeholders})",
                [t.upper() for t in tickers],
            ).fetchall()
        return {r["ticker"]: dict(r) for r in rows}

    # ── Internal ────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def close(self) -> None:
        pass  # SQLite connections are short-lived per-method call
