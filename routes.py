from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Series, Game, Team, ScoreButton, TeamScore
from schemas import (
    SeriesCreate, SeriesOut,
    GameCreate, GameOut,
    TeamCreate, TeamUpdate, TeamOut,
    ScoreButtonCreate, ScoreButtonUpdate, ScoreButtonOut,
    ScoreAction, TeamScoreOut, TeamScoreManual,
)

router = APIRouter(prefix="/api")


# ── Series ──────────────────────────────────────────────
@router.get("/series", response_model=List[SeriesOut])
def list_series(db: Session = Depends(get_db)):
    return db.query(Series).order_by(Series.id.desc()).all()


@router.post("/series", response_model=SeriesOut)
def create_series(data: SeriesCreate, db: Session = Depends(get_db)):
    s = Series(name=data.name)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.put("/series/{sid}/activate")
def activate_series(sid: int, db: Session = Depends(get_db)):
    db.query(Series).update({Series.is_active: False})
    s = db.query(Series).get(sid)
    if not s:
        raise HTTPException(404, "Series not found")
    s.is_active = True
    db.commit()
    return {"ok": True}


@router.put("/series/{sid}/deactivate")
def deactivate_series(sid: int, db: Session = Depends(get_db)):
    s = db.query(Series).get(sid)
    if not s:
        raise HTTPException(404, "Series not found")
    s.is_active = False
    # Stop all games in this series
    db.query(Game).filter(Game.series_id == sid).update({Game.is_active: False, Game.status: "stopped"})
    db.commit()
    return {"ok": True}


