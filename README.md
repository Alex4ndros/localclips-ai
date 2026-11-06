# LocalClips AI 0.2.2 — Smart Composition

Applicazione desktop Windows 11, PySide6, elaborazione locale e rendering FFmpeg.
Progetto aperto ai contributi: segnalazioni, miglioramenti e pull request sono
benvenuti, in italiano o inglese. Leggi [CONTRIBUTING.md](CONTRIBUTING.md) per
preparare l'ambiente, eseguire i test e proporre modifiche.
Questa revisione corregge il caricamento Qt dell'EXE e sostituisce il letterboxing
predefinito con un motore di ritaglio e composizione verticale reale.

La 0.2.2 migliora soltanto la leggibilità dei sottotitoli: Tech Clean passa da
58 a 66 px (+13,8%), testo bianco, contorno nero 4 px e ombra nera leggera 1 px
su canvas 1080×1920. La posizione resta invariata (margine inferiore 330 px).
Nell'Editor puoi regolare font, contorno, ombra, colore e posizione con feedback
immediato. I progetti salvati mantengono le proprie impostazioni: per aggiornarli
usa **Valori di leggibilità consigliati**. La preview renderizzata e l'MP4 usano
lo stesso ASS; la preview live condivide i parametri, con possibili piccole
differenze nella resa tipografica Qt. Nessuna nuova animazione o modifica al layout.
Campione verificato: `examples/subtitle-readability/readable-1080p.mp4`.

## Avvio dal codice sorgente (Windows 11)

Installa Python **3.12 x64** e Git, quindi clona il repository:

```powershell
git clone https://github.com/Alex4ndros/localclips-ai.git
cd localclips-ai
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1
.\.venv\Scripts\python.exe main.py
```

Il file delle dipendenze riproduce l'ambiente Windows usato per la build;
include runtime NVIDIA opzionali e il download può essere voluminoso. La CPU
funziona anche senza GPU NVIDIA. In alternativa al download FFmpeg, metti
`ffmpeg.exe` e `ffprobe.exe` in `tools/`, oppure rendili disponibili nel PATH.
FFmpeg deve supportare libx264, AAC e il filtro `subtitles` (libass).

YuNet e la sua licenza sono inclusi. Per la trascrizione scarica il modello
Whisper dalle Impostazioni dell'app: il primo download richiede Internet,
le elaborazioni successive sono locali. La composizione manuale non richiede
Whisper. I video, i progetti personali, i token e i modelli Whisper non sono
contenuti nel repository. L'integrazione ChatGPT è sperimentale; i limiti delle
verifiche sono elencati sotto e in [STATUS.md](STATUS.md).

## Avvio della distribuzione Windows

Le istruzioni seguenti valgono per una cartella onedir già compilata localmente;
il repository sorgente non contiene l'EXE né una release binaria pubblica.

Doppio clic su **Avvia LocalClips AI.lnk**, oppure su
**dist/LocalClipsAI/LocalClipsAI.exe**. Non serve Python né un terminale.
Mantieni insieme EXE, `_internal`, `tools`, `models`, `cuda` e `licenses`.
Usa una cartella scrivibile (es. Documenti). Il pacchetto include Whisper Small,
YuNet, FFmpeg/FFprobe e i runtime CUDA. LM Studio e ChatGPT sono facoltativi.

La cartella `dist/LocalClips-AI` appartiene alla versione precedente: usa il nuovo
percorso senza trattino. Progetti e file originali non vengono cancellati.
Build locale non firmata; distribuzione onedir, senza installer MSI.

## Prova immediata dello Smart Split, senza AI

Dal checkout sorgente genera prima i campioni con
`.\.venv\Scripts\python.exe scripts/generate_examples.py`.
Gli altri export, screenshot, progetti e report citati più sotto sono artefatti
delle verifiche locali, non file inclusi nel repository pubblico.

1. Importa `examples/smart-split/source-1440p.mp4` oppure un tuo video OBS.
2. Vai in Analisi → **Crea clip manuale**.
3. Nell'Editor scegli **Smart Split**.
4. Premi **Seleziona regione webcam**. Disegna il rettangolo attorno alla webcam.
   Trascina all'interno per spostarlo, l'angolo inferiore destro per ridimensionarlo,
   Shift + trascina per ridisegnarlo.
5. Con **Seleziona area schermo** delimita la parte della dimostrazione leggibile.
6. Regola **Altezza webcam**, zoom e posizione X/Y. La preview verticale cambia subito.
7. Usa le maniglie IN/OUT sulla timeline oppure i campi inizio/fine.
8. Premi **Genera anteprima verticale** per vedere anche il karaoke ASS esatto.
9. **Esporta questa clip** crea MP4 1080×1920 H.264/AAC, senza watermark.

Il nuovo test contro la duplicazione è `examples/no-duplicate/vertical-1080p.mp4`,
con frame estratto e misure in `pixel-report.json`. Il primo campione è
`examples/smart-split/vertical-1080p.mp4`;
`exported-frame.png` è estratto dall'MP4, non da un mockup.
Webcam arancione sopra, schermo blu sotto: i cerchi mantengono le proporzioni.
Puoi anche usare **Apri progetto** e selezionare `examples/smart-split/prova-split.lcproj`:
contiene già le regioni corrette e resta completamente modificabile.

