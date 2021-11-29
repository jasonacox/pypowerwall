FROM python:3.7-alpine
WORKDIR /app
RUN pip3 install pypowerwall==0.1.0
COPY . .
CMD ["python3", "server.py"]
EXPOSE 8675 
