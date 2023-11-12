import os
from dotenv import load_dotenv

# Retrieve enviroment variables from .env file
load_dotenv()

SECRET_KEY: str = os.environ.get("SECRET_KEY")
APP_BACKEND_URL = os.environ.get("APP_BACKEND_URL")
TIMEZONE = os.environ.get("TIMEZONE", "Chile/Continental")

EDGE_GATEWAY_BLE_IFACE = os.getenv("EDGE_GATEWAY_BLE_IFACE")
EDGE_GATEWAY_WLAN_IFACE = os.getenv("EDGE_GATEWAY_WLAN_IFACE")
EDGE_GATEWAY_WIFI_SSID = os.getenv("EDGE_GATEWAY_WIFI_SSID")
EDGE_GATEWAY_WIFI_PASSPHRASE = os.getenv("EDGE_GATEWAY_WIFI_PASSPHRASE")
EDGE_GATEWAY_DEVICE_NAME = os.getenv("EDGE_GATEWAY_DEVICE_NAME")
EDGE_GATEWAY_POP_KEYWORD = os.getenv("EDGE_GATEWAY_POP_KEYWORD")

EDGE_SENSOR_SERVICE_NAME_PREFIX = os.getenv("EDGE_SENSOR_SERVICE_NAME_PREFIX", "ESP32_")
EDGE_SENSOR_POP_KEYWORD = os.getenv("EDGE_SENSOR_POP_KEYWORD")
EDGE_SENSOR_OUI = os.getenv("EDGE_SENSOR_OUI", "B0:A7:32")

EDGEX_FOUNDRY_CORE_METADATA_API_URL = os.getenv("EDGEX_FOUNDRY_CORE_METADATA_API_URL")
EDGEX_FOUNDRY_CORE_COMMAND_API_URL = os.getenv("EDGEX_FOUNDRY_CORE_COMMAND_API_URL")
EDGEX_DEVICE_PROFILE_FILE = os.getenv("EDGEX_DEVICE_PROFILE_FILE", "device-profile.yaml")
EDGEX_DEVICE_CONFIG_TEMPLATE_FILE = os.getenv("EDGEX_DEVICE_CONFIG_TEMPLATE_FILE", "edgex-device-config-template.json")

APP_BACKEND_JWT_TOKEN = os.getenv("APP_BACKEND_JWT_TOKEN")

ORIGINS: list = [
    APP_BACKEND_URL,
]