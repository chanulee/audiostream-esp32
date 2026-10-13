#include "form_codec.h"
#include <cassert>
#include <stdexcept>
#include <cstdio>
int main() {
    auto form=spotify_parse_form("action=addUser&userName=a%26b&blob=x%2By%3D&clientKey=a+b");
    assert(form["userName"]=="a&b" && form["blob"]=="x+y=" && form["clientKey"]=="a b");
    for (auto bad : {"a=%", "a=%zz", "a=%00", "missing_equals", "=value", "a=1&a=2", "a=1&broken"}) {
        bool rejected=false;
        try { spotify_parse_form(bad); } catch(const std::invalid_argument &) { rejected=true; }
        assert(rejected);
    }
    assert(spotify_valid_client_key("0123456789abcdef0123456789ABCDEF"));
    assert(!spotify_valid_client_key("secret"));
    assert(!spotify_valid_client_key("0123456789abcdef0123456789abcdeg"));
    puts("Spotify form trust-boundary tests passed");
}
