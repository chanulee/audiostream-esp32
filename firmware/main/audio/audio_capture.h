#pragma once
#include "sdkconfig.h"
#ifdef CONFIG_AUDIO_CAPTURE_ENABLED
#include "esp_http_server.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
esp_err_t audio_capture_register_http(httpd_handle_t server);
void audio_capture_feed(const void *data, size_t bytes, bool audio, uint32_t rate);
#endif
