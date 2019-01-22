FROM python:3.4.9-stretch

ENV FTP_COMMAND_PORT 21
ENV FTP_DATA_PORT_RANGE 28011-28090
ENV TOKEN_VALIDATION_URL https://api.cardshop.hotspot.kiwix.org/auth/validate
ENV MASQUERADE_ADDRESS 163.1.1.1
VOLUME /files

COPY ./app /app
WORKDIR /app
RUN pip3 install -r /app/requirements.txt

EXPOSE 21

CMD ["python3", "/app/main.py"]
