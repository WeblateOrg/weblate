server {
    listen 8080 default_server;
    root /app/cache/static;
    client_max_body_size ${CLIENT_MAX_BODY_SIZE};
    server_tokens off;

    ${WEBLATE_REALIP}

    location ~ ^/favicon.ico$ {
        # DATA_DIR/static/favicon.ico
        alias /app/cache/static/favicon.ico;
        expires 30d;
    }

    location ${WEBLATE_URL_PREFIX}/static/ {
        # DATA_DIR/static/
        alias /app/cache/static/;
        expires 30d;
    }

    location ${WEBLATE_URL_PREFIX}/media/ {
        # DATA_DIR/media/
        alias /app/data/media/;
        expires 30d;
    }

    location / {
        proxy_set_header Host $http_host;
        proxy_pass http://unix:/run/gunicorn/app/weblate/socket;
        proxy_read_timeout 3600;
        proxy_connect_timeout 3600;
    }
}
