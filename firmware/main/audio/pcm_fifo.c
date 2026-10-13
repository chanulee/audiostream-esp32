#include "pcm_fifo.h"
#include <string.h>
void pcm_fifo_init(pcm_fifo_t *f, void *data, size_t capacity) {
    *f = (pcm_fifo_t){.data=data, .capacity=capacity - capacity%4};
}
void pcm_fifo_clear(pcm_fifo_t *f) { f->head=0; f->used=0; }
size_t pcm_fifo_write(pcm_fifo_t *f, const void *data, size_t bytes) {
    if (!f->data || !f->capacity) return 0;
    bytes -= bytes%4;
    if (bytes > f->capacity-f->used) bytes=f->capacity-f->used;
    size_t pos=(f->head+f->used)%f->capacity;
    size_t first=f->capacity-pos;
    if (first>bytes) first=bytes;
    memcpy(f->data+pos, data, first);
    memcpy(f->data, (const uint8_t*)data+first, bytes-first);
    f->used+=bytes;
    return bytes;
}
size_t pcm_fifo_read(pcm_fifo_t *f, void *data, size_t bytes) {
    if (!f->data || !f->capacity) return 0;
    bytes -= bytes%4;
    if (bytes>f->used) bytes=f->used;
    size_t first=f->capacity-f->head;
    if (first>bytes) first=bytes;
    memcpy(data, f->data+f->head, first);
    memcpy((uint8_t*)data+first, f->data, bytes-first);
    f->head=(f->head+bytes)%f->capacity;
    f->used-=bytes;
    return bytes;
}
