#!/bin/sh

STOREPASS="changeit"

import_certs() {
    cacerts=$1
    keytool=$2
    for cert in /etc/ssl/certs/*.pem; do
        [ -f "$cert" ] || continue
        alias=$(basename "$cert" .pem | tr '[:upper:]' '[:lower:]')
        "$keytool" -list -keystore "$cacerts" -storepass "$STOREPASS" -alias "$alias" >/dev/null 2>&1 && continue
        "$keytool" -import -trustcacerts -noprompt \
            -keystore "$cacerts" -storepass "$STOREPASS" \
            -alias "$alias" -file "$cert" 2>/dev/null || true
    done
}

imported=0

# Homebrew-managed OpenJDK instances
if command -v brew >/dev/null; then
    for jdk in "$(brew --prefix)"/opt/openjdk*/; do
        cacerts="$jdk/lib/security/cacerts"
        keytool="$jdk/bin/keytool"
        [ -f "$cacerts" ] && [ -x "$keytool" ] || continue
        import_certs "$cacerts" "$keytool"
        imported=1
    done
fi

# Fallback: system Java on PATH
if [ "$imported" = 0 ] && command -v keytool >/dev/null && command -v java >/dev/null; then
    JAVA_HOME=$(java -XshowSettings:properties 2>&1 | sed -n 's/.*java\.home = //p')
    cacerts="$JAVA_HOME/lib/security/cacerts"
    [ -f "$cacerts" ] && import_certs "$cacerts" keytool
fi
