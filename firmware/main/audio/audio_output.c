#include "audio_output.h"
#include "audio_capture.h"
#include "playback_control.h"
#ifdef CONFIG_BT_A2DP_ENABLE
#include "a2dp_sink.h"
#endif
#ifdef CONFIG_SPOTIFY_ENABLED
#include "spotify_audio.h"
#endif
#include "rtsp_server.h"

#include "audio_resample.h"
#include "dac.h"
#include "led.h"
#include "settings.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_check.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "audio_receiver.h"
#include <inttypes.h>
#include <stdlib.h>

// SIDE NOTE; providing power from GPIO pins is capped ~20mA.
#if CONFIG_I2S_GND_IO >= 0
#define I2S_GND_PIN CONFIG_I2S_GND_IO
#endif
#if CONFIG_I2S_VCC_IO >= 0
#define I2S_VCC_PIN CONFIG_I2S_VCC_IO
#endif

#define TAG           "audio_output"
#define I2S_SCK_PIN   CONFIG_I2S_SCK_IO
#define I2S_BCK_PIN   CONFIG_I2S_BCK_IO
#define I2S_LRCK_PIN  CONFIG_I2S_WS_IO
#define I2S_DOUT_PIN  CONFIG_I2S_DO_IO
#define OUTPUT_RATE   CONFIG_OUTPUT_SAMPLE_RATE_HZ
#define FRAME_SAMPLES 352

// DMA ring-buffer configuration.  Total DMA latency (in samples) is
//   I2S_DMA_DESC_NUM × I2S_DMA_FRAME_NUM
// which at OUTPUT_RATE gives the hardware pipeline delay in µs.
// Keep these in sync with the i2s_chan_config_t initialisation below.
#define I2S_DMA_DESC_NUM  8
#define I2S_DMA_FRAME_NUM 256

// PCM5102A XSMT soft mute: the ramp takes 150 samples + 0.2 ms (3.6 ms at
// 44.1 kHz) and needs running clocks. Unmute only after the DAC's PLL has
// locked onto a fresh clock (a few ms of silence).
#define DAC_MUTE_RAMP_MS 5
#define DAC_LOCK_MS      20

/* Max output frames after resampling one input frame */
#define MAX_RESAMPLE_FRAMES \
  ((size_t)((FRAME_SAMPLES + 2) * ((double)OUTPUT_RATE / 44100) + 16))

#if CONFIG_FREERTOS_UNICORE
#define PLAYBACK_CORE 0
#else
#define PLAYBACK_CORE 1
#endif

static i2s_chan_handle_t tx_handle;
static volatile bool flush_requested = false;
static volatile bool playback_running = false;
static TaskHandle_t playback_task_handle = NULL;
static volatile int source_rate = 44100;
static uint32_t hardware_rate = OUTPUT_RATE;
static volatile bool resample_reinit_needed = false;
static volatile audio_channel_mode_t channel_mode = AUDIO_CHANNEL_STEREO;

/* Live output cursor.  output_submitted_frames advances after a successful
 * i2s_channel_write(); output_sent_frames is advanced by the TX DMA
 * completion ISR.  Their difference is the amount of audio queued ahead of
 * the next write, i.e. the real pipeline delay.
 *
 * auto_clear keeps the DMA clocking descriptors even when the writer stalls,
 * so sent can overtake submitted.  The excess is output time that was played
 * as silence and can never be recovered; it is folded into
 * output_lost_frames so that the queue depth stays non-negative and the
 * cursor keeps a stable meaning across a starvation episode. */
static uint64_t output_submitted_frames;
static uint64_t output_sent_frames;
static uint64_t output_lost_frames;
static uint32_t output_underruns;

static bool IRAM_ATTR audio_output_on_sent(i2s_chan_handle_t handle,
                                           i2s_event_data_t *event,
                                           void *user_ctx) {
  (void)handle;
  (void)user_ctx;
  if (event && event->size > 0) {
    __atomic_add_fetch(&output_sent_frames,
                       (uint64_t)(event->size / (2U * sizeof(int16_t))),
                       __ATOMIC_RELAXED);
  }
  return false;
}

