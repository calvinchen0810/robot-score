from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base


class Series(Base):
    __tablename__ = "series"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    games = relationship("Game", back_populates="series", cascade="all, delete-orphan")


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    series_id = Column(Integer, ForeignKey("series.id"), nullable=False)
    is_active = Column(Boolean, default=False)
    status = Column(String(20), default="stopped")  # stopped, running, paused
    created_at = Column(DateTime, default=datetime.utcnow)

    series = relationship("Series", back_populates="games")
    teams = relationship("Team", back_populates="game", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    game = relationship("Game", back_populates="teams")
    scores = relationship("TeamScore", back_populates="team", cascade="all, delete-orphan")


class ScoreButton(Base):
    __tablename__ = "score_buttons"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(100), nullable=False)
    image_url = Column(String(500), nullable=True)
    points = Column(Integer, nullable=False, default=1)
    max_clicks = Column(Integer, nullable=True)  # None = unlimited (per team)
    max_clicks_game = Column(Integer, nullable=True)  # None = unlimited (total across all teams in a game)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    series_id = Column(Integer, ForeignKey("series.id"), nullable=False)


class TeamScore(Base):
    __tablename__ = "team_scores"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    button_id = Column(Integer, ForeignKey("score_buttons.id"), nullable=False)
    clicks = Column(Integer, default=0)

    team = relationship("Team", back_populates="scores")
    button = relationship("ScoreButton")
