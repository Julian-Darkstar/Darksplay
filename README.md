# Darksplay

![Logo oficial de Darksplay](assets/branding/Darksplay.png)

Darksplay es un proyecto experimental que busca permitir utilizar un dispositivo
Android como monitor extendido de una computadora. Actualmente incluye el
bootstrap, captura de un monitor existente (V0.2) y un monitor extendido virtual
(V0.3), validados físicamente en Fedora/GNOME/Wayland con Android por ADB/USB.
V0.3 usa ScreenCast VIRTUAL, PipeWire, GStreamer/OpenH264 y MediaCodec/SurfaceView.

La primera plataforma host será Fedora Linux con GNOME y Wayland; el cliente
inicial será Android. La separación del núcleo y los backends permitirá evaluar
Windows posteriormente, sin vincular el diseño a fabricantes o hardware de prueba.

## Implemented

- Host mínimo C++20/CMake: imprime `Darksplay host 0.0.1-dev` y termina con código 0.
- CTest sin frameworks externos: comprueba salida y código de terminación.
- Android Kotlin `io.darkstar.darksplay`: receiver explícito, MediaCodec y
  SurfaceView; Gradle Wrapper y APK debug compilado.
- PoC GStreamer/OpenH264 1280×720/30 FPS por ADB/USB físico, validado en Android
  real durante 60 segundos; véase [procedimiento y límites](docs/VIDEO_POC.md).
- V0.2 PipeWire Capture: captura real de un monitor mediante el portal ScreenCast
  de GNOME, con consentimiento explícito, validada físicamente; véase
  [PIPEWIRE_POC.md](docs/PIPEWIRE_POC.md).
- V0.3: ScreenCast VIRTUAL (`source_type=4`) materializa Meta-0 tras negociar
  PipeWire. Ventanas movidas al monitor extendido aparecen en Android; Stop
  elimina Meta-0 y limpia la sesión. [Prueba física y límites](docs/VIRTUAL_POC.md).
- Control V0.1-B: HELLO/ACK, VIDEO_CONFIG/ACK y GOODBYE mediante JSON Lines;
  véase [sesión experimental y validación](docs/SESSION_POC.md).
- Arquitectura, propuesta conceptual de protocolo, privacidad y roadmap.
- Logo oficial conservado como recurso fuente, sin modificaciones.

## Planned

- Protocolo definitivo, capabilities y evaluación de latencia: V0.1 sigue siendo experimental.
- Aceleración de encoding y entrada touch/stylus: fases posteriores.
- Backend Windows en una etapa futura.

V0.x usará exclusivamente ADB mediante USB físico. No se implementan transportes
Wi-Fi, Ethernet o Bluetooth, ni servidores HTTP/WebSocket.

## Arquitectura y privacidad

El flujo futuro separa display, captura y encoder del Core, protocolo y transporte.
Android no necesita conocer el sistema operativo host. Ninguna dependencia de
GNOME, PipeWire o Windows forma parte del núcleo común.

El runtime será local-first, sin cloud, cuentas, telemetría ni analytics. Una
sesión USB no requerirá Internet. Conectar el cable no iniciará una sesión:
Android envía HELLO únicamente tras Start. El host espera ese mensaje y abre
VIRTUAL solo después de VIDEO_CONFIG_ACK. No existe mensaje READY. Las herramientas de desarrollo pueden usar Internet.

## Monitor virtual V0.3

Con el APK actualizado, abre Darksplay sin pulsar Start y ejecuta:

```sh
python3 -u tools/video-poc.py --virtual-display
```

Después pulsa Start y acepta el portal si muestra un diálogo. El endpoint de
control debe estar preparado; no hay retries ni reconexión automática.
MONITOR sigue siendo el modo predeterminado y `--videotestsrc` conserva la prueba sintética.
La resolución validada es 1280×720: Meta-0 mostró modo de 60 Hz, mientras
VIDEO_CONFIG y H.264 permanecen a 30 FPS nominales. Se observaron tirones;
no se midió latencia ni se optimizó rendimiento.

## Compilar y validar el host mínimo

Requisitos actuales: CMake 3.20 o posterior, compilador C++20 (inicialmente GCC)
y herramienta de build compatible con el generador CMake disponible. Ninja no
es requisito. No se necesitan todavía GStreamer, PipeWire ni ADB para compilar.

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
./build/host/darksplay-host
```

Si el entorno resuelve GCC mediante `ccache` y su caché predeterminada no es
escribible, puede mantenerse la caché dentro del proyecto, sin cambiar el sistema:

```sh
CCACHE_DIR="$PWD/build/.ccache" cmake -S . -B build
CCACHE_DIR="$PWD/build/.ccache" cmake --build build
```

## Documentación

- [Vídeo PoC V0.1-A](docs/VIDEO_POC.md)
- [Sesión PoC V0.1-B](docs/SESSION_POC.md)
- [V0.2 PipeWire Capture](docs/PIPEWIRE_POC.md)
- [V0.3 monitor virtual](docs/VIRTUAL_POC.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Protocolo conceptual](docs/PROTOCOL.md)
- [Privacidad](docs/PRIVACY.md)
- [Roadmap](docs/ROADMAP.md)

La licencia está [pendiente de decisión](LICENSE). El logo e icono oficial es
`assets/branding/Darksplay.png`; su diseño, colores y proporciones deben conservarse.
