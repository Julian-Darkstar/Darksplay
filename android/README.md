# Android de Darksplay — sesión experimental V0.3

Aplicación Kotlin mínima con nombre Darksplay, package `io.darkstar.darksplay`,
una Activity nativa con logo, Start/Stop receiver y SurfaceView. Un receiver
experimental utiliza LocalServerSocket, un parser Annex B y MediaCodec `video/avc`
con configuración recibida mediante VIDEO_CONFIG (PoC host: 1280×720/30 FPS).
Con la app visible y Surface disponible se prepara únicamente el control técnico.
Start autoriza HELLO Android → Host; HELLO_ACK y VIDEO_CONFIG llegan del host.
Android prepara vídeo y responde VIDEO_CONFIG_ACK antes de recibir H.264.
El host V0.3 ya transmite un monitor extendido real; Android solo decodifica y
renderiza. No implementa protocolo final, servicios, sockets IP, captura local,
entrada remota, telemetría ni analytics. No declara permisos especiales ni Internet.

[Sesión V0.1-B](../docs/SESSION_POC.md) y [evidencia histórica V0.1-A](../docs/VIDEO_POC.md).

## Requisitos y versiones

- SDK Platform 37.0 estable (`compileSdk = 37`, `targetSdk = 37`).
- SDK Build Tools 36.0.0; Platform Tools para instalar mediante ADB.
- Gradle Wrapper 9.3.1, Android Gradle Plugin 9.1.1 y Kotlin integrado en AGP.
- JDK compatible con Gradle; en esta validación se utiliza el JDK JetBrains 25.0.3
  integrado en Android Studio Flatpak (incluye `javac`). El bytecode de la app se configura para Java 17.
- No se usa Gradle global, NDK, JNI ni CMake Android.

`minSdk = 23` (Android 6.0) mantiene una base amplia para el bootstrap usando
APIs nativas. No garantiza que cada capacidad futura de vídeo o stylus exista
ni que esté validada en todas esas versiones. La compatibilidad real se negociará
por capacidades y se probará antes de V0.1; elevar este mínimo requerirá revisión.

