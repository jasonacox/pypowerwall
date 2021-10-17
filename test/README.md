# pyPowerwall Simulator

You can use pyPowerwall simulator to mimic the responses from the Powerwall Gateway. This is useful for testing purposes.

## Setup

1. Build the Docker Container

    ```bash
    docker build -t pwsimulator:latest .
    ```

2. Setup the Docker Container to listen on port 8675

    ```bash
    docker run \
    -d \
    -p 443:443 \
    --name pwsimulator \
    --restart unless-stopped \
    -v `pwd`:/app \
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
