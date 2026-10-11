import json
import os
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import LessonNote, LearningProgress, User, Video, db


load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
DEVICE_COOKIE = "focustube_device"
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,32}$")

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(BASE_DIR, "focus_tube.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "focus-tube-development-key"),
)
db.init_app(app)


def ensure_schema():
    """Create new tables and add columns for users upgrading the original database."""
    db.create_all()
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns("video")}
    additions = {
        "description": "TEXT NOT NULL DEFAULT ''",
        "thumbnail": "VARCHAR(500) NOT NULL DEFAULT ''",
        "channel_title": "VARCHAR(200) NOT NULL DEFAULT ''",
        "published_at": "VARCHAR(40) NOT NULL DEFAULT ''",
        "ai_score": "FLOAT",
        "ai_reason": "VARCHAR(300)",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    }
    for name, definition in additions.items():
        if name not in existing_columns:
            db.session.execute(text(f"ALTER TABLE video ADD COLUMN {name} {definition}"))
    progress_columns = {column["name"] for column in inspector.get_columns("learning_progress")}
    if "user_id" not in progress_columns:
        db.session.execute(text("ALTER TABLE learning_progress ADD COLUMN user_id INTEGER"))
    db.session.commit()


with app.app_context():
    ensure_schema()


def get_device_id():
    return request.cookies.get(DEVICE_COOKIE) or secrets.token_urlsafe(24)


def response_with_device_cookie(response, device_id):
    if request.cookies.get(DEVICE_COOKIE) != device_id:
        response.set_cookie(
            DEVICE_COOKIE,
            device_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
        )
    return response


def valid_video_id(video_id):
    return bool(VIDEO_ID_PATTERN.fullmatch(video_id or ""))


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def claim_device_data(user, device_id):
    """Attach anonymous progress/notes from this browser to a newly signed-in user."""
    anonymous_progress = LearningProgress.query.filter_by(device_id=device_id, user_id=None).all()
    for item in anonymous_progress:
        existing = LearningProgress.query.filter_by(user_id=user.id, video_id=item.video_id).first()
        if existing:
            existing.saved = existing.saved or item.saved
            existing.completed = existing.completed or item.completed
            if item.position_seconds > existing.position_seconds:
                existing.position_seconds = item.position_seconds
                existing.duration_seconds = max(existing.duration_seconds, item.duration_seconds)
            db.session.delete(item)
        else:
            item.user_id = user.id
    for note in LessonNote.query.filter_by(device_id=device_id, user_id=None).all():
        note.user_id = user.id
    db.session.commit()


def active_scope(device_id):
    user = current_user()
    return user, user.id if user else None


def note_to_dict(note):
    return {
        "id": note.id,
        "content": note.content,
        "timestamp_seconds": note.timestamp_seconds,
        "created_at": note.created_at.strftime("%b %d, %Y %H:%M"),
    }


def search_youtube(query):
    """Fetch a small candidate set from YouTube with safe network handling."""
    if not YOUTUBE_API_KEY:
        return [], "Add YOUTUBE_API_KEY to .env to enable YouTube search."

    params = {
        "key": YOUTUBE_API_KEY,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": 12,
        "safeSearch": "strict",
        "order": "relevance",
        "videoCategoryId": "27",
    }
    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search", params=params, timeout=12
        )
        if response.status_code != 200:
            return [], f"YouTube search is unavailable right now ({response.status_code})."
        items = response.json().get("items", [])
        videos = []
        for item in items:
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url", "")
            )
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", "Untitled lesson"),
                    "description": snippet.get("description", ""),
                    "thumbnail": thumbnail,
                    "channel_title": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                }
            )
        return videos, None
    except requests.RequestException:
        return [], "YouTube could not be reached. Check your connection and try again."


