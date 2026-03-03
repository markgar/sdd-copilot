#!/bin/zsh
# build-review.sh — Build the next story, review, then test

cd "$(dirname "$0")" || exit 1

./build.sh && ./review.sh && ./test.sh
