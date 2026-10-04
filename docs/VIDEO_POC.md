# V0.1-A — vídeo sintético H.264 mediante ADB/USB

> Evidencia histórica V0.1-A (base `0142e8d`). El sender actual añade control
> V0.1-B antes del mismo pipeline de vídeo; véase [SESSION_POC.md](SESSION_POC.md).

Experimento específico Linux/Android, no un monitor extendido ni V0.1 completo.
El host C++ permanece informativo. La generación se aísla en `gst-launch-1.0` y
`tools/video-poc.py`, sin dependencias GStreamer en CMake.

## Pipeline reproducible

Inspeccionados en este entorno: GStreamer 1.28.7, `videotestsrc`, `videoconvert`,
`openh264enc`, `h264parse`, `filesink`, `fdsink`, `openh264dec`, `identity` y
`timeoverlay`. Este último está disponible pero no se necesita ni se usa.
No se instalaron plugins. La codificación local precedió a las pruebas ADB.

```sh
mkdir -p build/video-poc
gst-launch-1.0 -e -v \
  videotestsrc is-live=true pattern=ball num-buffers=90 \
  ! video/x-raw,width=1280,height=720,framerate=30/1 \
  ! videoconvert ! video/x-raw,format=I420 \
  ! openh264enc bitrate=4000000 rate-control=bitrate gop-size=30 \
      complexity=low enable-frame-skip=false \
  ! h264parse config-interval=-1 \
  ! video/x-h264,stream-format=byte-stream,alignment=au,profile=constrained-baseline \
  ! filesink location=build/video-poc/local.h264

gst-launch-1.0 -q filesrc location=build/video-poc/local.h264 \
  ! h264parse ! openh264dec ! fakesink sync=false
```

La muestra local contiene 90 AUD, 90 imágenes (3 IDR y 87 no-IDR), 3 SPS y 3 PPS.
El patrón `ball` muestra movimiento sobre fondo negro. Fedora genera la imagen
mediante `videotestsrc pattern=ball` y la transmite por USB; Android no genera la
animación, únicamente recibe, decodifica y renderiza. No contiene captura real.

| Configuración | Razón |
| --- | --- |
| 1280×720, 30/1 FPS, I420 | Reducir variables y satisfacer la entrada real del encoder |
| `bitrate=4000000`, `rate-control=bitrate` | Objetivo 4 Mbit/s, no promesa de caudal constante; el patrón sencillo utiliza mucho menos |
| `gop-size=30` | Un intra por segundo nominal |
| `complexity=low` | Priorizar tiempo de codificación |
| `enable-frame-skip=false` | Observar continuidad sin saltos deliberados del encoder |
| Perfil `constrained-baseline` | Perfil compatible, sin B-frames; el plugin no expone una propiedad `bframes` |
| `config-interval=-1` | SPS/PPS con cada IDR |
| `byte-stream`, `alignment=au` | Annex B y unidades de acceso completas del parser |
| `fdsink sync=false` | Fuente ya temporizada mediante `is-live`; sin buffering adicional explícito |

Las caps negociadas localmente confirman H.264 constrained-baseline, nivel 3.1,
progresivo, 8 bits y 4:2:0.

## Transporte y framing experimental

El script exige un serial autorizado con `usb:` en `adb devices -l`, o exactamente
un dispositivo USB autorizado. Rechaza un serial inalámbrico y un servidor ADB
personalizado mediante `ADB_SERVER_SOCKET`. No ejecuta `adb tcpip`.

```text
GStreamer fdsink (descriptor AF_UNIX)
  -> socket Unix en build/video-poc/session-*/video.sock
  -> adb -s SERIAL forward --no-rebind localfilesystem:PATH
       localabstract:io.darkstar.darksplay.video
  -> USB físico
  -> Android LocalServerSocket
  -> parser Annex B / MediaCodec / SurfaceView
```

No hay sockets IP de Darksplay, HTTP, WebSocket ni permiso Internet. ADB conserva
su propio servidor de control estándar; esto no introduce un transporte IP de
vídeo alternativo. El socket host está dentro de un directorio temporal privado.
Al terminar se elimina únicamente el forwarding creado por ese proceso.

V0.1-A.1 distingue tres resultados del sender, conservando el exit de GStreamer:

