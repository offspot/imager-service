FROM rabbitmq:3.7-management

ENV CARDSHOP_API_URL "https://api.demo.plug.kiwix.org"

RUN rabbitmq-plugins enable rabbitmq_auth_backend_http
RUN rabbitmq-plugins enable rabbitmq_auth_backend_cache

#COPY ./ssl/cert.pem /etc/rabbitmq/cert.pem
#COPY ./ssl/chain.pem /etc/rabbitmq/chain.pem
#COPY ./ssl/privkey.pem /etc/rabbitmq/privkey.pem
#RUN chown -R root:rabbitmq /etc/rabbitmq
#RUN chmod -R 644 /etc/rabbitmq/*.pem
#RUN ls -al /etc/rabbitmq

COPY ./rabbitmq.conf /etc/rabbitmq/rabbitmq.conf
COPY ./docker-cardshop-entrypoint.sh /usr/local/bin/

ENTRYPOINT ["docker-cardshop-entrypoint.sh"]
EXPOSE 4369 5671 5672 25672
CMD ["rabbitmq-server"]
