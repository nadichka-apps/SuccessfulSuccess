"""Store the original AI suggestion beside the user-approved meeting."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_ai_suggestion"
down_revision = "0002_users_and_meeting_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("ai_suggestion", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "ai_suggestion")