| Resultado | Condición | Salida del script |
| --- | --- | --- |
| `completed` | GStreamer termina con 0 | 0 |
| `transport_closed` | GStreamer termina por SIGPIPE **y** `recv(1, MSG_PEEK | MSG_DONTWAIT)` confirma EOF/reset en el socket remoto | 2 |
| Fallo inesperado | Otro exit no cero, SIGPIPE con peer vivo, datos entrantes o cierre no confirmado | 1 |

SIGPIPE no se ignora ni equivale por sí mismo a éxito. El chequeo Unix no bloquea,
no consume datos y no necesita un canal de control. El diagnóstico no distingue
Stop, salida de Activity, error del receiver o pérdida USB: informa cierre del
extremo ADB/receiver y motivo exacto desconocido. La salida 2 es interrupción, no
finalización normal. `finally` sigue recolectando GStreamer y retirando solo su
forwarding; el socket y TemporaryDirectory se cierran también si se retorna 2.

El wire stream es Annex B sin cabeceras Darksplay. `h264parse` produce AUD (NAL 9)
antes de cada frame. El reader Android admite start codes de 3/4 bytes y fragmentos
arbitrarios; agrupa NAL por AUD para entregar un AU a cada input buffer. Espera al
siguiente AUD (aproximadamente un frame de lookahead), o EOF para el último AU.
Exige SPS/PPS en el primer AU y los pasa como `csd-0`/`csd-1`, con start codes,
a `MediaFormat("video/avc", 1280, 720)`. No es un parser H.264 general ni el protocolo
final: exige AUD y limita NAL/AU a 1 MiB; rechaza datos incompatibles explícitamente.
En V0.1-A.1, al encontrar EOF se incorporan los ceros pendientes del NAL iniciado,
comprobando antes el límite de payload acumulado más ceros. Sin un start code
posterior no se descartan bytes ni se intenta interpretar el RBSP para distinguir
padding de payload: es una conservación de bytes deliberada para este parser PoC.

Los PTS de decoder se sintetizan como índice × 1 000 000 / 30 microsegundos;
no representan timestamps sincronizados entre host y Android.
La configuración MediaCodec pide 30 FPS y máximo input de 1 MiB. El decoder nativo
se selecciona mediante `createDecoderByType`; no se fuerza un fabricante.

## Sesión y recursos

Abrir Darksplay no abre el listener. Pulsar **Start receiver** lo prepara y habilita
una sola conexión. **Stop receiver**, salir de la Activity o destruir Surface
cierran transporte; el worker libera MediaCodec en `finally`. No hay servicios
Android ni daemon Darksplay. La pantalla permanece despierta mientras la vista
está visible, sin alterar configuración del dispositivo.

Hay un worker para lectura/decoding y callbacks de render en el main looper. No
se bloquea la UI ni se crea una cola de frames de aplicación. Se drena el decoder
al recibir datos y mientras se espera un input buffer. Lectura sin datos durante
5 s y decoder sin input disponible durante 5 s terminan la sesión. EOF drena EOS
hasta 2 s y libera recursos. No se reconecta automáticamente.

No se descartan frames comprimidos arbitrariamente: podrían ser referencias de
otros frames. El socket/ADB y MediaCodec pueden tener buffering interno. El
backpressure bloquea el writer; no hay cola ilimitada propia. Las estadísticas
`queued - released` observan el decoder, no todo el buffering del transporte.

## Procedimiento manual en hardware

1. Compilar el APK como indica `android/README.md`; instalar con `adb -s SERIAL install -r`.
2. Verificar `adb devices -l`: dispositivo autorizado con `usb:`. Desbloquearlo.
3. Abrir Darksplay y pulsar **Start receiver**; esperar el estado listo.
4. Desde la raíz ejecutar:

```sh
python3 tools/video-poc.py --serial SERIAL --seconds 60
# O continuo, hasta Ctrl-C:
python3 tools/video-poc.py --serial SERIAL
# En otra terminal:
adb -s SERIAL logcat -v threadtime -s DarksplayVideo:I AndroidRuntime:E
```

5. Observar movimiento, sincronización y logs de primer frame/render; las
   estadísticas salen cada 5 s. No se registra cada frame.
