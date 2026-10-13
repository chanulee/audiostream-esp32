#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct {
    uint8_t *data;
    size_t capacity, used;
    bool started;
} pcm_capture_t;
void pcm_capture_reset(pcm_capture_t *capture, void *data, size_t capacity);
void pcm_capture_append(pcm_capture_t *capture, const void *data, size_t bytes, bool audio);
void pcm_capture_wav_header(uint8_t header[44], uint32_t bytes, uint32_t rate);