EDUCATIONAL_TERMS = {
    "tutorial": 24,
    "course": 24,
    "lesson": 24,
    "lecture": 22,
    "explained": 20,
    "how to": 18,
    "learn": 18,
    "guide": 14,
    "beginner": 14,
    "fundamentals": 18,
    "introduction": 15,
    "concepts": 14,
    "practice": 10,
    "problem solving": 14,
    "education": 24,
    "educational": 24,
    "class": 18,
    "academy": 22,
    "university": 22,
    "school": 18,
    "study": 18,
    "science": 16,
    "mathematics": 18,
    "programming": 18,
    "documentary": 12,
    "open courseware": 30,
}
NON_EDUCATIONAL_TERMS = {
    "music": 55,
    "song": 55,
    "official video": 45,
    "trailer": 50,
    "reaction": 42,
    "prank": 50,
    "gaming": 38,
    "gameplay": 45,
    "vlog": 32,
    "shorts": 30,
    "compilation": 24,
    "mrbeast": 100,
    "mr beast": 100,
    "pewdiepie": 100,
    "pewdie pie": 100,
    "pewds": 100,
    "ishowspeed": 100,
    "i show speed": 100,
    "challenge": 42,
    "entertainment": 42,
    "comedy": 38,
    "funny": 34,
    "celebrity": 35,
    "speedrun": 45,
    "fortnite": 45,
    "minecraft": 45,
    "beast games": 100,
    "beast philanthropy": 100,
}

TRUSTED_EDUCATIONAL_SOURCES = {
    "khan academy",
    "mit opencourseware",
    "3blue1brown",
    "crash course",
    "freecodecamp",
    "coursera",
    "edx",
    "ted-ed",
    "stanford",
    "harvard",
    " yale ",
}
ACADEMIC_TOPIC_TERMS = {
    "math", "mathematics", "algebra", "calculus", "geometry", "physics", "chemistry",
    "biology", "science", "history", "economics", "finance", "law", "language",
    "english", "writing", "coding", "programming", "python", "javascript", "design",
    "photography", "music theory", "psychology", "哲学", "engineering",
}


def is_blocked_content(video):
    """Reject obvious entertainment before either AI or local ranking sees it."""
    text_blob = " ".join(
        [
            video.get("title", ""),
            video.get("description", ""),
            video.get("channel_title", ""),
        ]
    ).lower()
    return any(
        term in text_blob
        for term, points in NON_EDUCATIONAL_TERMS.items()
        if points >= 90
    )


def is_blocked_topic(query):
    return is_blocked_content({"title": query, "description": "", "channel_title": ""})


def heuristic_filter(query, videos):
    """Strict local fallback: uncertain content is excluded, not promoted."""
    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))
    ranked = []
    for video in videos:
        if is_blocked_content(video):
            continue
        text_blob = f"{video['title']} {video['description']}".lower()
        channel_blob = video.get("channel_title", "").lower()
        score = 0
        educational_hits = 0
        for term, points in EDUCATIONAL_TERMS.items():
            if term in text_blob:
                score += points
                educational_hits += 1
        for term, points in NON_EDUCATIONAL_TERMS.items():
            if term in text_blob:
                score -= points
        if any(source in channel_blob for source in TRUSTED_EDUCATIONAL_SOURCES):
            score += 30
            educational_hits += 1
        matching_query_words = sum(word in text_blob for word in query_words if len(word) > 2)
        if matching_query_words:
            score += min(24, matching_query_words * 8)
        if any(topic in query.lower() and topic in text_blob for topic in ACADEMIC_TOPIC_TERMS):
            score += 18
            educational_hits += 1
        score = max(0, min(100, score))
        # Require explicit teaching intent. Relevance alone is not enough.
        if score >= 42 and educational_hits > 0 and matching_query_words > 0:
            ranked.append({**video, "ai_score": score, "ai_reason": "Educational match"})
    return sorted(ranked, key=lambda item: item["ai_score"], reverse=True)[:9]


def extract_json(text_value):
    cleaned = text_value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    return json.loads(cleaned)


