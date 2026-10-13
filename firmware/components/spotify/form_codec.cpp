#include "form_codec.h"
#include <stdexcept>
static int hex(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
static std::string decode(std::string_view s) {
    std::string result;
    for (size_t i = 0; i < s.size(); i++) {
        char c = s[i];
        if (c == '+') c = ' ';
        else if (c == '%') {
            if (i + 2 >= s.size() || hex(s[i+1]) < 0 || hex(s[i+2]) < 0)
                throw std::invalid_argument("invalid percent encoding");
            c = static_cast<char>((hex(s[i+1]) << 4) | hex(s[i+2]));
            i += 2;
        }
        if (!c) throw std::invalid_argument("NUL in form");
        result += c;
    }
    return result;
}
std::map<std::string, std::string> spotify_parse_form(std::string_view body) {
    std::map<std::string, std::string> result;
    while (!body.empty()) {
        size_t amp = body.find('&');
        auto item = body.substr(0, amp);
        size_t eq = item.find('=');
        if (eq == std::string_view::npos || !eq)
            throw std::invalid_argument("invalid form field");
        auto key = decode(item.substr(0, eq));
        if (!result.emplace(key, decode(item.substr(eq+1))).second)
            throw std::invalid_argument("duplicate form field");
        if (amp == std::string_view::npos) break;
        body.remove_prefix(amp+1);
    }
    return result;
}
bool spotify_valid_client_key(std::string_view key) {
    if (key.size() != 32) return false;
    for (char c : key) if (hex(c) < 0) return false;
    return true;
}
