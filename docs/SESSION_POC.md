# Sesión PoC V0.1-B

Experimento sobre V0.1-A, no protocolo definitivo ni V0.1 completo. La bola se
**genera en Fedora mediante `videotestsrc pattern=ball`**, se codifica con OpenH264
y se transmite por USB. Android recibe, decodifica y renderiza; no genera la
animación. No hay captura de pantalla, PipeWire, display virtual ni monitor
extendido. No se midió latencia extremo a extremo.

## Dos canales de una sesión

- Control: socket Unix del host → ADB forward USB → Android
  `localabstract:io.darkstar.darksplay.control`.
- Vídeo: GStreamer/fdsink → socket Unix del host → ADB forward USB → Android
  `localabstract:io.darkstar.darksplay.video` → AnnexBReader → MediaCodec → SurfaceView.

Son dos forwards privados, con rutas temporales nuevas por ejecución; no hay
listeners TCP/UDP de Darksplay, permisos Internet, cloud ni transporte inalámbrico.
El sender exige un dispositivo autorizado que ADB identifica con `usb:`.
No añade dependencias: Python estándar y APIs JSON nativas Android.
El host C++ sigue siendo el ejecutable informativo de Fase 0.

## Control experimental

Una línea UTF-8 terminada en LF contiene exactamente un objeto JSON. Máximo
**4096 bytes antes del LF**, suficiente para estos cinco mensajes pequeños y
acotado incluso si nunca llega el delimitador. Se rechazan UTF-8/JSON inválidos,
claves duplicadas, campos extra, tipos incorrectos y mensajes fuera de secuencia.
Android admite campos escalares string/entero, sin coerción de floats o booleanos.

Mensajes y dirección actuales:

```json
{"type":"hello","protocol":1}
{"type":"hello_ack","protocol":1}
{"type":"video_config","codec":"h264","width":1280,"height":720,"fps":30}
{"type":"video_config_ack"}
{"type":"goodbye","reason":"completed"}
```

Host envía HELLO, VIDEO_CONFIG y GOODBYE; Android devuelve los dos ACK.
`protocol=1` no negocia rangos. Solo `codec=h264` está soportado; Android exige
enteros `width=1..1920`, `height=1..1080`, `fps=1..60`. Son límites conservadores
del PoC, no promesas de soporte para cada combinación ni capabilities finales.
`reason` es texto diagnóstico de hasta 128 caracteres; no taxonomía definitiva.
No hay READY, PING, CONFIG genérico, VIDEO_FRAME ni negociación de capacidades.
JSON Lines y Annex B + AUD son decisiones experimentales, no formatos Darksplay 1.0.

## Orden y estados

```mermaid
sequenceDiagram
    participant U as Usuario
    participant A as Android
    participant H as Sender Fedora
    U->>A: Start receiver
    Note over A: WAITING: solo endpoint de control
    H->>A: HELLO protocol=1
    A->>H: HELLO_ACK protocol=1
    H->>A: VIDEO_CONFIG h264 / 1280×720 / 30
    Note over A: Valida config y prepara endpoint de vídeo nuevo
    A->>H: VIDEO_CONFIG_ACK
    H->>A: Conecta vídeo y comienza H.264 Annex B
    Note over A: MediaCodec y SurfaceView
    H->>A: EOF de vídeo, después GOODBYE
    Note over A,H: Cleanup incluso sin GOODBYE
```

Android: WAITING → CONNECTED → HELLO_OK → CONFIGURED → STREAMING → CLOSING → CLOSED.
Errores/Stop/lifecycle pueden terminar desde cualquier estado. El host mantiene
CONNECTED → HELLO_OK → CONFIGURED → STREAMING → CLOSING → CLOSED.
El callback que conecta vídeo y crea GStreamer solo se invoca tras ambos ACK.
Android prepara el endpoint de vídeo antes de escribir CONFIG_ACK (para evitar
una carrera de conexión), pero no inicia su worker hasta escribir ese ACK.
El vídeo no lleva mensajes Darksplay por frame.

