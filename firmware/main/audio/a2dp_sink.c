#include "a2dp_sink.h"
#include "spiram_task.h"
#include "pcm_fifo.h"
#include "playback_control.h"
#include "esp_heap_caps.h"
#include <math.h>

#include "led.h"
#include "rtsp_events.h"
#include "settings.h"

#include "esp_a2dp_api.h"
#include "esp_avrc_api.h"
#include "esp_bt.h"
#include "esp_bt_device.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp_log.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static const char *TAG = "bt_a2dp";

/* ========================================================================== */
/* Configuration                                                              */
/* ========================================================================== */

// ~185 ms at 44.1 kHz stereo; playback starts once PREFILL is reached so the
// first SBC bursts do not underrun the I2S writer.
#define RINGBUF_SIZE    ((size_t)32 * 1024)
#define RINGBUF_PREFILL (RINGBUF_SIZE * 4 / 10)
// A stream that starts while another source owns the output (phone keyboard
// clicks, notification sounds) claims it only after this much non-silent PCM
// or an explicit AVRCP "playing" report.
#define CLAIM_AUDIBLE_MS 1500
#define SILENCE_LEVEL    64
#define BT_TASK_STACK 4096
#define BT_TASK_PRIO 5
#define BT_TASK_QLEN 16

/* ========================================================================== */
/* BT App Task Types                                                          */
/* ========================================================================== */

typedef void (*bt_app_cb_t)(uint16_t event, void *param);

typedef struct {
  uint16_t sig;
  uint16_t event;
  bt_app_cb_t cb;
  void *param;
} bt_app_msg_t;

enum { BT_APP_SIG_WORK_DISPATCH = 0 };
enum { BT_APP_EVT_STACK_UP = 0 };

/* ========================================================================== */
/* State                                                                      */
/* ========================================================================== */
static volatile bool s_connected;
static volatile bool s_audio_started;
static volatile bool s_avrc_playing;
static bool s_bt_discoverable = true;
static char s_device_name[64];
static esp_bd_addr_t s_peer_bda;
static uint8_t s_avrc_volume = 64;
static volatile bool s_vol_ntf_pending;
static volatile bool s_claim_pending;
static uint32_t s_audible_bytes;
static bool s_primed;
static pcm_fifo_t s_fifo;
static SemaphoreHandle_t s_fifo_lock;
static TaskHandle_t s_bt_task_handle;
static QueueHandle_t s_bt_task_queue;
static void send_passthrough(uint8_t key_code);

static uint32_t s_sample_rate = 44100;

/* ========================================================================== */
/* BT App Task — context-switch from BT stack to app task                     */
/* ========================================================================== */

static bool bt_app_send_msg(bt_app_msg_t *msg) {
  if (s_bt_task_queue == NULL) {
    return false;
  }
  return xQueueSend(s_bt_task_queue, msg, pdMS_TO_TICKS(10)) == pdTRUE;
}

static bool bt_app_work_dispatch(bt_app_cb_t cb, uint16_t event, void *param,
                                 int param_len) {
  bt_app_msg_t msg = {
      .sig = BT_APP_SIG_WORK_DISPATCH,
      .event = event,
      .cb = cb,
      .param = NULL,
  };
  if (param_len > 0 && param != NULL) {
    msg.param = malloc((size_t)param_len);
    if (!msg.param) {
      return false;
    }
    memcpy(msg.param, param, (size_t)param_len);
  }
  if (!bt_app_send_msg(&msg)) {
    free(msg.param);
    return false;
  }
  return true;
}

static void bt_app_task(void *arg) {
  bt_app_msg_t msg;
  while (true) {
    if (xQueueReceive(s_bt_task_queue, &msg, portMAX_DELAY) == pdTRUE) {
      if (msg.sig == BT_APP_SIG_WORK_DISPATCH && msg.cb) {
        msg.cb(msg.event, msg.param);
      }
      free(msg.param);
    }
  }
}

static void clear_pcm(void) {
  xSemaphoreTake(s_fifo_lock, portMAX_DELAY);
  pcm_fifo_clear(&s_fifo);
  s_primed = false;
  xSemaphoreGive(s_fifo_lock);
}

static bool bt_is_source(void) {
  return playback_control_get_source() == PLAYBACK_SOURCE_BLUETOOTH;
}

