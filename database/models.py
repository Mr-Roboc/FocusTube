from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint


db = SQLAlchemy()


class User(db.Model):
    """A small account used to sync learning data across sessions."""

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    progress = db.relationship("LearningProgress", back_populates="user")
    notes = db.relationship("LessonNote", back_populates="user")


class Video(db.Model):
    """A YouTube lesson that has passed FocusTube's educational filter."""

    __tablename__ = "video"

    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(200), unique=True, nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    thumbnail = db.Column(db.String(500), nullable=False, default="")
    channel_title = db.Column(db.String(200), nullable=False, default="")
    published_at = db.Column(db.String(40), nullable=False, default="")
    ai_score = db.Column(db.Float, nullable=True)
    ai_reason = db.Column(db.String(300), nullable=True)
    transcript_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    progress = db.relationship(
        "LearningProgress",
        back_populates="video",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Video {self.youtube_id}: {self.title}>"


class LearningProgress(db.Model):
    """A device-scoped bookmark and playback checkpoint for a lesson."""

    __tablename__ = "learning_progress"
    __table_args__ = (
        UniqueConstraint("device_id", "video_id", name="uq_device_video_progress"),
    )

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(80), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    position_seconds = db.Column(db.Float, nullable=False, default=0)
    duration_seconds = db.Column(db.Float, nullable=False, default=0)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    saved = db.Column(db.Boolean, nullable=False, default=False)
    last_watched_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    video = db.relationship("Video", back_populates="progress")
    user = db.relationship("User", back_populates="progress")

    @property
    def progress_percent(self):
        if not self.duration_seconds:
            return 0
        return min(100, round(self.position_seconds / self.duration_seconds * 100))


class LessonNote(db.Model):
    """A learner's note attached to a lesson and optionally a playback time."""

    __tablename__ = "lesson_note"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(80), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp_seconds = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", back_populates="notes")
    video = db.relationship("Video")
