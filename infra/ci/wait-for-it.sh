#!/bin/bash
# wait-for-it.sh

TIMEOUT=30
HOST_PORT=""

usage() {
    echo "Usage: $0 host:port [-t timeout]"
    exit 1
}

if [ -z "$1" ]; then
    usage
fi

HOST_PORT=$1
shift

while [ "$1" != "" ]; do
    case $1 in
        -t ) shift; TIMEOUT=$1 ;;
        * ) usage ;;
    esac
    shift
done

HOST=$(echo $HOST_PORT | cut -d: -f1)
PORT=$(echo $HOST_PORT | cut -d: -f2)

echo "Waiting for $HOST:$PORT (timeout $TIMEOUT seconds)..."

for i in $(seq 1 $TIMEOUT); do
    nc -z "$HOST" "$PORT" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "$HOST:$PORT is available."
        exit 0
    fi
    sleep 1
done

echo "Timeout occurred waiting for $HOST:$PORT"
exit 1
