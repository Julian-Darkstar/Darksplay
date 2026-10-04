# Protocolo Darksplay — propuesta conceptual 0.1

Propuesta de diseño futuro; el apartado V0.1-B registra la excepción implementada. La versión 0.1 identifica esta propuesta,
no una versión de wire protocol aceptada. El protocolo será independiente del SO
host y del transporte. V0.x solo implementará ADB mediante USB físico.

| Mensaje | Propósito | Dirección | Información conceptual | Etapa aproximada |
| --- | --- | --- | --- | --- |
| HELLO | Identificación y negociación inicial | Ambas | Versión compatible, capacidades y disponibilidad explícita del cliente | V0.1 |
| CONFIG | Acordar parámetros de sesión | Host → Android, con confirmación por definir | Parámetros elegidos entre capacidades comunes | V0.1 |
| VIDEO_CONFIG | Preparar decodificación | Host → Android | Codec, resolución, FPS y datos necesarios del decoder | V0.1 |
| VIDEO_FRAME | Entregar vídeo comprimido | Host → Android | Payload codificado, tiempo de presentación e información de sincronización | V0.1 |
| DISPLAY_RESIZE | Coordinar cambio de dimensiones | Ambas; autoridad por definir | Dimensiones solicitadas/aceptadas y actualización de configuración | V0.3 |
| INPUT_EVENT | Entregar entrada al host | Android → Host | Posición, tipo de evento/herramienta, presión, tilt y botones disponibles | V0.5 / V0.6 |
| PING | Comprobar continuidad de sesión | Ambas | Correlación y respuesta conceptual; tiempos por definir | V0.1 |
| GOODBYE | Finalizar sesión ordenadamente | Ambas | Motivo de cierre y liberación de recursos | V0.1 |

La negociación futura contemplará resolución, FPS, codecs, touch, stylus, pressure
y tilt. Solo se habilitarán capacidades soportadas y aceptadas por ambos extremos.
S Pen es una posibilidad de dispositivo, no un requisito de fabricante.

HELLO no sustituye la preparación explícita del cliente. La conexión física no
constituye consentimiento ni inicia la sesión. En V0.1-B la disponibilidad del endpoint tras Start representa preparación, sin
mensaje READY. La negociación futura de capacidades y cambios sigue pendiente.

## Excepción experimental V0.1-A

El [PoC de vídeo](VIDEO_POC.md) envía únicamente Annex B con AUD, SPS/PPS y
parámetros fijos, mediante forwarding ADB de sockets Unix. No implementa los
mensajes de esta propuesta ni control plane, negociación o serialización definitiva.
El estado listo depende de la acción explícita Start receiver en Android.

## Experimento implementado V0.1-B

[Session PoC](SESSION_POC.md) añade control separado del vídeo sobre dos sockets
Unix/localabstract mediante ADB/USB físico. Control usa JSON Lines UTF-8, una línea
por objeto, límite de 4096 bytes sin LF y wire version `protocol=1`.

| Mensaje experimental | Dirección | Campos exactos |
| --- | --- | --- |
| HELLO | Host → Android | `type="hello"`, `protocol=1` |
| HELLO_ACK | Android → Host | `type="hello_ack"`, `protocol=1` |
| VIDEO_CONFIG | Host → Android | `type="video_config"`, `codec="h264"`, `width`, `height`, `fps` enteros |
| VIDEO_CONFIG_ACK | Android → Host | `type="video_config_ack"` |
| GOODBYE | Host → Android | `type="goodbye"`, `reason` string diagnóstico |

No empieza vídeo hasta ambos ACK. Parámetros válidos en el PoC: width 1..1920,
height 1..1080, fps 1..60; no hay negociación de capabilities. Plazos de handshake
5 s; inválidos/EOF/timeout cierran la sesión. GOODBYE es best effort, nunca requisito
para cleanup. Annex B + AUD continúa exclusivamente en el video plane, sin
VIDEO_FRAME ni encapsulación Darksplay por frame.

**JSON Lines, wire version 1, límites y Annex B son experimentales de V0.1-B,
no formato definitivo de Darksplay 1.0.** Los mensajes futuros de la tabla
conceptual no están implementados; no hay CONFIG, PING ni INPUT_EVENT.

## Pendiente de revisión para integrar V0.1

Capabilities, correlación, formato definitivo, reconexión y backpressure. Los dos
canales y comprobación USB ya se prueban en el PoC, sin fijar arquitectura final.
No se fijan offsets, tamaños definitivos, endianness ni estructuras binarias.
La pérdida de transporte termina y libera la sesión aun sin GOODBYE.
