# Roadmap

Plan orientativo sin fechas. Las fases futuras no están implementadas y dependerán
de validación técnica y revisión de decisiones pendientes.

| Etapa | Alcance y objetivo |
| --- | --- |
| PHASE 0 | Bootstrap, arquitectura, documentación, host mínimo y CTest. Bootstrap Android Kotlin y APK debug validados; instalación física pendiente de dispositivo ADB. |
| V0.1 | Patrón de vídeo generado en host → H.264 con OpenH264 → ADB/USB → Android → MediaCodec → Surface o alternativa nativa adecuada. Demostrar transporte y reproducción con baja latencia razonable; definir métricas antes de evaluar. |
| V0.2 | Captura real de pantalla mediante PipeWire. |
| V0.3 | Monitor virtual y escritorio extendido real; mecanismo Linux pendiente de investigación. |
| V0.4 | Codificación por hardware y optimización de latencia y recursos; VA-API candidato Linux. |
| V0.5 | Entrada touch Android → Linux. |
| V0.6 | Stylus/S Pen cuando el dispositivo lo soporte: posición, presión, tilt, botones y tipo de herramienta cuando esté disponible. |
| V1.0 | Primera versión Linux considerada estable tras acordar criterios de estabilidad. |
| FUTURE | Backend Windows con captura, virtual display y aceleración apropiados. |

Fedora/GNOME/Wayland será el primer entorno host; Android el cliente inicial.
V0.x mantiene exclusivamente transporte ADB sobre USB físico. Otros transportes
podrán investigarse posteriormente, sin cambiar la independencia de Internet del
modo USB. No se continúa con V0.1 dentro de Fase 0.
