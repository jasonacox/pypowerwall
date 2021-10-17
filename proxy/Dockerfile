FROM python:3
WORKDIR /app
RUN pip3 install pypowerwall
COPY . .
CMD ["python3", "server.py"]
EXPOSE 8675 