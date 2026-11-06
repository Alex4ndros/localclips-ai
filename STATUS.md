# Stato revisione — 2 novembre 2026

## Correzione 0.2.2: leggibilità sottotitoli

Tech Clean predefinito 66 px (+13,8%), bianco, bordo nero 4 px, ombra 1 px;
posizione invariata a 330 px dal fondo. Controlli collegati alla preview live,
selettore colore e pulsante per applicare i valori consigliati ai progetti esistenti.
Parametri comuni tra preview ed ASS; proxy renderizzato con lo stesso motore finale.
Modificati `domain.py`, `subtitles.py`, `preview.py`, `ui.py`; metadati versione e
documentazione aggiornati. `media.py`, `reframing.py` e `vision.py` invariati.

Due test aggiunti in `tests/test_subtitle_readability.py`: export reale 1080×1920
su sfondo chiaro e complesso, testo intero entro i margini, bordo nero presente,
nessuna interferenza col volto, comparsa/scomparsa ai timestamp e confronto proxy.
Verificati controlli live e testo su più righe. Frame esportati ispezionati visivamente;
risultati riproducibili in `examples/subtitle-readability`. Audio sintetico di prova:
il controllo verifica i timestamp, non l'accuratezza del riconoscimento del parlato.
La build 0.2.2 è stata avviata fuori dal repository con PATH limitato a Windows:
importazione, Smart Split, riproduzione proxy ed export riusciti, nessun errore.
Un export del vero EXE, con i nuovi valori predefiniti, coincide pixel per pixel
con il campione verificato nei cinque timestamp controllati. Report dedicato:
`examples/subtitle-readability/frozen-caption-checks.json`; MP4:
`examples/subtitle-readability/frozen-readable-1080p.mp4`.

## Correzione 0.2.1: webcam visibile una sola volta

Il crop inferiore ora esclude obbligatoriamente la webcam OBS. Mantiene il crop
richiesto quando valido; altrimenti cerca un rettangolo libero, privilegiando
regione selezionata, dimensioni utili e vicinanza. Nessuna maschera o ricostruzione.
L'esclusione resta fissa durante il tracking, separata dal ritaglio del volto;
rispetta i cambi sulla timeline e viene salvata nei preset/progetti. I vecchi
progetti usano automaticamente le coordinate webcam già disponibili.

Nuovo test con crop iniziale che includeva la webcam: tre frame dell'MP4 1080×1920
mostrano il marcatore solo sopra, zero pixel webcam sotto e zero pixel neri sotto.
Cerchio del contenuto senza deformazione, audio presente, stream decodificabile,
proxy confrontato col finale. Test geometrici in quattro angoli e al centro,
zoom/pan, tracking, ROI completamente coperta, webcam separata e persistenza.
Margine del volto verificato anche sul rilevamento YuNet di materiale NASA.
Il controllo GUI della build prova inoltre il ritorno automatico alla preview live
modificando un parametro dopo aver riprodotto il proxy.

Dettagli e file modificati: `WEBCAM-FIX.md`. Test riproducibile del pacchetto:
`python scripts/validate_portable.py C:/percorso/esterno --exclusion`.

## Priorità 1: composizione verticale

Corretto il precedente fit/pad che manteneva il desktop intero dentro il 9:16.
`reframing.py` è il motore indipendente condiviso da `media.py` e `preview.py`:
ritagli reali, crop per rapporto, scaling proporzionale, split, face, screen, PiP,
cambi temporali e tracking interpolato. `domain.py` valida e salva le decisioni.
`ui.py` offre selezione/spostamento/resize ROI, zoom, pan, rapporto, preset e cambi;
`timeline.py` aggiunge maniglie IN/OUT e marcatori.

Verifiche concrete: sintetico OBS 2560×1440 a 60 fps, webcam arancione in basso a destra,
schermo blu con testo, cerchi colorati e tono audio. MP4 esportato 1080×1920,
SAR 1:1, audio AAC. Ispezione di tre frame: regioni previste sopra/sotto, nessuna
grande banda nera, cerchi con rapporto entro 3%, sincronismo tono entro 60 ms.
Confronto pixel proxy/finale, tracking interpolato, cambio split→screen, webcam
separata con offset, decodifica completa. Campioni in `examples/smart-split`.

## Priorità 2: eseguibile Windows

Causa identificata: PyInstaller raccoglieva `icuuc.dll` da Poppler/libheif presente
nel PATH dell'ambiente Codex. La DLL esportava simboli ICU versionati, incompatibili
con i simboli non versionati richiesti da Qt. Non era un problema di file video.