// Runs on bt_app_task. Takes the shared output for an explicit Bluetooth play.
static void claim_output(uint16_t event, void *param) {
  (void)event;
  (void)param;
  s_claim_pending = false;
  if (!s_connected || !s_audio_started || bt_is_source()) {
    return;
  }
  clear_pcm();
  playback_control_set_source(PLAYBACK_SOURCE_BLUETOOTH);
}

static void on_remote_playing(bool playing) {
  bool was_playing = s_avrc_playing;
  s_avrc_playing = playing;
  if (playing && !was_playing && s_audio_started) {
    claim_output(0, NULL);
  }
}

static bool pcm_audible(const uint8_t *data, uint32_t len) {
  const int16_t *pcm = (const int16_t *)data;
  for (uint32_t i = 0; i < len / 2; i += 8) {
    if (pcm[i] > SILENCE_LEVEL || pcm[i] < -SILENCE_LEVEL) {
      return true;
    }
  }
  return false;
}

static void emit_metadata(const rtsp_event_data_t *data) {
  if (bt_is_source()) {
    rtsp_events_emit(RTSP_EVENT_METADATA, data);
  }
}

static void pause_remote(uint16_t event, void *param) {
  (void)event; (void)param;
  send_passthrough(ESP_AVRC_PT_CMD_PAUSE);
}

void bt_a2dp_sink_yield(void) {
  clear_pcm();
  bt_app_work_dispatch(pause_remote, 0, NULL, 0);
}

// Bluedroid task context: never block on the output lock here.
static void bt_a2dp_data_cb(const uint8_t *data, uint32_t len) {
  if (!s_audio_started || len == 0) {
    return;
  }
  if (!bt_is_source()) {
    if (!s_claim_pending) {
      return;
    }
    s_audible_bytes = pcm_audible(data, len) ? s_audible_bytes + len : 0;
    if (s_audible_bytes >= s_sample_rate / 1000 * 4 * CLAIM_AUDIBLE_MS) {
      s_claim_pending = false;
      bt_app_work_dispatch(claim_output, 0, NULL, 0);
    }
    return;
  }
  xSemaphoreTake(s_fifo_lock, portMAX_DELAY);
  // Stereo frames only. Drop whole callbacks rather than replaying old data.
  if (bt_is_source() && len % 4 == 0 && len <= s_fifo.capacity - s_fifo.used) {
    pcm_fifo_write(&s_fifo, data, len);
  }
  xSemaphoreGive(s_fifo_lock);
}

size_t bt_a2dp_sink_read(int16_t *pcm, size_t max_frames) {
  if (!s_fifo_lock || !s_audio_started) {
    return 0;
  }
  xSemaphoreTake(s_fifo_lock, portMAX_DELAY);
  size_t bytes = 0;
  if (!s_primed && s_fifo.used >= RINGBUF_PREFILL) {
    s_primed = true;
  }
  if (s_primed) {
    bytes = pcm_fifo_read(&s_fifo, pcm, max_frames * 4);
    // Underrun: rebuild the cushion instead of playing every tiny burst.
    if (s_fifo.used == 0) {
      s_primed = false;
    }
  }
  xSemaphoreGive(s_fifo_lock);
  return bytes / 4;
}

uint32_t bt_a2dp_sink_sample_rate(void) {
  return __atomic_load_n(&s_sample_rate, __ATOMIC_RELAXED);
}

// AVRCP 0..127 maps to -30..0 dB, matching the AirPlay volume range.
int32_t bt_a2dp_sink_volume_q15(void) {
  uint8_t volume = __atomic_load_n(&s_avrc_volume, __ATOMIC_RELAXED);
  if (!volume) {
    return 0;
  }
  float db = ((float)volume / 127.0f) * 30.0f - 30.0f;
  return (int32_t)(32768.0f * powf(10.0f, db / 20.0f));
}

int bt_a2dp_sink_volume_percent(void) {
  return (s_avrc_volume * 100 + 63) / 127;
}

/* ========================================================================== */
/* A2DP event handler (runs in app task context) */
/* ========================================================================== */