def ai_filter_videos(query, videos):
    """Ask Gemini to classify candidates, then fall back to local scoring if needed."""
    if is_blocked_topic(query):
        return [], "smart"
    candidates = [video for video in videos if not is_blocked_content(video)]
    fallback = heuristic_filter(query, candidates)
    if not GEMINI_API_KEY or not candidates:
        return fallback, "smart"

    catalog = [
        {
            "index": index,
            "title": video["title"],
            "description": video["description"][:500],
            "channel": video["channel_title"],
        }
        for index, video in enumerate(candidates)
    ]
    prompt = (
        "You are FocusTube's educational content editor. The user wants to learn: "
        f"{query!r}. Review the YouTube candidates below. Keep only genuinely educational "
        "lessons, tutorials, lectures, courses, demonstrations, or explainers relevant "
        "to the request. Exclude music, entertainment, vlogs, reactions, gaming, "
        "shorts, clickbait, celebrity content, challenges, and unrelated videos. "
        "Reject creators whose content is primarily entertainment, including MrBeast "
        "and PewDiePie, even if the title contains the requested topic. If uncertain, "
        "exclude the candidate. Return JSON only in this exact shape: "
        '{"selected":[{"index":0,"score":91,"reason":"Short reason"}]}. '
        "Use scores from 0 to 100 and select at most 9 candidates.\n\n"
        + json.dumps(catalog, ensure_ascii=False)
    )
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(GEMINI_MODEL, safe='')}:generateContent"
        )
        response = requests.post(
            url,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
            },
            timeout=15,
        )
        response.raise_for_status()
        response_candidates = response.json().get("candidates", [])
        text_value = response_candidates[0]["content"]["parts"][0]["text"]
        selected = extract_json(text_value).get("selected", [])
        filtered = []
        locally_approved_ids = {
            video["video_id"] for video in heuristic_filter(query, candidates)
        }
        for item in selected:
            index = int(item.get("index", -1))
            if (
                0 <= index < len(candidates)
                and candidates[index]["video_id"] in locally_approved_ids
                and not is_blocked_content(candidates[index])
            ):
                filtered.append(
                    {
                        **candidates[index],
                        "ai_score": max(0, min(100, float(item.get("score", 0)))),
                        "ai_reason": str(item.get("reason", "Educational match"))[:300],
                    }
                )
        if filtered:
            return sorted(filtered, key=lambda item: item["ai_score"], reverse=True)[:9], "ai"
        # A successful empty Gemini response is a real rejection; do not refill it
        # with a weaker fallback result.
        return [], "ai"
    except (ValueError, KeyError, TypeError, requests.RequestException, json.JSONDecodeError):
        pass
    return fallback, "smart"


def save_video_metadata(video_data):
    video = Video.query.filter_by(youtube_id=video_data["video_id"]).first()
    if not video:
        video = Video(youtube_id=video_data["video_id"], title=video_data["title"])
        db.session.add(video)
    for field in (
        "title",
        "description",
        "thumbnail",
        "channel_title",
        "published_at",
        "ai_score",
        "ai_reason",
    ):
        if field in video_data:
            setattr(video, field, video_data[field])
    return video


def progress_for(device_id, video_id, user_id=None):
    video = Video.query.filter_by(youtube_id=video_id).first()
    if not video:
        return None
    query = LearningProgress.query.filter_by(video_id=video.id)
    if user_id:
        query = query.filter_by(user_id=user_id)
    else:
        query = query.filter_by(device_id=device_id)
    return query.order_by(LearningProgress.last_watched_at.desc()).first()


def serialize_progress(progress):
    return {
        "saved": bool(progress.saved),
        "completed": bool(progress.completed),
        "position_seconds": round(progress.position_seconds, 1),
        "duration_seconds": round(progress.duration_seconds, 1),
        "progress_percent": progress.progress_percent,
    }


def enrich_videos(videos, device_id, user_id=None):
    ids = [video["video_id"] for video in videos]
    stored = {video.youtube_id: video for video in Video.query.filter(Video.youtube_id.in_(ids)).all()}
    progress_query = LearningProgress.query.join(Video).filter(Video.youtube_id.in_(ids))
    progress_query = progress_query.filter(LearningProgress.user_id == user_id) if user_id else progress_query.filter(LearningProgress.device_id == device_id)
    progress_rows = {row.video.youtube_id: row for row in progress_query.all()}
    for video in videos:
        row = progress_rows.get(video["video_id"])
        video["saved"] = bool(row and row.saved)
        video["completed"] = bool(row and row.completed)
        video["progress_percent"] = row.progress_percent if row else 0
        video["stored"] = video["video_id"] in stored
    return videos


