# pyPowerwall Proxy Server

![Docker Pulls](https://img.shields.io/docker/pulls/jasonacox/pypowerwall)

This pyPowerwall Caching Proxy handles authentication to the Powerwall Gateway and will proxy API calls to /api/meters/aggregates (power metrics), /api/system_status/soe (battery level), and many others (see [HELP](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md) for full list). With the instructions below, you can containerize this proxy and run it as an endpoint for tools like telegraf to pull metrics without needing to authenticate.

Because pyPowerwall is designed to cache the auth and high frequency API calls, while also utilising HTTP persistent connections, this will reduce the load on the Gateway and prevent crash/restart issues that can happen if too many session are created on the Gateway.

Docker: docker pull [jasonacox/pypowerwall](https://hub.docker.com/r/jasonacox/pypowerwall)

## Quick Start

1. Run the Docker Container to listen on port 8675. Update the `-e` values for your Powerwall (see [Environmental Settings](https://github.com/jasonacox/pypowerwall/tree/main/proxy#environmental-settings) for options):

    ```bash
    docker run \
    -d \
    -p 8675:8675 \
    -e PW_PORT='8675' \
    -e PW_PASSWORD='password' \
    -e PW_EMAIL='email@example.com' \
    -e PW_HOST='IP_of_Powerwall_Gateway' \
    -e PW_TIMEZONE='America/Los_Angeles' \
    -e TZ='America/Los_Angeles' \
    -e PW_CACHE_EXPIRE='5' \
    -e PW_DEBUG='no' \
    -e PW_HTTPS='no' \
    -e PW_STYLE='clear' \
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

## Browser Cache Control

By default resources sent for the power flow animation passthrough are not cached by the browser.  This includes fairly large CSS, JavaScript and Image PNG files which are downloaded every time the browser reloads the animation.  Performance can be improved by directing the web browser to cache these resources locally - only reloading if the data in the cache is old, a period known as `max-age`.

You can control this with an optional environment variable `PW_BROWSER_CACHE` which takes a value in seconds. For example,

* PW_BROWSER_CACHE=86400 - set `max-age` to 24 hours.

If `PW_BROWSER_CACHE` is not set, or set to zero, then no caching takes place.  If you need to force a reload of the browser cache before `max-age` then most browsers will do this if you hold down the `shift` key while reloading the page.

## HTTPS Support (Experimental)

The Proxy now supports https protocol using the optional environmental variable `PW_HTTPS`. This is useful for placing data in secured iFrame, including the power flow animation available via the Powerwall portal (https://localhost:8675/).

There are three settings for PW_HTTPS:

* PW_HTTPS='no' - This is default - run in HTTP mode only.
* PW_HTTPS='http' - Run in HTTP mode but simulate HTTPS when behind https proxy.
* PW_HTTPS='yes' - Run in HTTPS mode using self-signed certificate.

## Troubleshooting Help

If you see python errors, make sure you entered your credentials correctly in `docker run`.

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

## API Help

Documentation for using the API is located in [HELP.md](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md#release-notes).

## Environmental Settings

The pyPowerwall Proxy will react to the following environmental variables with (defaults):

Powerwall Settings

* PW_PASSWORD - Powerwall customer password ("password")
* PW_EMAIL - Powerwall customer email ("email@example.com")
* PW_HOST - Powerwall hostname or IP address ("hostname")
* PW_TIMEZONE - Local timezone ("America/Los_Angeles")

Proxy Settings

* PW_BIND_ADDRESS - IP address ("") - Required
* PW_PORT - TCP port ("8675")
* PW_DEBUG - Turn on debug logging ("no")
* PW_CACHE_EXPIRE - Time to cache responses from Powerwall in sec ("5")
* PW_BROWSER_CACHE - Sets Cache-Control for browser in sec ("0" = no-cache)
* PW_TIMEOUT - Timeout waiting for Powerwall to respond in sec ("10")
* PW_POOL_MAXSIZE - Concurrent connections to Powerwall ("15")
* PW_HTTPS - Set https mode - see HTTPS section above ("no")
* PW_STYLE - Background color style for iframe [animation](http://localhost:8675/example.html) ("clear") - options:
    * clear (uses 'transparent')
    * black or dakboard (uses `#000` ![#000](https://via.placeholder.com/12/000/000000.png?text=+))
    * white (uses `#ffffff` ![#ffffff](https://via.placeholder.com/12/ffffff/000000.png?text=+))
    * grafana (uses `#161719` ![#161719](https://via.placeholder.com/12/161719/000000.png?text=+))
    * grafana-dark (uses `#111217` ![#111217](https://via.placeholder.com/12/111217/000000.png?text=+))

## Release Notes

Release notes are in the [RELEASE.md](https://github.com/jasonacox/pypowerwall/blob/main/proxy/RELEASE.md) file.
