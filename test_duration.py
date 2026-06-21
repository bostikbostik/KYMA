import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("MUSIXMATCH_API_KEY")
BASE_URL = "https://api.musixmatch.com/ws/1.1/"

# Test with Queen's Bohemian Rhapsody which is 5:55 (355 seconds)
# Let's say Shazam returns 365 seconds (10 seconds off)
params_strict = {
    "apikey": API_KEY,
    "q_track": "Bohemian Rhapsody",
    "q_artist": "Queen",
    "f_subtitle_length": 365,
    "f_subtitle_length_max_deviation": 5
}

print("1. Test matcher.subtitle.get WITH strict duration (e.g. slight mismatch)")
r1 = requests.get(f"{BASE_URL}matcher.subtitle.get", params=params_strict).json()
h1 = r1.get("message", {}).get("header", {})
print(f"Status: {h1.get('status_code')}")

print("\n2. Test matcher.lyrics.get WITHOUT duration (what the app does as fallback)")
params_loose = {
    "apikey": API_KEY,
    "q_track": "Bohemian Rhapsody",
    "q_artist": "Queen",
}
r2 = requests.get(f"{BASE_URL}matcher.lyrics.get", params=params_loose).json()
h2 = r2.get("message", {}).get("header", {})
print(f"Status: {h2.get('status_code')}")
