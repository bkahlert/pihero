#!/usr/bin/env bash

ansible-playbook playbook.yml

ansible-playbook playbook.yml \
  -l foo.local

ansible-playbook playbook.yml \
  -l foo.local \
  -e "ansible_host=10.10.10.10"

ansible-playbook playbook.yml \
  -l foo.local \
  -e "ansible_host=10.10.10.10" \
  -i inventory/homelab/hosts.yml
