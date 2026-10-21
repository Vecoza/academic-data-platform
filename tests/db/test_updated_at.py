from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection, text

from tests.support import Factory

pytestmark = pytest.mark.db


def test_update_sets_updated_at_to_the_transaction_time(db: Connection, factory: Factory) -> None:
    created = datetime(2020, 1, 1, tzinfo=UTC)
    student_id = factory.student(created_at=created, updated_at=created)

    db.execute(
        text("UPDATE students SET city = 'Mostar' WHERE student_id = :id"), {"id": student_id}
    )

    created_at, updated_at, transaction_time = db.execute(
        text("SELECT created_at, updated_at, now() FROM students WHERE student_id = :id"),
        {"id": student_id},
    ).one()
    assert created_at == created
    assert updated_at == transaction_time
