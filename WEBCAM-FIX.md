# Correzione webcam duplicata — 0.2.1

Causa: il pannello schermo ritagliava la ROI senza un vincolo di esclusione della
webcam incorporata. Una ROI ampia o spostata verso l'angolo poteva mostrarla due volte.

## Comportamento corretto

- Esclusione geometrica obbligatoria con piccolo margine contro bordi/frange di compressione.
- Crop proporzionale in una regione libera, senza rettangoli neri, blur o inpainting.
- Conservazione esatta del crop manuale quando già valido. Altrimenti priorità a ROI,
  area utile e vicinanza; fallback fuori dalla ROI se tutta coperta o troppo sottile.
- Regione OBS indipendente dal tracking/zoom del volto, fissa durante ogni segmento.
- Se non esiste spazio libero, errore esplicito e selezione manuale; nessun MP4 errato.
- Webcam superiore: più margine nella proposta facciale automatica; comando Bilancia
  per centratura, zoom 1× e rapporto coerente con il rettangolo selezionato.
- Selezione schermo con area esclusa rossa, zoom/pan live e preset riutilizzabili.
- Modificando la composizione dal proxy si torna automaticamente alla preview live.

## File modificati

`localclips/reframing.py`: vincolo e ricerca dei crop liberi, geometria condivisa.
`domain.py`: persistenza e validazione del rettangolo OBS indipendente.
`vision.py`: proposta schermo su gruppi di bordi/testo e crop valido; margine volto.
`ui.py`, `preview.py`: selezione esplicita, bilanciamento, avvisi e preview immediata.
`gui_check.py`, `scripts/validate_portable.py`: test dell'EXE con ROI che include la webcam
ed ispezione dei pixel esportati. Test aggiornati in `tests/test_reframing.py`,
`test_ui_worker.py`, `test_vision.py`. Versione in `pyproject.toml`.

## Evidenza

`examples/no-duplicate/source-1440p.mp4`: OBS sintetico 2560×1440, webcam arancione
con cerchio magenta in basso a destra, desktop blu con testo e cerchio verde.
La ROI schermo comprende tutto il desktop, con pan a destra: il vecchio crop
(1314, 0, 1246, 1440) include il centro webcam. Il nuovo crop è
(648, 0, 1246, 1440): stessa dimensione, nessuno zoom aggiuntivo, webcam esclusa.

`vertical-1080p.mp4`, `exported-frame.png` e `pixel-report.json` conservano il risultato:
nei frame a 0,1 / 1,4 / 2,8 secondi, zero pixel webcam nel pannello inferiore e zero
pixel neri; marcatore webcam presente solo sopra. Contenuto blu >96%, cerchio verde
con proporzioni entro 3%. Controllo proxy/finale e decodifica integrale superati.

45 test automatici superati nella suite completa; report `test-results.xml`.
Il report `portable-gui-results.json` documenta separatamente la build Windows
eseguita fuori repository, inclusi i controlli sui pixel dell'export del vero EXE.

## Uso sui propri OBS

Apri il progetto, seleziona l'intero riquadro webcam originale, poi scegli il
contenuto dello schermo. Usa l'area OBS da escludere per correggere separatamente
la regione nascosta. I pixel coperti non sono recuperabili: se il contenuto utile
è dietro alla webcam, scegli una parte diversa. Salva il preset per registrazioni
con la stessa disposizione OBS. I preset sono normalizzati e riutilizzabili a
1080p/1440p con la stessa geometria.

La proposta visiva usa bordi/testo, non OCR o identificazione semantica delle app.
Il rilevamento automatico non garantisce il bordo esatto della webcam: correggi
il rettangolo se necessario. Nessun video OBS reale dell'utente è disponibile qui.

Backup pre-correzione: `backups/before-webcam-exclusion-0.2.zip`.

## Esito del pacchetto compilato

EXE 0.2.1 verificato fuori dal repository con PATH Windows e senza virtualenv.
GUI visibile, proxy 360×640 decodificato, modifica live confermata, export 1080×1920.
Tre frame dell’MP4 prodotto dal vero EXE: webcam presente sopra, zero pixel webcam
sotto e zero pixel neri sotto. Nessun errore nei report. Inferenza CUDA e batch
NVENC di due clip superati. Il video nella cartella no-duplicate è l’export dell’EXE.
