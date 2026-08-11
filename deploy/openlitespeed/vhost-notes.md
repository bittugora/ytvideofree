# OpenLiteSpeed Reverse Proxy Notes

Create a Web Server External App:

```text
Type: Web Server
Name: ytvideofree
Address: 127.0.0.1:8000
Max Connections: 100
Initial Request Timeout: 1200
Retry Timeout: 0
Response Buffering: No
```

Then route the domain to the backend with either option:

## Option A: Proxy Context

```text
Virtual Hosts > ytvideofree.com > Context > Add > Proxy
URI: /
Web Server: [VHost Level]: ytvideofree
```

## Option B: Rewrite Rule

Enable rewrite for the virtual host and add:

```apache
RewriteRule ^/(.*)$ http://ytvideofree/$1 [P,L]
```

Perform a graceful restart after saving changes.

Note: gunicorn (Django) serves the app on 127.0.0.1:8000 behind this proxy;
static files are served by WhiteNoise inside gunicorn, so no extra document
root configuration is required.