6. Probar EOF finito, Ctrl-C host, Stop receiver y Stop antes de conectar host.
   Confirmar botón Start disponible y app abierta; repetir inicio manualmente.
7. Desconectar físicamente USB durante un stream; comprobar localmente en Android
   que la app sigue abierta y deja de recibir. Reconectar solo para consultar logs,
   confirmar `decoder stopped` y ausencia de reconexión automática.
8. Comprobar que `adb forward --list` no conserve el forwarding de este script.

La prueba de hardware exige observación; un build correcto no demuestra vídeo.
Los artefactos locales (logs y capturas) quedan en `build/video-poc`, fuera de Git.

## Prueba del parser sin frameworks

`tests/AnnexBReaderCheck.java` ejecuta el Kotlin compilado sobre el H.264 local,
con fragmentos de 1, 2, 3, 4, 7, 64 y 4096 bytes. Además de los 90 AU reales,
comprueba start codes de 3/4 bytes divididos entre lecturas, múltiples NAL/AU,
EOF final y repetido, conservación byte a byte de ceros de payload al EOF,
SPS/PPS exactos o ausentes, entradas cortas/truncadas sin acceso fuera de límites,
NAL demasiado grande, AU demasiado grande con NAL individuales válidos, límite
combinado payload+ceros al EOF y AU exactamente en MAX_BYTES. Tras `assembleDebug`, usando
un JDK completo y su stdlib Kotlin de build ya descargada:

```sh
CLASSES=android/app/build/intermediates/built_in_kotlinc/debug/compileDebugKotlin/classes
STDLIB=$(rg --files android/.gradle-user-home/caches -g 'kotlin-stdlib-2.2.10.jar' | head -n 1)
mkdir -p build/video-poc/parser-test
"$JAVA_HOME/bin/javac" -cp "$CLASSES:$STDLIB" -d build/video-poc/parser-test tests/AnnexBReaderCheck.java
"$JAVA_HOME/bin/java" -cp "build/video-poc/parser-test:$CLASSES:$STDLIB" \
  AnnexBReaderCheck build/video-poc/local.h264 90
```

Es un check específico de PoC, separado de CTest host y sin bibliotecas nuevas.
`parameterSet()` no se cambió: estos checks usan las unidades del Kotlin real.

Los seis checks stdlib del sender ejercitan sockets AF_UNIX reales (sin dispositivo):

```sh
python3 tests/test_video_poc.py
```

Cubren exit 0, SIGPIPE+EOF confirmado (salida 2), SIGPIPE con peer vivo o datos
entrantes (fallo y peek no destructivo), error ordinario con peer cerrado y señal
ajena a SIGPIPE. En entornos restringidos pueden requerir permisos para socketpair.

## Resultados y límites

Resultado: **SUCCESS para V0.1-A**, sin completar V0.1.

| Prueba | Resultado observado |
| --- | --- |
| Encoding local | 90 imágenes a 1280×720/30 FPS; 40.539 bytes; decodificación local correcta |
| Primer stream físico | 10 s, 300 frames renderizados y primer frame visible en captura |
| Stream continuo más largo | 59,997 s de pipeline, 1.800 AU encolados/liberados/renderizados |
| FPS de ventanas de 5 s tras arranque | 29,42–30,57 FPS; primer intervalo incluye espera previa del receiver y no sirve como FPS sostenido |
| Backlog de decoder observado | Normalmente 1, pico de 4, recuperado a 1; 0 al drenar EOS |
| EOF | App abierta, Stream terminado, codec liberado y forwarding eliminado |
| Stop durante vídeo | App abierta; 415 AU encolados, 414 renderizados; codec liberado |
| Stop esperando conexión | Worker terminado en 96 ms, sin codec ni frames |
| Desconexión física USB | Usuario observó Stream terminado; logs posteriores: 1.157 encolados/liberados/renderizados y decoder detenido |
| Reconectar USB | Mismo proceso Android, Start habilitado, ningún reinicio de sesión ni forwarding residual |
| Gradle / Lint | assembleDebug y lint offline correctos; 0 errores y 2 advertencias |
| Host | CMake/build correctos, CTest 1/1 y Darksplay host 0.0.1-dev / salida 0 |
| Parser | Checks sobre Kotlin real aprobados, sin framework externo |