static void bt_a2dp_evt_handler(uint16_t event, void *param) {
  esp_a2d_cb_param_t *a2d = (esp_a2d_cb_param_t *)param;

  switch (event) {
  case ESP_A2D_CONNECTION_STATE_EVT: {
    esp_a2d_connection_state_t state = a2d->conn_stat.state;

    if (state == ESP_A2D_CONNECTION_STATE_CONNECTING) {
      ESP_LOGI(TAG, "A2DP connecting...");
    } else if (state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
      ESP_LOGI(TAG, "A2DP connected");
      s_connected = true;
      memcpy(s_peer_bda, a2d->conn_stat.remote_bda, sizeof(s_peer_bda));

      clear_pcm();

      // Don't accept more connections while connected
      esp_bt_gap_set_scan_mode(ESP_BT_NON_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);

    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTING) {
      ESP_LOGI(TAG, "A2DP disconnecting...");
    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
      ESP_LOGI(TAG, "A2DP disconnected");
      s_connected = false;
      s_audio_started = false;
      s_avrc_playing = false;
      s_claim_pending = false;

      clear_pcm();
      playback_control_release_source(PLAYBACK_SOURCE_BLUETOOTH);
      bt_a2dp_sink_set_discoverable(true);

      // Persist the last-used volume to NVS once at disconnect
      settings_persist_bt_volume();
    }
    break;
  }

  case ESP_A2D_AUDIO_STATE_EVT: {
    esp_a2d_audio_state_t state = a2d->audio_stat.state;
    if (state == ESP_A2D_AUDIO_STATE_STARTED) {
      ESP_LOGI(TAG, "Audio stream started");
      if (!s_audio_started) {
        clear_pcm();
        s_audio_started = true;
        s_audible_bytes = 0;
        // An idle output or an explicit AVRCP play is a real request. Anything
        // else must prove itself as sustained audio first.
        if (playback_control_get_source() == PLAYBACK_SOURCE_NONE ||
            s_avrc_playing) {
          claim_output(0, NULL);
        } else {
          s_claim_pending = true;
        }
      }
    } else {
      ESP_LOGI(TAG, "Audio stream stopped/suspended");
      s_audio_started = false;
      s_claim_pending = false;
      clear_pcm();
      playback_control_set_playing(PLAYBACK_SOURCE_BLUETOOTH, false);
    }
    break;
  }

  case ESP_A2D_AUDIO_CFG_EVT: {
    ESP_LOGI(TAG, "Audio codec configured, type=%d", a2d->audio_cfg.mcc.type);
    if (a2d->audio_cfg.mcc.type == ESP_A2D_MCT_SBC) {
      // Use the new struct-based CIE accessors
      uint8_t sf = a2d->audio_cfg.mcc.cie.sbc_info.samp_freq;
      if (sf & ESP_A2D_SBC_CIE_SF_48K) {
        s_sample_rate = 48000;
      } else if (sf & ESP_A2D_SBC_CIE_SF_44K) {
        s_sample_rate = 44100;
      } else if (sf & ESP_A2D_SBC_CIE_SF_32K) {
        s_sample_rate = 32000;
      } else if (sf & ESP_A2D_SBC_CIE_SF_16K) {
        s_sample_rate = 16000;
      }
      ESP_LOGI(TAG, "SBC sample rate: %" PRIu32 " Hz", s_sample_rate);
      // The single output task changes clocks at its next buffer boundary.
    }
    break;
  }

  case ESP_A2D_PROF_STATE_EVT:
    ESP_LOGI(TAG, "A2DP profile %s",
             a2d->a2d_prof_stat.init_state == ESP_A2D_INIT_SUCCESS
                 ? "inited"
                 : "deinited");
    break;

  default:
    break;
  }
}

/* A2DP callback (BT stack context) → dispatch to app task */
static void bt_a2dp_cb(esp_a2d_cb_event_t event, esp_a2d_cb_param_t *param) {
  bt_app_work_dispatch(bt_a2dp_evt_handler, (uint16_t)event, param,
                       sizeof(esp_a2d_cb_param_t));
}

/* ========================================================================== */
/* AVRCP Controller — get metadata from source device                         */
/* ========================================================================== */

