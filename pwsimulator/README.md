# pyPowerwall Simulator

![Docker Pulls](https://img.shields.io/docker/pulls/jasonacox/pwsimulator)

You can use pyPowerwall simulator to mimic the responses from the Powerwall Gateway. This is useful for testing purposes.

## Quick Start

1. Run the Docker Container to listen on port 443 (https) - pulls from Docker Hub

    ```bash
    docker run \
    -d \
    -p 443:443 \
    --name pwsimulator \
    --restart unless-stopped \
    jasonacox/pwsimulator
    ```

2. Test using the [test.py](test.py) script set to use localhost as the Powerwall

    ```bash
    python3 test.py
    ```

3. Test using the pypowerwall proxy against the simulator:

    ```bash
    # Launch Proxy
    cd ..
    PW_HOST=localhost \
    PW_PASSWORD=password \
    PW_EMAIL=me@example.com \
    PW_DEBUG=yes python3 proxy/server.py

    # Open http://localhost:8675/example.html
    ```

4. Change simulated values using [https://localhost/test/](https://localhost/test/).

## Build Your Own

1. Build the Docker Container

    ```bash
    docker build -t pwsimulator:latest .
    ```

2. Setup the Docker Container to listen on port 443 (https)

    ```bash
    docker run \
    -d \
    -p 443:443 \
    --name pwsimulator \
    --restart unless-stopped \
    pwsimulator
    ```

3. Test the Proxy

    ```bash
    bash test.sh
    ```

## Troubleshooting Help

Check the logs: 

```bash
# See the logs
docker logs pwsimulator
```

If you see python errors, make sure you entered your credentials correctly in the `stub.py` file.  If you didn't, edit that file and restart docker:

```bash
# Stop the server
docker stop pypowerwall

# Start the server
docker start pypowerwall
```

## Test Commands

### TEDAPI Endpoints (Powerwall 3)

The simulator now supports TEDAPI endpoints used by Powerwall 3 systems:

#### Get DIN (Device Identification Number)
```bash
curl -k https://localhost/tedapi/din
```

#### Get Configuration
```bash
# Post a small protobuf request to get config.json
curl -k -X POST https://localhost/tedapi/v1 \
  --user Tesla_Energy_Device:ABCDEFGHIJ \
  -H "Content-Type: application/octet-stream" \
  --data-binary @- << EOF
test
EOF
```

#### Get Status
```bash
# Post a larger protobuf request to get status data
python3 test_tedapi.py
```

The simulator intelligently returns config or status data based on the request size:
- Small requests (< 100 bytes) return configuration data
- Larger requests return status/controller data

### Battery
Full: `curl -k https://localhost/test/battery-percentage/100.0`
Empty: `curl -k https://localhost/test/battery-percentage/0.0`

### Grid
Toggle Grid Connection: `curl -k https://localhost/test/toggle-grid`

### Solar
Zero solar: `curl -k https://localhost/test/solar-power/0`
Some solar: `curl -k https://localhost/test/solar-power/1450`

### Scenarios
This script includes some sample scenarios to cover common use cases

```sh
# Flow Scenarios
curl -k http://localhost/test/scenario/battery-exporting
curl -k http://localhost/test/scenario/solar-exporting
curl -k http://localhost/test/scenario/solar-powered
curl -k http://localhost/test/scenario/grid-powered
curl -k http://localhost/test/scenario/self-powered
curl -k http://localhost/test/scenario/battery-powered
curl -k http://localhost/test/scenario/grid-charging
curl -k http://localhost/test/scenario/solar-charging

# Outages
curl -k http://localhost/test/scenario/sunny-day-outage
curl -k http://localhost/test/scenario/cloudy-day-outage
curl -k http://localhost/test/scenario/nighttime-outage
```

## Powerwall Scenario Simulator

Thanks to @mccahan, there is an external UI that can be used to manage the Simulator while also watching the Power Flow Animation udpates. This can be installed with:

```bash
docker run --rm -p 3000:3000 mccahan/pypowerwall-simulator-control:latest

# Open http://localhost:3000
```

<img width="800" alt="image" src="https://github.com/user-attachments/assets/027674b0-f1ca-4363-9162-5f5f7be351ff" />
