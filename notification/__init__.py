"""Notification channel adapters for market and agent alerts."""

from .channels import (
    ChannelResult,
    NotificationChannel,
    NotificationManager,
    build_manager,
)

__all__ = [
    "ChannelResult",
    "NotificationChannel",
    "NotificationManager",
    "build_manager",
]
