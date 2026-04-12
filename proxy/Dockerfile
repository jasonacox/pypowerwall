FROM python:3.10-alpine

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache git curl

# Install pypowerwall and proxy dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy proxy server files (only runtime-needed files)
COPY server.py transform.py __init__.py /app/
COPY web/ /app/web/
EXPOSE 8675
CMD ["python3", "server.py"]
