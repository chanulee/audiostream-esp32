#include "spotify_audio.h"
#include <stdlib.h>
#include "spotify.h"
#include "pcm_fifo.h"
#include "audio_output.h"
#include "rtsp_events.h"
#include "playback_control.h"
#include "settings.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static SemaphoreHandle_t lock;
static pcm_fifo_t fifo;
static bool selected, paused, airplay_playing;
static uint64_t written, played;
static int32_t volume_q15=16384;
static void flush_locked(void) {
    pcm_fifo_clear(&fifo);
    written=played=0;
}
static bool begin(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bool allowed=!airplay_playing;
    if (allowed) {
        selected=true; paused=false; flush_locked();
        playback_control_set_source(PLAYBACK_SOURCE_SPOTIFY);
    }
    xSemaphoreGive(lock);
    if (allowed) {
        audio_output_flush();
    }
    return allowed;
}
static void pause_audio(bool value) {
    xSemaphoreTake(lock, portMAX_DELAY);
    // Resume only while AirPlay is idle; a paused buffer may be retained.
    if (!value && !selected && !airplay_playing) selected=true;
    paused=value || airplay_playing;
    if (selected && !paused) playback_control_set_source(PLAYBACK_SOURCE_SPOTIFY);
    xSemaphoreGive(lock);
    audio_output_flush();
}
static void end(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bool was_selected=selected;
    selected=false; paused=true; flush_locked();
    if (was_selected) playback_control_set_source(PLAYBACK_SOURCE_AIRPLAY);
    xSemaphoreGive(lock);
    audio_output_flush();
}
static void flush(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    flush_locked();
    xSemaphoreGive(lock);
    audio_output_flush();
}
static void volume(uint16_t value) {
    __atomic_store_n(&volume_q15, (int32_t)((uint32_t)value*32768/65535), __ATOMIC_RELAXED);
}
int32_t spotify_audio_volume_q15(void) {
    return __atomic_load_n(&volume_q15, __ATOMIC_RELAXED);
}
static size_t write_pcm(const uint8_t *pcm, size_t bytes) {
    xSemaphoreTake(lock, portMAX_DELAY);
    size_t result=selected && !paused ? pcm_fifo_write(&fifo, pcm, bytes) : 0;
    written+=result/4;
    xSemaphoreGive(lock);
    return result;
}
bool spotify_audio_read(int16_t *pcm, size_t max_frames, size_t *frames) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bool active=selected;
    size_t bytes=active && !paused ? pcm_fifo_read(&fifo, pcm, max_frames*4) : 0;
    played+=bytes/4;
    xSemaphoreGive(lock);
    *frames=bytes/4;
    return active;
}
static uint64_t written_frames(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    uint64_t result=written;
    xSemaphoreGive(lock);
    return result;
}
static uint64_t played_frames(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    uint64_t result=played;
    xSemaphoreGive(lock);
    return result;
}
static void airplay_event(rtsp_event_t event, const rtsp_event_data_t *data, void *user) {
    (void)data; (void)user;
    bool yield=false;
    xSemaphoreTake(lock, portMAX_DELAY);
    if (event==RTSP_EVENT_PLAYING) {
        airplay_playing=true;
        yield=selected;
        selected=false; paused=true; flush_locked();
        playback_control_set_source(PLAYBACK_SOURCE_AIRPLAY);
    } else if (event==RTSP_EVENT_PAUSED || event==RTSP_EVENT_DISCONNECTED) {
        airplay_playing=false;
    }
    xSemaphoreGive(lock);
    if (yield) { audio_output_flush(); spotify_command(SPOTIFY_YIELD); }
}
esp_err_t spotify_audio_init(void) {
    lock=xSemaphoreCreateMutex();
    void *data=heap_caps_malloc(64*1024, MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if (!lock || !data) { free(data); if (lock) vSemaphoreDelete(lock); lock=NULL; return ESP_ERR_NO_MEM; }
    pcm_fifo_init(&fifo, data, 64*1024);
    const spotify_callbacks_t callbacks={begin, pause_audio, end, flush, volume, write_pcm,
                                         written_frames, played_frames};
    char name[65];
    settings_get_device_name(name, sizeof(name));
    esp_err_t err=spotify_init(name, &callbacks);
    if (err==ESP_OK && rtsp_events_register(airplay_event, NULL)!=0) err=ESP_ERR_NO_MEM;
    return err;
}
