"""Tests for retrying and auditable prospect refresh execution."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import ProspectRefreshRunRecord
from app.db.session import Base
from app.services.refresh_runner import run_refresh_with_retries


class FlakyProvider:
    """Provider that fails a configured number of times before succeeding."""

    def __init__(self, failures: int) -> None:
        """Set the number of initial failures."""
        self.failures = failures
        self.calls = 0

    def fetch(self, draft_year: int) -> list[dict[str, object]]:
        """Return no records after transient failures resolve."""
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary provider failure")
        return []


def test_refresh_runner_retries_and_audits_success() -> None:
    """Transient provider failures should be retried and marked succeeded."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = FlakyProvider(2)

    with Session(engine) as session:
        assert run_refresh_with_retries(session, 2027, [provider], 3, 0) == 0
        audit = session.query(ProspectRefreshRunRecord).one()
        assert provider.calls == 3
        assert audit.status == "succeeded"
        assert audit.attempts == 3


def test_refresh_runner_records_failure_after_attempt_limit() -> None:
    """Permanent provider failures should produce a failed audit row."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = FlakyProvider(5)

    with Session(engine) as session:
        try:
            run_refresh_with_retries(session, 2027, [provider], 2, 0)
            raise AssertionError("Expected provider failure")
        except RuntimeError:
            audit = session.query(ProspectRefreshRunRecord).one()
            assert audit.status == "failed"
            assert audit.attempts == 2