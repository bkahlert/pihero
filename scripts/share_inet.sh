#!/usr/bin/env bash

declare os
if ! os=$(uname -s); then
    printf "\e[31mFailed to determine the operating system.\e[0m\n" >&2
    exit 1
fi

case "$os" in
*Darwin*)
    ./macos_connection_share.sh
    ;;
*Linux*)
    ./linux_connection_share.sh
    ;;
*OpenBSD*)
    ./openbsd_connection_share.sh
    ;;
*)
    printf "\e[31mThe operating system %s is not supported.\e[0m\n" "$os" >&2
    exit 1
    ;;
esac
