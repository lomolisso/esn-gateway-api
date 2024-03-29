from typing import Union
import json
from app.api import schemas
import copy
import requests
from app.config import (
    APP_BACKEND_URL,
    APP_BACKEND_JWT_TOKEN,
    EDGEX_FOUNDRY_CORE_METADATA_API_URL,
    EDGEX_FOUNDRY_CORE_COMMAND_API_URL,
    ESN_BLE_PROV_URL,
    ESN_PRED_NODE_URL,
    EDGEX_DEVICE_CONFIG_TEMPLATE_FILE,
)


# --- Cloud layer utils ---

def post_json_to_app_backend(endpoint: str, json_data: Union[dict, list]):
    # Sends a POST request to the app backend
    response = requests.post(
        url=f"{APP_BACKEND_URL}{endpoint}",
        json=json_data,
        headers={"Authorization": f"Bearer {APP_BACKEND_JWT_TOKEN}"},
    )
    if response.status_code != 200:
        raise Exception(f"API call failed. Status code: {response.status_code}")
    return response.json()


# --- Predictive node utils ---
def post_json_to_predictive_node(endpoint: str, json_data: Union[dict, list]):
    # Sends a POST request to the predictive node
    response = requests.post(
        url=f"{ESN_PRED_NODE_URL}{endpoint}",
        json=json_data,
    )
    if response.status_code != 200:
        raise Exception(f"API call failed. Status code: {response.status_code}")
    return response.json()

def check_prediction(prediction, measurement, **kwargs):
    pass

# --- Ble prov microservice utils ---

def get_wlan_iface_address():
    """
    Returns the MAC address of a given WLAN interface.
    """
    response = requests.get(url=f"{ESN_BLE_PROV_URL}/get-wlan-iface-address")

    if response.status_code != 200:
        raise Exception(
            f"Failed to retrieve wlan iface address from ble-prov microservice. Status code: {response.status_code}"
        )

    return response.json()["device_address"]


def discover_ble_devices():
    """
    Makes a GET request to the ble-prov microservice which returns
    a list of BLE devices obtained through a BLE discovery scan.
    """
    response = requests.get(url=f"{ESN_BLE_PROV_URL}/discover")

    if response.status_code != 200:
        raise Exception(
            f"Failed to retrieve BLEDevices from ble-prov microservice. Status code: {response.status_code}"
        )

    return response.json()


def provision_ble_devices(ble_devices: list[schemas.BLEDeviceWithPoP]):
    """
    Makes a POST request to the ble-prov microservice to provision
    a list of BLE devices.
    """
    ble_devices = [dev.model_dump() for dev in ble_devices]
    response = requests.post(
        url=f"{ESN_BLE_PROV_URL}/prov-device",
        json=ble_devices,
    )

    if response.status_code != 200:
        raise Exception(
            f"Failed to provision BLEDevices through the ble-prov microservice. Status code: {response.status_code}"
        )

    return response.json()


# --- EdgeX microservices utils ---

def _post_edgex_metadata_devices(devices):
    """
    Makes a POST request to EdgeX core-metadata API to create devices.
    """
    response = requests.post(
        url=f"{EDGEX_FOUNDRY_CORE_METADATA_API_URL}/device", json=devices
    )
    if response.status_code != 207:
        raise Exception(f"API call failed. Status code: {response.status_code}")

    # Check if all devices were created successfully
    device_names = [device["device"]["name"] for device in devices]
    device_addresses = [device["device"]["description"] for device in devices]
    dev_iterator = zip(device_names, device_addresses, response.json())

    _edgex_devices = []
    for dev_name, dev_address, dev_response in dev_iterator:
        if dev_response["statusCode"] != 201:
            raise Exception(
                f"Failed to create device {dev_name} in edgeX. Status code: {dev_response['statusCode']}"
            )

        _edgex_devices.append(
            schemas.EdgeXDeviceOut(
                device_name=dev_name,
                device_address=dev_address,
                edgex_device_uuid=dev_response["id"],
            )
        )
    return _edgex_devices


