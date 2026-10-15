#include "audio_output.h"
#include "audio_receiver.h"
#include "buttons.h"
#include "spiram_task.h"
#include "dns_server.h"
#include "led.h"
#include "hap.h"
#include "mdns_airplay.h"
#include "nvs_flash.h"
#include "playback_control.h"
#ifdef CONFIG_SPOTIFY_ENABLED
#include "spotify_audio.h"
#include "spotify.h"
#endif
#include "ptp_clock.h"
#include "rtsp_server.h"
#include "settings.h"
#include "web_server.h"
#include "log_stream.h"
#include "wifi.h"
#include "spiffs_storage.h"

#ifdef CONFIG_BT_A2DP_ENABLE
#include "a2dp_sink.h"
#include "rtsp_events.h"
#endif

#include "iot_board.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "main";

// AP mode IP address (192.168.4.1 in network byte order)
#define AP_IP_ADDR 0x0104A8C0

static bool s_airplay_started = false;
static bool s_airplay_infrastructure_ready = false;

static void start_airplay_services(void) {
  if (s_airplay_started) {
    return;
  }

  ESP_LOGI(TAG, "Starting AirPlay services...");

  // One-time infrastructure init (PTP, HAP, audio receiver/output)
  if (!s_airplay_infrastructure_ready) {
    esp_err_t err = ptp_clock_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
      ESP_LOGE(TAG, "Failed to init PTP clock: %s", esp_err_to_name(err));
      s_airplay_started = false;
      return;
    }

    ESP_ERROR_CHECK(hap_init());
    mdns_airplay_init();
#ifdef CONFIG_SPOTIFY_ENABLED
    ESP_ERROR_CHECK(spotify_start(80));
#endif
    s_airplay_infrastructure_ready = true;
  }

  audio_output_start();

  ESP_ERROR_CHECK(rtsp_server_start());

  s_airplay_started = true;
  ESP_LOGI(TAG, "AirPlay ready");
}
// Wi-Fi is the only network interface. Captive-portal DNS runs while the
// station is offline so the setup AP stays reachable.
static void network_monitor_task(void *pvParameters) {
  (void)pvParameters;
  bool had_network = wifi_is_connected();
  bool dns_running = !had_network;
  if (had_network) {
    start_airplay_services();
  } else {
    dns_server_start(AP_IP_ADDR);
  }

  while (1) {
    vTaskDelay(pdMS_TO_TICKS(2000));
    bool has_network = wifi_is_connected();
    if (has_network == had_network) {
      continue;
    }
    if (has_network) {
      ESP_LOGI(TAG, "Wi-Fi connected");
      start_airplay_services();
      if (dns_running) {
        dns_server_stop();
        dns_running = false;
      }
    } else if (!dns_running) {
      dns_server_start(AP_IP_ADDR);
      dns_running = true;
    }
    had_network = has_network;
  }
}

void app_main(void) {
  ESP_LOGW(TAG, "Boot: reset reason %d", (int)esp_reset_reason());

  // Initialize NVS
  esp_err_t ret = nvs_flash_init();
  if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
      ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_ERROR_CHECK(nvs_flash_erase());
    ret = nvs_flash_init();
  }
  ESP_ERROR_CHECK(ret);
  ESP_ERROR_CHECK(settings_init());
  spiffs_storage_init();
  log_stream_init();
  ESP_ERROR_CHECK(playback_control_init());
#ifdef CONFIG_SPOTIFY_ENABLED
  ESP_ERROR_CHECK(spotify_audio_init());
#endif
  led_init();

  // Board init: optional mute GPIO and DAC registration.
  ESP_LOGI(TAG, "Board: %s", iot_board_get_info());
  esp_err_t err = iot_board_init();
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Board init failed: %s", esp_err_to_name(err));
  }

  ESP_ERROR_CHECK(audio_receiver_init());
  ESP_ERROR_CHECK(audio_output_init());
  audio_output_start();

#ifdef CONFIG_BT_A2DP_ENABLE
  // Initialize Bluetooth A2DP Sink
  {
    char bt_name[65];
    settings_get_device_name(bt_name, sizeof(bt_name));
    esp_err_t bt_err = bt_a2dp_sink_init(bt_name);
    if (bt_err != ESP_OK) {
      ESP_LOGE(TAG, "BT A2DP init failed: %s", esp_err_to_name(bt_err));
    }
  }
#endif

  wifi_init_apsta(NULL, NULL);
  if (!settings_has_wifi_credentials() || !wifi_wait_connected(30000)) {
    ESP_LOGI(TAG, "Connect to '%s' -> http://192.168.4.1",
             CONFIG_DEFAULT_AP_SSID);
  }

  // Start services that work on any interface
  web_server_start(80);
  task_create_spiram(network_monitor_task, "net_mon", 4096, NULL, 5, NULL,
                     NULL);

  // Boot baseline: free internal DRAM once WiFi (and BT, where enabled) are
  // resident but before any stream is active.  Compare against the
  // "Buffered start" log to see the headroom available for WiFi/TCP buffers.
  ESP_LOGI(TAG,
           "Boot baseline: free heap %lu internal (largest block %lu), "
           "%lu SPIRAM",
           (unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
           (unsigned long)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
           (unsigned long)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));

  buttons_init();

  while (1) {
    vTaskDelay(pdMS_TO_TICKS(10000));
  }
}
