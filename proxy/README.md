# pyPowerwall Proxy Server

![Docker Pulls](https://img.shields.io/docker/pulls/jasonacox/pypowerwall)

This pyPowerwall Caching Proxy handles authentication to the Powerwall Gateway and will proxy API calls to /api/meters/aggregates (power metrics), /api/system_status/soe (battery level), and many others (see [HELP](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md) for full list). With the instructions below, you can containerize this proxy and run it as an endpoint for tools like telegraf to pull metrics without needing to authenticate.

Because pyPowerwall is designed to cache the auth and high frequency API calls, this will reduce the load on the Gateway and prevent crash/restart issues that can happen if too many session are created on the Gateway.

Docker: docker pull [jasonacox/pypowerwall](https://hub.docker.com/r/jasonacox/pypowerwall)

## Quick Start

1. Run the Docker Container to listen on port 8675. Update the `-e` values for your Powerwall.

    ```bash
    docker run \
    -d \
    -p 8675:8675 \
    -e PW_PASSWORD='password' \
    -e PW_EMAIL='email@example.com' \
    -e PW_HOST='localhost' \
    -e PW_TIMEZONE='America/Los_Angeles' \
    -e PW_CACHE_EXPIRE='5' \
    -e PW_DEBUG='no' \
    --name pypowerwall \
    --restart unless-stopped \
    jasonacox/pypowerwall
    ```

2. Test the Proxy

    ```bash
    # Get Powerwall Data
    curl -i http://localhost:8675/soe
    curl -i http://localhost:8675/aggregates
    curl -i http://localhost:8675/vitals
    curl -i http://localhost:8675/strings

    # Get Proxy Stats
    curl -i http://localhost:8675/stats

    # Clear Proxy Stats
    curl -i http://localhost:8675/stats/clear
    ```

## Build Your Own

This folder contains the `server.py` script that runs a simple python based webserver that makes the pyPowerwall API calls.  

The `Dockerfile` here will allow you to containerize the proxy server for clean installation and running.

1. Build the Docker Container

    ```bash
    # Build for local architecture  
    docker build -t pypowerwall:latest .

    # Build for all architectures - requires Docker experimental 
    docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t pypowerwall:latest . 

    ```

2. Setup the Docker Container to listen on port 8675.

    ```bash
    docker run \
    -d \
    -p 8675:8675 \
    --name pypowerwall \
    --restart unless-stopped \
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
