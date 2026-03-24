#!/bin/sh

command -v keytool >/dev/null || exit 0
command -v java >/dev/null || exit 0

JAVA_HOME=$(java -XshowSettings:properties 2>&1 | sed -n 's/.*java\.home = //p')
CACERTS="$JAVA_HOME/lib/security/cacerts"
STOREPASS="changeit"

[ -f "$CACERTS" ] || exit 0

for cert in /etc/ssl/certs/*.pem; do
    [ -f "$cert" ] || continue
    alias=$(basename "$cert" .pem | tr '[:upper:]' '[:lower:]')
    keytool -list -keystore "$CACERTS" -storepass "$STOREPASS" -alias "$alias" >/dev/null 2>&1 && continue
    keytool -import -trustcacerts -noprompt \
        -keystore "$CACERTS" -storepass "$STOREPASS" \
        -alias "$alias" -file "$cert" 2>/dev/null || true
done