def get_queue(device_id, user_id=None):
    query = LearningProgress.query.join(Video)
    query = query.filter(LearningProgress.user_id == user_id) if user_id else query.filter(LearningProgress.device_id == device_id)
    rows = (
        query.filter((LearningProgress.saved.is_(True)) | (LearningProgress.position_seconds > 0))
        .order_by(LearningProgress.completed.asc(), LearningProgress.last_watched_at.desc())
        .all()
    )
    unique = []
    seen = set()
    for row in rows:
        if row.video.youtube_id not in seen:
            unique.append(row)
            seen.add(row.video.youtube_id)
        if len(unique) == 8:
            break
    return unique


def upsert_progress(device_id, video_id, payload, user_id=None):
    if not valid_video_id(video_id):
        return None, "Invalid video id"
    video = Video.query.filter_by(youtube_id=video_id).first()
    if not video:
        video = Video(
            youtube_id=video_id,
            title=str(payload.get("title") or "Untitled lesson")[:300],
            description=str(payload.get("description") or "")[:5000],
            thumbnail=str(payload.get("thumbnail") or "")[:500],
            channel_title=str(payload.get("channel_title") or "")[:200],
        )
        db.session.add(video)
        db.session.flush()
    progress_query = LearningProgress.query.filter_by(video_id=video.id)
    progress_query = progress_query.filter_by(user_id=user_id) if user_id else progress_query.filter_by(device_id=device_id)
    progress = progress_query.first()
    if not progress:
        progress = LearningProgress(device_id=device_id, user_id=user_id, video_id=video.id)
        db.session.add(progress)
    return progress, None


