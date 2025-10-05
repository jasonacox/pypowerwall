FROM python:3.10-alpine

WORKDIR /app

# Install git (and build dependencies if needed)
RUN apk add --no-cache git curl

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8675 
CMD ["python3", "server.py"]
