#pragma once
#include <map>
#include <string>
#include <string_view>
std::map<std::string, std::string> spotify_parse_form(std::string_view body);
bool spotify_valid_client_key(std::string_view key);
