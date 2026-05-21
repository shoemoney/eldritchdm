"""Safety test fixtures — re-exposes the bootstrapped_db_with_repos fixture."""

from __future__ import annotations

# Import the fixture from persistence conftest so it's available here
from tests.persistence.conftest import bootstrapped_db, bootstrapped_db_with_repos

__all__ = ["bootstrapped_db", "bootstrapped_db_with_repos"]
