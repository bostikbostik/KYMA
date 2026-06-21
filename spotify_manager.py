import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
import re
from dotenv import load_dotenv
from text_utils import TextUtils

load_dotenv()

class SpotifyManager:
    def __init__(self):
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        
        self.sp = None
        if client_id and client_secret:
            try:
                auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
            except Exception as e:
                print(f"⚠️ [Spotify] Errore Auth: {e}")
        else:
            print("⚠️ [Spotify] Credenziali mancanti nel .env")

    def get_artist_complete_data(self, artist_name):
        """
        Recupera i brani per la whitelist del concerto:
        - Top 10 Tracks (Hit storiche)
        - Brani dell'ultimo Album (Novità del tour)
        """
        if not self.sp: return []
        
        collected_songs = set()
        print(f"🎧 [Spotify] Scarico Hit e Ultimo Album per: {artist_name}...")

        try:
            # 1. Cerca l'artista
            results = self.sp.search(q=artist_name, type='artist', limit=1)
            items = results['artists']['items']
            if not items:
                print("     ❌ Artista non trovato su Spotify.")
                return []
            
            artist_id = items[0]['id']

            # 2. Prendi le Top 10 Tracks
            top_tracks = self.sp.artist_top_tracks(artist_id, country='IT')
            for track in top_tracks['tracks']:
                clean_name = TextUtils.clean_for_search(track['name'])
                collected_songs.add(clean_name)
            
            # 3. Prendi l'ultimo Album (Cruciale per i nuovi tour)
            albums = self.sp.artist_albums(artist_id, album_type='album', limit=1)
            if albums['items']:
                latest_album = albums['items'][0]
                album_tracks = self.sp.album_tracks(latest_album['id'])
                for track in album_tracks['items']:
                    clean_name = TextUtils.clean_for_search(track['name'])
                    collected_songs.add(clean_name)

            print(f"     📥 [Spotify] {len(collected_songs)} brani pronti per Whitelist.")
            return list(collected_songs)

        except Exception as e:
            print(f"❌ Errore Spotify (get_artist_complete_data): {e}")
            return []

    def get_hd_cover(self, title, artist):
        """
        Recupera la copertina in alta definizione (600x600).
        """
        if not self.sp: return None
        
        # Pulizia leggera per la ricerca
        clean_title = TextUtils.clean_for_search(title)

        search_query = f"track:{clean_title} artist:{artist}"
        try:
            results = self.sp.search(q=search_query, type='track', limit=1)
            items = results['tracks']['items']
            if items and items[0]['album']['images']:
                # Restituisce l'immagine più grande (solitamente la prima nell'array)
                return items[0]['album']['images'][0]['url']
        except Exception as e: 
            print(f"⚠️ [Spotify] Errore recupero Cover HD: {e}")
        
        return None