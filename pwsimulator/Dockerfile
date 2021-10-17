FROM python:3.7-alpine
WORKDIR /app
RUN pip3 install pypowerwall
COPY . .
CMD ["python3", "stub.py"]
EXPOSE 443 