def upload_edgex_devices(devices):
    """
    Uploads to EdgeX core-metadata API the provided devices based on the
    device config template file.
    """
    # Load edgex device template for core metadata API
    with open(f"app/static/{EDGEX_DEVICE_CONFIG_TEMPLATE_FILE}", "r") as json_file:
        edgex_device_template = json.load(json_file)

    # Create edgex device config for each device
    edgex_devices_payload = []
    for device in devices:
        edgex_device = copy.deepcopy(edgex_device_template)
        edgex_device["device"]["name"] = device["device_name"]
        edgex_device["device"]["description"] = device["device_address"]
        edgex_device["device"]["protocols"]["mqtt"][
            "CommandTopic"
        ] = f"command/{device['device_name']}"
        edgex_devices_payload.append(edgex_device)

    return _post_edgex_metadata_devices(edgex_devices_payload)


def _run_edgex_device_set_command(device_name, command, payload):
    """
    Runs a SET command for a given device by making a PUT request
    to EdgeX core-command API. The payload must be a dict that
    includes the deviceResource name and the value to set.
    """
    response = requests.put(
        url=f"{EDGEX_FOUNDRY_CORE_COMMAND_API_URL}/device/name/{device_name}/{command}",
        json=payload,
    )
    if response.status_code != 200:
        raise Exception(
            f"Failed to execute the SET command on {device_name} through the EdgeX core command microservice. Status code: {response.status_code}"
        )

    return response.json()

# --- Redis private utils ---

async def _redis_enqueue_command(redis_client, device_name, command, params=None):
    """
    Enqueues a command for a given device by pushing it to the
    device's command queue.
    """
    queue_key = f"commands:queue:{device_name}"
    await redis_client.rpush(
        queue_key,
        json.dumps(
            {
                "command": command,
                "device_name": device_name,
                "params": params,
            }
        ),
    )


async def _redis_get_command_queue_len(redis_client, device_name):
    """
    Returns the length of the command queue for a given device.
    """
    queue_key = f"commands:queue:{device_name}"
    total_size = 0

    # Retrieve all commands in the queue without removing them
    all_commands = await redis_client.lrange(queue_key, 0, -1)
    return len(all_commands)


async def _redis_consume_command_queue(redis_client, device_name):
    """
    Consumes the command queue for a given device by popping the
    commands from the queue.
    """
    queue_key = f"commands:queue:{device_name}"
    commands = [
        json.loads(cmd.decode("utf-8"))
        for cmd in await redis_client.lrange(queue_key, 0, -1)
    ]
    await redis_client.ltrim(queue_key, 1, 0)
    for cmd in commands:
        _handle_command(
            command=cmd["command"],
            device_name=cmd["device_name"],
            params=cmd["params"],
        )


# --- Device commands private utils ---

def _handle_command(command, device_name, params=None):
    if command == "debug-prediction-command":
        _run_prediction_command(device_name, params)
    elif command == "device-predictive-model":
        _run_upload_devices_predictive_model_command(device_name, params)
    elif command == "device-config":
        _run_config_device_command(device_name, params)
    elif command == "state-machine-ready":
        _run_ready_device_command(device_name)
    elif command == "state-machine-start":
        _run_start_device_command(device_name)
    elif command == "state-machine-stop":
        _run_stop_device_command(device_name)
    elif command == "state-machine-reset":
        _run_reset_device_command(device_name)
    else:
        raise Exception(f"Unknown command: {command}")


def _run_upload_devices_predictive_model_command(device_name, params):
    """
    Updates the predictive model by setting the 'ml-model' deviceResource to true or false.
    """
    _payload = {
        "predictive-model-size": params["model_size"],
        "predictive-model-b64": params["b64_encoded_model"],
    }
    _run_edgex_device_set_command(
        device_name=device_name,
        command="device-predictive-model",
        payload={"device-predictive-model": _payload},
    )
    
def _run_prediction_command(device_name, params):
    _payload = {
        "pred-cmd-source-layer": params["prediction_source_layer"],
        "pred-cmd-request-timestamp": params["request_timestamp"],
        "pred-cmd-measurement": params["measurement"],
        "pred-cmd-prediction": params["prediction"],
    }
    _run_edgex_device_set_command(
        device_name=device_name,
        command="debug-prediction-command",
        payload={"debug-prediction-command": _payload},
    )

    
