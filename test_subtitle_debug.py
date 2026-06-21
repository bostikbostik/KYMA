"""
Debug script: verifica cosa restituisce Musixmatch per le subtitle (LRC karaoke)
su brani famosi, e confronta con il piano API disponibile.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("MUSIXMATCH_API_KEY")
BASE_URL = "https://api.musixmatch.com/ws/1.1/"

if not API_KEY:
    print("❌ Nessuna API KEY trovata nel .env")
    exit()

TEST_SONGS = [
    ("Bohemian Rhapsody", "Queen"),
    ("Blinding Lights", "The Weeknd"),
    ("Shape of You", "Ed Sheeran"),
    ("Smells Like Teen Spirit", "Nirvana"),
]

print(f"🔑 API Key: ***{API_KEY[-6:]}\n")
print("=" * 60)

for title, artist in TEST_SONGS:
    print(f"\n🎵 {title} — {artist}")
    
    params = {
        "apikey": API_KEY,
        "q_track": title,
        "q_artist": artist,
    }
    
    # Test 1: matcher.track.get → verifica has_subtitles e has_lyrics
    r_track = requests.get(f"{BASE_URL}matcher.track.get", params=params, timeout=8)
    if r_track.status_code == 200:
        d = r_track.json()
        h = d.get("message", {}).get("header", {})
        status = h.get("status_code")
        if status == 200:
            track = d["message"]["body"].get("track", {})
            print(f"   📋 Track: '{track.get('track_name')}' by '{track.get('artist_name')}'")
            print(f"   🎤 has_lyrics: {track.get('has_lyrics')}  |  has_subtitles: {track.get('has_subtitles')}  |  rating: {track.get('track_rating')}")
        elif status == 402:
            print(f"   ⚠️ 402 Rate limit raggiunto — API Plan insufficiente o limite giornaliero")
        elif status == 404:
            print(f"   ❌ 404 Brano non trovato su Musixmatch")
        else:
            print(f"   ❓ Status: {status}")
    else:
        print(f"   ❌ HTTP {r_track.status_code}")

    # Test 2: matcher.subtitle.get → tenta a prendere l'LRC
    r_sub = requests.get(f"{BASE_URL}matcher.subtitle.get", params=params, timeout=8)
    if r_sub.status_code == 200:
        d2 = r_sub.json()
        h2 = d2.get("message", {}).get("header", {})
        status2 = h2.get("status_code")
        if status2 == 200:
            sub_body = d2["message"]["body"].get("subtitle", {}).get("subtitle_body", "")
            print(f"   ✅ SUBTITLE OK — {len(sub_body)} chars — Inizio: {sub_body[:80]!r}")
        elif status2 == 402:
            print(f"   🚫 SUBTITLE → 402 (Rate limit / Piano non autorizzato per LRC)")
        elif status2 == 404:
            print(f"   ⚠️ SUBTITLE → 404 (Testo sincronizzato NON presente per questa traccia)")
        elif status2 == 401:
            print(f"   🔐 SUBTITLE → 401 (Piano API non autorizzato per subtitle)")
        else:
            print(f"   ❓ SUBTITLE status: {status2} — Header: {h2}")
    else:
        print(f"   ❌ SUBTITLE HTTP {r_sub.status_code}")

    # Test 3: matcher.lyrics.get → testo piano
    r_lyr = requests.get(f"{BASE_URL}matcher.lyrics.get", params=params, timeout=8)
    if r_lyr.status_code == 200:
        d3 = r_lyr.json()
        status3 = d3.get("message", {}).get("header", {}).get("status_code")
        if status3 == 200:
            lbody = d3["message"]["body"].get("lyrics", {}).get("lyrics_body", "")
            print(f"   📄 LYRICS OK — {len(lbody)} chars")
        elif status3 == 402:
            print(f"   🚫 LYRICS → 402 (Rate limit raggiunto)")
        else:
            print(f"   ❓ LYRICS status: {status3}")

print("\n" + "=" * 60)
print("✅ Debug completato.")
