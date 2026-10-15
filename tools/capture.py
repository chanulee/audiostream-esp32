#!/usr/bin/env python3
"""Arm the receiver, wait for PCM, and download a short WAV clip."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request
import wave


def request(base, path, method='GET'):
    with urllib.request.urlopen(urllib.request.Request(base + path, method=method), timeout=15) as response:
        return response.read()


def capture(base, seconds, output, timeout=120):
    if not 1 <= seconds <= 10:
        raise ValueError('seconds must be 1..10')
    base = base.rstrip('/')
    status = json.loads(request(base, f'/api/capture/start?seconds={seconds}', 'POST'))
    print('캡처 준비 완료. iPhone/Mac에서 이 기기를 AirPlay·Spotify Connect·Bluetooth 출력으로 선택하고 재생하세요.', flush=True)
    deadline = time.monotonic() + timeout
    while status['state'] != 'complete':
        if status['state'] == 'rate_changed':
            raise ValueError('캡처 중 출력 주파수가 바뀌었습니다. 같은 입력에서 다시 캡처하세요.')
        if time.monotonic() >= deadline:
            raise TimeoutError('PCM 캡처 시간 초과. AirPlay 연결과 재생 상태를 확인하세요.')
        time.sleep(0.5)
        status = json.loads(request(base, '/api/capture/status'))
    output = Path(output)
    # Validate before replacing the destination, including when a download fails.
    fd, name = tempfile.mkstemp(prefix='.capture-', suffix='.wav', dir=output.parent)
    try:
        with os.fdopen(fd, 'wb') as dest:
            dest.write(request(base, '/api/capture/wav'))
        with wave.open(name, 'rb') as wav:
            expected_frames = seconds * status['sample_rate']
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) != (2, 2, status['sample_rate'], expected_frames):
                raise ValueError('unexpected WAV format or duration')
            if len(wav.readframes(expected_frames)) != expected_frames * 4:
                raise ValueError('truncated WAV data')
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(f'저장 완료: {output} ({seconds}초, stereo PCM16)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', help='e.g. http://192.168.1.42')
    parser.add_argument('-o', '--output', type=Path, default=Path('capture.wav'))
    parser.add_argument('--seconds', type=int, choices=range(1, 11), default=3)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if not args.device.startswith(('http://', 'https://')):
        parser.error('device must start with http:// or https://')
    try:
        capture(args.device, args.seconds, args.output, args.timeout)
    except (OSError, ValueError, TimeoutError, wave.Error, EOFError) as exc:
        parser.exit(1, f'캡처 실패: {exc}\n')


if __name__ == '__main__':
    main()
