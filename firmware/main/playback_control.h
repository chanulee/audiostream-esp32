#pragma once

#include "esp_err.h"
#include <stdbool.h>

/**
 * Source-agnostic playback controller.
 *
 * Routes hardware button actions to the correct backend (AirPlay or
 * Bluetooth) and notifies the remote client of changes.
 *
 * For AirPlay: applies volume/pause locally, then sends DACP commands
 * to the iOS/macOS client so its UI stays in sync.
 *
 * For Bluetooth: sends AVRCP passthrough commands to the source device,
 * which controls playback and sends volume back via absolute volume.
 */

typedef enum {
  PLAYBACK_SOURCE_NONE,
  PLAYBACK_SOURCE_AIRPLAY,
  PLAYBACK_SOURCE_BLUETOOTH,
  PLAYBACK_SOURCE_SPOTIFY,
} playback_source_t;

/**
 * Initialize playback control module.
 */
esp_err_t playback_control_init(void);

/**
 * Select output on an explicit playback start/resume, never on connection.
 */
void playback_control_set_source(playback_source_t source);
esp_err_t playback_control_source_init(void);
void playback_control_release_source(playback_source_t expected);
void playback_control_set_playing(playback_source_t expected, bool playing);
/* Lock order: output lock, then a source FIFO. Never acquire in reverse. */
void playback_control_lock_output(void);
void playback_control_unlock_output(void);

/**
 * Get the current audio source.
 */
playback_source_t playback_control_get_source(void);

/**
 * Toggle play/pause.
 */
void playback_control_play_pause(void);

/**
 * Increase volume by one step (~3 dB).
 */
void playback_control_volume_up(void);

/**
 * Decrease volume by one step (~3 dB).
 */
void playback_control_volume_down(void);

/**
 * Skip to next track.
 */
void playback_control_next(void);

/**
 * Skip to previous track.
 */
void playback_control_prev(void);

/**
 * Drop the connected Bluetooth phone (if any) and become discoverable so a
 * new phone can pair. No-op without Bluetooth.
 */
void playback_control_pairing_mode(void);

/**
 * Toggle mute/unmute (AirPlay only — mirrors local mute logic from play/pause).
 */
void playback_control_toggle_mute(void);

/**
 * Check if currently muted.
 */
bool playback_control_is_muted(void);

/**
 * Get the current volume as a percentage (0..100), derived from the saved
 * AirPlay volume in NVS. Returns 0 when muted.
 */
int playback_control_get_volume_percent(void);
