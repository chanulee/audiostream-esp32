#include "spotify_audio.h"
#include "spotify.h"
#include "rtsp_events.h"
#include "playback_control.h"
#include "audio_output.h"
#include "freertos/semphr.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static spotify_callbacks_t hooks;
static rtsp_event_callback_t listener;
static unsigned bt_pauses;
void bt_a2dp_sink_yield(void) { bt_pauses++; }
static unsigned pause_requests, flushes, airplay_pauses;
static bool led_connected, led_playing;
static unsigned led_updates;
void led_set_playback_status(bool connected, bool playing) {
    led_connected=connected; led_playing=playing; led_updates++;
}
void *heap_caps_malloc(size_t bytes, unsigned caps) { (void)caps; return malloc(bytes); }
SemaphoreHandle_t xSemaphoreCreateMutex(void) { return (void *)1; }
int xSemaphoreTake(SemaphoreHandle_t h, TickType_t t) { (void)h; (void)t; return 1; }
int xSemaphoreGive(SemaphoreHandle_t h) { (void)h; return 1; }
void vSemaphoreDelete(SemaphoreHandle_t h) { (void)h; }
esp_err_t settings_get_device_name(char *name, size_t size) { strncpy(name,"Test",size); return ESP_OK; }
esp_err_t spotify_init(const char *name, const spotify_callbacks_t *cb) { assert(!strcmp(name,"Test")); hooks=*cb; return ESP_OK; }
int rtsp_events_register(rtsp_event_callback_t cb, void *data) { (void)data; listener=cb; return 0; }

void audio_output_flush(void) { flushes++; }
void audio_receiver_pause(void) { airplay_pauses++; }
void spotify_command(spotify_command_t command) { assert(command==SPOTIFY_YIELD); pause_requests++; }
int main(void) {
    assert(playback_control_source_init()==ESP_OK);
    assert(spotify_audio_init()==ESP_OK);
    int16_t input[]={1,2,3,4,5,6,7,8}, output[8]; size_t frames;
    assert(hooks.begin() && playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY);
    assert(led_connected && led_playing);
    assert(hooks.write((const uint8_t *)input,sizeof(input))==sizeof(input));
    assert(hooks.written_frames()==4);
    assert(spotify_audio_read(output,2,&frames) && frames==2 && !memcmp(input,output,8));
    hooks.pause(true);
    assert(led_connected && !led_playing);
    assert(spotify_audio_read(output,4,&frames) && frames==0);
    assert(hooks.write((const uint8_t *)input,sizeof(input))==0);
    hooks.pause(false);
    assert(led_connected && led_playing);
    assert(spotify_audio_read(output,4,&frames) && frames==2 && !memcmp(input+4,output,8));
    hooks.volume(0); assert(spotify_audio_volume_q15()==0);
    hooks.volume(65535); assert(spotify_audio_volume_q15()==32768);
    hooks.write((const uint8_t *)input,sizeof(input));
    listener(RTSP_EVENT_PLAYING,NULL,NULL);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_AIRPLAY && pause_requests==1);
    unsigned previous_flushes=flushes;
    hooks.pause(true); hooks.flush(); hooks.end();
    assert(playback_control_get_source()==PLAYBACK_SOURCE_AIRPLAY && flushes==previous_flushes);
    assert(hooks.begin() && playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY);
    assert(airplay_pauses==1 && led_connected && led_playing);
    previous_flushes=flushes;
    audio_output_flush_airplay();
    assert(flushes==previous_flushes);
    // Late pause/disconnect from the old AirPlay session cannot reclaim output.
    listener(RTSP_EVENT_PAUSED,NULL,NULL);
    listener(RTSP_EVENT_DISCONNECTED,NULL,NULL);
    hooks.write((const uint8_t *)input,sizeof(input));
    assert(spotify_audio_read(output,4,&frames) && frames==4);
    listener(RTSP_EVENT_PLAYING,NULL,NULL);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_AIRPLAY && pause_requests==2);
    audio_output_flush_airplay();
    assert(flushes>previous_flushes);
    previous_flushes=flushes;
    hooks.pause(true);
    assert(flushes==previous_flushes);
    hooks.pause(false);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY && airplay_pauses==2);
    assert(spotify_audio_read(output,4,&frames) && frames==0);
    assert(hooks.begin());
    assert(spotify_audio_read(output,4,&frames) && frames==0); // stale PCM discarded
    hooks.write((const uint8_t *)input,sizeof(input)); hooks.flush();
    assert(hooks.written_frames()==0 && hooks.played_frames()==0);
    assert(spotify_audio_read(output,4,&frames) && frames==0);
    hooks.end();
    assert(playback_control_get_source()==PLAYBACK_SOURCE_NONE);
    assert(!led_connected && !led_playing);
    assert(!spotify_audio_read(output,4,&frames) && flushes>0);
    // A Bluetooth connection alone never selects output. A2DP STARTED does.
    playback_control_set_source(PLAYBACK_SOURCE_BLUETOOTH);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_BLUETOOTH);
    previous_flushes=flushes;
    hooks.end();
    listener(RTSP_EVENT_PAUSED,NULL,NULL);
    listener(RTSP_EVENT_DISCONNECTED,NULL,NULL);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_BLUETOOTH && flushes==previous_flushes);
    hooks.begin();
    assert(bt_pauses==1 && playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY);
    playback_control_release_source(PLAYBACK_SOURCE_BLUETOOTH);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_SPOTIFY);
    playback_control_set_source(PLAYBACK_SOURCE_BLUETOOTH);
    assert(pause_requests==3);
    listener(RTSP_EVENT_PLAYING,NULL,NULL);
    assert(bt_pauses==2 && playback_control_get_source()==PLAYBACK_SOURCE_AIRPLAY);
    playback_control_release_source(PLAYBACK_SOURCE_BLUETOOTH);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_AIRPLAY);
    listener(RTSP_EVENT_DISCONNECTED,NULL,NULL);
    assert(playback_control_get_source()==PLAYBACK_SOURCE_NONE);
    puts("Spotify/AirPlay/Bluetooth output ownership tests passed");
}
