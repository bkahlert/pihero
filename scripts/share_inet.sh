#!/usr/bin/env bash

case $OSTYPE in
darwin*) ./macos_connection_share.sh ;;
linux*) ./linux_connection_share.sh ;;
openbsd*) ./openbsd_connection_share.sh ;;
*) printf "\e[31mThe operating system %s is not supported.\e[0m\n" "$OSTYPE" >&2 && exit 1 ;;
esac
