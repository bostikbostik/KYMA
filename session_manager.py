import threading
import time
import re
import unicodedata
from datetime import datetime
from threading import Lock
from metadata_manager import MetadataManager
from spotify_manager import SpotifyManager
from musixmatch_catalog import MusixmatchCatalog
from lastfm_catalog import LastFmCatalog
from difflib import SequenceMatcher
from text_utils import TextUtils
from werkzeug.security import generate_password_hash, check_password_hash

# Collegamento a Firestore
try:
    from firebase_admin import firestore
except ImportError:
    firestore = None

class SessionManager:
    def __init__(self, db_instance, lyrics_bot=None):
        self.db = db_instance
        self.playlist = []
        self.known_songs_cache = {}
        self.meta_bot = MetadataManager()
        self.spotify_bot = SpotifyManager()
        self.catalog_bot = MusixmatchCatalog()
        self.lastfm_bot = LastFmCatalog()
        self.lyrics_bot = lyrics_bot  # Riferimento a LyricsManager per recupero LRC on-demand
        self.lock = Lock()
        
        # Default user ID (modalità ospite/iniziale)
        self.user_id = "demo_user_01"
        self.session_ref = None
        self.user_ref = None

        # Mappa alias compositori
        self.composer_map = {}

        if self.db:
            self._refresh_composer_map()
            # Creiamo una sessione iniziale di default
            self._start_new_firestore_session()

    # Creazione sessione Firestore
    def _start_new_firestore_session(self):
        """Crea un nuovo documento sessione su Firestore per l'utente CORRENTE."""
        if not self.db: return

        try:
            self.user_ref = self.db.collection('users').document(str(self.user_id))
            session_id = f"session_{int(time.time())}"
            self.session_ref = self.user_ref.collection('sessions').document(session_id)
            
            # 1. Crea la sessione
            self.session_ref.set({
                'created_at': firestore.SERVER_TIMESTAMP,
                'status': 'live',
                'device': 'python_backend',
                'song_count': 0  # Inizializziamo contatore canzoni a 0
            }, merge=True)
            
            # 2. AGGIORNAMENTO STATS UTENTE: Incrementa contatore sessioni totali
            self.user_ref.set({
                'stats': {
                    'total_sessions': firestore.Increment(1)
                }
            }, merge=True)
            
            print(f"🔥 Nuova Sessione Firestore creata: users/{self.user_id}/sessions/{session_id}")
            
        except Exception as e:
            print(f"❌ Errore creazione sessione Firestore: {e}")

    # METODI DI GESTIONE UTENTE E AUTENTICAZIONE
    # Registrazione
    def register_user(self, user_data):
        """Registra utente con inizializzazione statistiche."""
        if not self.db: return {"success": False, "error": "Database offline"}

        username = user_data.get("username", "").strip()
        email = user_data.get("email", "").strip()
        role = user_data.get("role")
        
        if not username or not email:
            return {"success": False, "error": "Username ed Email obbligatori"}

        users_ref = self.db.collection('users')
        
        if users_ref.document(username).get().exists:
            return {"success": False, "error": "Username già utilizzato"}
        
        if any(users_ref.where("email", "==", email).stream()):
            return {"success": False, "error": "Email già utilizzata"}

        hashed_pw = generate_password_hash(user_data.get("password"))

        new_user = {
            "nome": user_data.get("nome"),
            "cognome": user_data.get("cognome"),
            "username": username,
            "email": email,
            "password": hashed_pw,
            "role": role,
            "birthdate": user_data.get("birthdate"),
            "created_at": firestore.SERVER_TIMESTAMP,
            # --- INIZIALIZZAZIONE STATISTICHE A ZERO ---
            "stats": {
                "total_sessions": 0,
                "total_songs": 0
            }
        }
        if role == "composer":
            new_user["stage_name"] = user_data.get("stage_name", "").strip()

        try:
            users_ref.document(username).set(new_user)
            print(f"👤 Nuovo utente registrato: {username}")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    #Login
    def login_user(self, identifier, password, required_role):
        """Login che aggiorna l'utente corrente e crea una nuova sessione."""
        if not self.db: 
            if identifier == "admin" and password == "admin": return {"success": True}
            return {"success": False, "error": "Database offline"}

        users_ref = self.db.collection('users')
        user_data = None
        
        # Ricerca utente (Username o Email)
        doc = users_ref.document(identifier).get()
        if doc.exists:
            user_data = doc.to_dict()
        else:
            query = users_ref.where("email", "==", identifier).limit(1).stream()
            for q_doc in query:
                user_data = q_doc.to_dict()
                identifier = user_data.get('username', identifier) # Normalizziamo identifier allo username
                break
        
        if not user_data:
            return {"success": False, "error": "Utente non trovato"}

        if not check_password_hash(user_data['password'], password):
            return {"success": False, "error": "Password errata"}

        if user_data.get('role') != required_role:
            return {"success": False, "error": f"Ruolo errato. Richiesto: {required_role}"}

        # === AGGIORNIAMO L'UTENTE E LA SESSIONE ===
        self.user_id = identifier
        print(f"✅ Login effettuato come: {self.user_id}")
        
        # Resettiamo la memoria locale
        self.clear_session() 
        
        return {"success": True, "user": user_data}
    
    #Logout
    def logout_user(self):
        """Resetta l'utente corrente a quello di default (Ospite)."""
        self.user_id = "demo_user_01"
        # Resetta anche la sessione in memoria per evitare mix di dati
        self.clear_session()
        print("👋 Logout effettuato. Tornato a demo_user_01.")
        return {"success": True}

    # Aggiornamento dati utente
    def update_user_data(self, old_username, new_data):
        """Aggiorna username e/o password."""
        if not self.db: return {"success": False, "error": "DB Offline"}
        
        users_ref = self.db.collection('users')
        user_doc_ref = users_ref.document(old_username)
        
        if not user_doc_ref.get().exists:
            return {"success": False, "error": "Utente non trovato"}

        updates = {}
        new_username = new_data.get("new_username")
        new_password = new_data.get("new_password")

        # Se cambia username, dobbiamo creare nuovo doc, copiare dati e cancellare vecchio (limitazione di Firebase)
        # Ma per semplicità, se cambia username, verifichiamo prima che non esista
        if new_username and new_username != old_username:
            if users_ref.document(new_username).get().exists:
                return {"success": False, "error": "Nuovo username già in uso"}
            
            # Copia dati
            old_data = user_doc_ref.get().to_dict()
            old_data['username'] = new_username
            if new_password:
                old_data['password'] = generate_password_hash(new_password)
            
            # Crea nuovo
            try:
                users_ref.document(new_username).set(old_data)
                # NOTA: al momento in caso di cambio username perdiamo lo storico sessioni e stats personali, perché sono legati al vecchio username.
                user_doc_ref.delete()                
                self.user_id = new_username
                return {"success": True, "new_username": new_username}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Se cambia solo password
        if new_password:
            updates['password'] = generate_password_hash(new_password)
            try:
                user_doc_ref.update(updates)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        return {"success": True, "message": "Nessuna modifica richiesta"}

    # Cancellazione account
    def delete_full_account(self, username):
        """Cancella l'utente e tenta di pulire le sue sessioni."""
        if not self.db: return {"success": False, "error": "DB Offline"}
        
        try:
            user_ref = self.db.collection('users').document(username)
            
            # 1. Cancellazione manuale delle sessioni (Firestore non ha cascade delete automatico)
            # Recupera tutte le sessioni
            sessions = user_ref.collection('sessions').stream()
            for sess in sessions:
                # Recupera canzoni della sessione
                songs = sess.reference.collection('songs').stream()
                for song in songs:
                    song.reference.delete()
                # Cancella sessione
                sess.reference.delete()
            
            # 2. Cancella documento utente
            user_ref.delete()
            
            print(f"🗑️ Account {username} eliminato definitivamente.")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- GESTIONE DATI SU DB ---
    # Salvataggio canzone
    def _save_song_to_db(self, song):
        if not self.session_ref: return
        try:
            doc_ref = self.session_ref.collection('songs').document(str(song['id']))
            # Campi esclusi da Firestore:
            # - synced_lyrics: contenuto Musixmatch → regola "no persistent storage" del Musicathon
            # - play_offset_ms / recognition_ms: dati temporanei di sync, validi solo per la sessione live
            # - plain_lyrics: contenuto Musixmatch → regola "no persistent storage" del Musicathon
            
            EXCLUDE_FROM_DB = {'plain_lyrics', 'play_offset_ms', 'recognition_ms', '_raw_meta'}
            db_entry = {k: v for k, v in song.items() if k not in EXCLUDE_FROM_DB}
            doc_ref.set(db_entry)
            print(f"☁️ Salvato su Cloud ({self.user_id}): {song['title']}")
        except Exception as e:
            print(f"❌ Errore scrittura Firestore: {e}")


    # Aggiornamento singolo campo (es. composer dopo arricchimento)
    def _update_single_field(self, song_id, field, value):
        if not self.session_ref: return
        # Non persistiamo su Firestore i campi con contenuto Musixmatch o dati temporanei di sync
        EXCLUDE_FROM_DB = {'plain_lyrics', 'play_offset_ms', 'recognition_ms', '_raw_meta'}
        if field in EXCLUDE_FROM_DB:
            return
        try:
            doc_ref = self.session_ref.collection('songs').document(str(song_id))
            doc_ref.update({field: value})
        except Exception as e:
            print(f"❌ Errore update campo '{field}': {e}")


    # Confronto fuzzy tra canzoni per evitare duplicati simili
    def _are_songs_equivalent(self, new_s, existing_s):
        if existing_s.get('is_deleted', False): return False
        tit_new = TextUtils.normalize_for_match(new_s['title'])
        tit_ex = TextUtils.normalize_for_match(existing_s['title'])
        art_new = TextUtils.normalize_for_match(new_s['artist'])
        art_ex = TextUtils.normalize_for_match(existing_s['artist'])
        title_similarity = SequenceMatcher(None, tit_new, tit_ex).ratio()
        if title_similarity > 0.90:
            if art_new == art_ex or art_new in art_ex or art_ex in art_new: return True
            art_similarity = SequenceMatcher(None, art_new, art_ex).ratio()
            if art_similarity > 0.60: return True
            return False
        if title_similarity > 0.80:
            if art_new == art_ex or art_new in art_ex or art_ex in art_new:
                if abs(len(tit_new) - len(tit_ex)) > 4: return False
                return True
        return False

    # Aggiungi canzone 
    def add_song(self, song_data, target_artist=None):
        with self.lock:
            if song_data.get('status') != 'success':
                return {"added": False, "reason": "No match"}
            
            # --- SALVATAGGIO DATI ORIGINALI (Cruciali per il Report PDF Tecnico) ---
            raw_title_for_report = song_data['title']
            raw_artist_for_report = song_data['artist']
            
            title = song_data['title']
            artist = song_data['artist']
            
            # Pulizia base del titolo (come nel tuo codice originale)
            clean_title_base = re.sub(r"[\(\[].*?[\)\]]", "", title).strip()
            clean_title_base = re.sub(r"(?i)\b(live\s+(at|in|from|on))\b.*", "", clean_title_base)
            clean_title_base = re.sub(r"(?i)\s-\s.*live.*", "", clean_title_base)
            clean_title_base = re.sub(r"(?i)\b(feat\.|ft\.|remix|edit|version)\b.*", "", clean_title_base).strip()

            # --- 1. FILTRO ANTI-DOPPIONI PREVENTIVO (Spietato sul titolo) ---
            # Controlliamo se c'è già una canzone con questo stesso titolo pulito
            norm_title_in = TextUtils.normalize_for_match(clean_title_base)
            for existing in self.playlist[-30:]: # Limitiamo agli ultimi 30 per performance
                if not existing.get('is_deleted', False):
                    if TextUtils.normalize_for_match(existing['title']) == norm_title_in:
                        return {"added": False, "reason": "Duplicate Title", "song": existing}

            # --- 2. LOGICA DI NORMALIZZAZIONE (Last.fm & Bias) ---
            if target_artist:
                # Modalità CONCERTO: Verifichiamo se l'artista è già lui o se ha fatto questo brano
                t_norm = TextUtils.normalize_for_match(target_artist)
                a_norm = TextUtils.normalize_for_match(artist)
                                
                if t_norm in a_norm or a_norm in t_norm:
                    print(f"🎯 [Bias] Artista target '{target_artist}' confermato nativamente. Skip popolarità.")
                    title = clean_title_base
                else:
                    match_info = self.catalog_bot.search_specific_version(clean_title_base, target_artist)
                    if match_info:
                        new_art, _ = match_info
                        print(f"🔄 [Bias Musixmatch] Trovata versione target: {new_art}")
                        artist = new_art
                        title = clean_title_base
            else:
                # Modalità LIVE BAND: Evitiamo cover sconosciute cercando la Hit Globale
                better_version = self.lastfm_bot.get_most_popular_version(clean_title_base, artist)
                if better_version:
                    new_artist, _, _ = better_version
                    print(f"🔄 [Popolarità Last.fm] Normalizzato verso hit originale: {new_artist}")
                    artist = new_artist
                    title = clean_title_base

            # --- 3. RECUPERO COVER HD (Spotify) ---
            # Ora che l'artista è "giusto", chiediamo a Spotify la copertina
            cover_url = self.spotify_bot.get_hd_cover(title, artist)
            if not cover_url:
                cover_url = song_data.get('cover') # Fallback su ACRCloud

            candidate_song = {
                'title': title, 'artist': artist,
                'duration_ms': song_data.get('duration_ms', 0),
                'cover': cover_url
            }

            # --- 4. SECONDO CHECK DOPPIONI (Post-Normalizzazione) ---
            # Usiamo la tua funzione originale per sicurezza estrema (fuzzy check)
            for existing_song in self.playlist[-30:]:
                if self._are_songs_equivalent(candidate_song, existing_song):
                    return {"added": False, "reason": "Duplicate After Norm", "song": existing_song}
            
            # --- 5. PREPARAZIONE SALVATAGGIO ---
            track_key = f"{title} - {artist}".lower()
            cached_entry = self.known_songs_cache.get(track_key)
            next_id = len(self.playlist) + 1
            
            if cached_entry:
                composer_name = cached_entry['composer']
                cover_url = cached_entry.get('cover') or cover_url
                status_enrichment = "Done"
            else:
                composer_name = "⏳ Ricerca..."
                status_enrichment = "Pending"

            # Creazione dizionario completo con TUTTI i tuoi dati originali ripristinati
            new_entry = {
                "id": next_id, 
                "title": title,
                "artist": artist,
                "composer": composer_name,      
                "album": song_data.get('album', 'Sconosciuto'),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "duration_ms": song_data.get('duration_ms', 0),
                "isrc": song_data.get('isrc'), 
                "upc": song_data.get('upc'), 
                "cover": cover_url,
                "_raw_meta": song_data.get('external_metadata', {}), 
                "original_title": raw_title_for_report, 
                "original_artist": raw_artist_for_report, 
                "original_composer": composer_name,
                "plain_lyrics": song_data.get('plain_lyrics', None),   # Offset Karaoke
                "recognition_ms": int(datetime.now().timestamp() * 1000), # Timestamp backend esatto (ms epoch) — usato per sync lyrics preciso
                "confirmed": True,
                "is_deleted": False,
                "manual": False
            }


            self.playlist.append(new_entry)
            self._save_song_to_db(new_entry)

            # Aggiornamento statistiche personali
            self._update_user_personal_stats(title, artist)

            if status_enrichment == "Pending":
                threading.Thread(target=self._background_enrichment, args=(new_entry, target_artist), daemon=True).start()

            print(f"✅ Aggiunto: {title} - {artist}")
            return {"added": True, "song": new_entry}

    # Arricchimento dati in background (compositori ed album cover)
    def _background_enrichment(self, entry, target_artist):
        attempts = 0
        found_composer = "Sconosciuto"
        final_cover = entry.get('cover')
        
        # Tentativi multipli per gestire eventuali errori temporanei di rete o API
        while attempts < 3:
            try:
                comp_result, cover_fallback = self.meta_bot.find_composer(
                    title=entry['title'], detected_artist=entry['artist'],
                    isrc=entry.get('isrc'), upc=entry.get('upc'),
                    setlist_artist=target_artist, raw_acr_meta=entry.get('_raw_meta')
                )
                found_composer = comp_result
                if not final_cover and cover_fallback: final_cover = cover_fallback
                break 
            except:
                attempts += 1
                time.sleep(1)

        # Aggiorniamo la canzone in playlist e DB SOLO se abbiamo trovato un compositore valido o una cover migliore,
        # per evitare di sovrascrivere dati buoni con "Sconosciuto" in caso di errori temporanei
        with self.lock:
            target_song = next((s for s in self.playlist if s['id'] == entry['id']), None)
            if target_song:
                target_song['composer'] = found_composer
                self._update_single_field(target_song['id'], 'composer', found_composer)
                
                if target_song.get('original_composer') == "⏳ Ricerca...":
                     target_song['original_composer'] = found_composer
                     self._update_single_field(target_song['id'], 'original_composer', found_composer)

                if final_cover and final_cover != target_song.get('cover'):
                    target_song['cover'] = final_cover
                    self._update_single_field(target_song['id'], 'cover', final_cover)

                # --- SYNC LYRICS: recupera Plain Text se non già presente ---
                if not target_song.get('plain_lyrics') and self.lyrics_bot:
                    try:
                        lyrics_data = self.lyrics_bot.get_best_lyrics(
                            title=target_song['title'],
                            artist=target_song.get('artist'),
                            duration_ms=target_song.get('duration_ms')
                        )
                        if lyrics_data:
                            if lyrics_data["type"] == "plain":
                                target_song['plain_lyrics'] = lyrics_data["text"]
                                self._update_single_field(target_song['id'], 'plain_lyrics', lyrics_data["text"])
                                print(f"   📄 [Lyrics] Plain Text aggiunto a '{target_song['title']}' via enrichment")
                    except Exception as e:
                        print(f"   ⚠️ [Sync] Errore recupero testi in enrichment: {e}")

                if found_composer not in ["Sconosciuto", "Errore Conn."]:
                    track_key = f"{target_song['title']} - {target_song['artist']}".lower()
                    self.known_songs_cache[track_key] = target_song.copy()

                if found_composer != "Sconosciuto":
                    self._update_global_stats(found_composer, target_song['title'])

    # --- GESTIONE STATISTICHE COMPOSITORI E PROFILI UTENTE ---
    def get_composer_stats(self, stage_name):
        if not self.db: return {"error": "DB Offline"}
        
        comp_id = TextUtils.normalize_for_match(stage_name).replace(" ", "_")
        doc_ref = self.db.collection('stats_composers').document(comp_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            return {
                "total_plays": 0,
                "total_revenue": 0.0,
                "top_tracks": [],
                "history": {},
                "display_name": stage_name
            }

        data = doc.to_dict()
        
        # Recupero tracce top
        tracks_ref = doc_ref.collection('top_tracks').stream()
        tracks = [{"title": t.get("title"), "count": t.get("play_count")} for t in [d.to_dict() for d in tracks_ref]]
        top_5 = sorted(tracks, key=lambda x: x['count'], reverse=True)[:5]

        # Recupero storico mensile
        hist_ref = doc_ref.collection('history').stream()
        history = {d.id: d.to_dict().get("play_count") for d in hist_ref} 

        return {
            "total_plays": data.get("total_plays", 0),
            "total_revenue": data.get("total_revenue", 0.0), 
            "top_tracks": top_5,
            "history": history,
            "display_name": data.get("display_name", stage_name)
        }
    
    # Recupero sessione precedente (ultima con canzoni valide) (per crash o chiusure errate)
    def recover_last_session(self):
        if not self.db or self.user_id == "demo_user_01":
            return {"success": False, "message": "Funzione non disponibile per ospiti o offline."}

        try:
            sessions_ref = self.user_ref.collection('sessions')
            query = sessions_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(25)
            last_sessions = list(query.stream())

            if not last_sessions:
                return {"success": False, "message": "Nessuna sessione trovata nello storico."}

            found_playlist = []
            target_session_doc = None

            for session_doc in last_sessions:
                songs_ref = session_doc.reference.collection('songs')
                songs_docs = list(songs_ref.stream())
                
                if len(songs_docs) > 0:
                    target_session_doc = session_doc
                    for doc in songs_docs:
                        found_playlist.append(doc.to_dict())
                    break 
            
            if not found_playlist or not target_session_doc:
                return {"success": False, "message": "Trovate sessioni recenti, ma sono tutte vuote."}

            found_playlist.sort(key=lambda x: int(x['id']) if isinstance(x['id'], int) else 0)

            with self.lock:
                self.playlist = found_playlist
                self.known_songs_cache = {
                    f"{s['title']} - {s['artist']}".lower(): s
                    for s in found_playlist
                }
                self.session_ref = target_session_doc.reference

            print(f"♻️ Ripristinata sessione del {target_session_doc.id}: {len(self.playlist)} brani.")
            return {"success": True, "count": len(self.playlist)}

        except Exception as e:
            print(f"❌ Errore recupero sessione: {e}")
            return {"success": False, "message": str(e)}
    
    # Recupero playlist corrente (per interfaccia o API)
    def get_playlist(self):
        with self.lock:
            return [dict(song) for song in self.playlist]

    # Pulizia sessione (reset completo, ad esempio dopo logout o per iniziare da zero)
    def clear_session(self):
        with self.lock:
            self.playlist = []
            self.known_songs_cache = {}
            self._start_new_firestore_session()
            return True

    # Aggiornamento statistiche globali compositori (incremento plays, top tracks, storico)
    def _update_global_stats(self, composer_raw, title):
        if not self.db or not composer_raw or composer_raw in ["Sconosciuto", "Pending", "⏳ Ricerca..."]:
            return

        # Pulizia stringa compositori
        composers = [c.strip() for c in composer_raw.replace("/", ",").split(",") if len(c.strip()) > 2]
        
        month_key = datetime.now().strftime("%Y-%m")

        batch = self.db.batch()
        
        for comp in composers:
            # Risoluzione alias per gestire nomi d'arte
            comp_id = self._resolve_composer_id(comp)
            
            if not comp_id: continue

            comp_ref = self.db.collection('stats_composers').document(comp_id)
            
            # Prepariamo i dati da aggiornare
            stats_update = {
                'total_plays': firestore.Increment(1),
                'last_updated': firestore.SERVER_TIMESTAMP,
                'last_detected_name': comp 
            }
            
            # Se il documento non esiste (nuovo autore), impostiamo anche il display_name.            
            batch.set(comp_ref, stats_update, merge=True)

            # Aggiornamento Top Tracks (sotto l'ID unificato)
            track_ref = comp_ref.collection('top_tracks').document(TextUtils.normalize_for_match(title).replace(" ", "_"))
            batch.set(track_ref, {
                'title': title,
                'play_count': firestore.Increment(1)
            }, merge=True)

            # Aggiornamento Storico
            hist_ref = comp_ref.collection('history').document(month_key)
            batch.set(hist_ref, {
                'date': month_key,
                'play_count': firestore.Increment(1)
            }, merge=True)

        try:
            batch.commit()
            print(f"📈 Stats aggiornate (Plays + Tracks) per ID unificati: {[self._resolve_composer_id(c) for c in composers]}")
        except Exception as e:
            print(f"❌ Errore aggiornamento stats: {e}")
    
    # Aggiornamento statistiche personali utente (totale canzoni, top tracks personali)
    def _update_user_personal_stats(self, title, artist):
        """Aggiorna le statistiche aggregate personali dell'utente."""
        if not self.db or self.user_id == "demo_user_01": return

        try:
            batch = self.db.batch()
            
            # 1. Incrementa contatore globale canzoni
            batch.set(self.user_ref, {
                'stats': {'total_songs': firestore.Increment(1)}
            }, merge=True)
            
            # 2. Incrementa contatore brani nella sessione corrente
            if self.session_ref:
                batch.update(self.session_ref, {'song_count': firestore.Increment(1)})

            # 3. Aggiorna Top Tracks Personali
            track_id = TextUtils.normalize_for_match(f"{title} - {artist}").replace(" ", "_")
            track_stats_ref = self.user_ref.collection('stats_tracks').document(track_id)
            
            batch.set(track_stats_ref, {
                'title': title,
                'artist': artist,
                'play_count': firestore.Increment(1),
                'last_played': firestore.SERVER_TIMESTAMP
            }, merge=True)

            batch.commit()
        except Exception as e:
            print(f"⚠️ Errore aggiornamento stats personali: {e}")
    
    # Rimuovi canzone (soft delete, per mantenere integrità storica e stats)
    def delete_song(self, song_id):
        with self.lock:
            try:
                song_id = int(song_id)
                for song in self.playlist:
                    if song['id'] == song_id:
                        song['is_deleted'] = True
                        self._update_single_field(song_id, 'is_deleted', True)
                        print(f"🗑️ Soft Delete (Marked): ID {song_id}")
                        return True
                return False
            except ValueError: return False

    # Recupero statistiche profilo utente (totale sessioni, totale canzoni, top artist, top tracks)
    def get_user_profile_stats(self):
        """Recupera stats, calcolando le sessioni valide dinamicamente."""
        if not self.db or not self.user_ref: 
            return {"total_sessions": 0, "total_songs": 0, "top_artist": "N/D", "top_tracks": []}
        
        try:
            doc_snap = self.user_ref.get()
            if not doc_snap.exists: return {}
            user_doc = doc_snap.to_dict()
            stats = user_doc.get('stats', {})
            
            total_songs = stats.get('total_songs', 0)
            valid_history = self.get_user_session_history()
            total_sessions_valid = len(valid_history)
            
            # Recupera Top Tracks
            top_tracks = []
            try:
                tracks_ref = self.user_ref.collection('stats_tracks')\
                    .order_by('play_count', direction=firestore.Query.DESCENDING).limit(5)
                for doc in tracks_ref.stream(): top_tracks.append(doc.to_dict())
            except: pass
            
            top_artist = top_tracks[0]['artist'] if top_tracks else "N/D"

            return {
                "total_sessions": total_sessions_valid,
                "total_songs": total_songs,
                "top_artist": top_artist,
                "top_tracks": top_tracks
            }
        except Exception as e:
            print(f"❌ Errore stats: {e}")
            return {}

    # Recupero storico sessioni utente (solo quelle con canzoni valide)
    def get_user_session_history(self):
        """Recupera le ultime sessioni IGNORANDO quelle vuote (song_count=0)."""
        if not self.db or not self.user_ref: return []
        
        try:
            history = []
            sessions_ref = self.user_ref.collection('sessions')
            
            # Recuperiamo tutto lo stream (limitato a 50 per sicurezza)
            # Non usiamo where('song_count', '>', 0) lato server per evitare problemi di indici mancanti
            sessions = sessions_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(50).stream()
            
            for s in sessions:
                data = s.to_dict()
                s_count = data.get('song_count', 0)
                
                # Se la sessione è vuota, la saltiamo
                if s_count == 0:
                    continue

                created = data.get('created_at')
                date_str = "Data sconosciuta"
                
                if created:
                    try:
                        if hasattr(created, 'strftime'):
                            date_str = created.strftime("%d/%m/%Y • %H:%M")
                        elif hasattr(created, 'to_datetime'):
                             date_str = created.to_datetime().strftime("%d/%m/%Y • %H:%M")
                    except: pass
                
                history.append({
                    "id": s.id,
                    "date": date_str,
                    "song_count": s_count,
                    "status": data.get('status', 'closed')
                })
            
            return history
        except Exception as e:
            print(f"❌ Errore fetch history: {e}")
            return []
        

    # Recupero canzoni di una sessione passata specifica (per visualizzazione dettagliata o ripristino)
    def get_past_session_songs(self, session_id):
        """Recupera i brani di una sessione specifica archiviata."""
        if not self.db or not self.user_ref: return []
        
        try:
            sess_ref = self.user_ref.collection('sessions').document(session_id)
            songs_ref = sess_ref.collection('songs')
            
            # Recupera i brani
            songs = []
            for doc in songs_ref.stream():
                songs.append(doc.to_dict())
            
            # Ordina per ID o Timestamp
            songs.sort(key=lambda x: int(x.get('id', 0)))
            return songs
        except Exception as e:
            print(f"❌ Errore recupero sessione passata: {e}")
            return []
        
    # Finalizzazione sessione e distribuzione revenue ai compositori
    def finalize_session_revenue(self, total_org_revenue):
        if not self.db or total_org_revenue <= 0:
            return {"success": False, "message": "Dati non validi o DB offline"}

        if not self.session_ref:
            return {"success": False, "message": "Nessuna sessione attiva trovata"}

        # Controllo anti-duplicazione per evitare revenue in eccesso
        # Leggiamo lo stato attuale della sessione dal DB
        session_snap = self.session_ref.get()
        if session_snap.exists:
            session_data = session_snap.to_dict()
            # Se è già segnata come 'paid', blocchiamo la finalizzazione
            if session_data.get('revenue_status') == 'paid':
                print(f"🛑 Tentativo di doppio pagamento bloccato per sessione {self.session_ref.id}")
                return {"success": False, "message": "Questa sessione è già stata pagata/liquidata."}

        # Logica standard di distribuzione revenue
        valid_songs = [s for s in self.playlist if not s.get('is_deleted', False)]
        if not valid_songs:
            return {"success": False, "message": "Nessun brano valido"}

        self._refresh_composer_map()

        rights_pot = total_org_revenue * 0.10
        value_per_song = rights_pot / len(valid_songs)

        print(f"💰 Finalizzazione: Incasso €{total_org_revenue}. Per brano: €{value_per_song:.2f}")

        try:
            batch = self.db.batch()
            
            # A. Distribuzione ai compositori
            for song in valid_songs:
                composer_raw = song.get('composer', "")
                if not composer_raw or composer_raw in ["Sconosciuto", "Pending", "⏳ Ricerca..."]:
                    continue

                composers = [c.strip() for c in composer_raw.replace("/", ",").split(",") if len(c.strip()) > 2]
                if not composers: continue

                value_per_composer = value_per_song / len(composers)

                for comp_name in composers:
                    final_id = self._resolve_composer_id(comp_name)
                    comp_ref = self.db.collection('stats_composers').document(final_id)
                    
                    batch.set(comp_ref, {
                        'last_detected_name': comp_name,
                        'total_revenue': firestore.Increment(value_per_composer),
                        'last_updated': firestore.SERVER_TIMESTAMP
                    }, merge=True)

            # Segniamo la sessione come 'paid' per evitare future modifiche o doppie finalizzazioni
            batch.update(self.session_ref, {
                'revenue_status': 'paid',     
                'final_revenue_amount': total_org_revenue,
                'closed_at': firestore.SERVER_TIMESTAMP
            })

            batch.commit()
            return {"success": True}

        except Exception as e:
            print(f"❌ Errore finalizzazione: {e}")
            return {"success": False, "message": str(e)}
        
   # Aggiornamento mappa alias compositori
    def _refresh_composer_map(self):
        """
        Scarica gli utenti 'composer' e crea le associazioni:
        - Nome d'arte -> ID Nome d'arte
        - Nome Reale + Cognome -> ID Nome d'arte
        """
        if not self.db: return
        print("🔄 Aggiornamento mappa alias compositori...")
        
        self.composer_map = {} # Reset mappa
        
        try:
            # Scarica tutti i compositori
            users_ref = self.db.collection('users').where('role', '==', 'composer').stream()
            
            for doc in users_ref:
                data = doc.to_dict()
                
                # Dati grezzi dal DB
                stage_name = data.get('stage_name', '').strip()
                nome = data.get('nome', '').strip()
                cognome = data.get('cognome', '').strip()
                
                # Se non c'è stage name, usiamo il nome reale come fallback
                if not stage_name: continue

                # ID DESTINAZIONE: Sarà sempre il nome d'arte normalizzato (es. "tropico")
                # Questo è l'ID del documento dove finiscono i soldi
                target_id = TextUtils.normalize_for_match(stage_name).replace(" ", "_")
                
                # CHIAVE 1: Nome d'arte (es. "tropico" -> "tropico")
                key_stage = TextUtils.normalize_for_match(stage_name)
                if key_stage:
                    self.composer_map[key_stage] = target_id
                
                # CHIAVE 2: Nome Reale Completo (es. "davide_petrella" -> "tropico")
                if nome and cognome:
                    full_name_raw = f"{nome} {cognome}"
                    key_real = TextUtils.normalize_for_match(full_name_raw).replace(" ", "_")
                    self.composer_map[key_real] = target_id
                    
                    # DEBUG: Stampiamo risultato per controllo
                    print(f"   🔗 Alias creato: '{key_real}' -> '{target_id}'")

            print(f"✅ Mappa Alias pronta: {len(self.composer_map)} voci.")
            
        except Exception as e:
            print(f"⚠️ Errore refresh mappa: {e}")

    # Funzione helper per risolvere l'ID
    def _resolve_composer_id(self, raw_name):
        # Pulisce la stringa in arrivo dai metadati (es. "Davide Petrella")
        clean_key = TextUtils.normalize_for_match(raw_name).replace(" ", "_")
        # Cerca nella mappa alias. Se trova "davide_petrella", restituisce "tropico".
        # Se non trova nulla, restituisce "davide_petrella" (creando un nuovo profilo slegato).
        return self.composer_map.get(clean_key, clean_key)
    
    # Funzione di migrazione dati legacy (da alias a profili principali)
    def migrate_legacy_data(self):
        """
        Sposta i dati dai profili 'alias' (es. davide_petrella) 
        ai profili 'principali' (es. tropico) ed elimina i vecchi.
        """
        if not self.db: return {"success": False, "message": "DB Offline"}
        
        # 1. Assicuriamoci di avere la mappa aggiornata
        self._refresh_composer_map()
        
        migrated_count = 0
        logs = []

        # 2. Iteriamo su tutti gli alias conosciuti
        # source_key = "davide_petrella" (chi deve sparire)
        # target_id = "tropico" (chi deve ricevere i dati)
        for source_key, target_id in self.composer_map.items():
            
            # Se la chiave è uguale al target, è il profilo principale. Saltiamo.
            if source_key == target_id: 
                continue

            source_ref = self.db.collection('stats_composers').document(source_key)
            target_ref = self.db.collection('stats_composers').document(target_id)

            # Controlliamo se esiste il profilo "sbagliato" (vecchio)
            source_snap = source_ref.get()
            if not source_snap.exists:
                continue

            print(f"📦 Migrazione in corso: {source_key} -> {target_id}...")
            source_data = source_snap.to_dict()
            
            # A. SPOSTIAMO I TOTALI (Plays e Revenue)
            plays_to_move = source_data.get('total_plays', 0)
            revenue_to_move = source_data.get('total_revenue', 0.0)

            if plays_to_move > 0 or revenue_to_move > 0:
                target_ref.set({
                    'total_plays': firestore.Increment(plays_to_move),
                    'total_revenue': firestore.Increment(revenue_to_move),
                    'last_updated': firestore.SERVER_TIMESTAMP
                }, merge=True)

            # B. SPOSTIAMO LE SOTTO-COLLEZIONI (Top Tracks)
            # Dobbiamo leggere ogni brano del vecchio profilo e sommarlo al nuovo
            tracks = source_ref.collection('top_tracks').stream()
            for t in tracks:
                t_data = t.to_dict()
                t_id = t.id # ID del documento (titolo normalizzato)
                t_plays = t_data.get('play_count', 0)
                t_title = t_data.get('title', 'Sconosciuto')

                target_track_ref = target_ref.collection('top_tracks').document(t_id)
                target_track_ref.set({
                    'title': t_title,
                    'play_count': firestore.Increment(t_plays)
                }, merge=True)
                
                # Cancelliamo la traccia vecchia
                t.reference.delete()

            # C. SPOSTIAMO LO STORICO (History)
            history = source_ref.collection('history').stream()
            for h in history:
                h_data = h.to_dict()
                h_id = h.id # es. "2023-10"
                h_plays = h_data.get('play_count', 0)

                target_hist_ref = target_ref.collection('history').document(h_id)
                target_hist_ref.set({
                    'date': h_id,
                    'play_count': firestore.Increment(h_plays)
                }, merge=True)
                
                # Cancelliamo lo storico vecchio
                h.reference.delete()

            # D. CANCELLIAMO IL PROFILO VECCHIO
            source_ref.delete()
            
            msg = f"✅ Migrato {source_key}: +{plays_to_move} plays, +€{revenue_to_move:.2f}"
            logs.append(msg)
            print(msg)
            migrated_count += 1

        return {"success": True, "migrated": migrated_count, "logs": logs}