VIDEO_CONFIG validada crea `VideoConfig`; VideoReceiver usa su MIME (`h264` →
`video/avc`), dimensiones y FPS en MediaFormat y los FPS para los PTS nominales.
SPS/PPS siguen procediendo del stream Annex B. No se implementa comparación
completa SPS/config ni un parser general H.264.

## Timeouts y cierre

- Host: conexión Unix y cada envío/lectura de ACK/control: 5 s. Lectura con plazo
  absoluto por línea; recibir bytes lentamente no extiende el handshake.
- Android: HELLO, VIDEO_CONFIG y líneas parciales: 5 s. `Os.poll` del descriptor
  de control en intervalos de 250 ms permite comprobar el plazo y despertar al
  cerrar el socket. No se depende de la clase de excepción de SO_TIMEOUT nativa.
- Espera inicial de usuario/host: sin límite, cancelable con Stop/lifecycle.
- Vídeo: accept y lectura existentes con límite de 5 s. Mientras el worker de
  vídeo vive, un control ocioso completo puede continuar sin mensajes/keepalive;
  una línea parcial nunca extiende su plazo. Al acabar vídeo se espera control
  hasta 5 s, luego se termina si no llegó GOODBYE.
- Join de vídeo: hasta 3 s por intento, solo en worker de control. Proceso host:
  SIGINT/espera 3 s → terminate/espera 2 s → kill/recolección.

En completion el host hace shutdown de escritura de vídeo, envía GOODBYE y
comprueba EOF de control. Android permite drenar vídeo, libera decoder y cierra
control. GOODBYE no es requisito: EOF, excepciones, Stop, onStop y surfaceDestroyed
cierran también. Control EOF durante streaming se informa como `transport_closed`
(exit 2), aunque GStreamer atienda SIGINT y termine en 0. SIGPIPE solo se clasifica
como transporte cerrado con evidencia de cierre del peer; otros fallos siguen
siendo errores (exit 1), incluso si coinciden con EOF de control. No se infiere si fue Stop, lifecycle o desconexión física.

## Ownership

SessionReceiver posee un worker de control, su listener y socket aceptado, y un
único VideoReceiver creado con esa configuración. El listener de control se cierra
tras aceptar una conexión. VideoReceiver posee su worker, listener/socket y codec;
acepta una conexión y cierra su listener. MediaCodec se libera en finally.
Stop cierra/shutdown ambos canales y despierta accept/poll/read. La UI no hace
joins y Start permanece deshabilitado hasta terminar el worker de sesión.
Una nueva acción Start crea objetos y endpoints nuevos, sin listeners de la
sesión anterior. Esta asociación por lifecycle no es autenticación ni emparejado.

El sender posee sockets, proceso GStreamer, directorio TemporaryDirectory y una
lista de forwards creados exitosamente por esa ejecución. Finally recolecta el
proceso y cierra sockets; elimina únicamente esos forwards y su directorio,
también ante error/interrupción. No usa shell=True ni comandos shell construidos.

## Reproducir y probar

Compilar e instalar como en [Android README](../android/README.md), abrir Darksplay
y pulsar Start receiver. Con un único dispositivo USB autorizado:

```sh
python3 tools/video-poc.py --seconds 10
# O seleccionar explícitamente:
python3 tools/video-poc.py --serial SERIAL --seconds 10
```

El pipeline y sus parámetros OpenH264 permanecen los de [V0.1-A](VIDEO_POC.md).
Una ejecución sin receiver preparado falla durante control, antes del pipeline.
`adb forward --list` debe quedar igual que antes de ejecutar el sender.

Pruebas Python de sender real, framing, ACK gates y cleanup:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

`SessionProtocolCheck.java` se compila con las clases Kotlin reales de
`app/build/intermediates/built_in_kotlinc/debug/compileDebugKotlin/classes` y el
kotlin-stdlib del build. Comprueba estados, HELLO/config/GOODBYE, parámetros,
UTF-8, límite, EOF y timeout. `AnnexBReaderCheck` conserva la regresión del parser.
No hay implementación productiva duplicada en los tests.

