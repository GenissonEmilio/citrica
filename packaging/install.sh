#!/bin/sh
set -eu
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
target_dir="${XDG_DATA_HOME:-$HOME/.local/share}/citrica"
bin_dir="$HOME/.local/bin"
if [ "$source_dir" != "$target_dir" ]; then
    mkdir -p "$target_dir"
    cp -R "$source_dir"/. "$target_dir"/
fi
mkdir -p "$bin_dir"
ln -sfn "$target_dir/citrica" "$bin_dir/citrica"
"$target_dir/citrica" --install-integrations
printf '\nCítrica instalado em %s\nAbra pelo menu de aplicativos ou execute %s/citrica\n' "$target_dir" "$bin_dir"
