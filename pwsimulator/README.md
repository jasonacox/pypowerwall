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
    export PW_PASSWORD="password"
    export PW_EMAIL="me@example.com"
    export PW_DEBUG="yes"
    python3 proxy/server.py
    # Open http://localhost:8675/example.html
    ```

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