static void output_cursor_reset(void) {
  __atomic_store_n(&output_submitted_frames, 0, __ATOMIC_RELAXED);
  __atomic_store_n(&output_sent_frames, 0, __ATOMIC_RELAXED);
  __atomic_store_n(&output_lost_frames, 0, __ATOMIC_RELAXED);
}

/* Frames queued in the DMA ring ahead of the next write.  Called from the
 * playback task only, which is also the sole writer of the submitted and
 * lost counters, so the rebase below needs no lock. */
static uint32_t output_queued_frames(void) {
  uint64_t submitted =
      __atomic_load_n(&output_submitted_frames, __ATOMIC_RELAXED);
  uint64_t lost = __atomic_load_n(&output_lost_frames, __ATOMIC_RELAXED);
  uint64_t sent = __atomic_load_n(&output_sent_frames, __ATOMIC_RELAXED);

  if (sent > submitted + lost) {
    /* The ring ran dry: rebase so queued reads 0 and remember how much
     * output time went out as silence. */
    __atomic_store_n(&output_lost_frames, sent - submitted, __ATOMIC_RELAXED);
    output_underruns++;
    return 0;
  }

  uint64_t queued = submitted + lost - sent;
  const uint64_t ring = (uint64_t)I2S_DMA_DESC_NUM * I2S_DMA_FRAME_NUM;
  return queued > ring ? (uint32_t)ring : (uint32_t)queued;
}

/* A bi-amp hybrid flow drives one output per crossover way, so there is no
 * left and right to pick from downstream — the DSP's input mixer makes the
 * selection instead, and the software downmix has to stand aside. */
bool audio_output_channel_mode_in_dsp(void) {
  return false;
}

static void dac_mute(bool mute) {
#if CONFIG_MUTE_GPIO >= 0
  gpio_set_level(CONFIG_MUTE_GPIO,
                 mute ? CONFIG_MUTE_GPIO_LEVEL : !CONFIG_MUTE_GPIO_LEVEL);
#else
  (void)mute;
#endif
}

// Stopping the I2S clocks under a playing DAC pops; ramp the output down
// first and back up once the new clock has settled.
static void i2s_restart_muted(const i2s_std_clk_config_t *clk_cfg) {
  dac_mute(true);
  vTaskDelay(pdMS_TO_TICKS(DAC_MUTE_RAMP_MS));
  i2s_channel_disable(tx_handle);
  if (clk_cfg) {
    ESP_ERROR_CHECK(i2s_channel_reconfig_std_clock(tx_handle, clk_cfg));
  }
  output_cursor_reset();
  i2s_channel_enable(tx_handle);
  vTaskDelay(pdMS_TO_TICKS(DAC_LOCK_MS));
  dac_mute(false);
}

// esp_restart() (OTA, settings) stops the clocks too.
static void dac_mute_on_shutdown(void) {
  dac_mute(true);
  esp_rom_delay_us(DAC_MUTE_RAMP_MS * 1000);
}

static void push_channel_mode_to_dsp(audio_channel_mode_t mode) {
  (void)mode;
}

static void apply_volume(int16_t *buf, size_t n, int32_t target) {
  // Ramp toward the target gain instead of applying volume changes
  // instantly.  An abrupt gain step mid-waveform is a discontinuity scaled
  // by the signal's current amplitude — the classic volume "zipper" click,
  // audible on every step of the sender's volume slider.  Approach the
  // target exponentially, stepping once per stereo frame (even indices) so
  // both channels always carry the same gain; the /256 divisor gives a
  // ~3 ms time constant and a worst-case per-frame gain step of ~0.4%,
  // with a minimum step of 1 so the ramp always completes.
  static int32_t cur_q15 = -1;
  if (cur_q15 < 0) {
    cur_q15 = target; // first call: no audio has played yet, jump silently
  }
  for (size_t i = 0; i < n; i++) {
    if ((i & 1) == 0 && cur_q15 != target) {
      int32_t diff = target - cur_q15;
      int32_t step = diff / 256;
      if (step == 0) {
        step = diff > 0 ? 1 : -1;
      }
      cur_q15 += step;
    }
    buf[i] = (int16_t)(((int32_t)buf[i] * cur_q15) >> 15);
  }
}

