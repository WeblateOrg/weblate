server {
    listen 8080 default_server;
    root /app/data/static;
    client_max_body_size 100M;

    location ~ ^/favicon.ico$ {
        # DATA_DIR/static/favicon.ico
        alias /app/data/static/favicon.ico;
        expires 30d;
    }

    location ~ ^/robots.txt$ {
        # DATA_DIR/static/robots.txt
        alias /app/data/static/robots.txt;
        expires 30d;
    }

    location ${WEBLATE_URL_PREFIX}/static/ {
        # DATA_DIR/static/
        alias /app/data/static/;
        expires 30d;
    }

    location ${WEBLATE_URL_PREFIX}/media/ {
        # DATA_DIR/media/
        alias /app/data/media/;
        expires 30d;
    }

    location / {
        include uwsgi_params;
        # Needed for long running operations in admin interface
        uwsgi_read_timeout 3600;
        # Adjust based to uwsgi configuration:
        uwsgi_pass unix:///run/uwsgi/app/weblate/socket;
    }
}