static void bt_avrc_ct_evt_handler(uint16_t event, void *param) {
  esp_avrc_ct_cb_param_t *rc = (esp_avrc_ct_cb_param_t *)param;
  static rtsp_event_data_t meta_data;

  switch (event) {
  case ESP_AVRC_CT_CONNECTION_STATE_EVT:
    ESP_LOGI(TAG, "AVRC CT %s",
             rc->conn_stat.connected ? "connected" : "disconnected");
    if (rc->conn_stat.connected) {
      // Request track metadata
      esp_avrc_ct_send_metadata_cmd(
          0, ESP_AVRC_MD_ATTR_TITLE | ESP_AVRC_MD_ATTR_ARTIST |
                 ESP_AVRC_MD_ATTR_ALBUM | ESP_AVRC_MD_ATTR_GENRE);
      // Request current play status (duration + position + play state)
      esp_avrc_ct_send_get_play_status_cmd(0);
      // Register for notifications: track change, play status, position
      esp_avrc_ct_send_register_notification_cmd(1, ESP_AVRC_RN_TRACK_CHANGE,
                                                 0);
      esp_avrc_ct_send_register_notification_cmd(
          2, ESP_AVRC_RN_PLAY_STATUS_CHANGE, 0);
      esp_avrc_ct_send_register_notification_cmd(3,
                                                 ESP_AVRC_RN_PLAY_POS_CHANGED,
                                                 10); // report every 10 seconds
    }
    break;

  case ESP_AVRC_CT_METADATA_RSP_EVT: {
    // Metadata response — one attribute per event.
    // attr_text was deep-copied in bt_avrc_ct_cb and must be freed here.
    uint8_t attr_id = rc->meta_rsp.attr_id;
    uint8_t *text = rc->meta_rsp.attr_text;
    int len = rc->meta_rsp.attr_length;

    if (text == NULL || len == 0) {
      free(text);
      break;
    }

    // Build metadata event for display
    char *dst = NULL;
    size_t dst_size = 0;

    switch (attr_id) {
    case ESP_AVRC_MD_ATTR_TITLE:
      dst = meta_data.metadata.title;
      dst_size = sizeof(meta_data.metadata.title);
      break;
    case ESP_AVRC_MD_ATTR_ARTIST:
      dst = meta_data.metadata.artist;
      dst_size = sizeof(meta_data.metadata.artist);
      break;
    case ESP_AVRC_MD_ATTR_ALBUM:
      dst = meta_data.metadata.album;
      dst_size = sizeof(meta_data.metadata.album);
      break;
    case ESP_AVRC_MD_ATTR_GENRE:
      dst = meta_data.metadata.genre;
      dst_size = sizeof(meta_data.metadata.genre);
      break;
    default:
      break;
    }

    if (dst) {
      size_t copy_len = (size_t)len < dst_size - 1 ? (size_t)len : dst_size - 1;
      memcpy(dst, text, copy_len);
      dst[copy_len] = '\0';
      ESP_LOGI(TAG, "Metadata attr %d: %s", attr_id, dst);

      // Emit metadata event after each attribute update
      emit_metadata(&meta_data);
    }
    free(text);
    break;
  }

  case ESP_AVRC_CT_PLAY_STATUS_RSP_EVT: {
    uint32_t duration_ms = rc->play_status_rsp.song_length;
    uint32_t position_ms = rc->play_status_rsp.song_position;
    esp_avrc_playback_stat_t status = rc->play_status_rsp.play_status;

    ESP_LOGI(TAG, "Play status: state=%d pos=%lums dur=%lums", status,
             (unsigned long)position_ms, (unsigned long)duration_ms);

    // Update duration and position in metadata for display
    // 0xFFFFFFFF means "not available" per AVRCP spec
    if (duration_ms != 0xFFFFFFFF) {
      meta_data.metadata.duration_secs = duration_ms / 1000;
    }
    if (position_ms != 0xFFFFFFFF) {
      meta_data.metadata.position_secs = position_ms / 1000;
    }
    emit_metadata(&meta_data);

    // Emit play state from AVRCP (faster than A2D audio state)
    if (status == ESP_AVRC_PLAYBACK_PLAYING) {
      on_remote_playing(true);
    } else if (status == ESP_AVRC_PLAYBACK_PAUSED ||
               status == ESP_AVRC_PLAYBACK_STOPPED) {
      on_remote_playing(false);
    }
    break;
  }

  case ESP_AVRC_CT_CHANGE_NOTIFY_EVT:
    if (rc->change_ntf.event_id == ESP_AVRC_RN_TRACK_CHANGE) {
      ESP_LOGI(TAG, "Track changed");
      // Clear old metadata so stale fields don't persist
      memset(&meta_data, 0, sizeof(meta_data));

      // Request new metadata and play status
      esp_avrc_ct_send_metadata_cmd(
          0, ESP_AVRC_MD_ATTR_TITLE | ESP_AVRC_MD_ATTR_ARTIST |
                 ESP_AVRC_MD_ATTR_ALBUM | ESP_AVRC_MD_ATTR_GENRE);
      esp_avrc_ct_send_get_play_status_cmd(0);
      // Re-register for track change
      esp_avrc_ct_send_register_notification_cmd(1, ESP_AVRC_RN_TRACK_CHANGE,
                                                 0);
    } else if (rc->change_ntf.event_id == ESP_AVRC_RN_PLAY_STATUS_CHANGE) {
      esp_avrc_playback_stat_t status = rc->change_ntf.event_parameter.playback;
      ESP_LOGI(TAG, "Play status changed: %d", status);

      // Refresh position/duration from source
      esp_avrc_ct_send_get_play_status_cmd(0);

      if (status == ESP_AVRC_PLAYBACK_PLAYING) {
        on_remote_playing(true);
      } else if (status == ESP_AVRC_PLAYBACK_PAUSED ||
                 status == ESP_AVRC_PLAYBACK_STOPPED) {
        on_remote_playing(false);
      }
      // Re-register
      esp_avrc_ct_send_register_notification_cmd(
          2, ESP_AVRC_RN_PLAY_STATUS_CHANGE, 0);
    } else if (rc->change_ntf.event_id == ESP_AVRC_RN_PLAY_POS_CHANGED) {
      uint32_t pos_ms = rc->change_ntf.event_parameter.play_pos;
      ESP_LOGD(TAG, "Play position: %lums", (unsigned long)pos_ms);

      if (pos_ms != 0xFFFFFFFF) {
        meta_data.metadata.position_secs = pos_ms / 1000;
        emit_metadata(&meta_data);
      }
      // Re-register
      esp_avrc_ct_send_register_notification_cmd(
          3, ESP_AVRC_RN_PLAY_POS_CHANGED, 10);
    }
    break;

  default:
    break;
  }
}

