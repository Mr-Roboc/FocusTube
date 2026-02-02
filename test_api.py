

import requests


BASE_URL = "https://www.googleapis.com/youtube/v3/search"

def get_youtube_videos(query):
    params = {
        'key': API_KEY,
        'q': query,
        'part': 'snippet', # asking for title, desc, etc.
        'type': 'video',     
        'maxResults': 5
    }
    response = requests.get(BASE_URL,params=params)
    
    

    if response.status_code == 200:
    
        data  = response.json()

        
        
        print(f"--- Results for '{query}' ---")
        
        # TODO: Write your loop here
        for item in data['items']:
            title = item['snippet']['title']
            video_id = item['id']['videoId']
            print(f"Title: {title} | ID: {video_id}")
    
    else:
        print("Error:",response.status_code)
        print(response.text)

if __name__=="__main__":
    get_youtube_videos("Python")