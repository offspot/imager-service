FROM rabbitmq:3.7-management
RUN rabbitmq-plugins enable rabbitmq_auth_backend_http
RUN rabbitmq-plugins enable rabbitmq_auth_backend_cache

COPY ./ssl/cert.pem /etc/rabbitmq/cert.pem
COPY ./ssl/chain.pem /etc/rabbitmq/chain.pem
COPY ./ssl/privkey.pem /etc/rabbitmq/privkey.pem
RUN chown -R root:rabbitmq /etc/rabbitmq
RUN chmod -R 644 /etc/rabbitmq/*.pem
RUN ls -al /etc/rabbitmq

COPY ./rabbitmq.conf /etc/rabbitmq/rabbitmq.conf
