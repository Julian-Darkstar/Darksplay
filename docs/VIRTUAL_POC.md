# V0.3 — Monitor extendido virtual por USB

Estado: **funcionalmente completado y validado físicamente**, resultado
**A — ÉXITO COMPLETO**. Implementación experimental en Fedora/GNOME/Wayland;
no implica rendimiento optimizado ni protocolo definitivo.

## Flujo y uso actual

```text
Android Start → HELLO → Host HELLO_ACK → VIDEO_CONFIG → Android VIDEO_CONFIG_ACK
→ ScreenCast VIRTUAL (source_type=4) → PipeWire negocia BGRx 1280×720
→ GNOME/Mutter materializa Meta-0 como monitor extendido independiente
→ GStreamer → OpenH264 → H.264 Annex B → ADB/USB físico
→ Android MediaCodec → SurfaceView
```

Abrir el APK actualizado y mantener la Surface visible, sin pulsar Start. Con un
único Android autorizado por USB, desde la raíz:

```sh
python3 -u tools/video-poc.py --virtual-display
```

El host conecta el transporte y espera HELLO sin transmitir. Pulsar Start en
Android y aceptar manualmente el diálogo del portal si aparece. No existe READY.
USB o conexión técnica por sí solos no crean sesión, Meta-0 ni vídeo. VIRTUAL
se abre solo tras VIDEO_CONFIG_ACK. La negociación PipeWire materializa el monitor;
DisplayConfig se utilizó únicamente para observarlo, nunca para crearlo.

La fuente utiliza el FD autorizado y node ID del portal, con caps explícitas
`video/x-raw,format=BGRx,width=1280,height=720`. Reutiliza el pipeline V0.2:
videorate, conversión/escalado, I420 1280×720/30, OpenH264, h264parse y fdsink.
MONITOR sigue siendo el modo predeterminado. No se duplicó el sender ni el transporte.

El modo de pantalla observado fue **1280×720@60 Hz**, mientras VIDEO_CONFIG y
H.264 permanecen a **1280×720/30 FPS nominales**. PipeWire negoció `framerate=0/1`
y `max-framerate=60/1`: 0/1 no es una medición de cero FPS. No se demuestra vídeo
Darksplay a 60 FPS ni se deduce latencia de estos valores.

## Evidencia de una única prueba integrada

APK debug actualizado instalado con `adb install -r`: Success. Dispositivo
Android autorizado mediante USB físico; sin forwards iniciales. Antes de Start,
el host permaneció esperando y GNOME tenía 1 monitor / 1 logical monitor (`eDP-1`).

Handshake observado, primer mensaje Android → Host:

```text
Waiting for Android HELLO / Start
control RX {'type': 'hello', 'protocol': 1}
control TX {"type":"hello_ack","protocol":1}
control TX {"type":"video_config","codec":"h264","width":1280,"height":720,"fps":30}
control RX {'type': 'video_config_ack'}
Capture source ready: node_id=88, fd=6
```

Se seleccionó y validó VIRTUAL, source_type=4. Node ID y FD son valores de esa
sesión, no constantes. GStreamer negoció BGRx → I420 → H.264 constrained-baseline,
Annex B / alignment=au, y pasó a PLAYING sin ERROR.

| DisplayConfig | Antes | Durante | Después de Stop |
| --- | --- | --- | --- |
| Monitors | 1 | 2 | 1 |
| Logical monitors | 1 | 2 | 1 |
| Meta-0 | Ausente | 1280×720@60, posición (1536,0), escala 1, no principal | Ausente |

La posición dependía del monitor principal de esa sesión; no es un requisito fijo.
Android registró:

```text
MediaCodec configured: c2.exynos.h264.decoder
first frame rendered to Surface
```

Ese decoder es una selección del hardware de prueba, no una dependencia del proyecto.
El usuario movió manualmente ventanas al segundo monitor y confirmó que aparecían
correctamente en Darksplay y se actualizaban. Reportó algunos tirones, pero fuera
de eso funcionamiento correcto. No hubo confirmación separada de cada subpaso
estático/movimiento posterior; sí continuidad hasta Stop. No se automatizó input.

## Stop y liberación

Android mostró `Stream finished` y registró:

```text
decoder stopped; queued=3933 released=3929 rendered=3929
video worker finished
state=CLOSED; control/video resources released
```

El host atendió el cierre de control y recolectó GStreamer con SIGINT/EOS/NULL:

```text
GStreamer exit=0; control EOF; PoC outcome=transport_closed
```

Host exit **2** es el cierre esperado por Stop, no un fallo de encoding.
La ejecución GStreamer duró aproximadamente 2 min 12 s. Meta-0 desapareció,
GNOME volvió a 1 monitor / 1 logical monitor, sin forwards ni procesos
`video-poc.py` / `gst-launch-1.0` residuales. Cleanup no requiere GOODBYE.

## Límites y revisión pendiente

- Tirones visuales observados; causa no diagnosticada ni atribuida a ningún componente.
- Sin medición formal de latencia y sin optimización de rendimiento en V0.3.
- La espera del diálogo portal es síncrona: Stop/USB durante esa espera se observa
  después de que retorne la operación portal; no se afirma validación física de ese caso.
- El endpoint Android debe estar disponible; no hay retry ni reconexión automática.
- `--seconds` limita buffers de origen y no garantiza duración exacta en captura variable.
- La prueba integrada valida Stop; no sustituye pruebas V0.3 específicas de pérdida
  USB o revocación durante todas las etapas.
- Sin hardware encoding, touch, stylus, audio, Windows ni transportes adicionales.
- La siguiente fase del roadmap es V0.4: optimización y evaluación de hardware encoding.

Los PoC aislados de investigación se retiraron por duplicar portal/cleanup y tests
ya presentes en la integración. No son necesarios para ejecutar V0.3. Esta evidencia
resume la prueba realizada; no exige conservar logs temporales ni identificadores USB.
