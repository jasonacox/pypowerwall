FROM python:3.10-alpine

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache git curl

# Install proxy extra dependencies first
RUN pip3 install --no-cache-dir bs4

# Copy full source and install pypowerwall from local source
COPY . /build
RUN pip3 install --no-cache-dir /build && rm -rf /build

# Copy proxy server files
COPY proxy/ /app/
EXPOSE 8675
CMD ["python3", "server.py"]