// Apply the selected channel mode to an interleaved stereo buffer (L,R,...).
// LEFT/RIGHT route the chosen source channel to BOTH outputs so the selected
// track is heard from both speakers; MONO plays the (L+R)/2 downmix on both
// outputs; STEREO leaves the buffer untouched.
static void apply_channel_mode(int16_t *buf, size_t frames) {
  if (audio_output_channel_mode_in_dsp()) {
    return;
  }
  audio_channel_mode_t mode = channel_mode;
  if (mode == AUDIO_CHANNEL_STEREO) {
    return;
  }
  if (mode == AUDIO_CHANNEL_MONO) {
    for (size_t i = 0; i < frames; i++) {
      int16_t m = (int16_t)(((int32_t)buf[i * 2] + buf[i * 2 + 1]) / 2);
      buf[i * 2] = m;
      buf[i * 2 + 1] = m;
    }
    return;
  }
  size_t src = (mode == AUDIO_CHANNEL_RIGHT) ? 1 : 0;
  for (size_t i = 0; i < frames; i++) {
    int16_t s = buf[i * 2 + src];
    buf[i * 2] = s;
    buf[i * 2 + 1] = s;
  }
}

// The selected source decides the I2S clock: A2DP may negotiate 48 kHz, every
// other source is decoded or resampled to OUTPUT_RATE.
static uint32_t source_hardware_rate(playback_source_t source) {
#ifdef CONFIG_BT_A2DP_ENABLE
  if (source == PLAYBACK_SOURCE_BLUETOOTH) {
    return bt_a2dp_sink_sample_rate();
  }
#endif
  (void)source;
  return OUTPUT_RATE;
}

static size_t source_read(playback_source_t source, int16_t *pcm,
                          size_t max_frames) {
  size_t frames = 0;
  switch (source) {
  case PLAYBACK_SOURCE_AIRPLAY:
    frames = audio_receiver_read(pcm, max_frames);
    break;
#ifdef CONFIG_SPOTIFY_ENABLED
  case PLAYBACK_SOURCE_SPOTIFY:
    spotify_audio_read(pcm, max_frames, &frames);
    break;
#endif
#ifdef CONFIG_BT_A2DP_ENABLE
  case PLAYBACK_SOURCE_BLUETOOTH:
    frames = bt_a2dp_sink_read(pcm, max_frames);
    break;
#endif
  default:
    break;
  }
  return frames;
}

static int32_t source_gain_q15(playback_source_t source) {
  switch (source) {
#ifdef CONFIG_SPOTIFY_ENABLED
  case PLAYBACK_SOURCE_SPOTIFY:
    return spotify_audio_volume_q15();
#endif
#ifdef CONFIG_BT_A2DP_ENABLE
  case PLAYBACK_SOURCE_BLUETOOTH:
    return bt_a2dp_sink_volume_q15();
#endif
  default:
    // PCM5102A has no hardware volume; local AirPlay mute is applied here.
    return playback_control_is_muted() ? 0 : airplay_get_volume_q15();
  }
}

