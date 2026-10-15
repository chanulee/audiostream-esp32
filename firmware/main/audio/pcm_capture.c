#include "pcm_capture.h"
#include <string.h>
void pcm_capture_reset(pcm_capture_t *c, void *data, size_t capacity) {
    *c = (pcm_capture_t){.data = data, .capacity = capacity - capacity % 4};
}
void pcm_capture_append(pcm_capture_t *c, const void *data, size_t bytes, bool audio) {
    if (!c->data || c->used == c->capacity || (!c->started && !audio)) return;
    bytes -= bytes % 4;
    if (!bytes) return;
    c->started = true;
    if (bytes > c->capacity - c->used) bytes = c->capacity - c->used;
    memcpy(c->data + c->used, data, bytes);
    c->used += bytes;
}
void pcm_capture_append_rate(pcm_capture_t *c, const void *data, size_t bytes, bool audio, uint32_t rate, unsigned seconds) {
    if (!c->data || c->used == c->capacity || c->rate_changed || (!c->started && !audio)) return;
    if (!c->started) {
        size_t capacity=(size_t)seconds*rate*4;
        if (!rate || !seconds || capacity > c->capacity) { c->rate_changed=true; return; }
        c->sample_rate=rate;
        c->capacity=capacity;
    } else if (rate != c->sample_rate) {
        c->rate_changed=true;
        return;
    }
    pcm_capture_append(c, data, bytes, audio);
}
static void le32(uint8_t *p, uint32_t v) {
    for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
void pcm_capture_wav_header(uint8_t h[44], uint32_t bytes, uint32_t rate) {
    memset(h, 0, 44);
    memcpy(h, "RIFF", 4); le32(h + 4, bytes + 36);
    memcpy(h + 8, "WAVEfmt ", 8); le32(h + 16, 16);
    h[20] = 1; h[22] = 2; // PCM, stereo
    le32(h + 24, rate); le32(h + 28, rate * 4);
    h[32] = 4; h[34] = 16;
    memcpy(h + 36, "data", 4); le32(h + 40, bytes);
}