@app.context_processor
def inject_globals():
    return {
        "current_year": datetime.now(timezone.utc).year,
        "logged_in_user": current_user(),
    }


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("auth.html", mode="signup")
    display_name = " ".join(request.form.get("display_name", "").split())[:80]
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not display_name or "@" not in email or len(password) < 8:
        return render_template("auth.html", mode="signup", error="Use a name, a valid email, and a password of at least 8 characters."), 400
    if User.query.filter_by(email=email).first():
        return render_template("auth.html", mode="signup", error="An account with that email already exists."), 409
    user = User(email=email, display_name=display_name, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    claim_device_data(user, get_device_id())
    return redirect(url_for("my_learning"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth.html", mode="login")
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return render_template("auth.html", mode="login", error="That email and password do not match."), 401
    device_id = get_device_id()
    session.clear()
    session["user_id"] = user.id
    claim_device_data(user, device_id)
    return redirect(url_for("my_learning"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/my-learning")
def my_learning():
    device_id = get_device_id()
    user = current_user()
    queue = get_queue(device_id, user.id if user else None)
    notes_query = LessonNote.query.join(Video)
    notes_query = notes_query.filter(LessonNote.user_id == user.id) if user else notes_query.filter(LessonNote.device_id == device_id, LessonNote.user_id.is_(None))
    notes = notes_query.order_by(LessonNote.updated_at.desc()).limit(12).all()
    response = make_response(render_template("my_learning.html", queue=queue, notes=notes))
    return response_with_device_cookie(response, device_id)


@app.route("/", methods=["GET"])
def home():
    device_id = get_device_id()
    user = current_user()
    response = make_response(render_template("index.html", queue=get_queue(device_id, user.id if user else None)))
    return response_with_device_cookie(response, device_id)


@app.route("/search", methods=["POST"])
def search_query():
    device_id = get_device_id()
    user = current_user()
    query = " ".join(request.form.get("query", "").split())[:120]
    videos, error = search_youtube(query) if query else ([], "Tell me what you want to learn first.")
    filter_mode = "smart"
    if videos:
        videos, filter_mode = ai_filter_videos(query, videos)
        for video in videos:
            save_video_metadata(video)
        db.session.commit()
        videos = enrich_videos(videos, device_id, user.id if user else None)
    response = make_response(
        render_template(
            "index.html",
            videos=videos,
            query=query,
            error=error,
            filter_mode=filter_mode,
            queue=get_queue(device_id, user.id if user else None),
        )
    )
    return response_with_device_cookie(response, device_id)


@app.route("/watch/<video_id>")
def watch(video_id):
    if not valid_video_id(video_id):
        return render_template("404.html"), 404
    device_id = get_device_id()
    user = current_user()
    video = Video.query.filter_by(youtube_id=video_id).first()
    if not video:
        video = Video(youtube_id=video_id, title="Your lesson")
        db.session.add(video)
        db.session.commit()
    progress = progress_for(device_id, video_id, user.id if user else None)
    notes_query = LessonNote.query.filter_by(video_id=video.id)
    notes_query = notes_query.filter(LessonNote.user_id == user.id) if user else notes_query.filter(LessonNote.device_id == device_id, LessonNote.user_id.is_(None))
    notes = notes_query.order_by(LessonNote.created_at.desc()).all()
    response = make_response(render_template("watch.html", video=video, progress=progress, notes=notes))
    return response_with_device_cookie(response, device_id)


@app.post("/api/videos/<video_id>/save")
def save_video(video_id):
    device_id = get_device_id()
    user = current_user()
    payload = request.get_json(silent=True) or {}
    progress, error = upsert_progress(device_id, video_id, payload, user.id if user else None)
    if error:
        return jsonify(error=error), 400
    progress.saved = bool(payload["saved"]) if "saved" in payload else not progress.saved
    db.session.commit()
    response = jsonify(**serialize_progress(progress))
    return response_with_device_cookie(response, device_id)


@app.post("/api/videos/<video_id>/progress")
def update_progress(video_id):
    device_id = get_device_id()
    user = current_user()
    payload = request.get_json(silent=True) or {}
    progress, error = upsert_progress(device_id, video_id, payload, user.id if user else None)
    if error:
        return jsonify(error=error), 400
    try:
        position = max(0, float(payload.get("position_seconds", progress.position_seconds)))
        duration = max(0, float(payload.get("duration_seconds", progress.duration_seconds)))
    except (TypeError, ValueError):
        return jsonify(error="Playback position must be numeric."), 400
    progress.position_seconds = position
    progress.duration_seconds = duration
    if payload.get("completed") or (duration > 0 and position / duration >= 0.95):
        progress.completed = True
    db.session.commit()
    response = jsonify(**serialize_progress(progress))
    return response_with_device_cookie(response, device_id)


@app.post("/api/videos/<video_id>/complete")
def complete_video(video_id):
    device_id = get_device_id()
    user = current_user()
    progress, error = upsert_progress(device_id, video_id, request.get_json(silent=True) or {}, user.id if user else None)
    if error:
        return jsonify(error=error), 400
    progress.completed = True
    db.session.commit()
    response = jsonify(**serialize_progress(progress))
    return response_with_device_cookie(response, device_id)


@app.post("/api/videos/<video_id>/notes")
def create_note(video_id):
    device_id = get_device_id()
    user = current_user()
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content", "")).strip()
    if not valid_video_id(video_id) or not content or len(content) > 5000:
        return jsonify(error="Write a note between 1 and 5000 characters."), 400
    video = Video.query.filter_by(youtube_id=video_id).first()
    if not video:
        return jsonify(error="Lesson not found."), 404
    timestamp = payload.get("timestamp_seconds")
    try:
        timestamp = max(0, float(timestamp)) if timestamp is not None else None
    except (TypeError, ValueError):
        timestamp = None
    note = LessonNote(
        device_id=device_id,
        user_id=user.id if user else None,
        video_id=video.id,
        content=content,
        timestamp_seconds=timestamp,
    )
    db.session.add(note)
    db.session.commit()
    response = jsonify(note=note_to_dict(note))
    return response_with_device_cookie(response, device_id)


@app.delete("/api/notes/<int:note_id>")
def delete_note(note_id):
    device_id = get_device_id()
    user = current_user()
    query = LessonNote.query.filter_by(id=note_id)
    query = query.filter(LessonNote.user_id == user.id) if user else query.filter(LessonNote.device_id == device_id, LessonNote.user_id.is_(None))
    note = query.first()
    if not note:
        return jsonify(error="Note not found."), 404
    db.session.delete(note)
    db.session.commit()
    return jsonify(deleted=True)


@app.get("/health")
def health():
    return jsonify(
        status="ok",
        youtube_configured=bool(YOUTUBE_API_KEY),
        ai_configured=bool(GEMINI_API_KEY),
    )


@app.cli.command("init-db")
def init_db():
    ensure_schema()
    print("FocusTube database is ready.")


if __name__ == "__main__":
    app.run(debug=True)
