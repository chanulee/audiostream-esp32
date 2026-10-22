#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I firmware/main/audio tests/test_pcm_capture.c firmware/main/audio/pcm_capture.c -o "$build_dir/capture"
"$build_dir/capture"
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I firmware/main/audio tests/test_pcm_fifo.c firmware/main/audio/pcm_fifo.c -o "$build_dir/fifo"
"$build_dir/fifo"
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -DCONFIG_SPOTIFY_ENABLED=1 -DCONFIG_BT_A2DP_ENABLE=1 \
  -I tests/stubs -I firmware/main/audio -I firmware/main/rtsp -I firmware/main \
  -I firmware/components/spotify tests/test_spotify_audio.c \
  firmware/main/audio/spotify_audio.c firmware/main/audio/pcm_fifo.c \
  firmware/main/audio/audio_source.c firmware/main/audio/audio_output_common.c -o "$build_dir/arbitration"
"$build_dir/arbitration"
clang++ -std=c++20 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I firmware/components/spotify tests/test_spotify_form.cpp \
  firmware/components/spotify/form_codec.cpp -o "$build_dir/form"
"$build_dir/form"
if command -v node > /dev/null; then
  node tests/test_figma_pcb.js
fi
python3 -m unittest discover -s tests -v
