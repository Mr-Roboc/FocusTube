# FocusTube

FocusTube is a minimal, distraction-free learning platform built on top of YouTube. Search for a topic, receive educationally filtered lessons, save your place, write notes, and return to your learning path later.

## What it includes

- YouTube search restricted to the Education category.
- Gemini-powered educational classification when `GEMINI_API_KEY` is configured.
- A strict local safety filter that rejects entertainment, celebrity, gaming, vlog, reaction, and other irrelevant content.
- A final local allowlist gate after Gemini so uncertain results are not displayed.
- Account creation, login, logout, and password hashing.
- Anonymous device progress that is claimed into an account after sign-in.
- A My learning dashboard for saved and in-progress lessons.
- Automatic playback checkpoints through the YouTube IFrame API.
- Timestamped lesson notes beside the video and in My learning.

## Architecture

```text
Browser
  ├─ GET /                         Home + search
  ├─ POST /search                  YouTube → safety filter → Gemini/local filter
  ├─ GET /watch/<video_id>         Focused YouTube watch room
  ├─ GET /my-learning              Saved lessons + recent notes
  ├─ GET/POST /login, /signup      Authentication
  └─ POST /api/videos/...          Save, progress, completion, and notes

Flask application
  ├─ YouTube Data API               Candidate discovery
  ├─ Gemini REST API                Educational classification
  ├─ Local safety classifier        Entertainment rejection and final gate
  └─ SQLAlchemy + SQLite            Users, videos, progress, and notes
```

## Configuration

Create a local `.env` file:

```env
YOUTUBE_API_KEY=your_youtube_data_api_key
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
FLASK_SECRET_KEY=replace-with-a-long-random-value
```

`GEMINI_API_KEY` is optional. Without it, the app uses the local educational filter. Never commit `.env` or expose an API key in frontend code.

## Running

The bundled environment currently contains Python 3.11 packages while its interpreter points to Python 3.14, so use:

```bash
PYTHONPATH="$PWD/venv/lib/python3.11/site-packages" venv/bin/python app.py
```

Open <http://127.0.0.1:5000>.

The database is initialized and upgraded automatically. To explicitly initialize it:

```bash
PYTHONPATH="$PWD/venv/lib/python3.11/site-packages" venv/bin/flask --app app init-db
```

## Authentication and learning data

Accounts use Flask sessions and Werkzeug password hashing. Learners can save lessons and playback progress. Anonymous progress and notes from the current browser are attached to the account on signup or login.

The main data models are:

- `User`: account identity and password hash.
- `Video`: YouTube metadata and classification information.
- `LearningProgress`: saved state, playback position, and completion.
- `LessonNote`: note content and optional playback timestamp.

## AI filtering flow

1. YouTube returns candidate videos using strict safe search and category `27` (Education).
2. Known entertainment topics and obvious non-learning signals are blocked locally.
3. Gemini receives the query, title, description, and channel for remaining candidates.
4. Gemini returns selected indices, relevance scores, and reasons.
5. Every Gemini result must also pass the local educational gate before display.
6. If Gemini is unavailable, the local filter remains active.

## Key files

- `app.py`: routes, API integrations, filtering, authentication, and schema upgrades.
- `database/models.py`: database models.
- `templates/index.html`: search and lesson results.
- `templates/watch.html`: video player and notes panel.
- `templates/my_learning.html`: saved learning path and recent notes.
- `templates/auth.html`: signup and login.
- `static/js/script.js`: save actions, playback progress, and notes.
- `static/css/style.css`: responsive visual system.
- `.env.example`: configuration template.
