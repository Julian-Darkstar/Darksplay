# Roadmap

Plan orientativo sin fechas. Las fases futuras no están implementadas y dependerán
de validación técnica y revisión de decisiones pendientes.

| Etapa | Alcance y objetivo |
| --- | --- |
| PHASE 0 | Bootstrap, arquitectura, documentación, host mínimo y CTest. Bootstrap Android Kotlin y APK debug validados; instalación física del bootstrap confirmada por el usuario. |
| V0.1-A | PoC implementado: vídeo sintético OpenH264 → ADB/USB físico → MediaCodec/SurfaceView. Prueba de 60 s y 1.800 frames; no equivale a monitor extendido ni V0.1 completo. |
| V0.1 | Patrón de vídeo generado en host → H.264 con OpenH264 → ADB/USB → Android → MediaCodec → Surface o alternativa nativa adecuada. Demostrar transporte y reproducción con baja latencia razonable; definir métricas antes de evaluar. |
| V0.2 | **Implementado y validado.** Captura real de un monitor mediante `xdg-desktop-portal ScreenCast` + PipeWire, consentimiento explícito de GNOME, GStreamer/OpenH264 y ADB/USB físico. La validación física confirmó imagen cambiante, pantalla estática durante más de 15 s seguida de movimiento, revocación desde GNOME y cleanup de procesos/forwards. No incluye monitor virtual ni escritorio extendido. Véase [PIPEWIRE_POC.md](PIPEWIRE_POC.md). |
| V0.3 | **Funcionalmente completado y validado físicamente.** ScreenCast VIRTUAL (`source_type=4`) → Meta-0 → PipeWire/OpenH264 → ADB/USB → Android. Ventanas del escritorio extendido visibles en Android; Stop elimina Meta-0 y limpia la sesión. 1280×720/30 FPS nominales, tirones observados sin diagnóstico ni medición de latencia. Véase [VIRTUAL_POC.md](VIRTUAL_POC.md). |
| V0.4 | Codificación por hardware y optimización de latencia y recursos; VA-API candidato Linux. |
| V0.5 | Entrada touch Android → Linux. |
| V0.6 | Stylus/S Pen cuando el dispositivo lo soporte: posición, presión, tilt, botones y tipo de herramienta cuando esté disponible. |
| V1.0 | Primera versión Linux considerada estable tras acordar criterios de estabilidad. |
| FUTURE | Backend Windows con captura, virtual display y aceleración apropiados. |

Fedora/GNOME/Wayland será el primer entorno host; Android el cliente inicial.
V0.x mantiene exclusivamente transporte ADB sobre USB físico. Otros transportes
podrán investigarse posteriormente, sin cambiar la independencia de Internet del
modo USB. No se continúa con V0.1 dentro de Fase 0.
