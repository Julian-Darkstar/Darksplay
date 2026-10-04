# V0.2 PipeWire Capture

V0.2 sustituye por defecto la fuente sintética `videotestsrc` por captura real
de pantalla en Fedora/GNOME/Wayland. La captura usa
`xdg-desktop-portal ScreenCast` para obtener consentimiento del usuario y un
FD autorizado de PipeWire. El vídeo continúa viajando por ADB/USB físico hacia
Android, donde se decodifica y renderiza.

V0.2 no implementa todavía un monitor virtual ni un escritorio extendido. Esas
capacidades corresponden a V0.3. Tampoco implementa reconexión automática,
aceleración de encoding, input, audio, Windows ni transporte de red.

## Arquitectura

```text
GNOME / xdg-desktop-portal ScreenCast
  -> consentimiento explícito
  -> un monitor, cursor embebido, sin persistencia
  -> FD PipeWire autorizado + node ID
  -> pipewiresrc
  -> GStreamer / OpenH264
  -> socket Unix de vídeo
  -> adb forward / USB físico
  -> Android MediaCodec / SurfaceView
```

El consentimiento del portal se solicita antes de iniciar los timeouts y el
handshake de Darksplay. GStreamer recibe el FD autorizado y el `node_id`
devuelto por el portal. Android permanece sin cambios para esta captura.

La señal `org.freedesktop.portal.Session.Closed` se despacha mediante un loop
GLib activo durante el streaming. Una revocación confirmada marca el estado
`source_revoked`; el proceso GStreamer se recolecta y el sender termina con
exit 2. El `GOODBYE` usa el reason wire existente `transport_closed`, porque
V0.1-B no define una taxonomía de reasons nueva. Un `exit=1` sin revocación
confirmada continúa siendo un fallo inesperado.

El cleanup es idempotente: se recolecta GStreamer, se cierran sockets y se
eliminan los forwards creados por la sesión. Stop del receiver, pérdida de USB
y revocación del portal siguen rutas de cierre sin reconexión ni inicio
automático.

## Pipeline

```text
pipewiresrc
  -> videorate
  -> video/x-raw,framerate=30/1
  -> videoconvert
  -> videoscale, add-borders=true
  -> 1280x720
  -> video/x-raw,format=I420
  -> openh264enc
  -> h264parse
  -> H.264 Annex B
  -> fdsink / ADB / USB
```

La configuración conserva `keepalive-time=1000`. En la prueba física, una
pantalla estática durante más de 15 s seguida de movimiento continuó
correctamente. Ese resultado valida el comportamiento de la captura en esa
secuencia; no es una medición de latencia ni de fluidez cuantificada.

`--videotestsrc` conserva la fuente sintética de V0.1 como diagnóstico y
regresión. No cambia el pipeline de captura por defecto.

## Ejecución

Requisitos: Fedora con GNOME/Wayland, `xdg-desktop-portal` ScreenCast,
PipeWire, GStreamer con `pipewiresrc` y `openh264enc`, ADB y un dispositivo
Android autorizado por USB físico.

Desde la raíz del proyecto, con el receiver Android preparado:

```sh
python3 tools/video-poc.py --serial SERIAL
```

El portal mostrará el consentimiento de ScreenCast. Selecciona un único
monitor. Para una prueba diagnóstica con la fuente sintética:

```sh
python3 tools/video-poc.py --serial SERIAL --videotestsrc
```

No se inicia ninguna sesión automáticamente y el script no implementa
reconexión.

## Validación

La captura física fue validada en Android real. La imagen cambia correctamente
y la secuencia de pantalla estática seguida de movimiento continuó después de
más de 15 s. También se validaron:

- revocación desde **Detener compartición** en GNOME: `source_revoked`, exit 2;
- cleanup sin procesos Darksplay/GStreamer residuales;
- eliminación de los ADB forwards de la sesión;
- Stop del receiver y pérdida de USB como cierres con cleanup;
- consentimiento del portal antes del handshake y los timeouts de Darksplay;
- captura de un único monitor con cursor embebido y sin persistencia.

Los tests Python pasan:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

Resultado validado: **37 tests OK**.

## Limitaciones

- Latencia extremo a extremo y fluidez todavía no están optimizadas ni
  cuantificadas.
- Los 30 FPS son la configuración nominal del pipeline y del protocolo, no una
  medición de latencia ni una promesa de rendimiento observado.
- No hay monitor virtual ni escritorio extendido; ese alcance pertenece a V0.3.
- No hay aceleración de encoding, input, audio, backend Windows ni transporte
  de red.
- El transporte actual sigue siendo ADB sobre USB físico.
- La revocación del portal termina la sesión; no hay reconexión automática.

## Relación con V0.1

[VIDEO_POC.md](VIDEO_POC.md) conserva la evidencia histórica de V0.1-A, basada
en `videotestsrc`. [SESSION_POC.md](SESSION_POC.md) conserva la evidencia
histórica de V0.1-B y su protocolo experimental. Esta documentación de V0.2
describe la fuente real de captura sin reescribir esos experimentos históricos.