static void bt_avrc_ct_cb(esp_avrc_ct_cb_event_t event,
                          esp_avrc_ct_cb_param_t *param) {
  esp_avrc_ct_cb_param_t local = *param;

  // Deep-copy attr_text for metadata responses — the BT stack frees the
  // original buffer when this callback returns, so the shallow copy made
  // by bt_app_work_dispatch would leave a dangling pointer that the
  // handler later free()s, corrupting the heap.
  //
  // Always overwrite local.meta_rsp.attr_text so the stack-owned pointer
  // never escapes this function: on success it points at our malloc'd
  // copy, on failure (zero-length, malloc returns NULL, or any non-
  // metadata event that happens to alias the union) it is NULL.  The
  // handler does free(text) unconditionally, and free(NULL) is a no-op.
  if (event == ESP_AVRC_CT_METADATA_RSP_EVT) {
    uint8_t *copy = NULL;
    if (param->meta_rsp.attr_text && param->meta_rsp.attr_length > 0) {
      copy = malloc((size_t)param->meta_rsp.attr_length + 1);
      if (copy) {
        memcpy(copy, param->meta_rsp.attr_text,
               (size_t)param->meta_rsp.attr_length);
        copy[param->meta_rsp.attr_length] = '\0';
      }
    }
    local.meta_rsp.attr_text = copy;
  }

  // On a full queue the deep-copied metadata text would otherwise leak.
  if (!bt_app_work_dispatch(bt_avrc_ct_evt_handler, (uint16_t)event, &local,
                            sizeof(esp_avrc_ct_cb_param_t)) &&
      event == ESP_AVRC_CT_METADATA_RSP_EVT) {
    free(local.meta_rsp.attr_text);
  }
}

/* ========================================================================== */
/* AVRCP Target — handle volume commands from source device                   */
/* ========================================================================== */

