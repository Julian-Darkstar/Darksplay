# Privacidad

Estas son garantías de diseño para el runtime futuro. La Fase 0 únicamente imprime
la identificación del host; el bootstrap Android muestra nombre y logo.
No implementan conexión ni sesión.

- Local-first: una sesión USB deberá funcionar completamente sin Internet.
- Sin servicios cloud durante runtime, cuentas, telemetría ni analytics.
- V0.x utilizará exclusivamente ADB sobre una conexión física USB; disponer de
  ADB inalámbrico no lo convierte en un transporte permitido para Darksplay V0.x.
- Conectar físicamente Android no iniciará automáticamente una sesión.
- El cliente Android deberá estar abierto y explícitamente listo antes del inicio.
- El host deberá liberar completamente los recursos al terminar o perder la sesión.

Git, Android Studio, Gradle, gestores de paquetes y otras herramientas de desarrollo
pueden requerir o utilizar Internet. Esto es independiente del runtime Darksplay.
Durante el bootstrap Android se descargaron la distribución oficial de Gradle y
dependencias estándar de build. No se instalaron paquetes del sistema ni nuevos
componentes SDK/JDK.

Transportes adicionales podrán incorporarse en versiones futuras, sin cambiar las
garantías de privacidad y operación completamente local del modo USB. No son
requisito de V0.x y no se implementan servicios HTTP o WebSocket alternativos.
