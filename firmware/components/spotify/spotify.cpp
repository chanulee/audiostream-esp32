#include "spotify.h"
#include "cJSON.h"
#include "form_codec.h"
#include "CSpotContext.h"
#include "SpircHandler.h"
#include "TrackPlayer.h"
#include "BellTask.h"
#include "BellLogger.h"
#include "LoginBlob.h"
#include "mdns.h"
#include "nvs.h"
#include "esp_log.h"
#include "esp_netif_sntp.h"
#include <ctime>
#include "esp_timer.h"
#include "freertos/queue.h"
#include <algorithm>
#include <atomic>
#include <deque>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

static const char *TAG="spotify";
static const char *NS="spotify";
static std::string nvs_string(const char *key) {
    nvs_handle_t handle;
    if (nvs_open(NS, NVS_READONLY, &handle)!=ESP_OK) return {};
    size_t size=0;
    std::string result;
    if (nvs_get_str(handle, key, nullptr, &size)==ESP_OK && size>0 && size<=8192) {
        result.resize(size);
        if (nvs_get_str(handle, key, result.data(), &size)!=ESP_OK) result.clear();
        else result.resize(size-1);
    }
    nvs_close(handle);
    return result;
}
static std::pair<std::string,std::string> app_credentials() {
    auto saved=nvs_string("app");
    cJSON *json=cJSON_ParseWithLength(saved.data(), saved.size());
    auto id=cJSON_GetObjectItemCaseSensitive(json,"client_id");
    auto secret=cJSON_GetObjectItemCaseSensitive(json,"client_secret");
    std::pair<std::string,std::string> result;
    if (cJSON_IsString(id) && cJSON_IsString(secret) &&
        spotify_valid_client_key(id->valuestring) && spotify_valid_client_key(secret->valuestring))
        result={id->valuestring,secret->valuestring};
    cJSON_Delete(json);
    return result;
}
static esp_err_t save_string(const char *key, const std::string &value) {
    nvs_handle_t handle;
    esp_err_t err=nvs_open(NS, NVS_READWRITE, &handle);
    if (err!=ESP_OK) return err;
    err=nvs_set_str(handle, key, value.c_str());
    if (err==ESP_OK) err=nvs_commit(handle);
    nvs_close(handle);
    return err;
}
static void erase_login() {
    nvs_handle_t handle;
    if (nvs_open(NS, NVS_READWRITE, &handle)==ESP_OK) {
        nvs_erase_key(handle, "credentials");
        nvs_commit(handle);
        nvs_close(handle);
    }
}
static esp_err_t http_error(httpd_req_t *r, const char *status, const char *message) {
    httpd_resp_set_status(r, status);
    return httpd_resp_send(r, message, HTTPD_RESP_USE_STRLEN);
}
static std::string receive(httpd_req_t *r, size_t limit) {
    if (r->content_len<=0 || static_cast<size_t>(r->content_len)>limit)
        throw std::invalid_argument("invalid request length");
    std::string body(r->content_len, '\0');
    size_t offset=0;
    while (offset<body.size()) {
        int n=httpd_req_recv(r, body.data()+offset, body.size()-offset);
        if (n<=0) throw std::invalid_argument("incomplete request");
        offset+=n;
    }
    return body;
}
static esp_err_t send_json(httpd_req_t *r, const std::string &body) {
    httpd_resp_set_type(r, "application/json");
    httpd_resp_set_hdr(r, "Cache-Control", "no-store");
    return httpd_resp_send(r, body.data(), body.size());
}

class Player : public bell::Task {
public:
    Player(const char *name, const spotify_callbacks_t &callbacks)
        : bell::Task("spotify_session", 24*1024, 0, 0, false), name(name), cb(callbacks) {
        commands=xQueueCreate(8, sizeof(spotify_command_t));
        wake=xSemaphoreCreateBinary();
        if (!commands || !wake) throw std::bad_alloc();
        try {
            std::string saved=nvs_string("volume");
            if (!saved.empty()) volume=std::clamp(std::stoi(saved), 0, 65535);
        } catch (...) {}
        configured=!app_credentials().first.empty();
    }
    std::atomic<bool> configured{false}, started{false}, connected{false}, paused{true};
    std::atomic<int> volume{32768};
    std::atomic<bool> volume_dirty{false};
    int pre_mute=32768;
    int64_t last_volume_save=0;
    std::mutex blob_mutex, state_mutex, markers_mutex;
    std::shared_ptr<cspot::LoginBlob> blob;
    std::string state="offline", title, artist, album;
    uint32_t duration=0;
    QueueHandle_t commands=nullptr;
    SemaphoreHandle_t wake=nullptr;
    std::string name;
    spotify_callbacks_t cb;
    std::unique_ptr<cspot::SpircHandler> spirc;
    std::deque<std::pair<uint64_t,std::string>> markers;
    std::string stream_id;
    std::atomic<bool> depleted{false}, forget{false};