Compatibilidad consultada en la documentación oficial:
[AGP 9.1.1](https://developer.android.com/build/releases/agp-9-1-0-release-notes),
[Kotlin integrado](https://developer.android.com/build/migrate-to-built-in-kotlin) y
[Java 25 desde Gradle 9.1](https://docs.gradle.org/9.1.0/release-notes.html).

## SDK local

Configurar `sdk.dir` en `android/local.properties` con la ubicación propia del SDK,
o proporcionar `ANDROID_HOME` al proceso. `local.properties` está excluido de Git.
En esta máquina el SDK detectado está en `/home/darkstar/Android/Sdk`; esa ruta no
forma parte de la configuración versionable ni es un requisito para otros equipos.
La descarga automática de componentes SDK está desactivada: los componentes
indicados deben existir. No se instalaron versiones adicionales del SDK ni JDK.

## Compilar

Desde `android/`:

```sh
./gradlew assembleDebug
```

El Wrapper oficial está incluido, fija su distribución y comprueba su SHA-256.
La primera compilación puede descargar Gradle y dependencias estándar de build;
esto no añade networking al runtime de Darksplay.

Para mantener las cachés y la clave debug locales dentro del proyecto:

```sh
GRADLE_USER_HOME="$PWD/.gradle-user-home" \
ANDROID_USER_HOME="$PWD/.android-user-home" \
./gradlew assembleDebug --no-daemon
```

En esta máquina Java del sistema es un runtime sin `javac`. Se usó el JDK completo
ya instalado de Android Studio, sin instalar Java ni modificar configuración global:

```sh
JAVA_HOME=/var/lib/flatpak/app/com.google.AndroidStudio/current/active/files/extra/jbr \
GRADLE_USER_HOME="$PWD/.gradle-user-home" \
ANDROID_USER_HOME="$PWD/.android-user-home" \
./gradlew assembleDebug --no-daemon
```

Esta ruta es un ejemplo local, no se fija en archivos Gradle versionables. En otro
entorno debe usarse la ubicación de su propio JDK completo compatible.

`--no-daemon` evita un proceso persistente; Gradle puede crear un proceso de uso
único que termina al finalizar el build. No se crea un daemon de Darksplay.

APK esperado: `app/build/outputs/apk/debug/app-debug.apk`.

## Instalar

Con un dispositivo autorizado:

```sh
adb devices -l
adb -s SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
```

Sustituir SERIAL por el identificador mostrado por ADB. Instalar no inicia una
sesión Darksplay: el transporte de control puede prepararse con la app visible, pero solo Start
autoriza HELLO y la sesión. No se modifican opciones del
dispositivo ni se habilita ADB inalámbrico.

## Logo

El recurso fuente permanece en `../assets/branding/Darksplay.png`. La tarea
`syncBranding` copia sus bytes a un recurso generado `drawable-nodpi`, usado en
pantalla y como icono. No hay reinterpretación ni variantes artísticas.
El ImageView conserva proporciones con `fitCenter`; la representación del icono
en el launcher depende del sistema Android.

## Validación histórica del bootstrap

- `assembleDebug --no-daemon`: `BUILD SUCCESSFUL in 47s`, 35 tareas ejecutadas,
  con el JDK integrado y las variables locales documentadas arriba.
- `lintDebug --no-daemon`: build correcto; véase el informe en
  `app/build/reports/lint-results-debug.html`. Resultado: 0 errores y 3 advertencias:
  versión Gradle más reciente disponible, sugerencia de `dataExtractionRules`
  para backup moderno y posible overdraw del fondo. No bloquean el bootstrap;
  la app no guarda datos y declara `allowBackup=false`.
- APK generado: `app/build/outputs/apk/debug/app-debug.apk`.
- El APK confirma package, nombre, SDK mínimo 23 y target 37; no contiene permisos.
- `adb devices -l` terminó correctamente con lista vacía: instalación física
  y apariencia no verificadas en aquella sesión; posteriormente el usuario
  confirmó instalación y ejecución del bootstrap en hardware.
- Logo generado y original tienen el mismo SHA-256.
- Advertencia de build no bloqueante: el lector SDK entiende XML hasta versión 3
  y encontró XML versión 4. No se modificó el SDK para suprimirla.
- En este entorno Gradle y ADB requirieron ejecución fuera del sandbox: este
  bloquea networking de build, bloqueos locales de Gradle y acceso USB/servidor ADB.


## Validación V0.1-A

- Wrapper `assembleDebug lint --offline --no-daemon`: correcto, usando el JDK
  integrado y variables locales anteriores. Lint: 0 errores, 2 advertencias
  (versión Gradle más reciente y reglas modernas de backup).
- Instalación debug en dispositivo autorizado USB: `Success`.
- Decoder seleccionado nativamente en hardware de prueba: `c2.exynos.h264.decoder`.
  El código no depende de ese fabricante ni selecciona el codec por nombre.
- Prueba continua de 60 s: 1.800 frames renderizados; EOF y Stop liberan recursos.
- Desconexión USB física: app abierta, Stream terminado y decoder liberado;
  reconectar no inicia otra sesión. Stop también funciona esperando conexión.
- Logs y detalles de desconexión/mediciones: `../docs/VIDEO_POC.md`.

## Validación V0.1-B

Control separado JSON Lines y vídeo Annex B; configuración recibida antes de
MediaCodec. `assembleDebug lint --offline --no-daemon` compila correctamente con
las versiones existentes. Lint mantiene 0 errores y 2 warnings históricos.
Sesión física normal de 10 s/300 frames, GOODBYE y cleanup; Stop, datos inválidos
y desconexión USB dejan la app utilizable. Detalles y prueba de reconexión en
[SESSION_POC.md](../docs/SESSION_POC.md), con las pruebas no realizadas explícitas.
No se midió latencia extremo a extremo ni se implementó captura/monitor virtual.

## Validación integrada V0.3

El APK con HELLO iniciado por Android fue instalado y probado mediante USB físico.
Meta-0 1280×720 permitió mover ventanas del escritorio GNOME hacia Android.
MediaCodec renderizó vídeo y Stop mostró `Stream finished`, liberó decoder/canales
y el host eliminó Meta-0 y sus forwards. Se observaron tirones; no se midió
latencia ni se optimizó rendimiento. [Evidencia completa](../docs/VIRTUAL_POC.md).
Las validaciones V0.1 anteriores son históricas y usaban el handshake anterior.
