"""Simulation clock in its own schema, kept apart from the operational tables.

Revision ID: 006
Revises: 005
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE SCHEMA sim;

        CREATE TABLE sim.clock (
            clock_id        SMALLINT NOT NULL DEFAULT 1,
            simulated_date  DATE NOT NULL,
            seed            BIGINT NOT NULL,
            last_run_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_clock PRIMARY KEY (clock_id),
            CONSTRAINT ck_clock_single_row CHECK (clock_id = 1)
        );

        CREATE TRIGGER trg_clock_set_updated_at
            BEFORE UPDATE ON sim.clock
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE sim.clock;
        DROP SCHEMA sim;
    """)