static void playback_task(void *arg) {
  int16_t *pcm = malloc((size_t)(FRAME_SAMPLES + 1) * 2 * sizeof(int16_t));
  int16_t *silence = calloc((size_t)FRAME_SAMPLES * 2, sizeof(int16_t));
  int16_t *resample_buf = malloc(MAX_RESAMPLE_FRAMES * 2 * sizeof(int16_t));
  if (!pcm || !silence || !resample_buf) {
    ESP_LOGE(TAG, "Failed to allocate buffers");
    free(pcm);
    free(silence);
    playback_task_handle = NULL;
    free(resample_buf);
    vTaskDelete(NULL);
    return;
  }

  size_t written;
  while (playback_running) {
    playback_control_lock_output();
    playback_source_t source = playback_control_get_source();
    uint32_t desired_rate = source_hardware_rate(source);
    if (hardware_rate != desired_rate) {
      audio_output_set_sample_rate(desired_rate);
    }
    if (resample_reinit_needed) {
      resample_reinit_needed = false;
      audio_resample_init((uint32_t)source_rate, OUTPUT_RATE, 2);
    }
    if (flush_requested) {
      flush_requested = false;
      audio_resample_reset();
      i2s_restart_muted(NULL);
    }
    size_t samples = source_read(source, pcm, FRAME_SAMPLES + 1);
    if (samples > 0) {
      int16_t *play_buf = pcm;
      size_t play_samples = samples;
      if (source == PLAYBACK_SOURCE_AIRPLAY && audio_resample_is_active()) {
        play_samples = audio_resample_process(pcm, samples, resample_buf,
                                              MAX_RESAMPLE_FRAMES);
        play_buf = resample_buf;
      }
      int32_t gain = source_gain_q15(source);
      apply_volume(play_buf, play_samples * 2, gain);
      apply_channel_mode(play_buf, play_samples);
      led_audio_feed(play_buf, play_samples);
      if (i2s_channel_write(tx_handle, play_buf,
                            play_samples * 2 * sizeof(int16_t), &written,
                            portMAX_DELAY) == ESP_OK) {
        __atomic_add_fetch(&output_submitted_frames,
                           (uint64_t)(written / (2U * sizeof(int16_t))),
                           __ATOMIC_RELAXED);
#ifdef CONFIG_AUDIO_CAPTURE_ENABLED
        audio_capture_feed(play_buf, written, true, hardware_rate);
#endif
      }
    } else {
      // Receiver underflow — output a frame of silence.  Block on the DMA
      // write (portMAX_DELAY) so the write itself paces the loop, instead of a
      // short timeout plus vTaskDelay(1) which produced jittery silence.
      led_audio_feed(silence, FRAME_SAMPLES);
      if (i2s_channel_write(tx_handle, silence,
                            (size_t)FRAME_SAMPLES * 2 * sizeof(int16_t),
                            &written, portMAX_DELAY) == ESP_OK) {
        __atomic_add_fetch(&output_submitted_frames,
                           (uint64_t)(written / (2U * sizeof(int16_t))),
                           __ATOMIC_RELAXED);
#ifdef CONFIG_AUDIO_CAPTURE_ENABLED
        audio_capture_feed(silence, written, false, hardware_rate);
#endif
      }
    }
    playback_control_unlock_output();
    taskYIELD();
  }

  free(resample_buf);
  free(pcm);
  free(silence);
  playback_task_handle = NULL;
  vTaskDelete(NULL);
}

esp_err_t audio_output_init(void) {
  uint8_t saved_mode;
  if (settings_get_channel_mode(&saved_mode) == ESP_OK &&
      saved_mode <= AUDIO_CHANNEL_MONO) {
    channel_mode = (audio_channel_mode_t)saved_mode;
    ESP_LOGI(TAG, "Loaded channel mode: %d", saved_mode);
  }

  if (channel_mode != AUDIO_CHANNEL_STEREO &&
      audio_output_channel_mode_locked()) {
    ESP_LOGI(TAG, "Dual DAC output: ignoring saved channel mode");
    // Not persisted: the preference is only meaningless while two amps are
    // fitted, so keep it for if the board is ever reconfigured.
    channel_mode = AUDIO_CHANNEL_STEREO;
  }
  push_channel_mode_to_dsp(channel_mode);

  i2s_chan_config_t chan_cfg =
      I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  chan_cfg.dma_desc_num = I2S_DMA_DESC_NUM;
  chan_cfg.dma_frame_num = I2S_DMA_FRAME_NUM;
  // Zero each DMA descriptor after it is sent.  Without this, a writer
  // stall longer than the DMA ring (~46 ms — e.g. an NVS/flash write
  // disabling the cache, or a CPU burst from the web server) makes the
  // hardware REPLAY the stale ring contents in a loop: a loud stutter, then
  // a second discontinuity on recovery.  With auto_clear an underrun
  // degrades to plain silence.
  chan_cfg.auto_clear = true;

  ESP_RETURN_ON_ERROR(i2s_new_channel(&chan_cfg, &tx_handle, NULL), TAG,
                      "channel create failed");

  i2s_std_config_t std_cfg = {
      .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(OUTPUT_RATE),
      .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,
                                                      I2S_SLOT_MODE_STEREO),
      .gpio_cfg =
          {
              .mclk = I2S_SCK_PIN,
              .bclk = I2S_BCK_PIN,
              .ws = I2S_LRCK_PIN,
              .dout = I2S_DOUT_PIN,
              .din = I2S_GPIO_UNUSED,
          },
  };
