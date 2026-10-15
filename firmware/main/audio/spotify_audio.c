#include "spotify_audio.h"
#include <stdlib.h>
#include "spotify.h"
#include "pcm_fifo.h"
#include "audio_output.h"
#include "audio_receiver.h"
#include "rtsp_events.h"
#include "playback_control.h"
#include "settings.h"
#include "led.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static SemaphoreHandle_t lock;
static pcm_fifo_t fifo;
static bool selected, paused;
static uint64_t written, played;
static int32_t volume_q15=16384;
static void flush_locked(void) {
    pcm_fifo_clear(&fifo);
    written=played=0;
}
static bool begin(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    selected=true; paused=false; flush_locked();
    xSemaphoreGive(lock);
    playback_control_set_source(PLAYBACK_SOURCE_SPOTIFY);
    return true;
}
static void pause_audio(bool value) {
    xSemaphoreTake(lock, portMAX_DELAY);
    if (!value && !selected) { selected=true; flush_locked(); }
    paused=value;
    xSemaphoreGive(lock);
    if (!value) playback_control_set_source(PLAYBACK_SOURCE_SPOTIFY);
    else playback_control_set_playing(PLAYBACK_SOURCE_SPOTIFY, false);
}
static void end(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    selected=false; paused=true; flush_locked();
    xSemaphoreGive(lock);
    playback_control_release_source(PLAYBACK_SOURCE_SPOTIFY);
}
static void flush(void) {
    playback_control_lock_output();
    xSemaphoreTake(lock, portMAX_DELAY);
    flush_locked();
    xSemaphoreGive(lock);
    if (playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY) audio_output_flush();
    playback_control_unlock_output();
}
void spotify_audio_yield(void) {
    xSemaphoreTake(lock, portMAX_DELAY);
    selected=false; paused=true; flush_locked();
    xSemaphoreGive(lock);
    spotify_command(SPOTIFY_YIELD);
}
static void volume(uint16_t value) {
    __atomic_store_n(&volume_q15, (int32_t)((uint32_t)value*32768/65535), __ATOMIC_RELAXED);
}
int32_t spotify_audio_volume_q15(void) {
    return __atomic_load_n(&volume_q15, __ATOMIC_RELAXED);
}
static size_t write_pcm(const uint8_t *pcm, size_t bytes) {
    xSemaphoreTake(lock, portMAX_DELAY);
    size_t result=selected && !paused && playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY ? pcm_fifo_write(&fifo, pcm, bytes) : 0;
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
    return err;
}
