#!/usr/bin/env bash
# Skript, mida agent kutsub OTA paigalduseks.
# $1 = .bin / .tar.gz / .deb / muu paigaldatav fail
# Default-realisatsioon: kui .deb, dpkg -i; kui .tar.gz, ekstrakteeri /opt; muidu loga.

set -euo pipefail
FILE="$1"
if [[ ! -f "$FILE" ]]; then
  echo "Faili pole: $FILE" >&2
  exit 1
fi

case "$FILE" in
  *.deb)
    dpkg -i "$FILE" || apt-get -f install -y
    systemctl restart kohvrikapid-agent.service
    ;;
  *.tar.gz|*.tgz)
    tar -xzf "$FILE" -C /opt/kohvrikapid-agent --strip-components=0
    systemctl restart kohvrikapid-agent.service
    ;;
  *)
    echo "Tundmatu firmware fail $FILE — paigalda käsitsi" >&2
    exit 2
    ;;
esac