static void bt_avrc_tg_evt_handler(uint16_t event, void *param) {
  esp_avrc_tg_cb_param_t *tg = (esp_avrc_tg_cb_param_t *)param;

  switch (event) {
  case ESP_AVRC_TG_CONNECTION_STATE_EVT:
    ESP_LOGI(TAG, "AVRC TG %s",
             tg->conn_stat.connected ? "connected" : "disconnected");
    break;

  case ESP_AVRC_TG_SET_ABSOLUTE_VOLUME_CMD_EVT: {
    uint8_t volume = tg->set_abs_vol.volume; // 0-127
    s_avrc_volume = volume > 127 ? 127 : volume;
    settings_set_bt_volume(s_avrc_volume);
    ESP_LOGD(TAG, "Set absolute volume: %d/127", volume);
    break;
  }

  case ESP_AVRC_TG_REGISTER_NOTIFICATION_EVT:
    if (tg->reg_ntf.event_id == ESP_AVRC_RN_VOLUME_CHANGE) {
      // Respond with current volume (interim response)
      esp_avrc_rn_param_t rn_param;
      rn_param.volume = s_avrc_volume;
      esp_avrc_tg_send_rn_rsp(ESP_AVRC_RN_VOLUME_CHANGE,
                              ESP_AVRC_RN_RSP_INTERIM, &rn_param);
      s_vol_ntf_pending = true;
    }
    break;

  default:
    break;
  }
}

static void bt_avrc_tg_cb(esp_avrc_tg_cb_event_t event,
                          esp_avrc_tg_cb_param_t *param) {
  bt_app_work_dispatch(bt_avrc_tg_evt_handler, (uint16_t)event, param,
                       sizeof(esp_avrc_tg_cb_param_t));
}

/* ========================================================================== */
/* GAP callback                                                               */
/* ========================================================================== */

static void bt_gap_cb(esp_bt_gap_cb_event_t event,
                      esp_bt_gap_cb_param_t *param) {
  switch (event) {
  case ESP_BT_GAP_AUTH_CMPL_EVT:
    if (param->auth_cmpl.stat == ESP_BT_STATUS_SUCCESS) {
      ESP_LOGI(TAG, "Auth success: %s", param->auth_cmpl.device_name);
    } else {
      ESP_LOGW(TAG, "Auth failed: status=%d", param->auth_cmpl.stat);
    }
    break;

  case ESP_BT_GAP_CFM_REQ_EVT:
    ESP_LOGI(TAG, "SSP confirm request (num=%" PRIu32 "), auto-accepting",
             param->cfm_req.num_val);
    esp_bt_gap_ssp_confirm_reply(param->cfm_req.bda, true);
    break;

  case ESP_BT_GAP_PIN_REQ_EVT:
    ESP_LOGI(TAG, "Legacy PIN request");
    break;

  case ESP_BT_GAP_KEY_NOTIF_EVT:
    ESP_LOGI(TAG, "SSP passkey notify: %" PRIu32, param->key_notif.passkey);
    break;

  case ESP_BT_GAP_KEY_REQ_EVT:
    ESP_LOGI(TAG, "SSP passkey request");
    break;

  case ESP_BT_GAP_MODE_CHG_EVT:
    ESP_LOGD(TAG, "GAP mode changed to %d", param->mode_chg.mode);
    break;

  default:
    break;
  }
}

/* ========================================================================== */
/* Stack-up handler — called once Bluedroid is enabled                        */
/* ========================================================================== */

// Register the GAP/AVRC/A2DP profiles on stack-up.
static void bt_register_profiles(void) {
  // GAP
  esp_bt_gap_register_callback(bt_gap_cb);

  // Apply the advertised device name.
  if (s_device_name[0] != '\0') {
    esp_bt_gap_set_device_name(s_device_name);
  }

#ifdef CONFIG_BT_SSP_ENABLED
  // Secure Simple Pairing, Just Works: the board has no display or keypad.
  esp_bt_sp_param_t param_type = ESP_BT_SP_IOCAP_MODE;
  esp_bt_io_cap_t iocap = ESP_BT_IO_CAP_NONE;
  esp_bt_gap_set_security_param(param_type, &iocap, sizeof(uint8_t));
#endif

  // Legacy Pairing — fixed PIN from Kconfig
  esp_bt_pin_type_t pin_type = ESP_BT_PIN_TYPE_FIXED;
  esp_bt_pin_code_t pin_code;
  const char *pin_str = CONFIG_BT_PIN_CODE;
  uint8_t pin_len = strlen(pin_str);
  if (pin_len > ESP_BT_PIN_CODE_LEN) {
    pin_len = ESP_BT_PIN_CODE_LEN;
  }
  memcpy(pin_code, pin_str, pin_len);
  esp_bt_gap_set_pin(pin_type, pin_len, pin_code);
  ESP_LOGI(TAG, "BT PIN set (%d digits)", pin_len);

  // AVRC Controller (to get metadata from source)
  esp_avrc_ct_register_callback(bt_avrc_ct_cb);
  esp_avrc_ct_init();

  // AVRC Target (to receive volume commands)
  esp_avrc_tg_register_callback(bt_avrc_tg_cb);
  esp_avrc_tg_init();
  esp_avrc_rn_evt_cap_mask_t evt_set = {0};
  evt_set.bits = (1 << ESP_AVRC_RN_VOLUME_CHANGE);
  esp_avrc_tg_set_rn_evt_cap(&evt_set);

  // A2DP Sink
  esp_a2d_register_callback(bt_a2dp_cb);
  esp_a2d_sink_register_data_callback(bt_a2dp_data_cb);
  esp_a2d_sink_init();
}

