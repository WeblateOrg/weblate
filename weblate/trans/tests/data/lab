#!/bin/sh

# Fake lab implementation for use in testsuite

case "$1" in
mr)
    exit 0
    ;;
fork)
    git remote add test "$(git config --get remote.origin.url)"
    exit 0
    ;;
esac

git "$@"
