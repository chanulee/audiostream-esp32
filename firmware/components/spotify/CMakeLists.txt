set(BELL cspot/bell)
set(sources "")
if(CONFIG_SPOTIFY_ENABLED)
    file(GLOB sources cspot/src/*.cpp cspot/src/*.c
        ${BELL}/main/utilities/*.cpp ${BELL}/main/utilities/*.c
        ${BELL}/main/io/*.cpp ${BELL}/main/io/*.c
        ${BELL}/main/platform/esp/*.cpp
        ${BELL}/external/nanopb/*.c ${BELL}/external/tremor/*.c
        generated/protobuf/*.c)
    list(FILTER sources EXCLUDE REGEX "(BellHTTPServer|MGStreamAdapter|EncodedAudioStream|X509Bundle|ivorbisfile_example)[.](cpp|c)$")
    # Preserve warnings in vendored cspot/Tremor without treating them as errors.
    set_source_files_properties(${sources} PROPERTIES COMPILE_OPTIONS "-Wno-error=all")
    list(APPEND sources spotify.cpp form_codec.cpp)
endif()
idf_component_register(SRCS ${sources} INCLUDE_DIRS "."
    PRIV_INCLUDE_DIRS cspot/include generated
        ${BELL}/main/utilities/include ${BELL}/main/io/include
        ${BELL}/main/platform ${BELL}/main/audio-codec/include
        ${BELL}/main/audio-dsp/include ${BELL}/main/audio-sinks/include
        ${BELL}/external/nanopb ${BELL}/external/tremor
    REQUIRES esp_http_server
    PRIV_REQUIRES mbedtls nvs_flash json espressif__mdns pthread esp_timer lwip esp_netif esp_http_client)
if(CONFIG_SPOTIFY_ENABLED)
    target_compile_features(${COMPONENT_LIB} PRIVATE cxx_std_20)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PB_ENABLE_MALLOC PB_FIELD_32BIT
        BELL_ONLY_CJSON BELL_DISABLE_CODECS BELL_DISABLE_FMT BELL_DISABLE_REGEX)
    target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=unused-variable
        -Wno-error=unused-function -Wno-error=sign-compare -Wno-error=format
        -Wno-error=char-subscripts -Wno-error=misleading-indentation -Wno-error=maybe-uninitialized -Wno-error=missing-field-initializers)
endif()
