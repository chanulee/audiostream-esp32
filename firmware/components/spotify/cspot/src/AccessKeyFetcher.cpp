#include "AccessKeyFetcher.h"

#include <cstring>           // for strrchr
#include <initializer_list>  // for initializer_list
#include <map>               // for operator!=, operator==
#include <type_traits>       // for remove_extent_t
#include <vector>            // for vector

#include "BellLogger.h"    // for AbstractLogger
#include "BellUtils.h"     // for BELL_SLEEP_MS
#include "CSpotContext.h"  // for Context
#include "HTTPClient.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include <stdexcept>
#include "Logger.h"            // for CSPOT_LOG
#include "MercurySession.h"    // for MercurySession, MercurySession::Res...
#include "NanoPBExtensions.h"  // for bell::nanopb::encode...
#include "NanoPBHelper.h"      // for pbEncode and pbDecode
#include "Packet.h"            // for cspot
#include "TimeProvider.h"      // for TimeProvider
#include "Utils.h"             // for string_format

#ifdef BELL_ONLY_CJSON
#include "cJSON.h"
#else
#include "nlohmann/json.hpp"      // for basic_json<>::object_t, basic_json
#include "nlohmann/json_fwd.hpp"  // for json
#endif

using namespace cspot;

static std::string SCOPES =
    "streaming,user-library-read,user-library-modify,user-top-read,user-read-"
    "recently-played";  // Required access scopes

AccessKeyFetcher::AccessKeyFetcher(std::shared_ptr<cspot::Context> ctx)
    : ctx(ctx) {}

bool AccessKeyFetcher::isExpired() {
  if (accessKey.empty()) {
    return true;
  }

  if (ctx->timeProvider->getSyncedTimestamp() > expiresAt) {
    return true;
  }

  return false;
}

std::string AccessKeyFetcher::getAccessKey() {
  if (!isExpired()) {
    return accessKey;
  }

  updateAccessKey();

  return accessKey;
}

void AccessKeyFetcher::updateAccessKey() {
  if (keyPending) return;
  keyPending = true;
  try {
    auto body = "grant_type=client_credentials&client_id=" + ctx->config.clientId +
                "&client_secret=" + ctx->config.clientSecret;
    esp_http_client_config_t config = {};
    config.url = "https://accounts.spotify.com/api/token";
    config.method = HTTP_METHOD_POST;
    config.timeout_ms = 15000;
    config.crt_bundle_attach = esp_crt_bundle_attach;
    auto client = esp_http_client_init(&config);
    if (!client) throw std::bad_alloc();
    struct Cleanup { esp_http_client_handle_t client; ~Cleanup() { esp_http_client_cleanup(client); } } cleanup{client};
    esp_http_client_set_header(client, "Content-Type", "application/x-www-form-urlencoded");
    if (esp_http_client_open(client, body.size()) != ESP_OK)
      throw std::runtime_error("Spotify token connection failed");
    size_t sent = 0;
    while (sent < body.size()) {
      int n = esp_http_client_write(client, body.data() + sent, body.size() - sent);
      if (n <= 0) throw std::runtime_error("Spotify token request failed");
      sent += n;
    }
    if (esp_http_client_fetch_headers(client) < 0 || esp_http_client_get_status_code(client) != 200)
      throw std::runtime_error("Spotify token rejected; check developer app credentials");
    char response[4096];
    int bytes = esp_http_client_read_response(client, response, sizeof(response));
    cJSON *json = bytes > 0 ? cJSON_ParseWithLength(response, bytes) : nullptr;
    struct JsonCleanup { cJSON *json; ~JsonCleanup() { cJSON_Delete(json); } } jsonCleanup{json};
    auto token = cJSON_GetObjectItemCaseSensitive(json, "access_token");
    auto expires = cJSON_GetObjectItemCaseSensitive(json, "expires_in");
    if (!cJSON_IsString(token) || !token->valuestring[0] || !cJSON_IsNumber(expires) || expires->valueint <= 0)
      throw std::runtime_error("Invalid Spotify token response");
    accessKey = token->valuestring;
    expiresAt = ctx->timeProvider->getSyncedTimestamp() + (static_cast<uint64_t>(expires->valueint) * 1000) - 30000;
    keyPending = false;
  } catch (...) { keyPending = false; throw; }
}
