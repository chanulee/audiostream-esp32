#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* A2DP/SBC receiver. Wi-Fi services stay available while Bluetooth is connected. */
esp_err_t bt_a2dp_sink_init(const char *device_name);
bool bt_a2dp_sink_is_connected(void);
void bt_a2dp_sink_set_discoverable(bool discoverable);
/* Disconnect the current phone (if any) and become discoverable. */
void bt_a2dp_sink_pairing_mode(void);
size_t bt_a2dp_sink_read(int16_t *pcm, size_t max_frames);
uint32_t bt_a2dp_sink_sample_rate(void);
int32_t bt_a2dp_sink_volume_q15(void);
int bt_a2dp_sink_volume_percent(void);
void bt_a2dp_sink_yield(void);
void bt_a2dp_send_playpause(void);
void bt_a2dp_send_next(void);
void bt_a2dp_send_prev(void);
void bt_a2dp_send_volume_up(void);
void bt_a2dp_send_volume_down(void);