@router.delete("/series/{sid}")
def delete_series(sid: int, db: Session = Depends(get_db)):
    s = db.query(Series).get(sid)
    if not s:
        raise HTTPException(404, "Series not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ── Games ───────────────────────────────────────────────
@router.get("/series/{sid}/games", response_model=List[GameOut])
def list_games(sid: int, db: Session = Depends(get_db)):
    return db.query(Game).filter(Game.series_id == sid).order_by(Game.id).all()


@router.post("/games", response_model=GameOut)
def create_game(data: GameCreate, db: Session = Depends(get_db)):
    g = Game(name=data.name, series_id=data.series_id)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@router.put("/games/{gid}/activate")
def activate_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    # deactivate and stop all games in same series
    db.query(Game).filter(Game.series_id == game.series_id).update({Game.is_active: False, Game.status: "stopped"})
    game.is_active = True
    game.status = "running"
    db.commit()
    return {"ok": True}


@router.put("/games/{gid}/pause")
def pause_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    if game.status != "running":
        raise HTTPException(400, "Game is not running")
    game.status = "paused"
    db.commit()
    return {"ok": True}


@router.put("/games/{gid}/resume")
def resume_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    if game.status != "paused":
        raise HTTPException(400, "Game is not paused")
    game.status = "running"
    db.commit()
    return {"ok": True}


@router.put("/games/{gid}/stop")
def stop_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    game.status = "stopped"
    game.is_active = False
    db.commit()
    return {"ok": True}


@router.delete("/games/{gid}")
def delete_game(gid: int, db: Session = Depends(get_db)):
    g = db.query(Game).get(gid)
    if not g:
        raise HTTPException(404, "Game not found")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ── Teams ───────────────────────────────────────────────
@router.get("/games/{gid}/teams", response_model=List[TeamOut])
def list_teams(gid: int, db: Session = Depends(get_db)):
    return db.query(Team).filter(Team.game_id == gid).order_by(Team.name).all()


@router.post("/teams", response_model=TeamOut)
def create_team(data: TeamCreate, db: Session = Depends(get_db)):
    t = Team(name=data.name, game_id=data.game_id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.put("/teams/{tid}", response_model=TeamOut)
def update_team(tid: int, data: TeamUpdate, db: Session = Depends(get_db)):
    t = db.query(Team).get(tid)
    if not t:
        raise HTTPException(404, "Team not found")
    t.name = data.name
    db.commit()
    db.refresh(t)
    return t


@router.delete("/teams/{tid}")
def delete_team(tid: int, db: Session = Depends(get_db)):
    t = db.query(Team).get(tid)
    if not t:
        raise HTTPException(404, "Team not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ── Score Buttons ───────────────────────────────────────
@router.get("/series/{sid}/buttons", response_model=List[ScoreButtonOut])
def list_buttons(sid: int, db: Session = Depends(get_db)):
    return (
        db.query(ScoreButton)
        .filter(ScoreButton.series_id == sid)
        .order_by(ScoreButton.display_order, ScoreButton.id)
        .all()
    )


@router.post("/buttons", response_model=ScoreButtonOut)
def create_button(data: ScoreButtonCreate, db: Session = Depends(get_db)):
    b = ScoreButton(**data.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.put("/buttons/{bid}", response_model=ScoreButtonOut)
def update_button(bid: int, data: ScoreButtonUpdate, db: Session = Depends(get_db)):
    b = db.query(ScoreButton).get(bid)
    if not b:
        raise HTTPException(404, "Button not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/buttons/{bid}")
def delete_button(bid: int, db: Session = Depends(get_db)):
    b = db.query(ScoreButton).get(bid)
    if not b:
        raise HTTPException(404, "Button not found")
    db.delete(b)
    db.commit()
    return {"ok": True}


# ── Scoring ─────────────────────────────────────────────
@router.post("/score")
def update_score(data: ScoreAction, db: Session = Depends(get_db)):
    """Increment or decrement a team's click count for a button."""
    # Check that the game is running
    team = db.query(Team).get(data.team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    game = db.query(Game).get(team.game_id)
    if not game or game.status != "running":
        raise HTTPException(400, "Game is not running – scoring is disabled")

    btn = db.query(ScoreButton).get(data.button_id)
    if not btn:
        raise HTTPException(404, "Button not found")

    ts = (
        db.query(TeamScore)
        .filter(TeamScore.team_id == data.team_id, TeamScore.button_id == data.button_id)
        .first()
    )
    if not ts:
        ts = TeamScore(team_id=data.team_id, button_id=data.button_id, clicks=0)
        db.add(ts)
        db.flush()

    new_clicks = ts.clicks + data.delta
    if new_clicks < 0:
        new_clicks = 0
    # Check per-team limit
    if btn.max_clicks is not None and new_clicks > btn.max_clicks:
        raise HTTPException(400, f"Max clicks per team ({btn.max_clicks}) reached")
    # Check game-wide total limit (only teams in the same game)
    if btn.max_clicks_game is not None:
        game_team_ids = [t.id for t in db.query(Team).filter(Team.game_id == game.id).all()]
        total_clicks = (
            db.query(TeamScore)
            .filter(TeamScore.button_id == btn.id, TeamScore.team_id.in_(game_team_ids))
            .with_entities(TeamScore.clicks)
            .all()
        )
        total = sum(r.clicks for r in total_clicks) - ts.clicks + new_clicks
        if total > btn.max_clicks_game:
            raise HTTPException(400, f"Max total clicks for game ({btn.max_clicks_game}) reached")

    ts.clicks = new_clicks
    db.commit()

    # Compute game total for this button
    game_team_ids = [t.id for t in db.query(Team).filter(Team.game_id == game.id).all()]
    game_total = sum(
        r.clicks for r in
        db.query(TeamScore)
        .filter(TeamScore.button_id == btn.id, TeamScore.team_id.in_(game_team_ids))
        .with_entities(TeamScore.clicks)
        .all()
    )
    return {"clicks": ts.clicks, "points": ts.clicks * btn.points, "game_total": game_total}


@router.get("/teams/{tid}/scores")
def get_team_scores(tid: int, db: Session = Depends(get_db)):
    team = db.query(Team).get(tid)
    rows = db.query(TeamScore).filter(TeamScore.team_id == tid).all()
    result = {}

    # Compute game totals for all buttons
    game_totals = {}
    if team:
        game_team_ids = [t.id for t in db.query(Team).filter(Team.game_id == team.game_id).all()]
        all_scores = (
            db.query(TeamScore)
            .filter(TeamScore.team_id.in_(game_team_ids))
            .all()
        )
        for s in all_scores:
            game_totals[s.button_id] = game_totals.get(s.button_id, 0) + s.clicks

    for r in rows:
        result[r.button_id] = {
            "clicks": r.clicks,
            "points": r.clicks * r.button.points,
            "game_total": game_totals.get(r.button_id, r.clicks),
        }
    return result


# ── Dashboard data ──────────────────────────────────────
@router.get("/dashboard")
def dashboard_data(db: Session = Depends(get_db)):
    """Return active series, its active game ranking, and all-teams ranking."""
    series = db.query(Series).filter(Series.is_active == True).first()
    if not series:
        return {"series": None, "active_game": None, "game_ranking": [], "all_ranking": []}

    buttons = (
        db.query(ScoreButton)
        .filter(ScoreButton.series_id == series.id, ScoreButton.is_active == True)
        .all()
    )
    btn_map = {b.id: b for b in buttons}

    active_game = db.query(Game).filter(Game.series_id == series.id, Game.is_active == True).first()

    def calc_ranking(teams):
        ranking = []
        for t in teams:
            total = 0
            details = []
            for sc in t.scores:
                if sc.button_id in btn_map:
                    pts = sc.clicks * btn_map[sc.button_id].points
                    total += pts
                    details.append({
                        "button_label": btn_map[sc.button_id].label,
                        "clicks": sc.clicks,
                        "points": pts,
                    })
            ranking.append({
                "team_id": t.id,
                "team_name": t.name,
                "game_id": t.game_id,
                "game_name": t.game.name,
                "total_points": total,
                "details": details,
            })
        ranking.sort(key=lambda x: x["total_points"], reverse=True)
        return ranking

    game_ranking = []
    if active_game:
        teams = db.query(Team).filter(Team.game_id == active_game.id).all()
        game_ranking = calc_ranking(teams)

    all_teams = db.query(Team).join(Game).filter(Game.series_id == series.id).all()
    all_ranking = calc_ranking(all_teams)

    games = db.query(Game).filter(Game.series_id == series.id).order_by(Game.id).all()

    return {
        "series": {"id": series.id, "name": series.name},
        "active_game": {"id": active_game.id, "name": active_game.name, "status": active_game.status} if active_game else None,
        "game_ranking": game_ranking,
        "all_ranking": all_ranking,
        "games": [{"id": g.id, "name": g.name, "is_active": g.is_active, "status": g.status} for g in games],
        "buttons": [{"id": b.id, "label": b.label, "points": b.points} for b in buttons],
    }


# ── Active game info for client page ───────────────────
@router.get("/active")
def get_active(db: Session = Depends(get_db)):
    series = db.query(Series).filter(Series.is_active == True).first()
    if not series:
        return {"series": None}
    game = db.query(Game).filter(Game.series_id == series.id, Game.is_active == True).first()
    buttons = (
        db.query(ScoreButton)
        .filter(ScoreButton.series_id == series.id, ScoreButton.is_active == True)
        .order_by(ScoreButton.display_order, ScoreButton.id)
        .all()
    )
    return {
        "series": {"id": series.id, "name": series.name},
        "game": {"id": game.id, "name": game.name, "status": game.status} if game else None,
        "buttons": [
            {
                "id": b.id, "label": b.label, "image_url": b.image_url,
                "points": b.points, "max_clicks": b.max_clicks,
                "max_clicks_game": b.max_clicks_game,
            }
            for b in buttons
        ],
    }


# ── Admin: manage team scores manually ──────────────────
@router.put("/admin/score")
def admin_set_score(data: TeamScoreManual, db: Session = Depends(get_db)):
    ts = (
        db.query(TeamScore)
        .filter(TeamScore.team_id == data.team_id, TeamScore.button_id == data.button_id)
        .first()
    )
    if not ts:
        ts = TeamScore(team_id=data.team_id, button_id=data.button_id, clicks=0)
        db.add(ts)
    ts.clicks = max(0, data.clicks)
    db.commit()
    return {"ok": True}


@router.delete("/admin/teams/{tid}/scores")
def admin_reset_team_scores(tid: int, db: Session = Depends(get_db)):
    db.query(TeamScore).filter(TeamScore.team_id == tid).delete()
    db.commit()
    return {"ok": True}


@router.delete("/admin/games/{gid}/scores")
def admin_reset_game_scores(gid: int, db: Session = Depends(get_db)):
    teams = db.query(Team).filter(Team.game_id == gid).all()
    for t in teams:
        db.query(TeamScore).filter(TeamScore.team_id == t.id).delete()
    db.commit()
    return {"ok": True}
