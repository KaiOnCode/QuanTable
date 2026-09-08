"""ContextStore — persistent context layer for Agentic-Quant.

Implements the M1 module from WORKLOAD_GAP_ANALYSIS.md.
Provides SQLite-backed storage for sessions, reports, decisions,
trades, approvals, and events per the database layout in docs/architecture.md.
"""

from storage.store import ContextStore, get_store

__all__ = ["ContextStore", "get_store"]
