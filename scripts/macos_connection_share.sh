#!/usr/bin/env bash

# sudo until the script has finished
sudo -v
while true; do
    sudo -n true
    sleep 60
    kill -0 "$" || exit
done 2>/dev/null &

# IP forwarding and NAT

DEBUG_CMDLINE=(sudo pfctl -s nat)
UPSTREAM_IFACE=${1:-$(route -n get default | awk '/interface:/ {print $2}')} # for example, en0
DOWNSTREAM_IFACE=${DOWNSTREAM_IFACE:-}                                       # for example, en11

if [ "$DOWNSTREAM_IFACE" = '' ]; then
    DOWNSTREAM_IP_PREFIX=${2:-10.0.0.}
    for interface in $(ifconfig -lu); do
        if ifconfig "$interface" | grep -q "$DOWNSTREAM_IP_PREFIX"; then DOWNSTREAM_IFACE=$interface; fi
    done
fi

[ -n "$DOWNSTREAM_IFACE" ] || { printf "\e[31mERROR: Downstream interface for \e[3m%s\e[23m not found.\e[0m\n" "$DOWNSTREAM_IP_PREFIX" >&2 && exit 1; }

sudo sysctl -w net.inet.ip.forwarding=1 || { printf "\e[31mERROR: Failed to enable IP forwarding.\e[0m\n" >&2 && exit 1; }
sudo pfctl -d || true
sudo pfctl -F all || true
printf "Enabling NAT on \e[3m%s\e[23m from \e[3m%s\e[23m... " "$UPSTREAM_IFACE" "$DOWNSTREAM_IFACE"
if echo "nat on $UPSTREAM_IFACE from $DOWNSTREAM_IFACE:network to any -> ($UPSTREAM_IFACE)" | sudo pfctl -f - -e 2>/dev/null; then
    printf "\e[32;1m✔\e[0m\n"
else
    printf "\e[31mFailed to enable NAT on \e[3m%s\e[23m from \e[3m%s\e[23m.\nOutput of \e[3m%s\e[23m:\n%s\e[0m\n" "$UPSTREAM_IFACE" "$DOWNSTREAM_IFACE" "${DEBUG_CMDLINE[*]}" "$("${DEBUG_CMDLINE[@]}" 2>&1)" >&2
    exit 1
fi
