#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
esp_err_t spotify_audio_init(void);
bool spotify_audio_read(int16_t *pcm, size_t max_frames, size_t *frames);
int32_t spotify_audio_volume_q15(void);
