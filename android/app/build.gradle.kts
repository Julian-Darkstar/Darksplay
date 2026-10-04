plugins {
    id("com.android.application")
}

android {
    namespace = "io.darkstar.darksplay"
    compileSdk = 37
    buildToolsVersion = "36.0.0"

    defaultConfig {
        applicationId = "io.darkstar.darksplay"
        minSdk = 23
        targetSdk = 37
        versionCode = 1
        versionName = "0.0.1-dev"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

// Preserve the official source bytes in a generated Android resource.
abstract class SyncBranding : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val logo: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun copyLogo() {
        val destination = outputDirectory.file("drawable-nodpi/darksplay_logo.png").get().asFile
        destination.parentFile.mkdirs()
        logo.get().asFile.copyTo(destination, overwrite = true)
    }
}

val syncBranding = tasks.register<SyncBranding>("syncBranding") {
    logo.set(rootProject.layout.projectDirectory.file("../assets/branding/Darksplay.png"))
    outputDirectory.set(layout.buildDirectory.dir("generated/branding/res"))
}
androidComponents {
    onVariants { variant ->
        variant.sources.res?.addGeneratedSourceDirectory(syncBranding, SyncBranding::outputDirectory)
    }
}
