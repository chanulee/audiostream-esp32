import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

spec = importlib.util.spec_from_file_location('capture', Path(__file__).parents[1] / 'tools/capture.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def wav_bytes():
    dest = io.BytesIO()
    with wave.open(dest, 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b'\x01\x00\x02\x00' * 44100)
    return dest.getvalue()


class CaptureTest(unittest.TestCase):
    def run_capture(self, payload):
        status = json.dumps({'state': 'complete', 'sample_rate': 44100}).encode()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'clip.wav'
            output.write_bytes(b'previous file')
            with patch.object(module, 'request', side_effect=[status, payload]):
                try:
                    module.capture('http://receiver', 1, output)
                except ValueError:
                    self.assertEqual(output.read_bytes(), b'previous file')
                    self.assertEqual(list(Path(directory).iterdir()), [output])
                    raise
            return output.read_bytes()

    def test_valid_wav(self):
        payload = wav_bytes()
        self.assertEqual(self.run_capture(payload), payload)

    def test_truncated_download_preserves_destination(self):
        with self.assertRaises(ValueError):
            self.run_capture(wav_bytes()[:-4])

    def test_rate_change_aborts_without_download(self):
        status = json.dumps({'state': 'rate_changed', 'sample_rate': 48000}).encode()
        with patch.object(module, 'request', return_value=status) as request:
            with self.assertRaisesRegex(ValueError, '주파수'):
                module.capture('http://receiver', 1, 'unused.wav')
            self.assertEqual(request.call_count, 1)

    def test_timeout_before_download(self):
        status = json.dumps({'state': 'armed', 'sample_rate': 44100}).encode()
        with patch.object(module, 'request', return_value=status) as request:
            with self.assertRaises(TimeoutError):
                module.capture('http://receiver', 1, 'unused.wav', timeout=0)
            self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