// Load the saved AVRCP volume (64 / -15 dB if none) so the first A2DP stream
// starts at the last Bluetooth level instead of waiting for the phone.
static void bt_restore_saved_volume(void) {
  uint8_t saved_vol;
  if (settings_get_bt_volume(&saved_vol) == ESP_OK) {
    s_avrc_volume = saved_vol;
  }
  float volume_db = ((float)s_avrc_volume / 127.0f) * 30.0f - 30.0f;
  ESP_LOGI(TAG, "BT volume restored: %d/127 (%.1f dB)", s_avrc_volume,
           volume_db);
}

static void bt_stack_evt_handler(uint16_t event, void *param) {
  (void)param;

  if (event != BT_APP_EVT_STACK_UP) {
    return;
  }

  ESP_LOGI(TAG, "BT stack up, initializing profiles");

  bt_register_profiles();

  // Apply saved discoverable state
  if (s_bt_discoverable) {
    esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
  } else {
    esp_bt_gap_set_scan_mode(ESP_BT_NON_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);
  }

  // Restore saved BT volume (falls back to 64 / -15 dB if none stored)
  bt_restore_saved_volume();

  ESP_LOGI(TAG, "BT A2DP sink ready, waiting for connections");
}

/* ========================================================================== */
/* Public API                                                                 */
/* ========================================================================== */

esp_err_t bt_a2dp_sink_init(const char *device_name) {
  // The FIFO lives as long as the firmware, so stack callbacks never see it
  // freed.
  s_fifo_lock = xSemaphoreCreateMutex();
  void *storage =
      heap_caps_malloc(RINGBUF_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!s_fifo_lock || !storage) {
    free(storage);
    if (s_fifo_lock) {
      vSemaphoreDelete(s_fifo_lock);
    }
    s_fifo_lock = NULL;
    return ESP_ERR_NO_MEM;
  }
  pcm_fifo_init(&s_fifo, storage, RINGBUF_SIZE);

  ESP_LOGI(TAG, "Initializing Bluetooth A2DP Sink: %s", device_name);

  // Release BLE memory — we only need Classic BT
  ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_BLE));

  // Initialize BT controller
  esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  esp_err_t err = esp_bt_controller_init(&bt_cfg);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "BT controller init failed: %s", esp_err_to_name(err));
    return err;
  }

  err = esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "BT controller enable failed: %s", esp_err_to_name(err));
    return err;
  }

  // Initialize Bluedroid
  esp_bluedroid_config_t bluedroid_cfg = BT_BLUEDROID_INIT_CONFIG_DEFAULT();
#ifndef CONFIG_BT_SSP_ENABLED
  bluedroid_cfg.ssp_en = false; // Disable SSP to force legacy PIN pairing
#endif
  err = esp_bluedroid_init_with_cfg(&bluedroid_cfg);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Bluedroid init failed: %s", esp_err_to_name(err));
    return err;
  }

  err = esp_bluedroid_enable();
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Bluedroid enable failed: %s", esp_err_to_name(err));
    return err;
  }

  // bt_register_profiles() applies the name again on stack-up.
  snprintf(s_device_name, sizeof(s_device_name), "%s", device_name);
  esp_bt_gap_set_device_name(device_name);

  // Create the BT app task and event queue
  s_bt_task_queue = xQueueCreate(BT_TASK_QLEN, sizeof(bt_app_msg_t));
  if (s_bt_task_queue == NULL) {
    ESP_LOGE(TAG, "Failed to create BT task queue");
    return ESP_ERR_NO_MEM;
  }

  BaseType_t ret =
      task_create_spiram(bt_app_task, "bt_app", BT_TASK_STACK, NULL,
                         BT_TASK_PRIO, &s_bt_task_handle, NULL);
  if (ret != pdPASS) {
    ESP_LOGE(TAG, "Failed to create BT app task");
    return ESP_ERR_NO_MEM;
  }

  // Dispatch stack-up event to app task
  bt_app_work_dispatch(bt_stack_evt_handler, BT_APP_EVT_STACK_UP, NULL, 0);

  return ESP_OK;
}