Check físico opt-in (app abierta, USB autorizado; pulsa Start/Stop, sin GStreamer):

```sh
python3 tests/check_session_device.py --serial SERIAL
```

Comprueba JSON real Android, versión/type/orden, duplicados, UTF-8, límite,
config inválida, EOF y timeout; cada rechazo debe devolver EOF y habilitar Start.
También Stop esperando host y durante handshake. Resuelve los botones por ID,
no por coordenadas fijas. El dump temporal UI se guarda en `/data/local/tmp`;
no cambia ajustes del dispositivo.

Validación manual adicional: sesión normal, Stop en vídeo, desconexión USB durante
negociación y vídeo, reconexión sin inicio automático. Observar bola, parámetros,
logs HELLO/ACK y CONFIG/ACK antes de GStreamer, GOODBYE/decoder stopped/CLOSED,
UI utilizable y ausencia de forwards propios residuales. Logs:

```sh
adb -s SERIAL logcat -v time -s DarksplaySession:I DarksplayVideo:I AndroidRuntime:E
```

## Evidencia de esta revisión

Validación con Android físico por USB (hardware de prueba, sin dependencia del
fabricante):

| Prueba | Resultado |
| --- | --- |
| A: sesión normal | 10 s, 300 frames renderizados, HELLO/ACK y CONFIG/ACK antes de vídeo; GOODBYE, decoder liberado y forwards eliminados. Bola visible y UI h264/1280×720/30 FPS. |
| B: Stop esperando host | Stream finished; listener/worker terminados y Start habilitado. |
| C: Stop durante handshake | Después de HELLO_ACK y antes de CONFIG; EOF, sin vídeo/codec, sesión cerrada y UI utilizable. |
| D: Stop en streaming | 398 frames renderizados; codec liberado y CLOSED. Sender exit 2 transport_closed (GStreamer exit 0 por interrupción); sin forwards residuales. |
| E: USB durante handshake | No realizada físicamente: no se coordinó una desconexión dentro del plazo de handshake de 5 s. EOF/timeout y bloqueo de vídeo están cubiertos por tests; no equivalen a esta prueba física. |
| F: USB durante vídeo | Usuario observó Session error: Control EOF; log confirma 574 frames y codec liberado/CLOSED. Sender exit 2 transport_closed; GOODBYE ausente y cleanup independiente. |
| G: reconexión | Sin inicio automático, Start habilitado/Stop deshabilitado y sin forwards. Intentar sender sin Start falla con Control EOF antes de GStreamer. Nueva sesión explícita: 3 s/90 frames, GOODBYE y cleanup correctos. |

Los 15 casos de control físico del check opt-in cerraron la sesión y recuperaron
la UI. Tests Python: 23 aprobados (17 de sesión y 6 de regresión V0.1-A); checks
Kotlin de sesión y AnnexBReader aprobados, incluyendo stream real de 90 AU.
CMake/build/CTest 1/1 y host informativo correctos.

Al desconectar USB, los intentos de adb forward --remove informaron device not
found. ADB eliminó los forwards asociados al transporte perdido: tras reconectar
la lista estaba vacía. El cleanup conserva ese diagnóstico, no lo declara una
eliminación exitosa por comando.

La primera prueba
reveló que LocalSocket SO_TIMEOUT devolvía IOException `Try again`, cortando
control tras seis frames. Se sustituyó por poll Unix y la sesión normal posterior
completó 10 s/300 frames, ambos ACK, GOODBYE, codec liberado y forwards eliminados.
No se midió latencia extremo a extremo; FPS y tiempo de sesión no la sustituyen.
EOF/SIGPIPE no identifican el motivo exacto de desconexión. Continúan pendientes
capabilities, métricas formales, protocolo definitivo y revisión para integrar
V0.1. No se implementan captura, monitor virtual ni fases posteriores.
