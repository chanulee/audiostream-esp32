#include "audio_capture.h"
#include "pcm_capture.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static SemaphoreHandle_t lock;
static pcm_capture_t clip;
static bool downloading;
static esp_err_t error(httpd_req_t *r, const char *status, const char *message) {
    httpd_resp_set_status(r, status);
    return httpd_resp_send(r, message, HTTPD_RESP_USE_STRLEN);
}
void audio_capture_feed(const void *data, size_t bytes, bool audio) {
    if (!lock) return;
    xSemaphoreTake(lock, portMAX_DELAY);
    pcm_capture_append(&clip, data, bytes, audio);
    xSemaphoreGive(lock);
}
static esp_err_t status_handler(httpd_req_t *r) {
    char body[192];
    xSemaphoreTake(lock, portMAX_DELAY);
    const char *state = !clip.data ? "idle" : clip.used == clip.capacity ? "complete" :
                        clip.started ? "recording" : "armed";
    snprintf(body, sizeof(body), "{\"state\":\"%s\",\"frames\":%u,\"target_frames\":%u,\"sample_rate\":%u,\"channels\":2,\"bits\":16}",
             state, (unsigned)(clip.used / 4), (unsigned)(clip.capacity / 4), CONFIG_OUTPUT_SAMPLE_RATE_HZ);
    xSemaphoreGive(lock);
    httpd_resp_set_type(r, "application/json");
    httpd_resp_set_hdr(r, "Cache-Control", "no-store");
    return httpd_resp_send(r, body, HTTPD_RESP_USE_STRLEN);
}
static esp_err_t start_handler(httpd_req_t *r) {
    char query[64], seconds_text[16], *end;
    if (httpd_req_get_url_query_str(r, query, sizeof(query)) != ESP_OK ||
        httpd_query_key_value(query, "seconds", seconds_text, sizeof(seconds_text)) != ESP_OK)
        return error(r, "400 Bad Request", "seconds=1..10 required");
    long seconds = strtol(seconds_text, &end, 10);
    if (!*seconds_text || *end || seconds < 1 || seconds > 10)
        return error(r, "400 Bad Request", "seconds must be an integer from 1 to 10");
    size_t bytes = (size_t)seconds * CONFIG_OUTPUT_SAMPLE_RATE_HZ * 4;
    xSemaphoreTake(lock, portMAX_DELAY);
    if (downloading) {
        xSemaphoreGive(lock);
        return error(r, "409 Conflict", "download in progress");
    }
    // Reuse the buffer when possible. A failed allocation preserves the old clip.
    if (clip.capacity != bytes) {
        void *data = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!data) {
            xSemaphoreGive(lock);
            return error(r, "503 Service Unavailable", "insufficient PSRAM; try a shorter clip");
        }
        free(clip.data);
        pcm_capture_reset(&clip, data, bytes);
    } else pcm_capture_reset(&clip, clip.data, bytes);
    xSemaphoreGive(lock);
    return status_handler(r);
}
static esp_err_t wav_handler(httpd_req_t *r) {
    xSemaphoreTake(lock, portMAX_DELAY);
    if (!clip.data || clip.used != clip.capacity || downloading) {
        xSemaphoreGive(lock);
        return error(r, "409 Conflict", "capture is not complete");
    }
    downloading = true;
    const uint8_t *data = clip.data;
    size_t bytes = clip.used;
    xSemaphoreGive(lock);
    uint8_t header[44];
    pcm_capture_wav_header(header, bytes, CONFIG_OUTPUT_SAMPLE_RATE_HZ);
    httpd_resp_set_type(r, "audio/wav");
    httpd_resp_set_hdr(r, "Cache-Control", "no-store");
    esp_err_t result = httpd_resp_send_chunk(r, (const char *)header, sizeof(header));
    for (size_t offset = 0; result == ESP_OK && offset < bytes;) {
        size_t n = bytes - offset;
        if (n > 4096) n = 4096;
        result = httpd_resp_send_chunk(r, (const char *)data + offset, n);
        offset += n;
    }
    if (result == ESP_OK) result = httpd_resp_send_chunk(r, NULL, 0);
    xSemaphoreTake(lock, portMAX_DELAY);
    downloading = false;
    xSemaphoreGive(lock);
    return result;
}
esp_err_t audio_capture_register_http(httpd_handle_t server) {
    if (!lock) lock = xSemaphoreCreateMutex();
    if (!lock) return ESP_ERR_NO_MEM;
    const httpd_uri_t routes[] = {
        {.uri = "/api/capture/start", .method = HTTP_POST, .handler = start_handler},
        {.uri = "/api/capture/status", .method = HTTP_GET, .handler = status_handler},
        {.uri = "/api/capture/wav", .method = HTTP_GET, .handler = wav_handler},
    };
    for (unsigned i = 0; i < sizeof(routes) / sizeof(routes[0]); i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
