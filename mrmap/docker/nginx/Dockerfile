FROM library/nginx:1.19-alpine

RUN apk add openssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt -subj "/C=DE/ST=Rhineland-Palatinate/L=Wiesbaden/O=MrMap Community/OU=Developers/CN=example.com"
