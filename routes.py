from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import hashlib
import secrets
import random

from database import get_db
from models import Series, Game, Team, ScoreButton, TeamScore, Song, AdminSetting
from schemas import (
    SeriesCreate, SeriesOut,
    GameCreate, GameUpdate, GameOut,
    TeamCreate, TeamUpdate, TeamOut,
    ScoreButtonCreate, ScoreButtonUpdate, ScoreButtonOut,
    ScoreAction, TeamScoreOut, TeamScoreManual,
    SongCreate, SongOut,
)

router = APIRouter(prefix="/api")

# ── Admin auth helpers ────────────────────────────────────
_DEFAULT_PASSWORD = "admin123"
_admin_tokens: set = set()

# Last draw event (in-memory, for dashboard animation)
_last_draw: dict = {}


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _ensure_admin_password(db: Session):
    """Create default admin password if not set."""
    row = db.query(AdminSetting).filter(AdminSetting.key == "admin_password").first()
    if not row:
        db.add(AdminSetting(key="admin_password", value=_hash_pw(_DEFAULT_PASSWORD)))
        db.commit()


def _require_admin(x_admin_token: Optional[str] = Header(None)):
    if not x_admin_token or x_admin_token not in _admin_tokens:
        raise HTTPException(401, "Unauthorized")


@router.post("/admin/login")
def admin_login(body: dict, db: Session = Depends(get_db)):
    _ensure_admin_password(db)
    password = body.get("password", "")
    row = db.query(AdminSetting).filter(AdminSetting.key == "admin_password").first()
    if not row or row.value != _hash_pw(password):
        raise HTTPException(401, "Wrong password")
    token = secrets.token_hex(32)
    _admin_tokens.add(token)
    return {"token": token}


