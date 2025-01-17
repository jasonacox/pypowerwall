FROM python:3.13-alpine
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install -r requirements.txt
COPY . .
CMD ["python3", "server.py"]
EXPOSE 8675
EXPOSE 8685