`scripts/build.py`: PATH isolato, staging, controllo DLL inattesa, test GUI obbligatorio,
preservazione di dati e runtime precedente. `main.py`: logging prima degli import Qt.
Eseguibile canonico `dist/LocalClipsAI/LocalClipsAI.exe`.

La versione Smart Split è stata copiata ed eseguita fuori dal repository con PATH
limitato a Windows e senza variabili del virtualenv. Finestra visibile, import via
worker GUI, selezione split, proxy riprodotto e MP4 verticale esportato. Il test usa
le vere azioni dell'app e il decoder Qt, con screenshot e log; non è un test manuale
con clic del mouse in Esplora file. Anche la build finale ha superato lo stesso controllo:
`ok: true`, frame decodificato 360×640, nessun errore. Worker compilati: inferenza
CUDA reale e due esportazioni NVENC completate; dettagli in `bundle-results.json`.

## Priorità 3–6: implementato

- Sidebar Home/Analisi/Risultati/Editor/Esportazione/Impostazioni, dark mode.
- Preview live grande, miniature generate in background, preset e timeline IN/OUT.
- YuNet locale, priorità angoli/persistenza, affidabilità, rifiuto ambiguità e manual fallback.
- Smoothing e interpolazione continua del ritaglio tra campioni; cambi scena distanziati.
- File webcam separato con offset manuale e secondo decoder di anteprima.
- Whisper Small CPU/CUDA, VAD, italiano/inglese, timestamp parola e recupero trascrizione.
- Ranking offline migliorato, confini frase, tolleranza durata, deduplicazione lessicale.
- LM Studio solo loopback, contesto rilevato quando disponibile, chunk con sovrapposizione,
  JSON validato, titoli/descrizioni correggibili.
- ChatGPT facoltativo tramite flusso ufficiale OSS: PKCE/state/nonce, verifica JWT,
  consenso piano separato, token DPAPI, refresh, revoca, catalogo modelli, Responses SSE.
- Quattro stili sottotitoli ASS/SRT, editor testo/tempi, safe area configurabile.
- Export singolo/batch, NVENC→CPU, H.264/AAC, annullamento, log e progetti persistenti.

## Evidenza dei test

`test-results.xml`: suite automatica corrente; `portable-gui-results.json` e screenshot:
avvio esterno e workflow GUI; `bundle-results.json`: worker compilati CUDA e batch NVENC;
`inference-results.json`: prova Whisper reale CPU/CUDA su voce sintetica inglese.
I report riportano esecuzioni reali; test OAuth usano solo callback locale e token di test.
47 test superati nell'ultima suite completa. La verifica GUI attende un fotogramma
proxy realmente decodificato 360×640, evitando falsi positivi con il frame sorgente precedente.
Gli esiti e i percorsi della build distribuita sono nei report allegati.

## Limiti e verifiche mancanti

- Nessuna prova su un tuo OBS italiano reale di 20–40 minuti o benchmark di qualità editoriale.
- Il rilevamento webcam stima un rettangolo attorno al volto, non il bordo esatto OBS.
  Volti persistenti in pagine web possono confonderlo; rivedere sempre le proposte.
- Tracking su campioni, non su ogni frame; movimenti rapidi/cambi angolo richiedono correzione.
- Screen ROI basata sui bordi; niente OCR, identificazione di finestre o comprensione visiva.
- Dynamic decide da cambi scena, non distingue semanticamente spiegazione/dimostrazione.
- Ranking offline lessicale, senza embeddings o analisi prosodica. Semantica tramite LLM opzionale.
- LM Studio: integrazione implementata, da verificare con un modello/server reale dell'utente.
- ChatGPT: protocollo e sicurezza testati localmente; login, refresh/revoca remoti e inferenza
  con account reale non eseguiti. Nessun consumo di quota AI esterna durante lo sviluppo.
- Webcam separata: sincronizzazione manuale tramite offset, non correlazione audio automatica.
- Live preview: stessa geometria, testo semplificato; proxy ASS per karaoke e animazioni esatti.
- PiP in alto a destra; posizione libera del riquadro destinazione non ancora implementata.
- Nessun riallineamento parola dopo correzione manuale dei sottotitoli.
- Nessun taglio automatico silenzi, montaggio multi-intervallo, waveform o timeline multipista.
- Normalizzazione audio a un passaggio; niente loudness a due passaggi.
- Nessun installer/firma; onedir utilizzabile senza Python. Non verificato su Windows appena installato.
- Nessun test prolungato di esaurimento VRAM o copertura di tutte le configurazioni DPI/monitor.

Il software non è dichiarato equivalente a OpusClip e le funzioni mancanti non sono
rappresentate da pulsanti finti. La composizione manuale funziona senza modelli AI.
