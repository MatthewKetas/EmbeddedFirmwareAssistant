#!/bin/sh

ulimit -c 0
if ! timeout -k 1 10 cc -std=c11 -Wall -Wextra -pedantic-errors \
    /submission.c /judge.o -lm -o /tmp/critter > /tmp/build.log 2>&1; then
    head -c 8192 /tmp/build.log >&2
    exit 2
fi

for group in io summary prediction pipeline; do
    if timeout -k 1 3 /tmp/critter "$group" > /tmp/test.log 2>&1 &&
        [ "$(head -c 128 /tmp/test.log)" = "PASS $group" ]; then
        printf '%s=pass\n' "$group"
    else
        printf '%s=fail\n' "$group"
        printf '%s failed\n' "$group" >&2
        head -c 2048 /tmp/test.log >&2
    fi
done
