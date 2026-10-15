/**
 * Output ownership for AirPlay, Spotify and Bluetooth.
 *
 * Exactly one source feeds the playback task. A source takes the output only
 * on an explicit play request; the previous owner is asked to pause and its
 * queued PCM is dropped. Lock order: output lock, then a source FIFO lock.
 */

#include "audio_output.h"
#include "audio_receiver.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "led.h"
#include "playback_control.h"
#include "rtsp_events.h"
#ifdef CONFIG_SPOTIFY_ENABLED
#include "spotify_audio.h"
#endif
#ifdef CONFIG_BT_A2DP_ENABLE
#include "a2dp_sink.h"
#endif

static SemaphoreHandle_t output_lock;
static playback_source_t source;

playback_source_t playback_control_get_source(void) {
  return __atomic_load_n(&source, __ATOMIC_ACQUIRE);
}

void playback_control_lock_output(void) {
  xSemaphoreTake(output_lock, portMAX_DELAY);
}

void playback_control_unlock_output(void) {
  xSemaphoreGive(output_lock);
}

void playback_control_set_source(playback_source_t next) {
  playback_control_lock_output();
  playback_source_t previous = playback_control_get_source();
  if (previous != next) {
    __atomic_store_n(&source, next, __ATOMIC_RELEASE);
    if (previous == PLAYBACK_SOURCE_AIRPLAY) {
      audio_receiver_pause();
    }
#ifdef CONFIG_SPOTIFY_ENABLED
    if (previous == PLAYBACK_SOURCE_SPOTIFY) {
      spotify_audio_yield();
    }
#endif
#ifdef CONFIG_BT_A2DP_ENABLE
    if (previous == PLAYBACK_SOURCE_BLUETOOTH) {
      bt_a2dp_sink_yield();
    }
#endif
    audio_output_flush();
  }
  led_set_playback_status(next != PLAYBACK_SOURCE_NONE,
                          next != PLAYBACK_SOURCE_NONE);
  playback_control_unlock_output();
}

void playback_control_release_source(playback_source_t expected) {
  playback_control_lock_output();
  if (playback_control_get_source() == expected) {
    __atomic_store_n(&source, PLAYBACK_SOURCE_NONE, __ATOMIC_RELEASE);
    audio_output_flush();
    led_set_playback_status(false, false);
  }
  playback_control_unlock_output();
}

void playback_control_set_playing(playback_source_t expected, bool playing) {
  playback_control_lock_output();
  if (playback_control_get_source() == expected) {
    audio_output_flush();
    led_set_playback_status(true, playing);
  }
  playback_control_unlock_output();
}

static void airplay_event(rtsp_event_t event, const rtsp_event_data_t *data,
                          void *user) {
  (void)data;
  (void)user;
  if (event == RTSP_EVENT_PLAYING) {
    playback_control_set_source(PLAYBACK_SOURCE_AIRPLAY);
  } else if (event == RTSP_EVENT_PAUSED) {
    playback_control_set_playing(PLAYBACK_SOURCE_AIRPLAY, false);
  } else if (event == RTSP_EVENT_DISCONNECTED) {
    playback_control_release_source(PLAYBACK_SOURCE_AIRPLAY);
  }
}

esp_err_t playback_control_source_init(void) {
  output_lock = xSemaphoreCreateMutex();
  if (!output_lock) {
    return ESP_ERR_NO_MEM;
  }
  if (rtsp_events_register(airplay_event, NULL) != 0) {
    vSemaphoreDelete(output_lock);
    output_lock = NULL;
    return ESP_ERR_NO_MEM;
  }
  return ESP_OK;
}