@router.get("/admin/verify")
def admin_verify(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token and x_admin_token in _admin_tokens:
        return {"ok": True}
    raise HTTPException(401, "Unauthorized")


@router.put("/admin/password")
def admin_change_password(
    body: dict,
    db: Session = Depends(get_db),
    _auth=Depends(_require_admin),
):
    old_pw = body.get("old_password", "")
    new_pw = body.get("new_password", "")
    if not new_pw or len(new_pw) < 4:
        raise HTTPException(400, "New password must be at least 4 characters")
    _ensure_admin_password(db)
    row = db.query(AdminSetting).filter(AdminSetting.key == "admin_password").first()
    if not row or row.value != _hash_pw(old_pw):
        raise HTTPException(401, "Current password is wrong")
    row.value = _hash_pw(new_pw)
    db.commit()
    return {"ok": True}

@router.get("/admin/qr")
def get_qr_image(db: Session = Depends(get_db), _auth=Depends(_require_admin)):
    row = db.query(AdminSetting).filter(AdminSetting.key == 'qr_image').first()
    return {"qr_image": row.value if row else None}


@router.put("/admin/qr")
def set_qr_image(data: dict, db: Session = Depends(get_db), _auth=Depends(_require_admin)):
    url = data.get('qr_image') if isinstance(data, dict) else None
    if url is None:
        raise HTTPException(400, "qr_image is required")
    row = db.query(AdminSetting).filter(AdminSetting.key == 'qr_image').first()
    if row:
        row.value = url
    else:
        db.add(AdminSetting(key='qr_image', value=url))
    db.commit()
    return {"ok": True, "qr_image": url}


def _remaining(game):
    """Compute seconds remaining for a game timer. Returns None if no timer."""
    if game.duration_seconds is None:
        return None
    base = game.paused_remaining if game.paused_remaining is not None else game.duration_seconds
    if game.status == "running" and game.started_at:
        elapsed = (datetime.now(timezone.utc) - game.started_at.replace(tzinfo=timezone.utc)).total_seconds()
        return max(0, base - elapsed)
    if game.status == "paused":
        return max(0, base)
    return game.duration_seconds


def _check_auto_stop(game, db):
    """Auto-stop game if timer expired. Returns True if stopped."""
    if game.status != "running" or game.duration_seconds is None or not game.started_at:
        return False
    base = game.paused_remaining if game.paused_remaining is not None else game.duration_seconds
    elapsed = (datetime.now(timezone.utc) - game.started_at.replace(tzinfo=timezone.utc)).total_seconds()
    if elapsed >= base:
        game.status = "stopped"
        game.is_active = False
        game.started_at = None
        game.paused_remaining = None
        db.commit()
        return True
    return False


def _game_out(game):
    """Serialize a Game to GameOut-compatible dict."""
    return {
        "id": game.id,
        "name": game.name,
        "series_id": game.series_id,
        "is_active": game.is_active,
        "status": game.status,
        "duration_seconds": game.duration_seconds,
        "remaining_seconds": _remaining(game),
    }


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
@router.get("/series/{sid}/games")
def list_games(sid: int, db: Session = Depends(get_db)):
    games = db.query(Game).filter(Game.series_id == sid).order_by(Game.id).all()
    for g in games:
        _check_auto_stop(g, db)
    return [_game_out(g) for g in games]


@router.post("/games", response_model=GameOut)
def create_game(data: GameCreate, db: Session = Depends(get_db)):
    g = Game(name=data.name, series_id=data.series_id,
             duration_seconds=data.duration_seconds if data.duration_seconds and data.duration_seconds > 0 else None)
    db.add(g)
    db.commit()
    db.refresh(g)
    return _game_out(g)


@router.put("/games/{gid}")
def update_game(gid: int, data: GameUpdate, db: Session = Depends(get_db)):
    g = db.query(Game).get(gid)
    if not g:
        raise HTTPException(404, "Game not found")
    if data.name is not None:
        g.name = data.name
    if data.duration_seconds is not None:
        g.duration_seconds = data.duration_seconds if data.duration_seconds > 0 else None
    db.commit()
    return _game_out(g)


@router.put("/games/{gid}/open")
def open_game(gid: int, db: Session = Depends(get_db)):
    """Make game visible for team joining, but don't start scoring yet."""
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    # deactivate all other games in same series
    db.query(Game).filter(Game.series_id == game.series_id).update({Game.is_active: False, Game.status: "stopped", Game.started_at: None})
    game.is_active = True
    game.status = "stopped"
    game.paused_remaining = None
    db.commit()
    return {"ok": True}


@router.put("/games/{gid}/activate")
def activate_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    # If not already open, open it first
    if not game.is_active:
        db.query(Game).filter(Game.series_id == game.series_id).update({Game.is_active: False, Game.status: "stopped", Game.started_at: None})
        game.is_active = True
    game.status = "running"
    game.paused_remaining = None
    game.started_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.put("/games/{gid}/pause")
def pause_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    if game.status != "running":
        raise HTTPException(400, "Game is not running")
    # Save remaining time into paused_remaining (preserve original duration_seconds)
    if game.duration_seconds is not None and game.started_at:
        base = game.paused_remaining if game.paused_remaining is not None else game.duration_seconds
        elapsed = (datetime.now(timezone.utc) - game.started_at.replace(tzinfo=timezone.utc)).total_seconds()
        game.paused_remaining = max(0, base - elapsed)
    game.status = "paused"
    game.started_at = None
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
    game.started_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.put("/games/{gid}/stop")
def stop_game(gid: int, db: Session = Depends(get_db)):
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    game.status = "stopped"
    game.is_active = False
    game.paused_remaining = None
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
    if data.name is not None:
        t.name = data.name
    if data.start_order is not None:
        t.start_order = data.start_order if data.start_order > 0 else None
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


@router.post("/games/{gid}/randomize")
def randomize_start_order(gid: int, db: Session = Depends(get_db)):
    global _last_draw
    game = db.query(Game).get(gid)
    if not game:
        raise HTTPException(404, "Game not found")
    if game.status == "running":
        raise HTTPException(400, "Cannot randomize while game is running")
    teams = db.query(Team).filter(Team.game_id == gid).all()
    if not teams:
        raise HTTPException(400, "No teams in this game")
    orders = list(range(1, len(teams) + 1))
    random.shuffle(orders)
    for team, order in zip(teams, orders):
        team.start_order = order
    db.commit()
    results = [
        {"name": t.name, "start_order": o, "team_index": i}
        for i, (t, o) in enumerate(zip(teams, orders))
    ]
    _last_draw = {
        "game_id": gid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    return {"ok": True, "count": len(teams)}


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
    # Auto-stop if timer expired
    if _check_auto_stop(game, db):
        raise HTTPException(400, "Time is up – game has been stopped")

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

    team_scores = {r.button_id: r for r in rows}

    # Return data for ALL active buttons, not just ones the team has scored on
    if team:
        series_id = db.query(Game).get(team.game_id).series_id
        all_buttons = (
            db.query(ScoreButton)
            .filter(ScoreButton.series_id == series_id, ScoreButton.is_active == True)
            .all()
        )
        for b in all_buttons:
            ts = team_scores.get(b.id)
            result[b.id] = {
                "clicks": ts.clicks if ts else 0,
                "points": (ts.clicks if ts else 0) * b.points,
                "game_total": game_totals.get(b.id, 0),
            }
    else:
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
    if active_game:
        _check_auto_stop(active_game, db)

    def calc_ranking(teams):
        ranking = []
        for t in teams:
            total = 0
            scored = {}
            for sc in t.scores:
                if sc.button_id in btn_map:
                    pts = sc.clicks * btn_map[sc.button_id].points
                    total += pts
                    scored[sc.button_id] = {"clicks": sc.clicks, "points": pts}
            # Include all buttons, even those with 0 clicks
            details = []
            for b in buttons:
                sc_data = scored.get(b.id, {"clicks": 0, "points": 0})
                details.append({
                    "button_label": b.label,
                    "button_image": b.image_url,
                    "clicks": sc_data["clicks"],
                    "points": sc_data["points"],
                })
            # Tiebreaker: for same total points, compare clicks on buttons by display_order (higher order = higher priority)
            # Build a tuple of clicks ordered by display_order descending for lexicographic comparison
            tiebreaker = tuple(
                scored.get(b.id, {"clicks": 0})["clicks"]
                for b in sorted(buttons, key=lambda b: b.display_order, reverse=True)
            )
            ranking.append({
                "team_id": t.id,
                "team_name": t.name,
                "game_id": t.game_id,
                "game_name": t.game.name,
                "start_order": t.start_order,
                "total_points": total,
                "details": details,
                "_tiebreaker": tiebreaker,
            })
        ranking.sort(key=lambda x: (x["total_points"], x["_tiebreaker"]), reverse=True)
        for r in ranking:
            del r["_tiebreaker"]
        return ranking

    game_ranking = []
    if active_game:
        teams = db.query(Team).filter(Team.game_id == active_game.id).all()
        game_ranking = calc_ranking(teams)

    all_teams = db.query(Team).join(Game).filter(Game.series_id == series.id).all()
    all_ranking = calc_ranking(all_teams)

    games = db.query(Game).filter(Game.series_id == series.id).order_by(Game.id).all()

    songs = db.query(Song).filter(Song.series_id == series.id).order_by(Song.display_order, Song.id).all()

    # Consume draw event once: return it to the first dashboard poller after the admin triggered it,
    # then clear it so the animation doesn't repeatedly show for later visitors.
    draw_to_send = None
    global _last_draw
    if active_game and isinstance(_last_draw, dict) and _last_draw.get("game_id") == active_game.id:
        draw_to_send = _last_draw
        _last_draw = {}

    return {
        "series": {"id": series.id, "name": series.name},
        "active_game": {"id": active_game.id, "name": active_game.name, "status": active_game.status, "remaining_seconds": _remaining(active_game)} if active_game else None,
        "game_ranking": game_ranking,
        "all_ranking": all_ranking,
        "games": [{"id": g.id, "name": g.name, "is_active": g.is_active, "status": g.status} for g in games],
        "buttons": [{"id": b.id, "label": b.label, "points": b.points} for b in buttons],
        "songs": [{"id": s.id, "title": s.title, "url": s.url} for s in songs],
        "draw_event": draw_to_send,
        "qr_image": (db.query(AdminSetting).filter(AdminSetting.key == 'qr_image').first().value
                     if db.query(AdminSetting).filter(AdminSetting.key == 'qr_image').first() else None),
    }


# ── Active game info for client page ───────────────────
@router.get("/active")
def get_active(db: Session = Depends(get_db)):
    series = db.query(Series).filter(Series.is_active == True).first()
    if not series:
        return {"series": None}
    game = db.query(Game).filter(Game.series_id == series.id, Game.is_active == True).first()
    if game:
        _check_auto_stop(game, db)
    buttons = (
        db.query(ScoreButton)
        .filter(ScoreButton.series_id == series.id, ScoreButton.is_active == True)
        .order_by(ScoreButton.display_order, ScoreButton.id)
        .all()
    )
    return {
        "series": {"id": series.id, "name": series.name},
        "game": {"id": game.id, "name": game.name, "status": game.status, "remaining_seconds": _remaining(game)} if game else None,
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


# ── Songs ───────────────────────────────────────────────
@router.get("/series/{sid}/songs", response_model=List[SongOut])
def list_songs(sid: int, db: Session = Depends(get_db)):
    return db.query(Song).filter(Song.series_id == sid).order_by(Song.display_order, Song.id).all()


@router.post("/songs", response_model=SongOut)
def create_song(data: SongCreate, db: Session = Depends(get_db)):
    s = Song(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/songs/{sid}")
def delete_song(sid: int, db: Session = Depends(get_db)):
    s = db.query(Song).get(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.put("/songs/{sid}", response_model=SongOut)
def update_song(sid: int, data: SongCreate, db: Session = Depends(get_db)):
    s = db.query(Song).get(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    # Update allowed fields
    s.title = data.title
    s.url = data.url
    s.display_order = data.display_order
    db.commit()
    db.refresh(s)
    return s


# ── Export / Import Database ──────────────────────────────

@router.get("/admin/export")
def export_database(db: Session = Depends(get_db), _auth=Depends(_require_admin)):
    """Export entire database as JSON."""
    data = {
        "series": [],
        "games": [],
        "teams": [],
        "score_buttons": [],
        "team_scores": [],
        "songs": [],
    }
    for s in db.query(Series).all():
        data["series"].append({
            "id": s.id, "name": s.name, "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    for g in db.query(Game).all():
        data["games"].append({
            "id": g.id, "name": g.name, "series_id": g.series_id,
            "is_active": g.is_active, "status": g.status,
            "duration_seconds": g.duration_seconds,
            "paused_remaining": g.paused_remaining,
            "started_at": g.started_at.isoformat() if g.started_at else None,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        })
    for t in db.query(Team).all():
        data["teams"].append({
            "id": t.id, "name": t.name, "game_id": t.game_id,
            "start_order": t.start_order,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    for b in db.query(ScoreButton).all():
        data["score_buttons"].append({
            "id": b.id, "label": b.label, "image_url": b.image_url,
            "points": b.points, "max_clicks": b.max_clicks,
            "max_clicks_game": b.max_clicks_game,
            "display_order": b.display_order, "is_active": b.is_active,
            "series_id": b.series_id,
        })
    for ts in db.query(TeamScore).all():
        data["team_scores"].append({
            "id": ts.id, "team_id": ts.team_id,
            "button_id": ts.button_id, "clicks": ts.clicks,
        })
    for sg in db.query(Song).all():
        data["songs"].append({
            "id": sg.id, "title": sg.title, "url": sg.url,
            "display_order": sg.display_order, "series_id": sg.series_id,
        })
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": "attachment; filename=robot_score_backup.json"},
    )


@router.post("/admin/import")
async def import_database(file: UploadFile = File(...), db: Session = Depends(get_db), _auth=Depends(_require_admin)):
    """Import database from JSON file, replacing all existing data."""
    content = await file.read()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON file")

    required_keys = {"series", "games", "teams", "score_buttons", "team_scores", "songs"}
    if not required_keys.issubset(data.keys()):
        raise HTTPException(400, f"Missing keys. Required: {required_keys}")

    # Clear existing data in correct order (foreign key deps)
    db.query(TeamScore).delete()
    db.query(Team).delete()
    db.query(Game).delete()
    db.query(ScoreButton).delete()
    db.query(Song).delete()
    db.query(Series).delete()
    db.flush()

    # Re-insert in dependency order
    for s in data["series"]:
        db.add(Series(
            id=s["id"], name=s["name"], is_active=s.get("is_active", True),
            created_at=datetime.fromisoformat(s["created_at"]) if s.get("created_at") else datetime.utcnow(),
        ))
    db.flush()
    for g in data["games"]:
        db.add(Game(
            id=g["id"], name=g["name"], series_id=g["series_id"],
            is_active=g.get("is_active", False), status=g.get("status", "stopped"),
            duration_seconds=g.get("duration_seconds"),
            paused_remaining=g.get("paused_remaining"),
            started_at=datetime.fromisoformat(g["started_at"]) if g.get("started_at") else None,
            created_at=datetime.fromisoformat(g["created_at"]) if g.get("created_at") else datetime.utcnow(),
        ))
    db.flush()
    for b in data["score_buttons"]:
        db.add(ScoreButton(
            id=b["id"], label=b["label"], image_url=b.get("image_url"),
            points=b.get("points", 1), max_clicks=b.get("max_clicks"),
            max_clicks_game=b.get("max_clicks_game"),
            display_order=b.get("display_order", 0),
            is_active=b.get("is_active", True), series_id=b["series_id"],
        ))
    db.flush()
    for t in data["teams"]:
        db.add(Team(
            id=t["id"], name=t["name"], game_id=t["game_id"],
            start_order=t.get("start_order"),
            created_at=datetime.fromisoformat(t["created_at"]) if t.get("created_at") else datetime.utcnow(),
        ))
    db.flush()
    for ts in data["team_scores"]:
        db.add(TeamScore(
            id=ts["id"], team_id=ts["team_id"],
            button_id=ts["button_id"], clicks=ts.get("clicks", 0),
        ))
    for sg in data["songs"]:
        db.add(Song(
            id=sg["id"], title=sg["title"], url=sg["url"],
            display_order=sg.get("display_order", 0), series_id=sg["series_id"],
        ))
    db.commit()
    return {"ok": True, "message": "Database imported successfully"}
