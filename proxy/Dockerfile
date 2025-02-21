FROM python:3.13-alpine
RUN apk add gcc python3-dev musl-dev linux-headers
WORKDIR /app
COPY ./proxy/requirements.txt /app/requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt
COPY pypowerwall /app/pypowerwall/pypowerwall/
COPY setup.py requirements.txt README.md /app/pypowerwall/
RUN pip3 install /app/pypowerwall
COPY ./proxy .
CMD ["python3", "server.py"]
EXPOSE 8675
EXPOSE 8685