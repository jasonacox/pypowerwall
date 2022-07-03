FROM python:3.8-alpine
WORKDIR /app
RUN pip3 install pypowerwall==0.5.0 bs4
COPY . .
CMD ["python3", "server.py"]
EXPOSE 8675 
