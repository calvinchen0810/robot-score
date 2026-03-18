from pydantic import BaseModel
from typing import Optional


class SeriesCreate(BaseModel):
    name: str

class SeriesOut(BaseModel):
    id: int
    name: str
    is_active: bool
    class Config:
        from_attributes = True

class GameCreate(BaseModel):
    name: str
    series_id: int

class GameOut(BaseModel):
    id: int
    name: str
    series_id: int
    is_active: bool
    status: str = "stopped"
    class Config:
        from_attributes = True

class TeamCreate(BaseModel):
    name: str
    game_id: int

class TeamOut(BaseModel):
    id: int
    name: str
    game_id: int
    class Config:
        from_attributes = True

class ScoreButtonCreate(BaseModel):
    label: str
    image_url: Optional[str] = None
    points: int = 1
    max_clicks: Optional[int] = None
    max_clicks_game: Optional[int] = None
    display_order: int = 0
    series_id: int

class ScoreButtonUpdate(BaseModel):
    label: Optional[str] = None
    image_url: Optional[str] = None
    points: Optional[int] = None
    max_clicks: Optional[int] = None
    max_clicks_game: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None

class ScoreButtonOut(BaseModel):
    id: int
    label: str
    image_url: Optional[str]
    points: int
    max_clicks: Optional[int]
    max_clicks_game: Optional[int]
    display_order: int
    is_active: bool
    series_id: int
    class Config:
        from_attributes = True

class ScoreAction(BaseModel):
    team_id: int
    button_id: int
    delta: int  # +1 or -1

class TeamScoreOut(BaseModel):
    id: int
    team_id: int
    button_id: int
    clicks: int
    class Config:
        from_attributes = True

class TeamScoreManual(BaseModel):
    team_id: int
    button_id: int
    clicks: int
