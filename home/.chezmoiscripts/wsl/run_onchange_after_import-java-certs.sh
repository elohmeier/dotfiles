#!/bin/sh

STOREPASS="changeit"

import_certs() {
	cacerts=$1
	keytool=$2
	count=0
	echo "Importing certs into $cacerts"
	for cert in /etc/ssl/certs/*.pem; do
		[ -f "$cert" ] || continue
		alias=$(basename "$cert" .pem | tr '[:upper:]' '[:lower:]')
		"$keytool" -list -keystore "$cacerts" -storepass "$STOREPASS" -alias "$alias" >/dev/null 2>&1 && continue
		"$keytool" -import -trustcacerts -noprompt \
			-keystore "$cacerts" -storepass "$STOREPASS" \
			-alias "$alias" -file "$cert" 2>/dev/null || true
		count=$((count + 1))
		echo "  Added: $alias"
	done
	echo "  $count new certificate(s) imported"
}

imported=0

# Homebrew-managed OpenJDK instances
if command -v brew >/dev/null; then
	for jdk in "$(brew --prefix)"/opt/openjdk*/; do
		keytool="$jdk/bin/keytool"
		[ -x "$keytool" ] || continue
		for cacerts in "$jdk/lib/security/cacerts" "$jdk/libexec/lib/security/cacerts"; do
			[ -f "$cacerts" ] || continue
			import_certs "$cacerts" "$keytool"
			imported=1
			break
		done
	done
fi

# Fallback: system Java on PATH
if [ "$imported" = 0 ] && command -v keytool >/dev/null && command -v java >/dev/null; then
	JAVA_HOME=$(java -XshowSettings:properties 2>&1 | sed -n 's/.*java\.home = //p')
	cacerts="$JAVA_HOME/lib/security/cacerts"
	[ -f "$cacerts" ] && import_certs "$cacerts" keytool
fi
