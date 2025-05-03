FROM python:3.13-alpine

WORKDIR /app

# 1) copy in all the things that affect pip
COPY proxy/requirements.txt .
COPY setup.py requirements.txt README.md pypowerwall/ ./pypowerwall/

# 2) install build deps, upgrade pip, install everything, then remove build deps
RUN apk add --no-cache --virtual .build-deps \
        gcc musl-dev python3-dev linux-headers \
    && python3 -m pip install --root-user-action ignore --upgrade pip \
    && python3 -m pip install --no-cache-dir --root-user-action ignore -r requirements.txt \
    && python3 -m pip install --no-cache-dir --root-user-action ignore ./pypowerwall \
    && apk del .build-deps

# 3) finally copy your proxy/server code
COPY proxy .

EXPOSE 8675 8685
CMD ["python3", "server.py"]