    void set_state(const char *value) {
        std::lock_guard lock(state_mutex);
        state=value;
    }
    void reset_audio() {
        std::lock_guard lock(markers_mutex);
        markers.clear(); stream_id.clear(); depleted=false;
        cb.flush();
    }
    void event(std::unique_ptr<cspot::SpircHandler::Event> event) {
        using E=cspot::SpircHandler::EventType;
        switch (event->eventType) {
        case E::PLAYBACK_START:
            reset_audio();
            if (!cb.begin()) { enqueue(SPOTIFY_PAUSE); set_state("airplay_busy"); }
            else set_state("playing");
            break;
        case E::PLAY_PAUSE:
            paused=std::get<bool>(event->data);
            cb.pause(paused);
            set_state(paused ? "paused" : "playing");
            break;
        case E::FLUSH: case E::NEXT: case E::PREV: case E::SEEK:
            reset_audio();
            break;
        case E::DISC:
            paused=true; cb.end(); reset_audio(); set_state("connected");
            break;
        case E::VOLUME:
            volume=std::clamp(std::get<int>(event->data), 0, 65535);
            cb.volume(volume); volume_dirty=true;
            break;
        case E::TRACK_INFO: {
            auto info=std::get<cspot::TrackInfo>(event->data);
            std::lock_guard lock(state_mutex);
            title=info.name; artist=info.artist; album=info.album; duration=info.duration;
            break;
        }
        case E::DEPLETED:
            depleted=true;
            break;
        default: break;
        }
    }
    size_t write(uint8_t *pcm, size_t bytes, std::string_view id) {
        std::lock_guard lock(markers_mutex);
        uint64_t boundary=cb.written_frames();
        size_t accepted=cb.write(pcm, bytes);
        if (accepted && stream_id!=id) {
            stream_id=id;
            markers.emplace_back(boundary, stream_id);
        }
        return accepted;
    }
    void enqueue(spotify_command_t command) {
        // AirPlay preemption must survive a full local button queue.
        if (command==SPOTIFY_YIELD) yield_requested=true;
        else if (command==SPOTIFY_PAUSE) pause_requested=true;
        else xQueueSend(commands, &command, 0);
    }
    std::atomic<bool> pause_requested{false}, yield_requested{false};
    void handle_commands() {
        if (yield_requested.exchange(false)) { reset_audio(); spirc->setPause(true); }
        if (pause_requested.exchange(false)) spirc->setPause(true);
        spotify_command_t command;
        while (xQueueReceive(commands, &command, 0)==pdTRUE) {
            switch (command) {
            case SPOTIFY_TOGGLE: spirc->setPause(!paused); break;
            case SPOTIFY_PAUSE: spirc->setPause(true); break;
            case SPOTIFY_YIELD: reset_audio(); spirc->setPause(true); break;
            case SPOTIFY_NEXT: spirc->nextSong(); break;
            case SPOTIFY_PREV: spirc->previousSong(); break;
            case SPOTIFY_MUTE_TOGGLE:
                if (volume==0) volume=pre_mute;
                else { pre_mute=volume; volume=0; }
                cb.volume(volume); spirc->setRemoteVolume(volume); volume_dirty=true;
                break;
            case SPOTIFY_VOLUME_UP: case SPOTIFY_VOLUME_DOWN:
                volume=std::clamp(volume.load() + (command==SPOTIFY_VOLUME_UP ? 1311 : -1311), 0, 65535);
                cb.volume(volume); spirc->setRemoteVolume(volume); volume_dirty=true; break;
            }
        }
    }
    void playback_notifications() {
        std::deque<std::pair<uint64_t,std::string>> reached;
        {
            std::lock_guard lock(markers_mutex);
            while (!markers.empty() && cb.played_frames()>markers.front().first) {
                reached.push_back(std::move(markers.front())); markers.pop_front();
            }
        }
        if (esp_timer_get_time()-last_volume_save > 2000000 && volume_dirty.exchange(false)) {
            if (save_string("volume", std::to_string(volume.load()))!=ESP_OK) volume_dirty=true;
            last_volume_save=esp_timer_get_time();
        }
        // shortcut: PCM dequeue precedes physical I2S by one DMA pipeline;
        // use a hardware cursor if tighter Connect progress sync is required.
        for (auto &marker : reached) spirc->notifyAudioReachedPlayback(marker.second);
        if (depleted && cb.played_frames()>=cb.written_frames()) {
            depleted=false;
            spirc->notifyAudioEnded(); paused=true; cb.end(); set_state("connected");
        }
    }
    void runTask() override {
        try {
            std::lock_guard lock(blob_mutex);
            blob=std::make_shared<cspot::LoginBlob>(name);
            std::string stored=nvs_string("credentials");
            if (!stored.empty()) {
                try { blob->loadJson(stored); } catch (...) { erase_login(); }
            }
        } catch (...) { set_state("out_of_memory"); return; }
        bool have_login;
        { std::lock_guard lock(blob_mutex); have_login=!blob->authData.empty(); }
        for (;;) {
            if (!have_login || !configured) {
                set_state(configured ? "waiting_for_login" : "needs_configuration");
                xSemaphoreTake(wake, portMAX_DELAY);
            }
            if (forget.exchange(false)) {
                erase_login();
                std::lock_guard lock(blob_mutex);
                blob=std::make_shared<cspot::LoginBlob>(name);
            }
            std::shared_ptr<cspot::LoginBlob> login;
            { std::lock_guard lock(blob_mutex); login=blob; have_login=!blob->authData.empty(); }
            if (!configured || !have_login) continue;
            std::shared_ptr<cspot::Context> ctx;
            bool failed=false, rejected=false;
            try {
                set_state("connecting");
                for (int i=0; std::time(nullptr)<1609459200 && i<120 && !forget; i++)
                    vTaskDelay(pdMS_TO_TICKS(250));
                if (std::time(nullptr)<1609459200) throw std::runtime_error("Internet clock sync failed");
                ctx=cspot::Context::createFromBlob(login);
                auto credentials=app_credentials();
                ctx->config.clientId=credentials.first;
                ctx->config.clientSecret=credentials.second;
                ctx->config.audioFormat=AudioFormat_OGG_VORBIS_160;
                ctx->config.volume=volume;
                ctx->session->connectWithRandomAp();
                ctx->config.authData=ctx->session->authenticate(login);
                if (ctx->config.authData.empty()) { rejected=true; throw std::runtime_error("Spotify login rejected"); }
                if (save_string("credentials", ctx->getCredentialsJson())!=ESP_OK)
                    ESP_LOGW(TAG, "Could not persist reusable login");
                spirc=std::make_unique<cspot::SpircHandler>(ctx);
                spirc->getTrackPlayer()->setDataCallback([this](uint8_t *data, size_t bytes, std::string_view id) {
                    return write(data, bytes, id);
                });
                spirc->setEventHandler([this](auto event) { this->event(std::move(event)); });
                ctx->session->startTask();
                connected=true; set_state("connected"); cb.volume(volume);
                while (!forget) {
                    ctx->session->handlePacket();
                    handle_commands(); playback_notifications();
                }
            } catch (const std::exception &e) {
                ESP_LOGE(TAG, "Session failed: %s", e.what());
                set_state("connection_failed"); failed=true;
            }
            connected=false; paused=true; cb.end(); reset_audio();
            if (spirc) { spirc->disconnect(); spirc.reset(); }
            else if (ctx) ctx->session->close();
            ctx.reset();
            xQueueReset(commands); pause_requested=false; yield_requested=false;
            if (rejected) {
                // A fresh addUser can replace rejected or expired account credentials.
                erase_login();
                { std::lock_guard lock(blob_mutex); blob->authData.clear(); blob->username.clear(); }
                have_login=false;
            }
            if (failed && !forget) vTaskDelay(pdMS_TO_TICKS(5000));
        }
    }
};
static Player *player=nullptr;

