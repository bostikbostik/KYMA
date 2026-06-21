import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("MUSIXMATCH_API_KEY")
print(f"API_KEY is {'None' if API_KEY is None else 'Set (len: ' + str(len(API_KEY)) + ')'}")

if API_KEY:
    base_url = "https://api.musixmatch.com/ws/1.1/"
    res = requests.get(f"{base_url}track.search", params={
        "apikey": API_KEY,
        "q_artist": "Coldplay",
        "page_size": 5
    }).json()
    print(res)
