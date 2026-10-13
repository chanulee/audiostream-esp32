#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct { uint8_t *data; size_t capacity, head, used; } pcm_fifo_t;
void pcm_fifo_init(pcm_fifo_t *fifo, void *data, size_t capacity);
void pcm_fifo_clear(pcm_fifo_t *fifo);
size_t pcm_fifo_write(pcm_fifo_t *fifo, const void *data, size_t bytes);
size_t pcm_fifo_read(pcm_fifo_t *fifo, void *data, size_t bytes);
