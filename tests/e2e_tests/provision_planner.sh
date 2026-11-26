#!/usr/bin/env bash
# Copyright 2026 The RPent Authors.
# Provision the pinned Linux x86-64 CPU planner on the GPU runner host.
set -euo pipefail
root=${1:?usage: provision_planner.sh INSTALL_DIRECTORY}
mkdir -p "$root"
cd "$root"
exec 9>.provision.lock
flock 9
tmp=$(mktemp -d .provision.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

fetch() {
  local name=$1 url=$2 digest=$3
  if [[ -f "$name" ]] && echo "$digest  $name" | sha256sum -c -; then
    return
  fi
  curl --fail --silent --show-error --location --retry 4 --output "$tmp/$name" "$url"
  echo "$digest  $tmp/$name" | sha256sum -c -
  mv "$tmp/$name" "$name"
}

model=https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/f6d5376be1edb4d416d56da11e5397a961aca8ae
release=https://github.com/ggml-org/llama.cpp/releases/download/b12774
fetch llama-b12774.tar.gz "$release/llama-b12774-bin-ubuntu-x64.tar.gz" ab5837cca2317cfb7ecb5f85b550934e7355cd9df74cdde6e106581457034dbb
if [[ ! -d llama-b12774 ]]; then
  mkdir "$tmp/runtime"
  tar -xzf llama-b12774.tar.gz --strip-components=1 -C "$tmp/runtime"
  test -x "$tmp/runtime/llama-server"
  mv "$tmp/runtime" llama-b12774
fi
fetch Qwen3.5-2B-Q4_K_M.gguf "$model/Qwen3.5-2B-Q4_K_M.gguf" aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223
fetch mmproj-F16.gguf "$model/mmproj-F16.gguf" 7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7
