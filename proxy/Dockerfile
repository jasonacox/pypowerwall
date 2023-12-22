FROM python:3.10-alpine
WORKDIR /app
RUN pip3 install pypowerwall bs4
RUN pip3 install pypowerwall==0.6.4 bs4
COPY . .
CMD ["python3", "server.py"]
EXPOSE 8675 
