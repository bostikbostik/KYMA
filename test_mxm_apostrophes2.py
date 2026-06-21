import sys
sys.path.append('.')
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from lyrics_manager import LyricsManager

lm = LyricsManager()

test_cases = [
    ("knockin' on heaven's door", "Guns N' Roses"),
    ("knockin on heavens door", "Guns N' Roses"),
    ("knockin' on heaven's door", "Guns N Roses"),
    ("knockin on heavens door", "Guns N Roses"),
    ("knockin on heavens door", "Bob Dylan"),
    ("knockin' on heaven's door", "Bob Dylan"),
]

for title, artist in test_cases:
    params = {"q_track": title, "q_artist": artist, "apikey": lm.musixmatch_token}
    resp = lm.session.get(f"{lm.base_url}matcher.lyrics.get", params=params, timeout=6).json()
    print(f"Track: '{title}', Artist: '{artist}' -> {resp.get('message', {}).get('header', {}).get('status_code')}")
