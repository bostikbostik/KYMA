![KYMA](link_alla_tua_cover_image.png)

# KYMA
> **Real-time music recognition and live lyrics provider powered by Musixmatch**

**🏆 Submission for the Musixmatch Musicathon**

**Author:** Bo Lorenzo

---

## 🎬 Demo Video
[Guarda la demo di 90 secondi su YouTube](link_al_tuo_video_youtube)

---

## 🎵 Descrizione del Progetto
**KYMA** è una web app completa progettata per arricchire l'esperienza degli eventi musicali dal vivo, offrendo un riconoscimento accurato in tempo reale e un accesso immediato ai testi sincronizzati e ai metadati dei brani eseguiti.

Utilizzando un motore di riconoscimento ibrido (Audio + Testo) e integrandosi profondamente con le **API di Musixmatch**, KYMA "ascolta" le performance live (come concerti o tribute band), riconosce le canzoni in tempo reale, e mostra i testi sincronizzati (LRC) a schermo, recuperando inoltre i dettagli precisi sui compositori di ogni specifica traccia.

---

## 🌟 Come utilizziamo Musixmatch (Core Feature)
Musixmatch è il cuore del nostro sistema di riconoscimento e fornitura testi:
* **`track.search`**: Per scaricare il repertorio di un artista (modalità Tribute Band) e favorire un match estremamente preciso.
* **`matcher.subtitle.get`**: Per mostrare a schermo i **testi sincronizzati in tempo reale (LRC)** dei brani riconosciuti durante l'esibizione.
* **`matcher.lyrics.get`**: Fallback intelligente per ottenere i testi completi in plain text.
* **`matcher.track.get`**: Per recuperare l'**ISRC ufficiale** del brano e garantire l'accuratezza nell'identificazione dei compositori e degli autori.

---

## 🚀 Funzionalità Principali

### 🧠 Motore di riconoscimento ibrido
* **Integrazione con ACRCloud:** Utilizza il confronto di campioni audio per ottenere un riconoscimento musicale ad alta precisione.
* **ElevenLabs Scribe:** Utilizza un modello di IA per trascrivere il testo cantato dal vivo in tempo reale, fornendo una validazione aggiuntiva per il riconoscimento.
* **Decisione smart:** Incrociando l'audio puro e il testo trascritto con il database di Musixmatch, il software garantisce un match corretto anche per cover e arrangiamenti live.

### 🌍 Attenzione al contesto e ai Testi
* **Live Music & Tribute Band:** Inserendo il nome dell'artista omaggiato, KYMA ottimizza la ricerca testuale e audio focalizzandosi su quel repertorio specifico.
* **Aggregazione dei metadati:** Il software effettua una ricerca approfondita per estrarre la lista corretta e completa dei compositori e degli autori originali per ciascun brano rilevato.

### ⏱️ Gestione della sessione Live
* **Testi in tempo reale:** L'interfaccia mostra in tempo reale le canzoni rilevate e permette l'accesso immediato al testo del brano.
* **Modifiche manuali:** Durante o dopo la sessione, è possibile correggere o annotare manualmente l'esito dei riconoscimenti.

---

## 🛠️ Info Tecniche

### Backend
* **Linguaggio:** Python 3.x
* **Framework:** Flask
* **Audio Processing:** numpy, scipy, sounddevice
* **APIs:**
    * **Musixmatch API** (Lyrics, LRC, Search, ISRC)
    * ACRCloud (Audio Fingerprinting) 
    * ElevenLabs (Speech-to-Text)
    * Spotify Web API / MusicBrainz (Metadati extra)

### Frontend
* **Struttura:** HTML5, CSS3
* **Logica:** Vanilla JavaScript (ES6+)
* **Real-time:** Meccanismo di polling per aggiornare la playlist e i testi live

---

## ⚙️ Installazione

### Prerequisiti
* Python 3.8+
* Chiavi API per Musixmatch, ACRCloud, ed ElevenLabs

### Passaggi

**1. Clona la repository**
```bash
git clone https://github.com/bostikbostik/KYMA.git
cd KYMA
```

**2. Installa le dipendenze**
```bash
pip install -r requirements.txt
```

**3. Configurazione dell'ambiente**
Crea un file `.env` nella cartella principale e aggiungi le tue chiavi API:
```env
MUSIXMATCH_API_KEY=your_musixmatch_key
ACR_HOST=Identify-EU-West-1.acrcloud.com
ACR_ACCESS_KEY=your_acr_key
ACR_ACCESS_SECRET=your_acr_secret
ELEVENLABS_API_KEY=your_elevenlabs_key
```

**4. Avvio dell'applicazione**
```bash
python app.py
```
L'applicazione si avvierà sul server locale: `http://localhost:5050`.