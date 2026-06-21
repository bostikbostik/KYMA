import sys
sys.path.append('.')
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from lyrics_manager import LyricsManager
import requests

lm = LyricsManager()

params1 = {"q_track": "don't look back in anger", "q_artist": "Oasis", "apikey": lm.musixmatch_token}
resp1 = lm.session.get(f"{lm.base_url}matcher.lyrics.get", params=params1, timeout=6).json()
print("With apostrophe:", resp1.get("message", {}).get("header", {}).get("status_code"))

params2 = {"q_track": "dont look back in anger", "q_artist": "Oasis", "apikey": lm.musixmatch_token}
resp2 = lm.session.get(f"{lm.base_url}matcher.lyrics.get", params=params2, timeout=6).json()
print("Without apostrophe:", resp2.get("message", {}).get("header", {}).get("status_code"))

params3 = {"q_track": "knockin' on heaven's door", "q_artist": "Guns N' Roses", "apikey": lm.musixmatch_token}
resp3 = lm.session.get(f"{lm.base_url}matcher.lyrics.get", params=params3, timeout=6).json()
print("With apostrophe (Knockin'):", resp3.get("message", {}).get("header", {}).get("status_code"))

params4 = {"q_track": "knockin on heavens door", "q_artist": "Guns N' Roses", "apikey": lm.musixmatch_token}
resp4 = lm.session.get(f"{lm.base_url}matcher.lyrics.get", params=params4, timeout=6).json()
print("Without apostrophe (Knockin'):", resp4.get("message", {}).get("header", {}).get("status_code"))
