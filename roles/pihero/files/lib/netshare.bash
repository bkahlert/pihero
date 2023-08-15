# Shared functions related to network sharing

newest_dhcp_lease() {
  iface="${1:-.*}"
  journalctl --boot --unit dnsmasq.service --grep 'DHCPACK\('"$iface"'\)' --output cat --reverse --lines 1
}

dns_set() {
  dns_servers=('8.8.8.8' '8.8.4.4')
  printf "Configuring dnsmasq to use DNS servers \e[3m%s\e[23m...\n" "${dns_servers[*]}" >&2
  printf 'server=%s\n' "${dns_servers[@]}" >/etc/dnsmasq.d/hero-dns.conf
  systemctl restart dnsmasq.service
}

dns_unset() {
  printf "Removing dnsmasq DNS servers...\n" >&2
  [ -f /etc/dnsmasq.d/hero-dns.conf ] || { printf "No servers set.\n" >&2 && return 0; }
  rm /etc/dnsmasq.d/hero-dns.conf
  systemctl restart dnsmasq.service
}

add_default_route() {
  host_ip="${1?host IP missing}"
  printf "Adding default route via \e[3m%s\e[23m...\n" "$host_ip" >&2
  ip route add default via "$host_ip"
}

delete_default_route() {
  host_ip="${1?host IP missing}"
  printf "Deleting default route via \e[3m%s\e[23m...\n" "$host_ip" >&2
  ip route delete default via "$host_ip"
}
