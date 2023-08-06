#!/usr/bin/env bash

ansible-playbook playbook.yml \
  -e "inventory=gadget"

ansible-playbook playbook.yml \
  -e "inventory=gadget" \
  -e "ansible_host=10.10.10.10" \
  --skip-tags "reboot"

ansible-playbook playbook.yml \
  -e "inventory=gadget0" \
  -e "ansible_host=10.10.20.10" \
  -i inventory/homelab/hosts.yml \
  --skip-tags "reboot"