## Composizioni

- **Smart Split**: ritaglio webcam sopra, ritaglio schermo sotto. Rapporto 20–65%,
  inizialmente 35/65. Ogni pannello riempie la propria area senza deformazioni.
- **Face Focus**: ritaglio webcam a piena altezza verticale.
- **Screen Focus**: regione schermo a pieno canvas.
- **Screen + Picture in Picture**: schermo pieno con webcam in alto a destra.
- **Dynamic**: cambi tra schermo e split basati su variazioni di scena, almeno 6 s
  tra cambi automatici. È una regola visiva iniziale, non comprensione dell'attività.
- **Composizione manuale**: geometria split modificabile e cambi sulla timeline.
- **Crop verticale**: posizione orizzontale tramite slider.
- **Adatta con bande**: vecchio letterbox disponibile solo per scelta esplicita.

**Salva layout / Carica layout** conserva preset locali. I cambi si inseriscono con
**Inserisci composizione qui**: valgono dal cursore in avanti. Doppio clic sul cambio
per raggiungerlo; rimuovilo per tornare alla composizione precedente. Inserire un
cambio manuale disattiva il tracking automatico. I progetti conservano questi dati.

Il programma copia i pixel della webcam incorporata; non ricostruisce ciò che essa
copre. Dalla 0.2.1 il contenuto inferiore esclude automaticamente il suo rettangolo,
anche se la regione schermo selezionata lo comprende. Usa **Area webcam OBS da escludere**
per correggere l'intero riquadro originale, inclusi bordi. Il rettangolo rosso nel
selettore è solo una guida: nell'MP4 non vengono applicate maschere o buchi.
**Bilancia webcam** azzera lo zoom aggiuntivo e adatta il rapporto del pannello
per preservare margini e proporzioni. I preset salvano anche l'area esclusa. Un ingrandimento
superiore a 2,5× genera un avviso: non può recuperare dettaglio assente nel sorgente.

## Automazione locale

**Analizza e genera clip** trascrive con faster-whisper, VAD e timestamp di parola.
Modello Small multilingue incluso, auto lingua / italiano / inglese, CUDA float16
con fallback CPU int8. Le trascrizioni salvate vengono riutilizzate.

La modalità **Offline** usa confini di frase, termini tematici, hook iniziali,
densità del parlato e diversità lessicale. Può superare moderatamente la durata
indicativa per finire una frase; non genera segmenti artificiali sul silenzio.
Non equivale alla comprensione semantica di un LLM e richiede revisione editoriale.
Il punteggio 0–100 non predice la viralità.

YuNet cerca volti persistenti negli angoli su campioni distribuiti della clip.
Volti centrali e candidati instabili sono penalizzati; due angoli altrettanto
plausibili richiedono selezione manuale. L'affidabilità è un indice euristico.
Se non è sufficiente, rimane Screen Focus e viene indicata la correzione necessaria.
La regione attorno al volto è stimata, non un riconoscimento esatto del bordo OBS.

Il tracking smussa i rilevamenti e interpola la posizione del ritaglio tra campioni;
non esegue face detection su ogni fotogramma. Preview ed export condividono geometria
e interpolazione. Per movimenti rapidi o webcam che cambia angolo usa i cambi manuali.
La regione dello schermo è proposta dalla densità di bordi/testo: controlla che
comprenda il contenuto utile, perché non è OCR o comprensione del software mostrato.

## Webcam separata

Nell'Editor, **Collega video webcam separato** aggiunge una seconda sorgente.
Il tempo letto dalla webcam è `tempo originale + offset`. Regola l'offset a mano
con un evento comune (es. battito di mani). L'audio finale proviene dal video principale.
La preview live usa un secondo decoder; la preview renderizzata verifica il sincronismo
esatto della pipeline finale. L'export rifiuta offset che superano la durata della webcam.
Non è implementata la sincronizzazione automatica tramite correlazione audio.

## LM Studio

Nelle Impostazioni scegli LM Studio, avvia il suo server locale e carica un modello.
Usa `http://127.0.0.1:1234/v1`, poi **Leggi modelli disponibili**.
Sono accettati solo indirizzi loopback; proxy e redirect HTTP sono esclusi.
Le trascrizioni lunghe sono divise in blocchi con sovrapposizione e timestamp assoluti.
Il contesto caricato viene letto dall'API LM Studio quando disponibile; altrimenti
imposta manualmente un valore non superiore al contesto effettivo del modello.

Il modello propone JSON con timestamp, titolo, descrizione, score, motivo e layout.
Le risposte vengono validate e riallineate ai confini di frase; intervalli inventati,
fuori durata o sovrapposti vengono scartati. Le regioni non vengono inventate dal LLM.
Titolo e descrizione restano modificabili nell'Editor. Non è necessario LM Studio
per importare, montare, trascrivere o esportare.

## ChatGPT facoltativo — integrazione in anteprima

