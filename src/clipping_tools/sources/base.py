"""Source provider abstraction — every ingest backend implements this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import ClipCandidate


class SourceProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch_candidates(self, since: datetime, until: datetime | None = None) -> list[ClipCandidate]:
        """Return new clip candidates created in [since, until]."""

    @abstractmethod
    async def health(self) -> bool:
        """Cheap liveness/auth check."""