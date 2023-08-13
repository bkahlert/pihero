# Shared functions related to services

service_start_cmdline() {
  service="${1:?service name missing}"
  systemctl show -p ExecStart "$service.service" | sed -n -e 's/^ExecStart.*argv\[\]=\(.*\); ignore_errors.*/\1/p'
}
