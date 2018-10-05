FROM python:3.7.0-slim-stretch

ENV SYSTEM_PASSWORD system

COPY ./app /app
WORKDIR /app

RUN pip3 install -U pip
RUN pip3 install -r /app/requirements.txt

CMD ["python3", "/app/main.py"]
