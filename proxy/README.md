# pyPowerwall Proxy Server

![Docker Pulls](https://img.shields.io/docker/pulls/jasonacox/pypowerwall)

This pyPowerwall Caching Proxy handles authentication to the Powerwall Gateway and will proxy API calls to /api/meters/aggregates (power metrics), /api/system_status/soe (battery level), and many others (see [HELP](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md) for full list). With the instructions below, you can containerize this proxy and run it as an endpoint for tools like telegraf to pull metrics without needing to authenticate.

Because pyPowerwall is designed to cache the auth and high frequency API calls, while also utilising HTTP persistent connections, this will reduce the load on the Gateway and prevent crash/restart issues that can happen if too many session are created on the Gateway.

Docker: docker pull [jasonacox/pypowerwall](https://hub.docker.com/r/jasonacox/pypowerwall)

## Quick Start

1. Run the Docker Container to listen on port 8675. Update the `-e` values for your Powerwall.

    ```bash
    docker run \
    -d \
    -p 8675:8675 \
    -e PW_PORT='8675' \
    -e PW_PASSWORD='password' \
    -e PW_EMAIL='email@example.com' \
    -e PW_HOST='localhost' \
    -e PW_TIMEZONE='America/Los_Angeles' \
    -e PW_CACHE_EXPIRE='5' \
    -e PW_DEBUG='no' \
    -e PW_HTTPS='no' \
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

    Browse to http://localhost:8675/ to see Powerwall web interface.

## Power Flow Animation - Passthrough

The Proxy will pass authenticated calls through to the Powerwall Web Interface allowing the display of the Power Flow Animation:

[![flow.png](https://raw.githubusercontent.com/jasonacox/pypowerwall/main/docs/flow.png)](https://raw.githubusercontent.com/jasonacox/pypowerwall/main/docs/flow.png)

This is available by directly accessing the proxy endpoint, https://localhost:8675 (replace localhost with the address of host running pyPowerwall Proxy). You can embed this animation within an iFrame. See [web/example.html](web/example.html).

## HTTPS Support (Experimental)

The Proxy now supports https protocol using the optional environmental variable `PW_HTTPS`. This is useful for placing data in secured iFrame, including the power flow animation available via the Powerwall portal (https://localhost:8675/).

There are three settings for PW_HTTPS:

* PW_HTTPS='no' - This is default - run in HTTP mode only.
* PW_HTTPS='http' - Run in HTTP mode but simulate HTTPS when behind https proxy.
* PW_HTTPS='yes' - Run in HTTPS mode using self-signed certificate.

## Troubleshooting Help

Check the logs. If you see python errors, make sure you entered your credentials correctly in the `server.py` file.  If you didn't, edit that file and restart docker:

```bash
# See the logs
docker logs pypowerwall

# Stop the server
docker stop pypowerwall

# Start the server
docker start pypowerwall
```

Content does not render in iFrame or prompts you for a login:

* Browser may be set to never accept third party cookies. The web app requires cookies and in an iFrame it will look like a third party, [see here](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB#security)).
* iFrame doesn't render.  Make sure the browser is not running in incognito mode.  Try other browsers.

## Release Notes

Release notes are included in the [HELP documentation here](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md#release-notes).
