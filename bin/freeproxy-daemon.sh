#!/usr/bin/env bash

if [ $# -lt 1 ]; then
    exit 1
fi

bin=$(dirname $0)
bin=$(cd "$bin"; pwd)

cmd=$1
shift

PYTHON=python3
HOME=$(cd "$bin"/../; pwd)
log="$HOME"/.log
pid="$HOME"/.pid
stop_timeout=5

case $cmd in
    start)
        nohup "$PYTHON" "$HOME"/freeproxy.py "$cmd" $@ > "$log" 2>&1 < /dev/null &
        echo $! > "$pid"
        sleep 3
        if ! ps -p $! > /dev/null; then
            echo "fail to start freeproxy"
            exit 1
        fi
        ;;
    stop)
        if [ -f "$pid" ]; then
            target_pid=$(cat "$pid")
            if kill -0 $target_pid > /dev/null 2>&1; then
                echo "kill $target_pid"
                kill $target_pid
                sleep $stop_timeout
                if kill -0 $target_pid > /dev/null 2>&1; then
                    echo "freeproxy did not stop gracefully after $stop_timeout seconds: killing with kill -9"
                    kill -9 $target_pid
                fi
            else
                echo "no freeproxy to stop"
            fi
            rm -f "$pid"
        else
            echo "no freeproxy to stop"
        fi
        ;;
    *)
        exit 1
        ;;
esac