def _run_config_device_command(device_name, params):
    """
    Configures the devices by setting the 'ml-model' deviceResource to true or false.
    """
    _payload = {
        "config-measurement-interval-ms": params["measurement_interval_ms"],
    }
    _run_edgex_device_set_command(
        device_name=device_name,
        command="device-config",
        payload={
            "device-config": _payload,
        },
    )


def _run_ready_device_command(device_name):
    """
    Sets the 'state-machine-ready' deviceResource to true.
    """
    _run_edgex_device_set_command(
        device_name=device_name,
        command="state-machine-ready",
        payload={"state-machine-ready": "true"},
    )


def _run_start_device_command(device_name):
    """
    Starts a device by setting the 'state-machine-start' deviceResource to true.
    """
    _run_edgex_device_set_command(
        device_name=device_name,
        command="state-machine-start",
        payload={"state-machine-start": "true"},
    )


def _run_stop_device_command(device_name):
    """
    Stops a device by setting the 'state-machine-stop' deviceResource to false.
    """
    _run_edgex_device_set_command(
        device_name=device_name,
        command="state-machine-stop",
        payload={"state-machine-stop": "true"},
    )


def _run_reset_device_command(device_name):
    """
    Resets a device by setting the 'state-machine-reset' deviceResource to true.
    """
    _run_edgex_device_set_command(
        device_name=device_name,
        command="state-machine-reset",
        payload={"state-machine-reset": "true"},
    )
    
def _send_num_pending_commands(device_name, pending_commands):
    """
    Sets the 'response-pending-commands' deviceResource with the number of pending commands.
    """
    _run_edgex_device_set_command(
        device_name=device_name,
        command="response-pending-commands",
        payload={
            "response-pending-commands": pending_commands,
        },
    )


# --- Device commands public utils ---

async def upload_gateway_predictive_model(model_payload):
    """
    Sends a predictive model to the gateway predictive node
    """
    response = requests.post(
        url=f"{ESN_PRED_NODE_URL}/predictive-model",
        json=model_payload,
    )
    
    if response.status_code != 202:
        raise Exception(
            f"Failed to upload predictive model to the gateway predictive node. Status code: {response.status_code}"
        )
    
    return response.json()
        


async def retrieve_gateway_predictive_model(redis_client):
    """
    Retrieves the gateway model from redis
    """
    model = await redis_client.get("gateway-predictive-model")
    return json.loads(model)


async def upload_devices_predictive_model(redis_client, devices, model):
    """
    Enqueues a command for each device to update its predictive model.
    """ 
    for dev in devices:
        await _redis_enqueue_command(
            redis_client=redis_client,
            device_name=dev,
            command="device-predictive-model",
            params=model,
        )

async def prediction_command(redis_client, device_name, payload):
    await _redis_enqueue_command(
        redis_client=redis_client,
        device_name=device_name,
        command="debug-prediction-command",
        params=payload,
    )


async def config_devices(redis_client, devices, config):
    for dev in devices:
        await _redis_enqueue_command(
            redis_client=redis_client,
            device_name=dev,
            command="device-config",
            params=config,
        )


async def devices_ready(redis_client, devices):
    for dev in devices:
        await _redis_enqueue_command(
            redis_client=redis_client,
            device_name=dev,
            command="state-machine-ready",
        )


async def start_devices(redis_client, devices):
    for dev in devices:
        await _redis_enqueue_command(
            redis_client=redis_client,
            device_name=dev,
            command="state-machine-start",
        )


async def stop_devices(redis_client, devices):
    for dev in devices:
        await _redis_enqueue_command(
            redis_client=redis_client,
            device_name=dev,
            command="state-machine-stop",
        )


async def reset_devices(redis_client, devices):
    for dev in devices:
        await _redis_enqueue_command(
            redis_client=redis_client,
            device_name=dev,
            command="state-machine-reset",
        )


async def pending_commands(redis_client, device_name):
    """
    First sends the number of pending commands of a device, then
    consumes the command queue.
    """
    queue_size = await _redis_get_command_queue_len(
        redis_client=redis_client, device_name=device_name
    )
    _send_num_pending_commands(device_name=device_name, pending_commands=queue_size)

    if queue_size > 0:
        await _redis_consume_command_queue(redis_client=redis_client, device_name=device_name)