// Runs on bt_app_task. The disconnect event re-enables discovery.
static void enter_pairing_mode(uint16_t event, void *param) {
  (void)event;
  (void)param;
  if (s_connected) {
    ESP_LOGI(TAG, "Pairing mode: disconnecting current phone");
    esp_a2d_sink_disconnect(s_peer_bda);
  } else {
    ESP_LOGI(TAG, "Pairing mode: discoverable");
    bt_a2dp_sink_set_discoverable(true);
  }
}

void bt_a2dp_sink_pairing_mode(void) {
  bt_app_work_dispatch(enter_pairing_mode, 0, NULL, 0);
}

bool bt_a2dp_sink_is_connected(void) {
  return s_connected;
}

void bt_a2dp_sink_set_discoverable(bool discoverable) {
  s_bt_discoverable = discoverable;
  if (s_connected) {
    // One phone at a time: the preference applies after it disconnects.
    return;
  }
  if (discoverable) {
    ESP_LOGI(TAG, "BT discoverable enabled");
    esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
  } else {
    ESP_LOGI(TAG, "BT discoverable disabled");
    esp_bt_gap_set_scan_mode(ESP_BT_NON_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);
  }
}

static void send_passthrough(uint8_t key_code) {
  if (!s_connected) {
    return;
  }
  esp_avrc_ct_send_passthrough_cmd(0, key_code, ESP_AVRC_PT_CMD_STATE_PRESSED);
  vTaskDelay(pdMS_TO_TICKS(50));
  esp_avrc_ct_send_passthrough_cmd(0, key_code, ESP_AVRC_PT_CMD_STATE_RELEASED);
}

void bt_a2dp_send_playpause(void) {
  if (s_avrc_playing) {
    send_passthrough(ESP_AVRC_PT_CMD_PAUSE);
    ESP_LOGI(TAG, "AVRCP: pause");
  } else {
    send_passthrough(ESP_AVRC_PT_CMD_PLAY);
    ESP_LOGI(TAG, "AVRCP: play");
  }
}

void bt_a2dp_send_next(void) {
  send_passthrough(ESP_AVRC_PT_CMD_FORWARD);
  ESP_LOGI(TAG, "AVRCP: next");
}

void bt_a2dp_send_prev(void) {
  send_passthrough(ESP_AVRC_PT_CMD_BACKWARD);
  ESP_LOGI(TAG, "AVRCP: prev");
}

/**
 * Notify the source (phone) that local volume changed via AVRCP TG.
 * Only sends if the phone previously registered for the notification.
 */
static void notify_volume_changed(void) {
  if (s_vol_ntf_pending) {
    esp_avrc_rn_param_t rn_param;
    rn_param.volume = s_avrc_volume;
    esp_avrc_tg_send_rn_rsp(ESP_AVRC_RN_VOLUME_CHANGE, ESP_AVRC_RN_RSP_CHANGED,
                            &rn_param);
    s_vol_ntf_pending = false;
  }
}

void bt_a2dp_send_volume_up(void) {
  // Adjust local AVRCP volume by ~10 units (≈3 dB equivalent)
  uint8_t new_vol = s_avrc_volume;
  if (new_vol <= 117) {
    new_vol += 10;
  } else {
    new_vol = 127;
  }
  s_avrc_volume = new_vol;
  settings_set_bt_volume(new_vol);
  notify_volume_changed();
  ESP_LOGI(TAG, "AVRCP: volume up -> %d/127", new_vol);
}

void bt_a2dp_send_volume_down(void) {
  uint8_t new_vol = s_avrc_volume;
  if (new_vol >= 10) {
    new_vol -= 10;
  } else {
    new_vol = 0;
  }
  s_avrc_volume = new_vol;
  settings_set_bt_volume(new_vol);
  notify_volume_changed();
  ESP_LOGI(TAG, "AVRCP: volume down -> %d/127", new_vol);
}
