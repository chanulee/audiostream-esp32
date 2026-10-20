"""Exercise the production checks without KiCad, a network, or ESP32 hardware."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
JLC = ROOT / 'hardware/lovelace-as-008/jlc_check.py'


class StockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        source = JLC.read_text()
        # Load definitions only: the rest of this script needs a KiCad board.
        tree = ast.parse(source)
        fetch = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'fetch')
        self.env = dict(CACHE=self.cache, UA='test', json=json, subprocess=subprocess,
                        time=types.SimpleNamespace(sleep=lambda _: None))
        exec(compile(ast.Module(body=[fetch], type_ignores=[]), str(JLC), 'exec'), self.env)
        self.stock_check = source.split('# Stock and Basic / Extended.\n')[1].split('with (ROOT')[0]

    def test_stock_refreshes_but_footprints_stay_cached(self):
        for kind in ('stock', 'easyeda'):
            (self.cache / f'C1.{kind}.json').write_text('{"old": true}')
        response = types.SimpleNamespace(returncode=0, stdout='{"fresh": true}')
        with patch.object(subprocess, 'run', return_value=response) as run:
            self.assertEqual(self.env['fetch']('C1', 'easyeda'), {'old': True})
            run.assert_not_called()
            self.assertEqual(self.env['fetch']('C1', 'stock'), {'fresh': True})
            self.assertEqual(self.env['fetch']('C1', 'stock'), {'fresh': True})
            self.assertEqual(run.call_count, 2)

    def test_failed_refresh_never_falls_back_to_cache(self):
        cached = self.cache / 'C1.stock.json'
        cached.write_text('{"old": true}')
        response = types.SimpleNamespace(returncode=22, stdout='')
        with patch.object(subprocess, 'run', return_value=response):
            with self.assertRaises(SystemExit):
                self.env['fetch']('C1', 'stock')
        self.assertEqual(json.loads(cached.read_text()), {'old': True})

    def test_stock_missing_low_invalid_and_sufficient(self):
        for count in (None, 0, 99, '100', 100, 2705):
            with self.subTest(count=count):
                parts = [] if count is None else [dict(componentCode='C1', stockCount=count)]
                env = dict(design={'R1': dict(kind='resistor', lcsc='C1'),
                                   'C26': dict(kind='capacitor', lcsc='C2', dnp=True)}, bad=[])
                env['fetch'] = lambda *_: {'data': {'componentPageInfo': {'list': parts}}}
                exec(self.stock_check, env)
                self.assertEqual(bool(env['bad']), count not in (100, 2705))
                self.assertEqual(list(env['stock']), ['C1'])


class OtaRecoveryTest(unittest.TestCase):
    def test_handler_failure_and_success_paths(self):
        source = (ROOT / 'firmware/main/network/web_server.c').read_text()
        handler = 'static esp_err_t ota_update_handler' + source.split(
            'static esp_err_t ota_update_handler', 1)[1].split('\nstatic ', 1)[0]
        harness = r'''
#include <assert.h>
#include <stddef.h>
typedef int esp_err_t;
typedef struct { int content_len; } httpd_req_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define pdMS_TO_TICKS(x) (x)
static int stops, starts, updates, reboots, status, sends, update_err, restart_err;
static const char *esp_err_to_name(int err) { assert(err == update_err); return "OTA error"; }
static void rtsp_server_stop(void) { ++stops; }
static int rtsp_server_start(void) { ++starts; return restart_err; }
static int ota_start_from_http(httpd_req_t *req) { (void)req; ++updates; return update_err; }
static int httpd_resp_send_err(httpd_req_t *req, int code, const char *msg) {
  (void)req; (void)msg; status = code; return 0;
}
static void httpd_resp_sendstr(httpd_req_t *req, const char *msg) {
  (void)req; (void)msg; ++sends;
}
static void vTaskDelay(int ticks) { (void)ticks; }
static void esp_restart(void) { ++reboots; }
'''
        cases = r'''
int main(void) {
  httpd_req_t req = {0};
  assert(ota_update_handler(&req) == ESP_FAIL);
  assert(status == 400 && stops == 0 && starts == 0 && updates == 0);
  req.content_len = 4096;
  /* Invalid image, interrupted upload, and inability to restart the server. */
  for (int i = 1; i <= 3; ++i) {
    stops = starts = updates = reboots = sends = status = 0;
    update_err = i;
    restart_err = (i == 3) ? ESP_FAIL : ESP_OK;
    assert(ota_update_handler(&req) == ESP_FAIL);
    assert(stops == 1 && starts == 1 && updates == 1 && status == 500);
    assert(reboots == 0 && sends == 0);
  }
  stops = starts = updates = status = 0;
  update_err = 0;
  assert(ota_update_handler(&req) == ESP_OK);
  assert(stops == 1 && starts == 0 && updates == 1 && status == 0);
  assert(reboots == 1 && sends == 1);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(harness + handler + cases)
            subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)
