# Protocolo Darksplay — propuesta conceptual 0.1

Documento de diseño, sin implementación. La versión 0.1 identifica esta propuesta,
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
constituye consentimiento ni inicia la sesión. Se deberá definir cómo se comunica
el estado listo, cómo se confirman CONFIG y cambios, y cómo se rechazan versiones
incompatibles o capacidades no soportadas.

## Excepción experimental V0.1-A

El [PoC de vídeo](VIDEO_POC.md) envía únicamente Annex B con AUD, SPS/PPS y
parámetros fijos, mediante forwarding ADB de sockets Unix. No implementa los
mensajes de esta propuesta ni control plane, negociación o serialización definitiva.
El estado listo depende de la acción explícita Start receiver en Android.

## Pendiente de revisión para integrar V0.1

Framing, serialización, versión efectiva, límites de mensajes/buffers, correlación,
confirmaciones, errores, timeouts, reconexión y backpressure. También quedan por
acordar los canales ADB y la comprobación de USB físico para excluir ADB inalámbrico.
No se fijan offsets, tamaños definitivos, endianness ni estructuras binarias.
La pérdida de transporte deberá terminar y liberar la sesión aun sin GOODBYE.