El dispositivo de prueba ejecutó Android API 36 y el decoder seleccionado por el
sistema fue `c2.exynos.h264.decoder`. Esto es evidencia de una prueba, no un requisito
arquitectónico de fabricante. Las capturas muestran el patrón en Surface y posiciones
diferentes de la bola; no apareció congelamiento sostenido en contadores. No se hizo
una inspección visual fotograma a fotograma para cuantificar tearing.

Artefactos locales: `first-logcat.txt`, `continuous-logcat.txt`, `stop-logcat.txt`,
`disconnect-logcat.txt`, logs del pipeline y capturas dentro de `build/video-poc`.
No hay errores Darksplay/AndroidRuntime en los logs recogidos de las sesiones válidas.
Una prueba inicial pulsó Start demasiado pronto tras reinstalar, y el sender recibió
SIGPIPE; se repitió después de comprobar la pantalla lista.

En el commit base V0.1-A, Stop o desconectar USB producían SIGPIPE (`exit=-13`) y
el script lo clasificaba genéricamente como fallo, salida 1. V0.1-A.1 corrige esa
clasificación según la comprobación de cierre descrita arriba. En desconexión, intentar quitar el forwarding puede informar
`device not found`; ADB lo elimina al perder el transporte. La comprobación posterior
mostró lista vacía. Esto es un diagnóstico de PoC, no reconexión sofisticada.
La advertencia de XML SDK versión 4 persiste; Lint advierte versión Gradle más reciente
y `dataExtractionRules` de backup, sin errores.

No se ha medido
latencia extremo a extremo: los contadores de decoder y el tiempo de arranque no
son una medición de latencia visual. No hay relojes sincronizados ni captura
simultánea host/pantalla. Antes de V0.1-B deben revisarse ese método, la respuesta a
backpressure, el alcance del parser, configuración negociable y el control plane.
No se implementan PipeWire, display virtual, escritorio extendido, audio, entrada,
aceleración de encoder, Windows ni el protocolo Darksplay definitivo.

## Validación de correcciones V0.1-A.1

Sobre `25755f0`, sin cambios de encoding, Activity, receiver, manifiesto o permisos:

| Check | Resultado |
| --- | --- |
| Sender, 6 checks AF_UNIX stdlib | Aprobados; SIGPIPE sin cierre confirmado sigue siendo fallo |
| Parser Kotlin real | Todos los casos sintéticos ampliados y 90 AU GStreamer recién generados aprobados |
| `parameterSet()` | SPS/PPS presentes, ausentes y entradas cortas aprobados; no requirió cambios |
| Android `assembleDebug lint --offline --no-daemon` | BUILD SUCCESSFUL; Lint 0 errores, 2 advertencias existentes |
| Host configure/build/CTest | Correctos; 1/1 test y host 0.0.1-dev, salida 0 |
| A. Stream normal físico | 9,994 s, 300 frames renderizados, patrón visible; `completed`, salida 0; decoder liberado |
| B. Stop durante stream | App abierta; decoder liberado, 527 frames renderizados; SIGPIPE+EOF confirmado, `transport_closed`, salida 2 |
| C. Stop esperando host | Worker terminó en 61 ms; cero frames |
| D. Desconexión USB física | Usuario confirmó Stream terminado; 438 frames renderizados, decoder liberado; sender `transport_closed`, salida 2 |
| Reconexión | Mismo proceso app, Start habilitado, sin sesión automática ni forwarding residual |
| Branding | SHA-256 idéntico al commit base |

Logs y captura están en `build/video-poc/review`, excluido de Git. En desconexión,
cleanup intentó retirar su forward e informó `device not found`; tras reconectar se
confirmó lista vacía. No se ocultó ese diagnóstico. El primer intento del check Python
fue bloqueado por el sandbox en `socketpair.sendall`; los seis checks pasaron al
repetir fuera de esa restricción, sin introducir sockets IP ni dependencias.

La corrección conserva los ceros finales y comprueba su límite combinado; no se
hallaron otros bugs pequeños del parser ni se reescribió `parameterSet()`. Esta
regresión física no vuelve a medir 60 s ni latencia extremo a extremo. Annex B+AUD
sigue siendo framing experimental y no se implementa control plane V0.1-B.
