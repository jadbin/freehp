#!/usr/bin/env bash

bin=$(dirname $0)
bin=$(cd "$bin"; pwd)

echo "stop freeproxy"
"$bin"/freeproxy-daemon.sh stop $@