#ifdef I2S_GND_PIN
  gpio_reset_pin(I2S_GND_PIN);
  gpio_set_direction(I2S_GND_PIN, GPIO_MODE_OUTPUT);
  gpio_set_level(I2S_GND_PIN, 0);
#endif
#ifdef I2S_VCC_PIN
  gpio_reset_pin(I2S_VCC_PIN);
  gpio_set_direction(I2S_VCC_PIN, GPIO_MODE_OUTPUT);
  gpio_set_level(I2S_VCC_PIN, 1);
#endif

  ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(tx_handle, &std_cfg), TAG,
                      "std mode init failed");

  // TX completion callback drives the live output cursor used by the timing
  // engine (see audio_output_get_pipeline_us).
  const i2s_event_callbacks_t callbacks = {
      .on_recv = NULL,
      .on_recv_q_ovf = NULL,
      .on_sent = audio_output_on_sent,
      .on_send_q_ovf = NULL,
  };
  ESP_RETURN_ON_ERROR(
      i2s_channel_register_event_callback(tx_handle, &callbacks, NULL), TAG,
      "event callback registration failed");
  output_cursor_reset();

  ESP_RETURN_ON_ERROR(i2s_channel_enable(tx_handle), TAG,
                      "channel enable failed");
  ESP_LOGI(TAG, "I2S initialized: Rate=%u, DMA_Desc=%d, DMA_Frame=%d",
           (unsigned int)OUTPUT_RATE, I2S_DMA_DESC_NUM, I2S_DMA_FRAME_NUM);
  // The DAC has been muted since reset (board pull-down, iot_board_init).
  vTaskDelay(pdMS_TO_TICKS(DAC_LOCK_MS));
  dac_mute(false);
  esp_register_shutdown_handler(dac_mute_on_shutdown);

  // MCLK/BCLK/LRCK are now running. Some codecs need this edge to finish their
  // clock setup; amplifiers that manage power from board RTSP events can ignore
  // the hook.
  dac_on_i2s_started();

  audio_resample_init(44100, OUTPUT_RATE, 2);

  return ESP_OK;
}

void audio_output_start(void) {
  if (playback_task_handle != NULL) {
    return; // already running
  }
  playback_running = true;
  // The DMA has been free-running (A2DP, or plain silence) since the last
  // AirPlay session, so the cursor carries an arbitrary submitted/sent skew.
  // Start the new session from a clean slate.
  output_cursor_reset();
  xTaskCreatePinnedToCore(playback_task, "audio_play", 4096, NULL,
                          AUDIO_PLAYBACK_TASK_PRIORITY, &playback_task_handle,
                          PLAYBACK_CORE);
}

void audio_output_stop(void) {
  if (playback_task_handle == NULL) {
    return;
  }
  playback_running = false;
  // Wait for task to exit cleanly
  int timeout = 40;
  while (playback_task_handle != NULL && timeout-- > 0) {
    vTaskDelay(pdMS_TO_TICKS(50));
  }
  if (playback_task_handle != NULL) {
    ESP_LOGW(TAG, "Playback task did not exit within timeout");
  } else {
    ESP_LOGI(TAG, "Playback task stopped");
  }
}

esp_err_t audio_output_write(const void *data, size_t bytes, TickType_t wait) {
  size_t written = 0;
  return i2s_channel_write(tx_handle, data, bytes, &written, wait);
}

void audio_output_set_sample_rate(uint32_t rate) {
  // Called only by the single writer, holding the output lock.
  ESP_LOGI(TAG, "Setting sample rate to %" PRIu32 " Hz", rate);
  i2s_std_clk_config_t clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(rate);
  i2s_restart_muted(&clk_cfg);
  hardware_rate = rate;
  dac_on_i2s_started();
}

