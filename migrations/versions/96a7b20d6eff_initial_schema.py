"""initial schema

Revision ID: 96a7b20d6eff
Revises: 
Create Date: 2026-03-31 14:56:26.809427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96a7b20d6eff'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("series"):
        op.create_table(
            "series",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime),
            sa.Column("is_active", sa.Boolean, default=True),
        )

    if not _table_exists("games"):
        op.create_table(
            "games",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
            sa.Column("is_active", sa.Boolean, default=False),
            sa.Column("status", sa.String(20), default="stopped"),
            sa.Column("duration_seconds", sa.Float, nullable=True),
            sa.Column("paused_remaining", sa.Float, nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime),
        )

    if not _table_exists("rounds"):
        op.create_table(
            "rounds",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
            sa.Column("round_number", sa.Integer, default=1),
            sa.Column("status", sa.String(20), default="stopped"),
            sa.Column("duration_seconds", sa.Float, nullable=True),
            sa.Column("paused_remaining", sa.Float, nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime),
        )

    if not _table_exists("teams"):
        op.create_table(
            "teams",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
            sa.Column("start_order", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime),
        )

    if not _table_exists("score_buttons"):
        op.create_table(
            "score_buttons",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("image_url", sa.String(500), nullable=True),
            sa.Column("points", sa.Integer, nullable=False, server_default="1"),
            sa.Column("max_clicks", sa.Integer, nullable=True),
            sa.Column("max_clicks_game", sa.Integer, nullable=True),
            sa.Column("display_order", sa.Integer, default=0),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        )

    if not _table_exists("team_scores"):
        op.create_table(
            "team_scores",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("button_id", sa.Integer, sa.ForeignKey("score_buttons.id"), nullable=False),
            sa.Column("round_id", sa.Integer, sa.ForeignKey("rounds.id"), nullable=True),
            sa.Column("clicks", sa.Integer, default=0),
        )

    if not _table_exists("songs"):
        op.create_table(
            "songs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("url", sa.String(500), nullable=False),
            sa.Column("display_order", sa.Integer, default=0),
            sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        )

    if not _table_exists("admin_settings"):
        op.create_table(
            "admin_settings",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(100), unique=True, nullable=False),
            sa.Column("value", sa.String(500), nullable=False),
        )

    # Backfill columns that may be missing in older databases
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if _table_exists("games"):
        game_cols = [c["name"] for c in insp.get_columns("games")]
        if "paused_remaining" not in game_cols:
            op.add_column("games", sa.Column("paused_remaining", sa.Float, nullable=True))

    if _table_exists("team_scores"):
        ts_cols = [c["name"] for c in insp.get_columns("team_scores")]
        if "round_id" not in ts_cols:
            op.add_column("team_scores", sa.Column("round_id", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_table("team_scores")
    op.drop_table("songs")
    op.drop_table("admin_settings")
    op.drop_table("score_buttons")
    op.drop_table("teams")
    op.drop_table("rounds")
    op.drop_table("games")
    op.drop_table("series")
