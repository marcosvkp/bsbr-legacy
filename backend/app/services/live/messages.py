"""Scorefeed ao vivo — ScoreSaber e BeatLeader WebSockets.

Uma mensagem do feed é um score recém-jogado em qualquer lugar do mundo.
`LiveScore` normaliza ambos os formatos; o listener publica no Redis e o
endpoint WS repassa para o frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Dificuldade numérica do ScoreSaber -> nome (mesmo mapa do builder)
SS_DIFF_RANK_TO_NAME = {1: "Easy", 3: "Normal", 5: "Hard", 7: "Expert", 9: "ExpertPlus"}


@dataclass
class LiveScore:
    source: str  # "scoresaber" | "beatleader"
    score_id: str
    leaderboard_id: str
    player_id: str
    player_name: str | None
    player_country: str | None
    song_hash: str | None
    difficulty: str | None
    score: int
    acc: float | None
    pp: float | None
    mods: str
    full_combo: bool
    max_score: int | None
    rank: int | None
    time_set: datetime  # naive-UTC (mesma convenção do sync)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "score_id": self.score_id,
            "leaderboard_id": self.leaderboard_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "player_country": self.player_country,
            "song_hash": self.song_hash,
            "difficulty": self.difficulty,
            "score": self.score,
            "acc": round(self.acc, 4) if self.acc is not None else None,
            "pp": round(self.pp, 2) if self.pp is not None else None,
            "mods": self.mods,
            "full_combo": self.full_combo,
            "max_score": self.max_score,
            "rank": self.rank,
            "time_set": self.time_set.isoformat(),
        }


def _parse_time(raw: str | None) -> datetime | None:
    """Aceita ISO 8601 (ScoreSaber) OU unix timestamp (BeatLeader timepost)."""
    if not raw:
        return None
    # unix timestamp (ex. "1788028773")
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def parse_scoresaber_message(msg: dict) -> LiveScore | None:
    """wss://scoresaber.com/ws.

    Formato real observado (2026-08-28):
      {"commandName":"score","commandData":{
        "score": {"id":..., "leaderboardPlayerInfo":{"id","name","country"}, "baseScore",
                  "modifiedScore","pp","modifiers","fullCombo","timeSet","rank"},
        "leaderboard": {"id","songHash","songName","maxScore","difficulty":{"difficulty":n}}}}
    Também aceita o formato antigo {"command":"score","data":{...}} como fallback.
    """
    if msg.get("commandName") == "score" and isinstance(msg.get("commandData"), dict):
        data = msg["commandData"]
        score = data.get("score") or {}
        lb = data.get("leaderboard") or {}
        player_info = score.get("leaderboardPlayerInfo") or {}
        player_id = str(player_info.get("id") or score.get("playerId") or "")
        leaderboard_id = str(lb.get("id") or data.get("leaderboardId") or "")
        score_id = str(score.get("id") or "")
        if not (score_id and player_id and leaderboard_id):
            return None
        player_name = player_info.get("name") or score.get("playerName")
        player_country = player_info.get("country")
        song_hash = lb.get("songHash")
        max_score = lb.get("maxScore") or score.get("maxScore")
        base = score.get("baseScore")
        score_value = int(score.get("modifiedScore") or base or 0)
        acc = score.get("acc")
        if acc is None and max_score and base:
            acc = float(base) / float(max_score)
        diff_num = (lb.get("difficulty") or {}).get("difficulty")
        diff_name = (
            SS_DIFF_RANK_TO_NAME.get(diff_num) if isinstance(diff_num, int) else None
        )
        time_set = _parse_time(score.get("timeSet")) or datetime.utcnow()
        pp = score.get("pp")
        return LiveScore(
            source="scoresaber",
            score_id=score_id,
            leaderboard_id=leaderboard_id,
            player_id=player_id,
            player_name=player_name,
            player_country=player_country,
            song_hash=song_hash,
            difficulty=diff_name,
            score=score_value,
            acc=float(acc) if acc is not None else None,
            pp=float(pp) if pp is not None and float(pp) > 0 else None,
            mods=str(score.get("modifiers") or score.get("mods") or ""),
            full_combo=bool(score.get("fullCombo") or score.get("fc")),
            max_score=int(max_score) if max_score else None,
            rank=score.get("rank"),
            time_set=time_set,
            raw=data,
        )

    # Fallback: formato antigo {"command":"score","data":{...}}
    if msg.get("command") != "score":
        return None
    data = msg.get("data") or {}
    score_id = str(data.get("id") or "")
    player_id = str(data.get("playerId") or data.get("playerID") or "")
    leaderboard_id = str(data.get("leaderboardId") or "")
    if not (score_id and player_id and leaderboard_id):
        return None

    max_score = data.get("maxScore")
    base = data.get("unmodififiedScore") or data.get("baseScore")
    score_value = int(data.get("score") or base or 0)
    acc = data.get("acc")
    if acc is None and max_score and base:
        acc = float(base) / float(max_score)

    diff_num = data.get("difficulty")
    diff_name = SS_DIFF_RANK_TO_NAME.get(diff_num) if isinstance(diff_num, int) else None

    time_set = _parse_time(data.get("timeSet")) or datetime.utcnow()
    return LiveScore(
        source="scoresaber",
        score_id=score_id,
        leaderboard_id=leaderboard_id,
        player_id=player_id,
        player_name=data.get("playerName"),
        player_country=data.get("playerCountry"),
        song_hash=data.get("songHash"),
        difficulty=diff_name,
        score=score_value,
        acc=float(acc) if acc is not None else None,
        pp=float(data["pp"]) if data.get("pp") is not None else None,
        mods=str(data.get("mods") or data.get("modifiers") or ""),
        full_combo=bool(data.get("fullCombo") or data.get("fc")),
        max_score=int(max_score) if max_score else None,
        rank=data.get("rank"),
        time_set=time_set,
        raw=data,
    )


def parse_beatleader_message(msg: dict) -> LiveScore | None:
    """wss://sockets.api.beatleader.com/scores.

    Formato real observado (2026-08-29): o frame é o PRÓPRIO objeto de score
    (sem envelope "command"), com os campos do ScoreResponse do BeatLeader:
      {id, playerId, leaderboardId, baseScore, modifiedScore, accuracy (0..1),
       modifiers, fullCombo, rank, timepost (unix), country, player: {...},
       leaderboard: {song: {hash, name}, difficulty: {...}}}
    Aceita o formato antigo {"command":"score","data":{...}} como fallback.
    """
    data = msg
    if msg.get("command") == "score" and isinstance(msg.get("data"), dict):
        data = msg["data"]
    score_id = str(data.get("id") or "")
    player_id = str(data.get("playerId") or "")
    leaderboard_id = str(data.get("leaderboardId") or "")
    if not (score_id and player_id and leaderboard_id):
        return None

    player = data.get("player") or {}
    leaderboard = data.get("leaderboard") or {}
    song = leaderboard.get("song") or {}
    difficulty = leaderboard.get("difficulty") or {}
    acc = data.get("accuracy")
    if acc is None:
        acc = data.get("acc")
    # accuracy do BL é 0..1; alguns eventos vêm com accuracy 0 (score inválido)
    if acc is not None and float(acc) == 0.0:
        acc = None

    time_set = _parse_time(str(data.get("timepost") or data.get("timeset") or ""))
    if time_set is None:
        time_set = datetime.utcnow()
    return LiveScore(
        source="beatleader",
        score_id=score_id,
        leaderboard_id=leaderboard_id,
        player_id=player_id,
        player_name=data.get("playerName") or player.get("name"),
        player_country=data.get("country") or player.get("country") or data.get("playerCountry"),
        song_hash=song.get("hash") or data.get("songHash"),
        difficulty=data.get("difficulty") or difficulty.get("difficultyName"),
        score=int(data.get("modifiedScore") or data.get("baseScore") or data.get("score") or 0),
        acc=float(acc) if acc is not None else None,
        pp=float(data["pp"]) if data.get("pp") is not None and float(data["pp"]) > 0 else None,
        mods=str(data.get("modifiers") or data.get("mods") or ""),
        full_combo=bool(data.get("fullCombo") or data.get("fc")),
        max_score=None,
        rank=data.get("rank"),
        time_set=time_set,
        raw=data,
    )


PARSERS = {
    "scoresaber": parse_scoresaber_message,
    "beatleader": parse_beatleader_message,
}


def parse_message(source: str, payload: str | bytes | dict) -> LiveScore | None:
    """Rota a mensagem JSON bruta para o parser da fonte."""
    parser = PARSERS.get(source)
    if parser is None:
        return None
    try:
        if isinstance(payload, (str, bytes)):
            import json

            msg = json.loads(payload)
        else:
            msg = payload
    except (ValueError, TypeError):
        return None
    if not isinstance(msg, dict):
        return None
    return parser(msg)
