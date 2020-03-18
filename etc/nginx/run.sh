#!/bin/bash
if [ -f /app/data/ssl/privkey.pem ] ; then
    template=/etc/nginx/ssl.tpl
else
    template=/etc/nginx/default.tpl
fi
envsubst '$WEBLATE_URL_PREFIX' < $template > /etc/nginx/sites-available/default
exec /usr/sbin/nginx -g "daemon off;"
