# Shared functions related to services

# Prints the command line used to start a service, for example,
#   - service_start_cmdline smbd.service
# Globals:
#   None
# Arguments:
#   $1 (string): Unit name
# Outputs:
#   Command line used to start the service
# Returns:
#   0: Command line printed
#   1: An error occurred
service_start_cmdline() {
  local service="${1:?service name missing}"
  case "$service" in
  dnsmasq.service)
    printf '%s\n' 'dnsmasq --no-daemon --log-queries=extra --log-dhcp --log-queries --conf-file=/etc/dnsmasq.conf'
    ;;
  *)
    systemctl show -p ExecStart "$service" | sed -n -e 's/^ExecStart.*argv\[\]=\(.*\); ignore_errors.*/\1/p'
    ;;
  esac
}
