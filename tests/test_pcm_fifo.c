#include "pcm_fifo.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    uint32_t storage[5], data[]={10,20,30,40,50,60}, out[6];
    pcm_fifo_t fifo;
    pcm_fifo_init(&fifo,storage,sizeof(storage));
    assert(pcm_fifo_write(&fifo,data,16)==16);
    assert(pcm_fifo_read(&fifo,out,12)==12 && !memcmp(out,data,12));
    assert(pcm_fifo_write(&fifo,data+4,8)==8); // wrap around storage
    assert(pcm_fifo_read(&fifo,out,24)==12 && out[0]==40 && out[1]==50 && out[2]==60);
    assert(pcm_fifo_read(&fifo,out,4)==0);
    assert(pcm_fifo_write(&fifo,data,24)==20); // bounded backpressure
    assert(pcm_fifo_write(&fifo,data,4)==0);
    pcm_fifo_clear(&fifo);
    assert(pcm_fifo_write(&fifo,data,7)==4 && pcm_fifo_read(&fifo,out,7)==4 && out[0]==10);
    puts("PCM FIFO wrap/backpressure tests passed");
}
