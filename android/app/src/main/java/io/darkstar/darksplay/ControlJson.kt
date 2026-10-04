package io.darkstar.darksplay

import android.util.JsonReader
import android.util.JsonToken
import java.io.StringReader

internal object ControlJson {
    fun parse(line: String): Map<String, Any> {
        val result = mutableMapOf<String, Any>()
        JsonReader(StringReader(line)).use { reader ->
            reader.isLenient = false
            reader.beginObject()
            while (reader.hasNext()) {
                val key = reader.nextName()
                require(!result.containsKey(key)) { "Duplicate JSON key" }
                result[key] = when (reader.peek()) {
                    JsonToken.STRING -> reader.nextString()
                    JsonToken.NUMBER -> {
                        val number = reader.nextString()
                        require(number.matches(Regex("-?(0|[1-9][0-9]*)"))) { "Integer required" }
                        number.toLong()
                    }
                    else -> error("Only string/integer control fields supported")
                }
            }
            reader.endObject()
            require(reader.peek() == JsonToken.END_DOCUMENT) { "Trailing JSON data" }
        }
        require(result["type"] is String) { "Missing string type" }
        return result
    }
}
