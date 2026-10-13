#include "pcm_capture.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static unsigned read32(const uint8_t *p) {
    return p[0] | (unsigned)p[1] << 8 | (unsigned)p[2] << 16 | (unsigned)p[3] << 24;
}
int main(void) {
    uint8_t data[13], header[44];
    const uint8_t audio[] = {1,2,3,4,5,6,7,8};
    const uint8_t silence[8] = {0};
    memset(data, 0xff, sizeof(data));
    pcm_capture_t clip;
    pcm_capture_reset(&clip, data, sizeof(data));
    pcm_capture_append(&clip, silence, 8, false);
    assert(clip.used == 0 && !clip.started);
    pcm_capture_append(&clip, audio, 7, true);
    assert(clip.used == 4 && clip.started && !memcmp(data, audio, 4));
    pcm_capture_append(&clip, silence, 8, false);
    assert(clip.used == 12 && data[12] == 0xff);
    pcm_capture_append(&clip, audio, 8, true);
    assert(clip.used == 12 && data[4] == 0);
    pcm_capture_wav_header(header, 12, 44100);
    assert(!memcmp(header, "RIFF", 4) && !memcmp(header + 8, "WAVEfmt ", 8));
    assert(read32(header + 4) == 48 && read32(header + 24) == 44100);
    assert(read32(header + 28) == 176400 && read32(header + 40) == 12);
    assert(header[20] == 1 && header[22] == 2 && header[32] == 4 && header[34] == 16);
    pcm_capture_reset(&clip, data, 8);
    assert(clip.used == 0 && !clip.started);
    pcm_capture_append(&clip, audio, 8, true);
    assert(!memcmp(data, audio, 8));
    puts("PCM capture tests passed");
}
