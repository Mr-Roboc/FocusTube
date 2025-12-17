from flask_sqlalchemy import SQLAlchemy


# Initialize the database object
db=SQLAlchemy()


# Video class is a model that represents a table in the database.
class Video(db.Model):
    """
    This table stores the educational videos we have 'approved'.
    """

    # Primary Key: The unique ID for every row (1, 2, 3...)
    id = db.Column(db.Integer,primary_key=True)

    youtube_id = db.Column(db.String(200),unique=True,nullable=False)

    # Title of the video
    title = db.Column(db.String(200),nullable=False)

   # The full transcript text (can be very long, so we use Text instead of String)
    transcript_text=db.Column(db.Text,nullable=True)

    def __repr__(self):

        return f"<Video : {self.title}"





