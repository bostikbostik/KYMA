import os
import requests
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from collections import Counter
from langdetect import detect, LangDetectException
from musixmatch_catalog import MusixmatchCatalog
from text_utils import TextUtils

load_dotenv()

class LyricsManager:
    def __init__(self):
        self.musixmatch_token = os.getenv("MUSIXMATCH_API_KEY")
        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        
        self.base_url = "https://api.musixmatch.com/ws/1.1/"
        self.session = requests.Session()

        if not self.musixmatch_token:
            print("⚠️ [Lyrics] ATTENZIONE: Nessun MUSIXMATCH_API_KEY valido trovato nel file .env!")

        self.catalog_bot = MusixmatchCatalog()
        self.lyrics_cache = {}
        self.subtitles_cache = {}
        self.titles_map = {} 
        self.current_artist = None
        self.detected_language_code = None
        
        # Limitazione a 2 thread per evitare di sovraccaricare le API
        self.executor = ThreadPoolExecutor(max_workers=2)

    # Costruzione contesto artista bias
    def update_artist_context(self, artist_name):
        if not artist_name or artist_name == self.current_artist:
            return
        
        self.current_artist = artist_name
        self.lyrics_cache = {}
        self.subtitles_cache = {}
        self.titles_map = {}
        self.detected_language_code = None 
        
        print(f"📖 [Lyrics] Analisi artista: {artist_name}...")
        self.executor.submit(self._async_lyrics_flow_smart, artist_name)

    # Download testi asincrono
    def _async_lyrics_flow_smart(self, artist_name):
        start_time = time.time()
        try:
            print(f"    ⏳ [00s] Contatto Musixmatch Catalog...")
            all_songs = self.catalog_bot.get_artist_top_tracks(artist_name)
            
            # FILTRO INTELLIGENTE PRE-MUSIXMATCH
            target_songs = []
            seen_titles = set()
            for song in all_songs[:50]: 
                clean = song.lower().split(' - ')[0] 
                if clean not in seen_titles and "instrumental" not in clean and "karaoke" not in clean:
                    target_songs.append(song)
                    seen_titles.add(clean)
            
            # Limitiamo a 30 brani "buoni"
            target_songs = target_songs[:30]
            
            # FIX LINGUA: Calcoliamo la lingua dominante
            self.detected_language_code = self._detect_dominant_language(target_songs)
            print(f"    🌍 [Lingua] Rilevata lingua dominante per Scribe: {self.detected_language_code}")
            
            total = len(target_songs)
            
            if total == 0:
                print("    ⚠️ [Lyrics] Nessun brano trovato da scaricare.")
                return
                
            print(f"    🚀 [Musixmatch] Download SMART (2 thread) per {total} brani...")

            future_to_song = {
                self.executor.submit(self._fetch_single_lyric_smart, song, artist_name): song 
                for song in target_songs
            }
            
            count = 0
            for i, future in enumerate(as_completed(future_to_song), 1):
                song_title = future_to_song[future]
                try:
                    success = future.result()
                    if success: count += 1
                    if i % 5 == 0: print(f"       [{i}/{total}] ...processing...") 
                except Exception as e: 
                    pass # Manteniamo il flow pulito asincrono
            
            total_time = time.time() - start_time
            print(f"🏁 [Lyrics] FINITO in {total_time:.1f}s. Cache: {count}/{total} testi.")

        except Exception as e:
            print(f"❌ [Lyrics] Errore Flow: {e}")

    # Versione SEQUENZIALE
    def _sync_lyrics_flow(self, artist_name):
        start_time = time.time()
        try:
            print(f"    ⏳ [00s] Contatto Musixmatch Catalog...")
            all_songs = self.catalog_bot.get_artist_top_tracks(artist_name)
            
            spotify_time = time.time() - start_time
            print(f"    ✅ [{spotify_time:.1f}s] Catalog: Trovati {len(all_songs)} brani.")

            if not all_songs:
                print(f"⚠️ [Lyrics] Nessun brano trovato per l'artista.")
                return

            limit = 40
            target_songs = all_songs[:limit] if len(all_songs) > limit else all_songs

            self.detected_language_code = self._detect_dominant_language(target_songs)
            
            total = len(target_songs)
            print(f"    🐌 [Musixmatch] Avvio download SAFE (Sequenziale) per {total} brani...")

            count = 0
            
            for i, song_title in enumerate(target_songs, 1):
                try:
                    success = self._fetch_single_lyric_safe(song_title, artist_name)
                    
                    if success:
                        count += 1
                        print(f"       [{i}/{total}] ✅ {song_title}")
                    else:
                        print(f"       [{i}/{total}] ⏩ {song_title} (No testo)")
                    
                    time.sleep(random.uniform(0.5, 1.5))

                except Exception as e:
                    print(f"       [{i}/{total}] ❌ {song_title} - {e}")
            
            total_time = time.time() - start_time
            print(f"🏁 [Lyrics] FINITO in {total_time:.1f}s. Cache: {count}/{total} testi.")

        except Exception as e:
            print(f"❌ [Lyrics] Errore Flow: {e}")

    def _fetch_single_lyric_smart(self, title, artist):
        return self._fetch_from_musixmatch(title, artist)
    
    def _fetch_single_lyric_safe(self, title, artist):
        return self._fetch_from_musixmatch(title, artist)

    def _fetch_from_musixmatch(self, title, artist):
        if not self.musixmatch_token: return False
        
        clean_search_title = TextUtils.clean_for_search(title)
        norm_key = TextUtils.normalize_for_match(title)
        
        success = False
        try:
            # 1. Fetch plain lyrics
            lyrics_url = f"{self.base_url}matcher.lyrics.get"
            params = {
                "q_track": clean_search_title,
                "q_artist": artist or "",
                "apikey": self.musixmatch_token
            }
            resp = self.session.get(lyrics_url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                header_status = data.get("message", {}).get("header", {}).get("status_code")
                if header_status == 402:
                    print("   ⚠️ [Musixmatch] Rate limit giornaliero raggiunto (402). Interrompo download testi.")
                    return False  # Interrompe il batch corrente
                if header_status == 200:
                    lyrics_body = data["message"]["body"]["lyrics"]["lyrics_body"]
                    # TODO (compliance): chiamare pixel_tracking_url da data["message"]["body"]["lyrics"]["pixel_tracking_url"]
                    self.lyrics_cache[norm_key] = lyrics_body.lower()
                    self.titles_map[norm_key] = title
                    success = True
            
            # 2. Fetch subtitles (time-synced)
            subs_url = f"{self.base_url}matcher.subtitle.get"
            resp_subs = self.session.get(subs_url, params=params, timeout=5)
            if resp_subs.status_code == 200:
                data_subs = resp_subs.json()
                header_status_subs = data_subs.get("message", {}).get("header", {}).get("status_code")
                if header_status_subs == 200:
                    subtitle_body = data_subs["message"]["body"]["subtitle"]["subtitle_body"]
                    # TODO (compliance): chiamare pixel_tracking_url da data_subs["message"]["body"]["subtitle"]["pixel_tracking_url"]
                    self.subtitles_cache[norm_key] = subtitle_body
                    self.titles_map[norm_key] = title
                    success = True

            return success
        except Exception as e:
            print(f"       ⚠️ Errore download Musixmatch '{title}': {e}")
        return False

    def get_best_lyrics(self, title, artist=None, duration_ms=None):
        """
        Cerca testi sincronizzati (LRC). Se non li trova, fa fallback su testi semplici (plain text).
        Ritorna un dict: {"type": "lrc"|"plain", "text": "..."} oppure None.
        """
        if not title:
            return None

        norm_key = TextUtils.normalize_for_match(title)

        # 1. Cerca nella cache pre-scaricata (LRC)
        if norm_key in self.subtitles_cache:
            print(f"   🎤 [Lyrics] Cache HIT per '{title}' → LRC pronto")
            return {"type": "lrc", "text": self.subtitles_cache[norm_key]}

        # 2. Fallback on-demand a Musixmatch
        if not self.musixmatch_token:
            return None

        print(f"   🎤 [Lyrics] Cache MISS per '{title}' → Chiamata on-demand Musixmatch...")
        clean_title = TextUtils.clean_for_search(title)
        
        try:
            duration_ms = int(duration_ms) if duration_ms else 0
        except ValueError:
            duration_ms = 0

        def _try_match(q_track, q_artist):
            params = {
                "q_track": q_track,
                "q_artist": q_artist,
                "apikey": self.musixmatch_token
            }
            if duration_ms and duration_ms > 0:
                duration_s = int(duration_ms / 1000)
                params["f_subtitle_length"] = duration_s
                params["f_subtitle_length_max_deviation"] = 5

            # Tentativo 1: Testo Sincronizzato
            try:
                resp = self.session.get(f"{self.base_url}matcher.subtitle.get", params=params, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    h_status = data.get("message", {}).get("header", {}).get("status_code")
                    if h_status == 402:
                        print("   ⚠️ [Lyrics] Rate limit Musixmatch (402).")
                        return "rate_limit"
                    if h_status == 200:
                        sub_body = data.get("message", {}).get("body", {}).get("subtitle", {}).get("subtitle_body", "")
                        if sub_body:
                            self.subtitles_cache[norm_key] = sub_body
                            self.titles_map[norm_key] = title
                            print(f"   ✅ [Lyrics] LRC on-demand ottenuto per '{title}'")
                            return {"type": "lrc", "text": sub_body}
            except Exception as e:
                print(f"   ⚠️ [Lyrics] Errore matcher.subtitle.get per '{title}': {e}")

            # Tentativo 2: Testo Semplice
            try:
                params.pop("f_subtitle_length", None)
                params.pop("f_subtitle_length_max_deviation", None)
                resp2 = self.session.get(f"{self.base_url}matcher.lyrics.get", params=params, timeout=6)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    h_status2 = data2.get("message", {}).get("header", {}).get("status_code")
                    if h_status2 == 200:
                        lyrics_body = data2.get("message", {}).get("body", {}).get("lyrics", {}).get("lyrics_body", "")
                        if lyrics_body:
                            lyrics_body = lyrics_body.split('******* This Lyrics is NOT for Commercial use *******')[0].strip()
                            print(f"   ✅ [Lyrics] Plain Text fallback ottenuto per '{title}'")
                            return {"type": "plain", "text": lyrics_body}
            except Exception as e:
                print(f"   ⚠️ [Lyrics] Errore matcher.lyrics.get per '{title}': {e}")

            return None

        # Strategia 1: Match esatto pulito
        res = _try_match(clean_title, artist or self.current_artist or "")
        if res == "rate_limit": return None
        if res: return res

        # Strategia 2: Rimozione drastica di apostrofi (Musixmatch matcher è debole sugli apostrofi)
        clean_title_no_apos = clean_title.replace("'", "").replace("’", "").replace("`", "")
        clean_artist_no_apos = (artist or self.current_artist or "").replace("'", "").replace("’", "").replace("`", "")
        
        if clean_title_no_apos != clean_title or clean_artist_no_apos != (artist or self.current_artist or ""):
            res2 = _try_match(clean_title_no_apos, clean_artist_no_apos)
            if res2 == "rate_limit": return None
            if res2: return res2

        # Strategia 3: Fallback usando track.search senza artista (per cover e casi complessi)
        try:
            search_params = {
                "q_track": clean_title_no_apos,
                "apikey": self.musixmatch_token,
                "page_size": 5,
                "s_track_rating": "desc"
            }
            search_res = self.session.get(f"{self.base_url}track.search", params=search_params, timeout=6).json()
            matches = search_res.get("message", {}).get("body", {}).get("track_list", [])
            for m in matches:
                track = m.get("track", {})
                if track.get("has_subtitles") == 1 or track.get("has_lyrics") == 1:
                    track_id = track.get("track_id")
                    
                    if track.get("has_subtitles") == 1:
                        s_res = self.session.get(f"{self.base_url}track.subtitle.get", params={"track_id": track_id, "apikey": self.musixmatch_token}, timeout=6).json()
                        if s_res.get("message", {}).get("header", {}).get("status_code") == 200:
                            sub_body = s_res.get("message", {}).get("body", {}).get("subtitle", {}).get("subtitle_body", "")
                            if sub_body:
                                self.subtitles_cache[norm_key] = sub_body
                                self.titles_map[norm_key] = title
                                print(f"   ✅ [Lyrics] LRC on-demand ottenuto (via track search) per '{title}'")
                                return {"type": "lrc", "text": sub_body}
                    
                    if track.get("has_lyrics") == 1:
                        l_res = self.session.get(f"{self.base_url}track.lyrics.get", params={"track_id": track_id, "apikey": self.musixmatch_token}, timeout=6).json()
                        if l_res.get("message", {}).get("header", {}).get("status_code") == 200:
                            lyrics_body = l_res.get("message", {}).get("body", {}).get("lyrics", {}).get("lyrics_body", "")
                            if lyrics_body:
                                lyrics_body = lyrics_body.split('******* This Lyrics is NOT for Commercial use *******')[0].strip()
                                print(f"   ✅ [Lyrics] Plain Text fallback ottenuto (via track search) per '{title}'")
                                return {"type": "plain", "text": lyrics_body}
        except Exception as e:
            print(f"   ⚠️ [Lyrics] Errore fallback track.search per '{title}': {e}")

        return None



    def _detect_dominant_language(self, titles):
        if not titles: return None
        detected_langs = []
        iso_map = {'it': 'ita', 'en': 'eng', 'es': 'spa', 'fr': 'fra', 'de': 'deu', 'pt': 'por'}

        for t in titles:
            try:
                clean = re.sub(r"[\(\[].*?[\)\]]", "", t).strip()
                if len(clean) > 3:
                    lang = detect(clean)
                    detected_langs.append(lang)
            except LangDetectException: pass

        if not detected_langs: return None
        most_common = Counter(detected_langs).most_common(1)
        if most_common:
            return iso_map.get(most_common[0][0])
        return None

    # --- ELEVENLABS SCRIBE ---
    def transcribe_and_match(self, audio_buffer):
        if not self.elevenlabs_key: return None
        transcribed_text = self._call_scribe_api(audio_buffer, lang_code=self.detected_language_code)
        if not transcribed_text or len(transcribed_text) < 5: return None
        return self._find_best_match(transcribed_text)

    def _call_scribe_api(self, audio_buffer, lang_code=None):
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": self.elevenlabs_key}
        files = {"file": ("audio.wav", audio_buffer, "audio/wav")}
        data = {"model_id": "scribe_v1", "tag_audio_events": "false"}
        if lang_code: data["language_code"] = lang_code

        try:
            response = requests.post(url, headers=headers, files=files, data=data, timeout=10)
            if response.status_code == 200:
                text_result = response.json().get("text")
                if text_result:
                    print(f"    🗣️ [Scribe] Ha capito: '{text_result.strip()}'")
                    return text_result.strip()
                return ""
            else:
                print(f"⚠️ [Scribe] Errore API {response.status_code}: {response.text}")
        except Exception as e:
            print(f"❌ [Scribe] Caduta di connessione: {e}")
        return None

    def _find_best_match(self, transcript):
        if not self.lyrics_cache: return None

        transcript_clean = re.sub(r'[^\w\s]', '', transcript.lower()).strip()

        if len(transcript_clean) < 10: return None

        for title_key, lyrics in self.lyrics_cache.items():
            if transcript_clean in lyrics:
                return self._package_result(title_key, 100)

        transcript_words = [w for w in transcript_clean.split() if len(w) > 2]

        if len(transcript_words) < 2: return None

        best_ratio = 0.0
        best_title_key = None

        for title_key, lyrics in self.lyrics_cache.items():
            hits = 0
            for word in transcript_words:
                if word in lyrics: hits += 1
            ratio = hits / len(transcript_words)
            if ratio > best_ratio:
                best_ratio = ratio
                best_title_key = title_key
        if best_title_key and best_ratio > 0.60:
            return self._package_result(best_title_key, int(best_ratio * 100))
        return None

    def _package_result(self, title_key, score):
        real_title = self.titles_map[title_key]
        print(f"🧩 [Lyrics MATCH] Identificato: '{real_title}' (Confidence: {score}%)")
        
        # Include i subtitles se disponibili per questo brano
        synced_lyrics = self.subtitles_cache.get(title_key, None)
        
        return {
            "status": "success", "title": real_title, "artist": self.current_artist,
            "score": score, "type": "Lyrics Match", "duration_ms": 0,
            "album": "Sconosciuto", "external_metadata": {}, "contributors": {}, "cover": None,
            "synced_lyrics": synced_lyrics
        }