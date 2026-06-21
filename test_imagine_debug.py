import os, sys, requests
from dotenv import load_dotenv
from difflib import SequenceMatcher

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = os.getenv("MUSIXMATCH_API_KEY")
BASE_URL = "https://api.musixmatch.com/ws/1.1/"

TITLE = "Imagine"
CURRENT_ARTIST = "Che Ecru"

print(f"=== DEBUG SWAP: '{TITLE}' rilevata da '{CURRENT_ARTIST}' ===\n")

# --- STEP 1: Cerca hit globale per titolo ---
print("STEP 1: track.search per titolo (senza artista) → cerca la hit globale")
search_params = {
    "apikey": API_KEY,
    "q_track": TITLE,
    "page_size": 10,
    "s_track_rating": "desc"
}
res = requests.get(f"{BASE_URL}track.search", params=search_params, timeout=15).json()
tracks = res.get("message", {}).get("body", {}).get("track_list", [])
print(f"  Trovati {len(tracks)} brani, ecco la lista ordinata per rating:\n")

valid_tracks = []
for t in tracks:
    tk = t["track"]
    found_name = tk.get("track_name", "")
    found_artist = tk.get("artist_name", "")
    rating = tk.get("track_rating", 0)
    # Simula il filtro del codice (ratio > 0.85)
    ratio = SequenceMatcher(None, TITLE.lower(), found_name.lower()).ratio()
    passed = ratio > 0.85
    marker = "OK" if passed else "FILTRATO (ratio basso)"
    print(f"  [{rating:3}] '{found_name}' by '{found_artist}'  (ratio={ratio:.2f}) → {marker}")
    if passed:
        valid_tracks.append(tk)

if not valid_tracks:
    print("\n  *** PROBLEMA: Nessun brano supera il filtro ratio 0.85! Lo swap non può avvenire. ***")
else:
    best = max(valid_tracks, key=lambda x: int(x.get("track_rating", 0)))
    best_artist = best.get("artist_name")
    best_rating = int(best.get("track_rating", 0))
    print(f"\n  => Miglior versione trovata: '{best_artist}' (rating={best_rating})")

    # --- STEP 2: Cerca rating della versione attuale (Che Ecru) ---
    print(f"\nSTEP 2: track.search per '{TITLE}' by '{CURRENT_ARTIST}' → rating cover")
    curr_params = {
        "apikey": API_KEY,
        "q_track": TITLE,
        "q_artist": CURRENT_ARTIST,
        "page_size": 1,
        "s_track_rating": "desc"
    }
    curr_res = requests.get(f"{BASE_URL}track.search", params=curr_params, timeout=15).json()
    curr_list = curr_res.get("message", {}).get("body", {}).get("track_list", [])
    current_rating = 0
    if curr_list:
        current_rating = int(curr_list[0]["track"].get("track_rating", 0))
        print(f"  Rating '{CURRENT_ARTIST}': {current_rating}")
    else:
        print(f"  '{CURRENT_ARTIST}' non trovato su Musixmatch → rating=0")

    # --- STEP 3: Simula la logica di swap ---
    print(f"\nSTEP 3: Valutazione regole di swap")
    print(f"  best_artist='{best_artist}' | best_rating={best_rating}")
    print(f"  current_artist='{CURRENT_ARTIST}' | current_rating={current_rating}")
    print(f"  Artisti diversi? {best_artist.lower() != CURRENT_ARTIST.lower()}")
    print(f"  best_rating > 50? {best_rating > 50}")
    print(f"  current_rating < (best_rating - 20)? {current_rating} < {best_rating - 20} = {current_rating < (best_rating - 20)}")

    if best_artist.lower() != CURRENT_ARTIST.lower() and best_rating > 50 and current_rating < (best_rating - 20):
        print(f"\n  => SWAP DOVREBBE AVVENIRE verso '{best_artist}'")
    else:
        print(f"\n  => SWAP NON AVVIENE - Analisi causa:")
        if best_artist.lower() == CURRENT_ARTIST.lower():
            print("     Causa: Musixmatch ritorna lo stesso artista come miglior versione")
        if best_rating <= 50:
            print(f"     Causa: best_rating ({best_rating}) non supera 50")
        if current_rating >= (best_rating - 20):
            print(f"     Causa: current_rating ({current_rating}) >= best_rating-20 ({best_rating - 20}). Cover troppo 'famosa' per Musixmatch.")
