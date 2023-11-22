# Decode /tedapi API Payloads

This tool is to help decode `/tedapi` API payloads (requests and responses) using a Protobuf schema definition file [tedapi.proto](tedapi.proto).

## Tool

```bash
# Build python bindings for protobuf schema - tedapi_pb2.py
protoc --python_out=. tedapi.proto

# Decode payload
python decode.py <filename>
```

## Background

* This requires using the gateway WiFi access point (for PW2/+ systems this is TEG-xxx and for PW3 it is TeslaPW_xxx) and the https://192.168.91.1 endpoint. It seems that this is required for the /tedapi endpoints (LAN or other access results in "User does not have adequate access rights" 403 Error)
* The /tedapi API calls are using binary Protocol Buffers ([protobuf](https://protobuf.dev/)) payloads.

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

An example response shows the system config data in the JSON `text` (removed to protect the innocent) and a `code` payload (TBD).

```
message {
  head: 1
  response {
    din: "1232100-00-E--TG123456789012"
  }
  request {
    value: 1
  }
  config {
    recv {
      file {
        name: "config.json"
        text: "{...JSON Payload Removed...}"
      }
      code: "...Binary Data Removed..."
    }
  }
}
tail {
  value: 1
}
```

#### QUERY Example

To get the status of the Powerwall, send a binary query.bin payload. The structure of the query payload has a `text` query string that seems to be an exhaustive list of labels.  The `code` field is a binary payload.

```
message {
  head: 1
  response {
    value: 1
  }
  request {
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

```bash
# Request Status Data from Powerwall
curl -v -k -H 'Content-type: application/octet-string' -u "Tesla_Energy_Device:GW_PWD" --data-binary @query.bin https://192.168.91.1/tedapi/v1 > response.bin

# Decode Config Data
python3 decode.py response.bin
```

An example response shows the system status data in the JSON `text` field (truncated).

```
message {
  head: 1
  response {
    din: "1232100-00-E--TG121048001E4G"
  }
  request {
    value: 1
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
