#!/bin/bash

# rewrite the rabbitmq config file with URL from ENV
echo "rewriting rabbitmq.conf with CARDSHOP_API_URL (${CARDSHOP_API_URL})"
sed -i "s#CARDSHOP_API_URL#${CARDSHOP_API_URL}#g" /etc/rabbitmq/rabbitmq.conf

# continue with regular entry-point
echo "passing over to main entrypoint"
exec docker-entrypoint.sh "$@"