static esp_err_t info_handler(httpd_req_t *r) {
    try {
        std::lock_guard lock(player->blob_mutex);
        if (!player->blob) return http_error(r, "503 Service Unavailable", "Spotify is starting");
        return send_json(r, player->blob->buildZeroconfInfo());
    } catch (...) { return http_error(r, "500 Internal Server Error", "Spotify info failed"); }
}
static esp_err_t login_handler(httpd_req_t *r) {
    try {
        auto form=spotify_parse_form(receive(r, 8192));
        if (form["action"]!="addUser" || form["userName"].empty() || form["userName"].size()>256 ||
            form["blob"].empty() || form["clientKey"].empty())
            return http_error(r, "400 Bad Request", "invalid addUser request");
        if (!player->configured) return http_error(r, "503 Service Unavailable", "Configure /spotify first");
        std::lock_guard lock(player->blob_mutex);
        if (!player->blob) return http_error(r, "503 Service Unavailable", "Spotify is starting");
        if (player->connected) {
            if (form["userName"]!=player->blob->username)
                return http_error(r, "409 Conflict", "Forget the previous account in /spotify first");
        } else {
            // A pending blob stays immutable until authentication completes.
            if (player->started && player->blob->authData.size())
                return http_error(r, "409 Conflict", "Login already pending; retry later");
            player->blob->loadZeroconfQuery(form);
            xSemaphoreGive(player->wake);
        }
        return send_json(r, "{\"status\":101,\"statusString\":\"OK\",\"spotifyError\":0}");
    } catch (const std::invalid_argument &) {
        return http_error(r, "400 Bad Request", "invalid login data");
    } catch (...) { return http_error(r, "500 Internal Server Error", "Spotify login failed"); }
}
static esp_err_t config_handler(httpd_req_t *r) {
    try {
        auto form=spotify_parse_form(receive(r, 512));
        if (!spotify_valid_client_key(form["client_id"]) || !spotify_valid_client_key(form["client_secret"]))
            return http_error(r, "400 Bad Request", "Client ID and Secret must be 32 hex characters");
        cJSON *json=cJSON_CreateObject();
        if (!json) return ESP_ERR_NO_MEM;
        cJSON_AddStringToObject(json,"client_id",form["client_id"].c_str());
        cJSON_AddStringToObject(json,"client_secret",form["client_secret"].c_str());
        char *encoded=cJSON_PrintUnformatted(json);
        cJSON_Delete(json);
        if (!encoded) return ESP_ERR_NO_MEM;
        esp_err_t err=save_string("app",encoded);
        free(encoded);
        if (err!=ESP_OK) return http_error(r,"500 Internal Server Error","Saving configuration failed");
        player->configured=true;
        xSemaphoreGive(player->wake);
        return send_json(r, "{\"configured\":true,\"restart_required\":true}");
    } catch (...) { return http_error(r, "400 Bad Request", "invalid configuration"); }
}
static esp_err_t status_handler(httpd_req_t *r) {
    std::lock_guard lock(player->state_mutex);
    cJSON *json=cJSON_CreateObject();
    if (!json) return ESP_ERR_NO_MEM;
    cJSON_AddStringToObject(json, "state", player->state.c_str());
    cJSON_AddBoolToObject(json, "configured", player->configured);
    cJSON_AddBoolToObject(json, "connected", player->connected);
    cJSON_AddBoolToObject(json, "paused", player->paused);
    cJSON_AddNumberToObject(json, "volume_percent", spotify_volume_percent());
    cJSON_AddStringToObject(json, "title", player->title.c_str());
    cJSON_AddStringToObject(json, "artist", player->artist.c_str());
    cJSON_AddStringToObject(json, "album", player->album.c_str());
    cJSON_AddNumberToObject(json, "duration_ms", player->duration);
    char *body=cJSON_PrintUnformatted(json);
    cJSON_Delete(json);
    if (!body) return ESP_ERR_NO_MEM;
    esp_err_t result=send_json(r, body); free(body);
    return result;
}
static esp_err_t forget_handler(httpd_req_t *r) {
    player->forget=true;
    xSemaphoreGive(player->wake);
    return send_json(r, "{\"accepted\":true}");
}
static esp_err_t page_handler(httpd_req_t *r) {
    static const char page[]=R"HTML(<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Spotify Connect</title>
<style>body{font:16px system-ui;max-width:600px;margin:40px auto;padding:20px}input,button{padding:10px;margin:8px 0;width:100%;box-sizing:border-box}pre{white-space:pre-wrap}</style>
<h1>Spotify Connect</h1><p>Spotify 개발자 앱의 Client ID와 Secret을 저장하세요. 저장된 값은 이 화면에 다시 표시하지 않습니다.</p>
<form id="config"><label>Client ID<input name="client_id" maxlength="32" required autocomplete="off"></label><label>Client Secret<input name="client_secret" type="password" maxlength="32" required autocomplete="off"></label><button>저장</button></form>
<p id="message"></p><button id="forget">연결된 Spotify 계정 잊기</button><pre id="status"></pre><p><a href="/">기기 설정</a></p>
<script>const msg=document.querySelector('#message');document.querySelector('#config').onsubmit=async e=>{e.preventDefault();try{let r=await fetch('/api/spotify/config',{method:'POST',body:new URLSearchParams(new FormData(e.target))});if(!r.ok)throw Error(await r.text());e.target.reset();msg.textContent='저장되었습니다. 설정 변경 후 보드를 재부팅하세요.'}catch(e){msg.textContent=e.message}};document.querySelector('#forget').onclick=async()=>{let r=await fetch('/api/spotify/forget',{method:'POST'});msg.textContent=r.ok?'계정 연결 해제 요청 완료. Spotify 앱에서 다시 선택하세요.':'연결 해제 실패'};async function status(){try{let r=await fetch('/api/spotify/status');document.querySelector('#status').textContent=JSON.stringify(await r.json(),null,2)}catch(e){msg.textContent='기기에 연결할 수 없습니다.'}}status();setInterval(status,2000);</script>)HTML";
    httpd_resp_set_type(r, "text/html; charset=utf-8");
    httpd_resp_set_hdr(r, "Cache-Control", "no-store");
    return httpd_resp_send(r, page, sizeof(page)-1);
}
extern "C" esp_err_t spotify_init(const char *name, const spotify_callbacks_t *callbacks) {
    if (player) return ESP_OK;
    try { bell::setDefaultLogger(); player=new Player(name, *callbacks); return ESP_OK; }
    catch (...) { return ESP_ERR_NO_MEM; }
}
extern "C" esp_err_t spotify_register_http(httpd_handle_t server) {
    if (!player) return ESP_ERR_INVALID_STATE;
    auto make_route=[](const char *uri, httpd_method_t method, esp_err_t (*handler)(httpd_req_t *)) {
        httpd_uri_t route={};
        route.uri=uri; route.method=method; route.handler=handler;
        return route;
    };
    const httpd_uri_t routes[]={
        make_route("/spotify", HTTP_GET, page_handler),
        make_route("/spotify_info", HTTP_GET, info_handler),
        make_route("/spotify_info", HTTP_POST, login_handler),
        make_route("/api/spotify/config", HTTP_POST, config_handler),
        make_route("/api/spotify/status", HTTP_GET, status_handler),
        make_route("/api/spotify/forget", HTTP_POST, forget_handler),
    };
    for (const auto &route : routes) {
        esp_err_t err=httpd_register_uri_handler(server, &route);
        if (err!=ESP_OK) return err;
    }
    return ESP_OK;
}
extern "C" esp_err_t spotify_start(uint16_t port) {
    if (!player) return ESP_ERR_INVALID_STATE;
    if (player->started.exchange(true)) return ESP_OK;
    mdns_txt_item_t txt[]={ {"VERSION","1.0"}, {"CPath","/spotify_info"}, {"Stack","SP"} };
    esp_err_t err=mdns_service_add(player->name.c_str(), "_spotify-connect", "_tcp", port, txt, 3);
    if (err!=ESP_OK) { player->started=false; return err; }
    esp_sntp_config_t clock = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    err = esp_netif_sntp_init(&clock);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        mdns_service_remove("_spotify-connect", "_tcp"); player->started=false; return err;
    }
    if (!player->startTask()) { mdns_service_remove("_spotify-connect", "_tcp"); player->started=false; return ESP_ERR_NO_MEM; }
    ESP_LOGI(TAG, "Spotify Connect discovery ready; settings at /spotify");
    return ESP_OK;
}
extern "C" void spotify_command(spotify_command_t command) { if (player) player->enqueue(command); }
extern "C" int spotify_volume_percent(void) { return player ? (player->volume*100+32767)/65535 : 0; }
