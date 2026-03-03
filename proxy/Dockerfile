FROM python:3.13-alpine

WORKDIR /app

# 1) copy in all the things that affect pip
COPY proxy/requirements.txt .
COPY setup.py requirements.txt README.md ./pypowerwall/
COPY pypowerwall/ ./pypowerwall/pypowerwall/

# 2) install build deps, upgrade pip, build protobuf from source, install everything,
#    then remove build-only deps
RUN apk add --no-cache --virtual .build-deps \
        gcc musl-dev python3-dev linux-headers \
    && python3 -m pip install --root-user-action ignore --upgrade pip \
    && python3 -m pip install --no-cache-dir --root-user-action ignore grpcio-tools \
    && python3 -m grpc_tools.protoc \
        --python_out=./pypowerwall/pypowerwall/tedapi \
        --pyi_out=./pypowerwall/pypowerwall/tedapi \
        --proto_path=./pypowerwall/pypowerwall/tedapi \
        tedapi.proto \
    && python3 -m pip install --no-cache-dir --root-user-action ignore -r requirements.txt \
    && python3 -m pip install --no-cache-dir --root-user-action ignore ./pypowerwall \
    && python3 -m pip uninstall -y grpcio-tools grpcio \
    && apk del .build-deps

# 3) finally copy your proxy/server code
COPY proxy .

EXPOSE 8675 8685
CMD ["python3", "server.py"]
