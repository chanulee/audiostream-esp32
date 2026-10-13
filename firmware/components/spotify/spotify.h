#pragma once
#include "esp_http_server.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef enum { SPOTIFY_TOGGLE, SPOTIFY_PAUSE, SPOTIFY_NEXT, SPOTIFY_PREV,
               SPOTIFY_VOLUME_UP, SPOTIFY_VOLUME_DOWN, SPOTIFY_YIELD, SPOTIFY_MUTE_TOGGLE } spotify_command_t;
typedef struct {
    bool (*begin)(void);
    void (*pause)(bool paused);
    void (*end)(void);
    void (*flush)(void);
    void (*volume)(uint16_t volume);
    size_t (*write)(const uint8_t *pcm, size_t bytes);
    uint64_t (*written_frames)(void);
    uint64_t (*played_frames)(void);
} spotify_callbacks_t;
esp_err_t spotify_init(const char *name, const spotify_callbacks_t *callbacks);
esp_err_t spotify_register_http(httpd_handle_t server);
esp_err_t spotify_start(uint16_t port);
void spotify_command(spotify_command_t command);
int spotify_volume_percent(void);
#ifdef __cplusplus
}
#endif
