# Decode /tedapi API Payloads

The Tesla Powerwall Gateway has an installer API accessible via the Gateway WiFi. This endpoint includes an API `/tedapi` that is used to setup and monitor the Powerwall. 

The API includes configuration and status payloads that use a simple Protobuf schema definition file [tedapi.proto](tedapi.proto). Accessing this API requires the Gateway Password (usually found on the QR code inside the Powerwall access panel)

## Usage

The [tedapi.py](tedapi.py) script includes a TEDAPI class and runtime tool that will fetch and save the configuration settings and current live status in `config.json` and `status.json` files:

```bash
# Download 
git clone https://github.com/jasonacox/pypowerwall.git
cd pypowerwall/tools/tedapi

# Install required dependencies
pip install protobuf requests

# Get configuration and status
python tedapi.py

# Simple Test Proxy 
python web.py <gateway_password>

# Web API http://localhost:4444
#    GET /din - Returns the Powerwall Gateway DIN number
#    GET /config - Returns the Powerwall Gateway configuration
#    GET /status - Returns the Powerwall Gateway status
```

## Background

* This requires using the gateway WiFi access point (for PW2/+ systems this is TEG-xxx and for PW3 it is TeslaPW_xxx) and the https://192.168.91.1 endpoint. It seems that this is required for the /tedapi endpoints (LAN or other access results in "User does not have adequate access rights" 403 Error)
* The /tedapi API calls are using binary Protocol Buffers ([protobuf](https://protobuf.dev/)) payloads.

The protobuf python bindings were created using this:
```bash
# Build python bindings for protobuf schema - tedapi_pb2.py
protoc --python_out=. tedapi.proto
```

## Research Details

The [decode.py](decode.py) scrip will use the tedapi protobuf schema to decode a specified payload. This is useful for troubleshooting and downloading payloads with curl.

```bash
# Decode payload file
python decode.py <filename>
```

## APIs

### GET /tedapi/din

This API fetches the Powerwall DIN (device identification number). It uses basic auth that appears to be: Tesla_Energy_Device:GW_PWD where the GW_PWD is the password near the QR code on the Powerwall that you scan with the Tesla Pros app.

```bash
curl -v -k -u "Tesla_Energy_Device:GW_PWD"" https://192.168.91.1/tedapi/din
```

It only returns a simple string that contains the DIN:

```
1232100-00-E--TG123456789012
```

### POST /tedapi/v1

This appears to be the workhorse function. It uses basic auth that appears to be: `Tesla_Energy_Device:GW_PWD` where the GW_PWD is the password near the QR code on the Powerwall that you scan with the Tesla Pros app.

```bash
curl -v -k -H 'Content-type: application/octet-string' -u "Tesla_Energy_Device:GW_PWD" --data-binary @request.bin https://192.168.91.1/tedapi/v1
```

Payloads are binary Protocol Buffers (protobufs). 

* The [decode.py](decode.py) tool will help decode this using the proto file.
* Or you can use `protoc --decode_raw < v1_request` to decode the raw response.

There appear to be different types of request sent. One is for `config` which gets a payload that contains the configuration of the Powerwall. Another is for `query` that gets current data (e.g. systemStatus, realPowerW, voltages, frequencies, etc.).

#### CONFIG Example

```bash
# Request Config Data from Powerwall
curl -v -k -H 'Content-type: application/octet-string' -u "Tesla_Energy_Device:GW_PWD" --data-binary @request.bin https://192.168.91.1/tedapi/v1 > response.bin

# Decode Config Data
python3 decode.py response.bin
```

The request payload set the recipient din:

```
message {
  deliveryChannel: 1
  sender {
    local: 1
  }
  recipient {
    din: "1232100-00-E--TG123456789012"
  }
  config {
    send {
      num: 1
      file: "config.json"
    }
  }
}
tail {
  value: 1
}
```

An example response shows the system config data in the JSON `text` (removed to protect the innocent) and a `code` payload (TBD).

```
message {
  deliveryChannel: 1
  sender {
    din: "1232100-00-E--TG123456789012"
  }
  recipient {
    local: 1
  }
  config {
    recv {
      file {
        name: "config.json"
        text: "{\"vin\":\"1232100-00-E--TG123456789012\",\"meters\": ...Truncated... }"
      }
      code: "\255\177t+5\3530...Truncated..."
    }
  }
}
tail {
  value: 1
}
```

#### QUERY Example

```bash
# Request Status Data from Powerwall
curl -v -k -H 'Content-type: application/octet-string' -u "Tesla_Energy_Device:GW_PWD" --data-binary @query.bin https://192.168.91.1/tedapi/v1 > response.bin

# Decode Config Data
python3 decode.py response.bin
```

To get the status of the Powerwall, send a binary query.bin payload. The structure of the query payload has a `text` query string that seems to be an exhaustive list of labels.  The `code` field is a binary payload.

```
message {
  deliveryChannel: 1
  sender {
    local: 1
  }
  recipient {
    din: "1232100-00-E--TG123456789012"
  }
  payload {
    send {
      num: 2
      payload {
        value: 1
        text: " query DeviceControllerQuery {\n  control {\n    systemStatus {\n        nominalFullPackEnergyWh...Truncated..."
      }
      code: "0\201\210...Truncated..."
      b {
        value: "{}"
      }
    }
  }
}
tail {
  value: 1
}
```

An example response shows the system status data in the JSON `text` field (truncated).

```
message {
  deliveryChannel: 1
  sender {
    din: "1232100-00-E--TG123456789012"
  }
  recipient {
    local: 1
  }
  payload {
    recv {
      value: 1
      text: "{\"control\":{\"alerts\":{\"active\":[\"SystemConnectedToGrid\",\"FWUpdateSucceeded\",\"GridCodesWrite\",\"PodCommissionTime\"]},\"batteryBlocks\":[{\"din\":\"2012170-25-E#TG123456789012\", ...Truncated...\"updateUrgencyCheck\":null}}"
    }
  }
}
tail {
  value: 1
}
```


## Credit

* Thanks to [zigam](https://github.com/zigam) for starting this research and the initial discovery, [post](https://github.com/jrester/tesla_powerwall/issues/20#issuecomment-1810848383) and tips.
* Thanks to [jesaf00](https://github.com/jesaf00) for opening the [Powerwall 3 Support issue](https://github.com/jasonacox/Powerwall-Dashboard/issues/387) and help testing.
* Thanks to others helping test: [longzheng](https://github.com/longzheng) [pbburkhalter](https://github.com/pbburkhalter) [stevecastaneda](https://github.com/stevecastaneda) 
