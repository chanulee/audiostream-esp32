idf_component_register(
    SRC_DIRS "esp32-generic" "."
    INCLUDE_DIRS "esp32-generic" "."
    REQUIRES esp_driver_i2c board_utils
    PRIV_REQUIRES driver dac main
)
