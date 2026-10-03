#!/bin/bash

# Retry a command up to a specific numer of times until it exits successfully,
# with exponential back off.
#
# From https://gist.github.com/sj26/88e1c6584397bb7c13bd11108a579746

function retry {
  local retries=$1
  shift

  local count=0
  until "$@"; do
    exit=$?
    wait=$((2 ** $count))
    count=$(($count + 1))
    if [ $count -lt $retries ]; then
      echo "Retry $count/$retries exited $exit, retrying in $wait seconds..."
      sleep $wait
    else
      echo "Retry $count/$retries exited $exit, no more retries left."
      return $exit
    fi
  done
  return 0
}