La documentazione ufficiale consultata il 2 novembre 2026 prevede registrazione
dinamica per app locali/open source, senza segreto incorporato nel programma:
[registrazione](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[inferenza](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference),
[limiti](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

**Continua con ChatGPT** apre il browser di sistema. La casella separata **Autorizza
anche l'uso del mio piano ChatGPT** richiede gli scope del piano; il solo accesso
non abilita l'inferenza. Il callback usa 127.0.0.1, PKCE, state e nonce. L'app verifica
firma, issuer, audience, scadenza e identità dell'ID token. Non legge password o cookie.
I token sono cifrati da Windows DPAPI in `%LOCALAPPDATA%/LocalClipsAI/credentials.dpapi`,
fuori dal progetto e dal pacchetto. Refresh serializzato, account/workspace distinti,
revoca della sessione in disconnessione e cancellazione locale dei token.

Seleziona ChatGPT e leggi il catalogo modelli del tuo account. Ogni analisi richiede
una conferma esplicita: invia **solo trascrizione e timestamp**, mai video/audio.
Le chiamate usano esclusivamente Responses API pubblica, `store:false`, streaming;
sono accettate solo dopo `response.completed`. Errori o limiti non attivano servizi
alternativi. Può consumare quota e crediti già autorizzati in ChatGPT; controllali con
**Visualizza limiti del piano**. Il software non abilita crediti a pagamento da solo.

Protocollo e controlli sono testati localmente con risposte simulate e chiavi di test.
**Accesso e inferenza reali con un account ChatGPT non sono stati eseguiti**: disponibilità,
consenso e limiti effettivi dipendono dall'account. L'app resta utilizzabile offline.
Non è stata aggiunta una connessione API-key alternativa perché il flusso ufficiale
locale risulta documentato; nessuna chiave o credenziale viene inclusa nella build.

## Sottotitoli, salvataggio ed export

Minimal, Dynamic, Bold Social e Tech Clean; karaoke sincronizzato alle parole,
font/dimensioni/colori/bordo/ombra/posizione modificabili. Usa **Mostra / nascondi
sottotitoli** nell'Editor per testo, timing e suddivisione in righe. Dopo una correzione
manuale, il timing della riga resta valido, ma le parole non sono riallineate automaticamente.
La preview live mostra geometria e testo; per tipografia/animazione ASS esatte usa il proxy.
Safe area iniziali conservative, da rivedere sul contenuto e sulla piattaforma.

Salva `.lcproj`: comprende trascrizione, clip, regioni, tracking, cambi e stili.
I video sono riferimenti a file esterni. Snapshot dopo analisi in `data/recovery.lcproj`;
se un servizio AI fallisce, la trascrizione locale è recuperabile nel job come
`transcription-recovery.lcproj`. Non occorre ritrascrivere.

Export singolo/batch, 1080×1920 o 720×1280, 30/60 fps, bitrate configurabile, NVENC
provato realmente e fallback CPU. Audio originale, AAC; normalizzazione opzionale
−16 LUFS a passaggio unico. SRT relativo alla clip. Nessun watermark o pubblicazione
automatica. I file esistenti sono conservati; Annulla termina worker e processi figli.

## Diagnostica e limiti

- Startup: `data/startup.log`; job: `data/jobs/<id>/worker.log` e `native.log`.
- L'errore QtCore originale dipendeva da un `icuuc.dll` con ABI incompatibile,
  raccolto da strumenti di sviluppo estranei. La build ora isola PATH e verifica
  obbligatoriamente l'avvio della GUI compilata.
- Non copiare singole DLL da altri programmi. Mantieni integra la distribuzione.
- FFmpeg assente: indica la sua cartella in Impostazioni. CUDA assente/OOM: usa CPU.
- I modelli sono locali. Solo il download esplicito contatta Hugging Face; le modalità
  LM Studio/ChatGPT contattano il provider scelto come descritto sopra. Nessuna telemetria.
- Taglio silenzi, montaggio multi-intervallo, OCR e timeline multipista non sono inclusi.
- Non è stato fornito un tuo video reale da 20–40 minuti; la qualità italiana e
  editoriale su quel materiale non è ancora misurata. Vedi `STATUS.md` per la matrice completa.

## Build e test riproducibili

Python 3.12 x64; `scripts/build.ps1` installa `requirements-lock.txt`, esegue test,
raccoglie licenze e avvia `scripts/build.py`. Modelli e tools presenti nelle rispettive
cartelle vengono inclusi. Il build usa staging, preserva dati/esportazioni e salva
il runtime precedente. I backup locali non sono pubblicati.

```
python -m pytest tests -q
python scripts/build.py
python scripts/validate_portable.py C:/percorso/esterno/LocalClips-Test
python scripts/validate_bundle.py
```

Il test portabile avvia il vero EXE con PATH di Windows, directory di lavoro esterna,
nessun virtualenv; importa il campione, seleziona split, riproduce il proxy ed esporta.
I test di composizione ispezionano pixel, proporzioni, audio e decodifica dell'MP4.
Il test OAuth locale richiede che il sistema consenta connessioni TCP a 127.0.0.1.
Non richiede un account o chiamate AI reali. Vedi report XML/JSON allegati.
