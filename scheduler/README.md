## Nginx front-end

server {
    server_name api.demo.plug.kiwix.org;
    listen 80;
    listen [::]:80;

    location /.well-known/ {
        root /var/www/html/;
        autoindex on;
    }
    root /var/www/pub;
    autoindex on;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    server_name api.demo.plug.kiwix.org;
    listen 443 ssl http2;

    add_header Strict-Transport-Security "max-age=31536000;";
    add_header Access-Control-Allow-Origin "*";

    ssl_certificate /etc/letsencrypt/live/api.demo.plug.kiwix.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.demo.plug.kiwix.org/privkey.pem;

    location /.well-known/ {
        root /var/www/html/;
        autoindex on;
    }

    root /var/www/pub;
    index index.html;
    autoindex on;

    location / {
        proxy_pass http://127.0.0.1:28000;
        proxy_pass_header X-CSRFToken;
        proxy_set_header    Host            $http_host;
        proxy_set_header    X-Real-IP       $remote_addr;
        proxy_set_header    X-Forwarded-for $remote_addr;
        port_in_redirect off;
        proxy_connect_timeout 300;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        client_max_body_size 200M;
    }
}
