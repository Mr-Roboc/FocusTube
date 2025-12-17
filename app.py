import os
import requests
from flask import Flask, render_template,request
from dotenv import load_dotenv
from database.models import db,Video

from database.models import db,Video # Import the db and model we just made.

load_dotenv()
API_KEY = os.getenv('YOUTUBE_API_KEY') # load_dotenv is a function from the python-dotenv package that loads environment variables from a .env file into the environment, making them accessible in your Python application.

app = Flask(__name__)



base_dir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'focus_tube.db')

# 2. Disable a feature we don't need (saves memory)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def search_youtube(query):
    URL = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": API_KEY,
        "q": query,
        'part': 'snippet',
        'type': 'video',
        'maxResults': 9
    }

    try:
        # FIX 1: Use keyword argument 'params='
        response = requests.get(URL, params=params)

        if response.status_code == 200:
            data = response.json()
            cleaned_videos = []

            for item in data['items']:
                video_data = {
                    "title": item['snippet']['title'],
                    'video_id': item['id']['videoId'],
                    'thumbnail': item['snippet']['thumbnails']['medium']['url'],
                    'description': item['snippet']['description']
                }
                cleaned_videos.append(video_data)
            
            # FIX 2: Return is OUTSIDE the loop (aligned with 'for')
            return cleaned_videos

        # FIX 3: Else is aligned with 'if response...'
        else:
            print(f"Error: API returned {response.status_code}")
            return []

    except Exception as e:
        print(f"Connection error: {e}")
        return []

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search',methods=['POST'])
def search_query():
    user_query = request.form.get('query')

    if user_query:
        results = search_youtube(user_query)
    
    else:
        results= []
    
    return render_template('index.html', videos=results)


@app.route('/watch/<video_id>')
def watch(video_id):
    # We only have the ID for now. 
    # (Later, we can use the DB to look up the title using this ID
    return render_template('watch.html',video_id = video_id)


# COMMAND TO CREATE THE DATABASE
# We create a custom command so we can initialize the DB from the terminal
@app.cli.command("init-db")
def init_db():
    """Creates the database tables."""
    db.create_all()
    print("✅ Database created successfully!")





if __name__ == '__main__':
    app.run(debug=True)
