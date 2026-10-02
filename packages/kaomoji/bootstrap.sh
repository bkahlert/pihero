#!/bin/sh
# Purpose: Run kaomoji @VERSION@ without installing it: fetches the binary for this machine once, then runs it.
# Usage:   curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/@NAME@ | sh -s -- [<argument>...]
#
# Published with every release as kaomoji, hero, wizard, and visitor; the last three run that character.
# The binary for this machine's OS and architecture is fetched from the release this script belongs to
# into ${XDG_CACHE_HOME:-~/.cache}/kaomoji/<version>/, checked against the hash baked in here, and run
# with the arguments. Needs curl, and sha256sum or shasum. Everything is inside one function called on
# the last line, so a download cut short runs nothing.

set -eu

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

main() {
    version='@VERSION@'
    character='@CHARACTER@'
    repo='https://github.com/bkahlert/pihero'
    hashes='
kaomoji-linux-armv6 @SHA256_LINUX_ARMV6@
kaomoji-linux-arm64 @SHA256_LINUX_ARM64@
kaomoji-linux-amd64 @SHA256_LINUX_AMD64@
kaomoji-darwin-arm64 @SHA256_DARWIN_ARM64@
kaomoji-darwin-amd64 @SHA256_DARWIN_AMD64@
'
    system=$(uname -s)
    machine=$(uname -m)
    case $system in
    Linux) os=linux ;;
    Darwin) os=darwin ;;
    *) os='' ;;
    esac
    # A 32-bit Raspberry Pi OS on a 64-bit kernel reports aarch64 and gets the arm64 binary, which runs there, being static.
    case $machine in
    x86_64 | amd64) arch=amd64 ;;
    aarch64 | arm64) arch=arm64 ;;
    armv6l | armv7l) arch=armv6 ;;
    *) arch='' ;;
    esac
    if [ -z "$os" ] || [ -z "$arch" ]; then
        printf 'kaomoji: no binary for %s %s\n' "$system" "$machine" >&2
        exit 1
    fi
    asset="kaomoji-$os-$arch"
    expected=$(printf '%s\n' "$hashes" | awk -v asset="$asset" '$1 == asset { print $2 }')

    dir="${XDG_CACHE_HOME:-$HOME/.cache}/kaomoji/$version"
    bin="$dir/kaomoji"
    if [ ! -x "$bin" ]; then
        tag="v$(printf '%s' "$version" | tr '~' '-')" # the Debian version 2.1.0~rc.1 was tagged v2.1.0-rc.1
        url="$repo/releases/download/$tag/$asset"
        mkdir -p "$dir"
        tmp="$dir/.$asset.$$"
        if ! curl -fsSL -o "$tmp" "$url"; then
            rm -f "$tmp"
            printf 'kaomoji: download failed: %s\n' "$url" >&2
            exit 1
        fi
        actual=$(sha256 "$tmp")
        if [ "$actual" != "$expected" ]; then
            rm -f "$tmp"
            printf 'kaomoji: checksum mismatch for %s\n' "$asset" >&2
            exit 1
        fi
        chmod 755 "$tmp"
        mv "$tmp" "$bin"
    fi
    if [ -n "$character" ]; then
        exec "$bin" "$character" "$@"
    fi
    exec "$bin" "$@"
}

main "$@"
