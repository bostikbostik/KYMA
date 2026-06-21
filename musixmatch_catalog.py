import os
import requests
from difflib import SequenceMatcher
from dotenv import load_dotenv
from text_utils import TextUtils

load_dotenv()

class MusixmatchCatalog:
    def __init__(self):
        self.api_key = os.getenv("MUSIXMATCH_API_KEY")
        self.base_url = "https://api.musixmatch.com/ws/1.1/"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "KYMA/1.0 (music-recognition-app)"})
        
        if not self.api_key:
            pass


    def search_specific_version(self, title, target_artist):
        """
        Controlla se l'artista target ha nel repertorio questo brano.
        Restituisce (Target_Artist, None) se confermato, altrimenti None.
        """
        if not self.api_key: return None
        
        clean_search = TextUtils.clean_for_search(title)
        if len(clean_search) < 2: return None

        params = {
            "apikey": self.api_key,
            "q_track": clean_search,
            "q_artist": target_artist,
            "page_size": 1,
            "s_track_rating": "desc"
        }

        try:
            response = self.session.get(f"{self.base_url}track.search", params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("message", {}).get("header", {}).get("status_code") == 200:
                    track_list = data["message"]["body"].get("track_list", [])
                    if track_list:
                        track = track_list[0]["track"]
                        # Se il rating è > 0, consideriamolo un brano valido
                        if track.get("track_rating", 0) > 0:
                            return (target_artist, None)
        except Exception as e:
            print(f"⚠️ Errore Musixmatch (search_specific_version): {e}")
            
        return None

    def get_track_isrc(self, title, artist):
        """
        Recupera l'ISRC ufficiale di un brano da Musixmatch tramite matcher.track.get.
        Questa endpoint fa il fuzzy match in una sola chiamata e restituisce il track object
        completo incluso track_isrc — fonte discografica certificata.
        Restituisce la stringa ISRC oppure None se non trovato.
        """
        if not self.api_key or not title: return None

        clean_title = TextUtils.clean_for_search(title)
        if len(clean_title) < 2: return None
        
        # Guard: artista vuoto o None
        artist_param = (artist or "").strip()

        params = {
            "apikey": self.api_key,
            "q_track": clean_title,
            "q_artist": artist_param,
        }
        try:
            resp = self.session.get(f"{self.base_url}matcher.track.get", params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                header = data.get("message", {}).get("header", {})
                status = header.get("status_code")
                if status == 402:
                    print(f"⚠️ [Musixmatch] Limite giornaliero API raggiunto (402). Skip ISRC.")
                    return None
                if status == 200:
                    track = data["message"]["body"].get("track", {})
                    isrc = track.get("track_isrc")
                    if isrc:
                        print(f"     🎫 [Musixmatch ISRC] Trovato: {isrc} per '{title}'")
                        return isrc
        except Exception as e:
            print(f"⚠️ [Musixmatch] Errore get_track_isrc per '{title}': {e}")
        return None

    def get_artist_top_tracks(self, artist_name, limit=30):
        """
        Recupera i brani più popolari di un artista ordinati per track_rating.
        """
        if not self.api_key: return []
        
        print(f"🎧 [Musixmatch] Scarico le Hit per: {artist_name}...")
        
        params = {
            "apikey": self.api_key,
            "q_artist": artist_name,
            "page_size": limit,
            "s_track_rating": "desc"
        }

        try:
            response = self.session.get(f"{self.base_url}track.search", params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("message", {}).get("header", {}).get("status_code") == 200:
                    tracks = data["message"]["body"].get("track_list", [])
                    
                    collected_songs = []
                    for t in tracks:
                        track = t["track"]
                        title = track.get("track_name", "")
                        clean_name = TextUtils.clean_for_search(title)
                        if clean_name and clean_name not in collected_songs:
                            collected_songs.append(clean_name)
                            
                    print(f"     📥 [Musixmatch] {len(collected_songs)} brani pronti.")
                    return collected_songs
        except Exception as e:
            print(f"❌ Errore Musixmatch (get_artist_top_tracks): {e}")
            
        return []

    def get_most_popular_version(self, title, current_artist):
        """
        Cerca la hit mondiale per evitare cover sconosciute.
        Restituisce (Top_Artist, None, Top_Rating) se fa lo swap, altrimenti None.
        """
        if not self.api_key: return None
        
        clean_search = TextUtils.clean_for_search(title)
        if len(clean_search) < 2: return None

        try:
            # 1. CERCA LA HIT GLOBALE PER NOME BRANO
            search_params = {
                "apikey": self.api_key,
                "q_track": clean_search,
                "page_size": 10,
                "s_track_rating": "desc"
            }
            search_res = self.session.get(f"{self.base_url}track.search", params=search_params, timeout=5).json()
            matches = search_res.get("message", {}).get("body", {}).get("track_list", [])
            
            if not matches: return None

            # Filtra per titolo quasi identico
            valid_tracks = []
            for t in matches:
                track = t["track"]
                found_clean = TextUtils.clean_for_search(track.get("track_name", ""))
                if SequenceMatcher(None, clean_search, found_clean).ratio() > 0.85:
                    valid_tracks.append(track)
            
            if not valid_tracks: return None

            # Ordina per rating (Musixmatch ha rating 1-100)
            best_match = max(valid_tracks, key=lambda x: int(x.get("track_rating", 0)))
            best_artist = best_match.get("artist_name")
            best_rating = int(best_match.get("track_rating", 0))

            # 2. CERCA I DATI DELLA TRACCIA ATTUALE (La possibile cover)
            current_rating = 0
            info_params = {
                "apikey": self.api_key,
                "q_track": clean_search,
                "q_artist": current_artist,
                "page_size": 1,
                "s_track_rating": "desc"
            }
            info_res = self.session.get(f"{self.base_url}track.search", params=info_params, timeout=5)
            if info_res.status_code == 200:
                data = info_res.json()
                if data.get("message", {}).get("header", {}).get("status_code") == 200:
                    curr_list = data["message"]["body"].get("track_list", [])
                    if curr_list:
                        current_rating = int(curr_list[0]["track"].get("track_rating", 0))

            print(f"     📊 [Musixmatch] Cover '{current_artist}' (Rating: {current_rating}) vs Hit '{best_artist}' (Rating: {best_rating})")

            # 3. LA MATEMATICA DELLO SWAP
            # Esegui lo swap SOLO SE l'artista è diverso, la Top Hit è famosa, e la cover ha un rating molto inferiore
            if best_artist and current_artist and best_artist.lower() != current_artist.lower():
                # Regola: La Hit deve avere un rating di almeno 50 (scala 1-100)
                if best_rating > 50:
                    # Regola: La traccia rilevata deve avere un rating notevolmente inferiore
                    if current_rating < (best_rating - 20):
                        print(f"     🔄 [Swap] Cover bloccata! Promosso originale: {best_artist}")
                        return (best_artist, None, best_rating)

        except Exception as e:
            print(f"⚠️ Errore check popolarità Musixmatch: {e}")
            
        return None
