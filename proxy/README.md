# pyPowerwall Proxy Server

You can use pyPowerwall to proxy API requests to your Tesla Energy Gateway Powerwall. Because pyPowerwall is designed to cache the auth and high frequency API calls, this will reduce the load on the Gateway and prevent crash/restart issues that can happen if too many session are created on the Gateway.

## Setup

This folder contains the `server.py` script that runs a simple python based webserver that makes the pyPowerwall API calls.  

The `Dockerfile` here will allow you to containerize the proxy server for clean installation and running.

1. Build the Docker Container

    ```bash
    docker build -t pypowerwall:v1 .
    ```

2. Setup the Docker Container 

    ```bash
    docker run \
    -d \
    -p 8675:8675 \
    --name pypowerwall \
    --restart unless-stopped \
    pypowerwall:v1
    ```

3. Run the Docker Container

    ```bash
    docker start pypowerwall
    ```

4. Test the Proxy

    ```bash
    curl -i http://localhost:8675/soe
    curl -i http://localhost:8675/aggregates
    ```

## Troubleshooting Help

```bash
docker logs pypowerwall
```
