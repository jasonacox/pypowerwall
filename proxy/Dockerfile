FROM python:3.10-alpine
WORKDIR /app
RUN pip3 install pypowerwall==0.7.0 bs4
COPY . .
CMD ["python3", "server.py"]
EXPOSE 8675 