void audio_output_flush(void) {
  flush_requested = true;
}

void audio_output_set_source_rate(int rate) {
  if (rate > 0 && rate != source_rate) {
    source_rate = rate;
    resample_reinit_needed = true;
  }
}

uint32_t audio_output_get_hardware_latency_us(void) {
  // Delay between i2s_channel_write() accepting a sample and that sample
  // leaving the DAC.  This is the DMA ring occupancy AHEAD of the newly
  // written data, which is NOT the full ring: i2s_channel_write() blocks
  // only until space frees, so the writer refills as soon as a descriptor
  // completes and steady-state occupancy oscillates between
  // (DESC_NUM - 1) and DESC_NUM descriptors.
  //
  // Using the full ring (DESC_NUM) overstates the delay by half a
  // descriptor on average — 2.9 ms at 44.1 kHz with the config below — and
  // that bias lands directly in compute_early_us(), pushing every frame
  // toward the "late" side of the threshold.  Model the midpoint instead:
  //   (DESC_NUM - 0.5) x FRAME_NUM == (2*DESC_NUM - 1) x FRAME_NUM / 2
  // The residual +/-2.9 ms swing is real jitter that the drift servo in
  // audio_timing.c absorbs; only the constant bias is removed here.
  return (uint32_t)((((uint64_t)(2 * I2S_DMA_DESC_NUM - 1) * I2S_DMA_FRAME_NUM *
                      1000000ULL) /
                     2) /
                    hardware_rate);
}

bool audio_output_get_pipeline_us(int64_t *now_us, uint32_t *pipeline_us) {
  // Sample the queue depth first, then the clock: any DMA completion that
  // lands between the two makes the reported depth slightly stale in the
  // conservative direction (we believe the pipeline is fuller, i.e. that the
  // next sample plays later, than it really is).  The error is bounded by
  // one descriptor period and is absorbed by the position servo.
  uint32_t queued = output_queued_frames();
  if (now_us) {
    *now_us = esp_timer_get_time();
  }
  if (pipeline_us) {
    *pipeline_us = (uint32_t)(((uint64_t)queued * 1000000ULL) / hardware_rate);
  }
  return true;
}

uint32_t audio_output_get_underruns(void) {
  return __atomic_load_n(&output_underruns, __ATOMIC_RELAXED);
}

/* With two amplifiers the DAC configuration already fixes the routing, so a
 * channel selection on top of that would only mute a speaker. */
bool audio_output_channel_mode_locked(void) {
  return false;
}

audio_channel_mode_t audio_output_cycle_channel_mode(void) {
  if (audio_output_channel_mode_locked()) {
    return channel_mode;
  }
  audio_channel_mode_t next;
  switch (channel_mode) {
  case AUDIO_CHANNEL_STEREO:
    next = AUDIO_CHANNEL_LEFT;
    break;
  case AUDIO_CHANNEL_LEFT:
    next = AUDIO_CHANNEL_RIGHT;
    break;
  case AUDIO_CHANNEL_RIGHT:
    next = AUDIO_CHANNEL_MONO;
    break;
  default:
    next = AUDIO_CHANNEL_STEREO;
    break;
  }
  audio_output_set_channel_mode(next);
  return next;
}

void audio_output_set_channel_mode(audio_channel_mode_t mode) {
  if (audio_output_channel_mode_locked()) {
    return;
  }
  if (mode > AUDIO_CHANNEL_MONO) {
    mode = AUDIO_CHANNEL_STEREO;
  }
  channel_mode = mode;
  settings_set_channel_mode((uint8_t)mode);
  push_channel_mode_to_dsp(mode);
  ESP_LOGI(TAG, "Channel mode: %s",
           mode == AUDIO_CHANNEL_LEFT    ? "LEFT only"
           : mode == AUDIO_CHANNEL_RIGHT ? "RIGHT only"
           : mode == AUDIO_CHANNEL_MONO  ? "MONO (L+R)"
                                         : "STEREO");
}

audio_channel_mode_t audio_output_get_channel_mode(void) {
  return channel_mode;
}
