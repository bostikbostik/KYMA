import musicbrainzngs
import time
import re
import requests
import json
from difflib import SequenceMatcher
from text_utils import TextUtils
import os

class MetadataManager:
    def __init__(self):
        # Configurazione MusicBrainz
        musicbrainzngs.set_useragent("KYMA_MusicRecognition", "1.0", "kyma@esempio.com")
        
        # Configurazione iTunes e Deezer
        self.itunes_url = "https://itunes.apple.com/search"
        self.deezer_search_url = "https://api.deezer.com/search"
        
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "KYMA/1.0 (music-recognition-app)"})
        
        # Import lazy di MusixmatchCatalog per evitare import circolare
        from musixmatch_catalog import MusixmatchCatalog
        self.mxm_catalog = MusixmatchCatalog()
        
        print("📚 Metadata Manager (Aggregation Mode: ON) Pronto.")

    # Aggiunta di nomi al set con pulizia e capitalizzazione
    def _add_to_set(self, source_set, names_str):
        """Helper per pulire e aggiungere nomi separati da virgola al set"""
        if not names_str: return
        # Rimuove etichette tra parentesi tipo (Apple) o (produttore) se presenti
        clean_str = re.sub(r"\(.*?\)", "", names_str)
        # Divide per virgola, slash o &
        parts = re.split(r'[,/&]', clean_str)
        for p in parts:
            p = p.strip()
            if len(p) > 2: 
                # Capitalizza ogni parola
                source_set.add(p.title())

    # Controllo duplicati sui compositori con fuzzy matching
    def _fuzzy_clean_composers(self, composers_set):
        """
        Rimuove SOLO i duplicati simili (es. 'De Benedettis' vs 'De Benedittis').
        Mantiene tutto il resto.
        """
        if not composers_set:
            return []

        # Convertiamo in lista e ordiniamo per lunghezza decrescente
        sorted_names = sorted(list(composers_set), key=len, reverse=True)
        unique_names = []

        for name in sorted_names:
            is_duplicate = False
            for existing in unique_names:
                # Se la similarità è alta (> 0.85) o uno è contenuto nell'altro lo consideriamo duplicato
                ratio = SequenceMatcher(None, name.lower(), existing.lower()).ratio()
                
                if ratio > 0.85:
                    is_duplicate = True
                    break
                
                if len(name) > 4 and name.lower() in existing.lower():
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_names.append(name)

        return unique_names

    # Metodo principale per trovare i compositori, con strategia di ricerca multi-fonte e fallback intelligente
    def find_composer(self, title, detected_artist, isrc=None, upc=None, setlist_artist=None, raw_acr_meta=None):
        clean_title = TextUtils.clean_for_search(title)
        search_title = clean_title if len(clean_title) > 2 else title
        
        print(f"\n🔎 [META] Aggregazione Dati per: '{search_title}' (Art: '{detected_artist}')")

        found_composers = set()
        final_cover = None
        
        artists_to_try = []
        if setlist_artist: artists_to_try.append(setlist_artist)
        if detected_artist and detected_artist != setlist_artist: artists_to_try.append(detected_artist)

        # 1. MUSIXMATCH ISRC (Fonte più affidabile — fonte discografica certificata)
        # Se Musixmatch trova l'ISRC, lo usiamo al posto di quello di ACRCloud (spesso assente)
        print("   🎫 [Musixmatch] Ricerca ISRC certificato...")
        # Guard: se artists_to_try è vuota, usa detected_artist come fallback (mai None)
        artist_for_isrc = (artists_to_try[0] if artists_to_try else detected_artist) or ""
        mxm_isrc = self.mxm_catalog.get_track_isrc(search_title, artist_for_isrc)
        if mxm_isrc:
            # Sovrascriviamo l'ISRC da ACRCloud con quello più affidabile di Musixmatch
            isrc = mxm_isrc
            print(f"     -> ISRC Musixmatch: {isrc} (override ISRC ACRCloud)")


        # 2. MUSICBRAINZ via ISRC (Metodo più preciso in assoluto)
        print("   🧠 [MB] Scansione MusicBrainz...")
        mb_found = False
        if isrc:
            res = self._search_mb_by_isrc(isrc)
            if res: 
                print(f"     -> Trovato via ISRC: {res}")
                self._add_to_set(found_composers, res)
                mb_found = True

        if not mb_found:
            for artist in artists_to_try:
                res = self._strategy_musicbrainz(search_title, artist)
                if res: 
                    print(f"     -> Trovato via Search: {res}")
                    self._add_to_set(found_composers, res)
                    mb_found = True
                    break

        # 3. ITUNES (Fonte secondaria affidabile)
        if not mb_found:
            print("   🍏 [Apple] Scansione iTunes...")
            for artist in artists_to_try:
                comp, cover = self._search_itunes(search_title, artist)
                if cover and not final_cover: final_cover = cover
                if comp:
                    print(f"     -> Trovato su iTunes: {comp}")
                    self._add_to_set(found_composers, comp)
                    break

        # 4. ACRCLOUD NATIVE & DEEZER (Ultima spiaggia)
        if len(found_composers) == 0:
            print("   ⚠️ Risultati scarsi, attivo scansione profonda (ACR/Deezer)...")
            if raw_acr_meta and "contributors" in raw_acr_meta:
                composers_list = raw_acr_meta["contributors"].get("composers", [])
                for c in composers_list: self._add_to_set(found_composers, c)

            for artist in artists_to_try:
                comp, cover = self._search_deezer(search_title, artist)
                if cover and not final_cover: final_cover = cover
                if comp:
                    self._add_to_set(found_composers, comp)
                    break
        
        # --- CLEANUP FINALE ---
        cleaned_list = self._fuzzy_clean_composers(found_composers)

        if not cleaned_list:
            final_composer_str = "Sconosciuto"
        else:
            final_composer_str = ", ".join(sorted(cleaned_list))
            print(f"   ✅ [AGGR] Lista Finale Compositori: {final_composer_str}")

        return final_composer_str, final_cover

    # MOTORI DI RICERCA DEI SINGOLI PROVIDER

    # iTunes
    def _search_itunes(self, title, artist):
        try:
            # 1. Tentativo SPECIFICO (Titolo + Artista Semplificato)
            simple_artist = re.sub(r"(?i)\b(feat\.|ft\.|&|the)\b.*", "", artist).strip()
            params = {
                "term": f"{title} {simple_artist}",
                "media": "music",
                "entity": "song",
                "limit": 5,
                "country": "IT",
            }
            resp = self.session.get(self.itunes_url, params=params, timeout=5)
            results = resp.json().get("results", []) if resp.status_code == 200 else []

            # 2. Tentativo FALLBACK (Solo Titolo - Utile se l'artista è poco riconoscibile o omonimo)
            if not results:
                params["term"] = title
                resp = self.session.get(self.itunes_url, params=params, timeout=5)
                results = resp.json().get("results", []) if resp.status_code == 200 else []

            target_norm = TextUtils.clean_for_search(artist)
            
            for res in results:
                track_name = res.get("trackName", "")
                artist_name = res.get("artistName", "")
                
                # Controllo similarità titolo (>60%)
                if SequenceMatcher(None, title.lower(), track_name.lower()).ratio() < 0.6: 
                    continue
                
                # Controllo presenza artista (per evitare omonimie nel fallback)
                found_art_clean = TextUtils.clean_for_search(artist_name)
                if target_norm in found_art_clean or found_art_clean in target_norm:
                    cover = res.get('artworkUrl100', '').replace('100x100', '600x600')
                    composer = res.get('composerName')
                    
                    if cover or composer:
                        return composer, cover
        except: pass
        return None, None

    # Deezer
    def _search_deezer(self, title, artist):
        try:
            query = f"{title} {artist}"
            params = {"q": query, "limit": 3}
            resp = self.session.get(self.deezer_search_url, params=params, timeout=4)
            if resp.status_code != 200: return None, None
            
            data = resp.json()
            target_norm = TextUtils.clean_for_search(artist)
            title_norm = TextUtils.clean_for_search(title)

            for res in data.get("data", []):
                found_title = TextUtils.clean_for_search(res.get("title", ""))
                if SequenceMatcher(None, title_norm, found_title).ratio() < 0.6: continue
                
                found_artist = TextUtils.clean_for_search(res.get("artist", {}).get("name", ""))
                if target_norm not in found_artist and found_artist not in target_norm: continue

                cover = res.get('album', {}).get('cover_medium', None)
                composer = None
                
                try:
                    track_resp = self.session.get(f"https://api.deezer.com/track/{res['id']}", timeout=3)
                    if track_resp.status_code == 200:
                        contributors = track_resp.json().get("contributors", [])
                        comps_list = []
                        for p in contributors:
                            if p.get("role") in ["Composer", "Writer", "Author"]:
                                comps_list.append(p.get("name"))
                        if comps_list:
                            composer = ", ".join(list(set(comps_list)))
                except: pass
                
                if cover or composer:
                    return composer, cover
        except: pass
        return None, None

    # MusicBrainz
    def _strategy_musicbrainz(self, title, artist):
        try:
            query = f'recording:"{title}" AND artist:"{artist}"'
            res = musicbrainzngs.search_recordings(query=query, limit=3)
            if res.get("recording-list"):
                for r in res["recording-list"]:
                    c = self._get_comp(r["id"])
                    if c: return c
            
            time.sleep(0.5) 
            query_w = f'work:"{title}" AND artist:"{artist}"'
            res_w = musicbrainzngs.search_works(query=query_w, limit=3)
            if res_w.get("work-list"):
                return self._extract_comp(res_w["work-list"][0])
        except: pass
        return None

    # Ricerca diretta via ISRC (se disponibile, è il metodo più preciso)
    def _search_mb_by_isrc(self, isrc):
        try:
            res = musicbrainzngs.get_recordings_by_isrc(isrc, includes=["work-rels", "artist-rels"])
            if res.get("isrc", {}).get("recording-list"):
                return self._extract_comp(res["isrc"]["recording-list"][0])
        except: return None

    # Estrazione compositori da MB con gestione relazioni complesse
    def _get_comp(self, rid):
        try:
            time.sleep(0.5)
            rec = musicbrainzngs.get_recording_by_id(rid, includes=["work-rels", "artist-rels"])
            return self._extract_comp(rec["recording"])
        except: return None

    # Estrazione compositori da una work di MB, con fallback su relazioni più profonde
    def _extract_comp(self, data):
        comps = set()
        if "artist-relation-list" in data:
            for r in data["artist-relation-list"]:
                if r["type"] in ["composer", "writer"]:
                    comps.add(r["artist"]["name"])
        
        if not comps and "work-relation-list" in data:
            try:
                wid = data["work-relation-list"][0]["work"]["id"]
                w = musicbrainzngs.get_work_by_id(wid, includes=["artist-rels"])["work"]
                if "artist-relation-list" in w:
                    for r in w["artist-relation-list"]:
                        if r["type"] in ["composer", "writer", "lyricist"]:
                            comps.add(r["artist"]["name"])
            except: pass
            
        return ", ".join(comps) if comps else None