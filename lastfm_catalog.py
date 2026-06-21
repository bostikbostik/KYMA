import os
import requests
from difflib import SequenceMatcher
from dotenv import load_dotenv
from text_utils import TextUtils

load_dotenv()


class LastFmCatalog:
    """
    Gestisce le chiamate all'API Last.fm per determinare la popolarità
    dei brani e identificare la versione originale rispetto a cover/tribute.

    Usa il listener count (ascoltatori unici) come metrica — molto più affidabile
    del rating Musixmatch per distinguere gli originali storici dalle cover recenti.
    """

    BASE_URL = "https://ws.audioscrobbler.com/2.0/"
    SWAP_RATIO_THRESHOLD = 3.0   # L'originale deve avere almeno 3x i listener della cover
    TITLE_RATIO_MIN      = 0.80  # Soglia similarità titolo (SequenceMatcher)

    def __init__(self):
        self.api_key = os.getenv("LASTFM_API_KEY")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "KYMA/1.0 (music-recognition-app)"})

        if not self.api_key:
            print("⚠️ [Last.fm] Nessun LASTFM_API_KEY trovato nel .env!")

    # ------------------------------------------------------------------
    # Metodo principale: cerca la versione più popolare di un brano
    # ------------------------------------------------------------------
    def get_most_popular_version(self, title, current_artist):
        """
        Cerca la versione originale/più popolare del brano tramite Last.fm.

        Strategia:
          1. Chiama track.search con il solo titolo → ottieni lista risultati
          2. Filtra per similarità titolo (ratio >= TITLE_RATIO_MIN)
          3. Ordina per listener count e prendi il candidato migliore
          4. Confronta con il listener count del current_artist
          5. Esegui lo swap solo se il candidato ha almeno SWAP_RATIO_THRESHOLD volte
             più listener (evita swap su brani dove la cover è nota quanto l'originale)

        Restituisce (best_artist, None, listeners) se lo swap va fatto, altrimenti None.
        """
        if not self.api_key or not title:
            return None

        clean_title = TextUtils.clean_for_search(title)
        if len(clean_title) < 2:
            return None

        try:
            # --- Step 1: Cerca candidati per titolo ---
            search_params = {
                "method": "track.search",
                "track": clean_title,
                "limit": 20,
                "api_key": self.api_key,
                "format": "json"
            }
            resp = self.session.get(self.BASE_URL, params=search_params, timeout=6)
            if resp.status_code != 200:
                return None

            data = resp.json()
            track_matches = (
                data.get("results", {})
                    .get("trackmatches", {})
                    .get("track", [])
            )
            if not track_matches:
                return None

            # --- Step 2: Filtra per similarità titolo ---
            valid_candidates = []
            for t in track_matches:
                found_title = t.get("name", "")
                ratio = SequenceMatcher(
                    None, clean_title.lower(), found_title.lower()
                ).ratio()
                if ratio >= self.TITLE_RATIO_MIN:
                    listeners = int(t.get("listeners", 0))
                    valid_candidates.append({
                        "artist": t.get("artist", ""),
                        "title":  found_title,
                        "listeners": listeners,
                        "ratio": ratio
                    })

            if not valid_candidates:
                print(f"     ⚠️ [Last.fm] Nessun candidato con titolo simile per '{title}'")
                return None

            # --- Step 3: Miglior candidato per listener count ---
            best = max(valid_candidates, key=lambda x: x["listeners"])
            best_artist    = best["artist"]
            best_listeners = best["listeners"]

            # --- Step 4: Listener count del current_artist ---
            current_listeners = self._get_track_listeners(clean_title, current_artist)

            print(f"     📊 [Last.fm] '{current_artist}' ({current_listeners:,}) vs '{best_artist}' ({best_listeners:,})")

            # --- Step 5: Valuta lo swap ---
            if best_artist.lower() == current_artist.lower():
                # Already the most popular version
                return None

            if best_listeners == 0:
                return None

            # Protezione contro swap indesiderati quando la cover è già nota
            if current_listeners > 0:
                ratio = best_listeners / current_listeners
            else:
                ratio = float("inf")  # current ha 0 listener → swap sicuro

            if ratio >= self.SWAP_RATIO_THRESHOLD:
                print(f"     🔄 [Last.fm] Swap: '{current_artist}' → '{best_artist}' (ratio listener: {ratio:.1f}x)")
                return (best_artist, None, best_listeners)
            else:
                print(f"     ✋ [Last.fm] Swap bloccato: ratio {ratio:.1f}x < {self.SWAP_RATIO_THRESHOLD}x (cover abbastanza nota)")
                return None

        except Exception as e:
            print(f"⚠️ [Last.fm] Errore get_most_popular_version per '{title}': {e}")
            return None

    # ------------------------------------------------------------------
    # Helper: recupera il listener count di una specifica coppia titolo/artista
    # ------------------------------------------------------------------
    def _get_track_listeners(self, title, artist):
        """
        Recupera il numero di listener unici per titolo+artista tramite track.getInfo.
        Restituisce 0 in caso di errore o brano non trovato.
        """
        if not artist:
            return 0
        try:
            params = {
                "method": "track.getInfo",
                "track": title,
                "artist": artist,
                "api_key": self.api_key,
                "format": "json"
            }
            resp = self.session.get(self.BASE_URL, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                track_info = data.get("track", {})
                return int(track_info.get("listeners", 0))
        except Exception:
            pass
        return 0
