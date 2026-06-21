import re
import unicodedata

class TextUtils:
    
    @staticmethod
    def normalize_for_match(text):
        """
        Normalizzazione ESTREMA. 
        Usata per il controllo anti-doppioni (es. in SessionManager).
        Rimuove tutto: spazi, punteggiatura, accenti e parole di disturbo.
        """
        if not text: return ""
        # Rimuove contenuti tra parentesi
        text = re.sub(r"[\(\[\{].*?[\)\]\}]", "", text)
        
        # Rimuove "Live at...", "Live in..." in modo sicuro (senza distruggere brani come "Live Forever")
        text = re.sub(r"(?i)\b(live\s+(at|in|from|on))\b.*", "", text)
        
        # Rimuove parole di disturbo e tutto ciò che le segue
        text = re.sub(r"(?i)\b(amazon|apple|spotify|deezer|youtube|vevo|remaster|remix|edit|version|karaoke)\b.*", "", text)
        
        # Rimuove accenti (es. "più" -> "piu")
        text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode("utf-8")
        
        # Rimuove tutti i caratteri non alfanumerici (inclusi gli spazi!)
        clean = re.sub(r"[^a-zA-Z0-9]", "", text)
        return clean.strip().lower()

    @staticmethod
    def clean_for_search(text):
        """
        Pulizia BILANCIATA per le API.
        Usata per cercare brani su Spotify, Last.fm e MusicBrainz.
        Rimuove versioni tecniche e featuring, ma mantiene spazi e formattazione base.
        """
        if not text: return ""
        # Rimuove contenuti tra parentesi
        clean = re.sub(r"[\(\[].*?[\)\]]", "", text)
        
        # Rimuove "Live at...", "Live in..." in modo sicuro
        clean = re.sub(r"(?i)\b(live\s+(at|in|from|on))\b.*", "", clean)
        
        # Rimuove parole tecniche come remaster, feat, remix e ciò che le segue
        clean = re.sub(r"(?i)\b(feat\.|ft\.|remix|edit|version|remastered|remaster)\b.*", "", clean)
        
        # Rimuove suffissi dopo il trattino (es. " - Live at Wembley")
        clean = re.sub(r"(?i)\s-\s.*", "", clean)
        
        # Compatta eventuali doppi spazi lasciati dalle rimozioni precedenti
        clean = re.sub(r'\s+', ' ', clean)
        
        return clean.strip().lower()

    @staticmethod
    def clean_for_display(text):
        """
        Pulizia ESTETICA.
        Usata in AudioManager per mostrare a schermo o nel PDF un titolo leggibile.
        Rimuove solo la "spazzatura", mantenendo intatte le parentesi valide.
        """
        if not text: return ""
        
        junk_keywords = [
            "live", "remix", "edit", "club", "mix", "extended", "version", 
            "remaster", "re-master", "feat", "ft.", "karaoke", "instrumental", 
            "acoustic", "demo", "session", "registrazione", "mono", "stereo",
            "amazon music", "amazon original", "apple music", "spotify singles", 
            "spotify", "deezer", "youtube", "vevo", "presents", "exclusive"
        ]
        
        # Rimuove le parentesi SOLO se contengono una parola spazzatura
        def clean_parens(match):
            content = match.group(1).lower()
            if any(k in content for k in junk_keywords): return "" 
            return match.group(0)

        text = re.sub(r"\s*[\(\[](.*?)[\)\]]", clean_parens, text)
        
        # Controlla la parte dopo il trattino (" - ")
        parts = text.split(" - ")
        if len(parts) > 1:
            last_part = parts[-1].lower()
            if any(k in last_part for k in junk_keywords):
                text = " - ".join(parts[:-1])
                
        # Compatta eventuali doppi spazi
        text = re.sub(r'\s+', ' ', text)
                
        return text.strip()