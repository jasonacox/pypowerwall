# pyPowerwall Proxy Server

You can use pyPowerwall to proxy API requests to your Tesla Energy Gateway Powerwall. Because pyPowerwall is designed to cache the auth and high frequency API calls, this will reduce the load on the Gateway and prevent crash/restart issues that can happen if too many session are created on the Gateway.

## Setup

This folder contains the `server.py` script that runs a simple python based webserver that makes the pyPowerwall API calls.  

The `Dockerfile` here will allow you to containerize the proxy server for clean installation and running.

1. Build the Docker Container

    ```bash
    docker build -t pypowerwall:latest .
    ```

2. Setup the Docker Container to listen on port 8675

    ```bash
    docker run \
    -d \
    -p 8675:8675 \
    --name pypowerwall \
    --restart unless-stopped \
    -v `pwd`:/app \
    pypowerwall
    ```

3. Test the Proxy

    ```bash
    curl -i http://localhost:8675/soe
    curl -i http://localhost:8675/aggregates
    ```

## Troubleshooting Help

Check the logs: 

```bash
# See the logs
docker logs pypowerwall
```

If you see python errors, make sure you entered your credentials correctly in the `server.py` file.  If you didn't, edit that file and restart docker:

```bash
# Stop the server
docker stop pypowerwall

# Start the server
docker start pypowerwall
```
