# Componenti e licenze

Il repository pubblico contiene il codice originale, il piccolo modello YuNet
con licenza MIT e la foto NASA di test attribuita in fondo. Non distribuisce
EXE, DLL, modelli Whisper o runtime NVIDIA. Gli inventari e i bundle menzionati
qui sotto si riferiscono alle build locali e possono essere generati con gli
script inclusi; non sono tutti presenti nel checkout sorgente.

Il codice originale di LocalClips AI è MIT (`LICENSE.txt`). Librerie, pesi e runtime
rimangono soggetti alle rispettive licenze. `licenses/inventory.json` riporta le versioni
installate e i testi trovati nelle distribuzioni; include anche componenti dell'ambiente
di build non necessariamente presenti nell'EXE.

| Componente | Licenza / informazioni |
|---|---|
| Python | PSF; testo incluso |
| PySide6 / Qt | LGPLv3/GPL e componenti con licenze proprie; librerie dinamiche separate |
| faster-whisper | MIT, SYSTRAN |
| CTranslate2 | MIT |
| Whisper Small convertito SYSTRAN | MIT dichiarata nella model card |
| Silero VAD incluso in faster-whisper | MIT; verificare anche notices dell'asset |
| ONNX Runtime | MIT |
| PyAV | BSD; FFmpeg sottostante con licenze proprie |
| psutil | BSD-3-Clause |
| OpenCV headless | Apache-2.0, dipendenze native con notices inclusi |
| YuNet ONNX | MIT; `licenses/YUNET-LICENSE.txt`, modello OpenCV Zoo |
| PyJWT | MIT; verifica OIDC |
| cryptography / CFFI | Apache/BSD/MIT secondo i testi inclusi nell'inventario |
| FFmpeg Gyan 9.0.2 essentials | **GPLv3**, build con libx264/libx265, non LGPL-only |
| PyInstaller | GPL con eccezione per i bundle generati |
| cuBLAS/cuDNN/NVRTC NVIDIA | Runtime **proprietari**, opzionali, soggetti alle EULA NVIDIA incluse |

Questa cartella è stata assemblata localmente per l'uso richiesto. La presenza di CUDA
non rende i runtime NVIDIA open source. La CPU non richiede i runtime in `cuda`.
Il driver NVIDIA non viene ridistribuito. Le DLL Qt e NVIDIA sono conservate separatamente
e sostituibili; non si applicano restrizioni aggiuntive al debugging delle librerie LGPL.

La build FFmpeg è eseguita come processo esterno. Il relativo testo GPL è in
`tools/FFMPEG-LICENSE.txt`; configurazione completa e riferimento al sorgente corrispondente
sono in `tools/FFMPEG-BUILD.txt` (commit FFmpeg `946fcce07b`). L'archivio scaricato è stato
verificato contro il checksum del distributore, conservato in `tools/ffmpeg.sha256`.

**Prima di pubblicare un pacchetto per terzi**, completare la consegna/offerta dei sorgenti
corrispondenti di FFmpeg/Qt e delle librerie native secondo le rispettive licenze e verificare
le condizioni di redistribuzione NVIDIA. Il presente inventario non equivale a una certificazione
legale né a un pacchetto già pronto per la distribuzione pubblica.

Fonti primarie consultate:

- [Licenze Qt for Python](https://doc.qt.io/qtforpython-6/commercial/index.html)
- [Obblighi LGPL Qt](https://www.qt.io/development/open-source-lgpl-obligations)
- [Licenza faster-whisper](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE)
- [Modello SYSTRAN Small](https://huggingface.co/Systran/faster-whisper-small)
- [FFmpeg legal](https://ffmpeg.org/legal.html)
- [Build Windows Gyan](https://www.gyan.dev/ffmpeg/builds/)
- [EULA NVIDIA CUDA](https://docs.nvidia.com/cuda/eula/index.html)
- [EULA cuDNN](https://docs.nvidia.com/deeplearning/cudnn/backend/latest/reference/eula.html)
- [Compatibilità faster-whisper CUDA](https://github.com/SYSTRAN/faster-whisper)
- [Changelog PyAV: rimozione metadata_errors](https://pyav.basswood.io/docs/stable/development/changelog.html)

Il materiale di test `tests/assets/astronaut.png` proviene da scikit-image v0.24.0,
foto NASA di Eileen Collins dichiarata di pubblico dominio nella documentazione
[scikit-image data.astronaut](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut).
È usato soltanto per verificare il rilevamento facciale, senza riconoscimento di identità.
Il modello YuNet proviene da [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet).

Nessuna inferenza AI remota è stata eseguita nello sviluppo. L'app include una modalità
ChatGPT facoltativa, attivata esclusivamente dall'utente; il rendering rimane locale.
