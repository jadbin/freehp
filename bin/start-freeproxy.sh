#!/usr/bin/env bash

bin=$(dirname $0)
bin=$(cd "$bin"; pwd)

echo "start freeproxy"
"$bin"/freeproxy-daemon.sh start $@ --config "$bin"/../conf/freeproxy.yaml --logger "$bin"/../conf/logger.yaml
