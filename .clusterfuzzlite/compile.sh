#!/bin/bash

# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

: "${SRC:=/src}"
: "${OUT:=/out}"
: "${WORK:=/work}"
: "${SANITIZER:=address}"
: "${FUZZING_LANGUAGE:=python}"
: "${FUZZING_ENGINE:=libfuzzer}"
: "${ARCHITECTURE:=x86_64}"
: "${CC:=clang}"
: "${CXX:=clang++}"
: "${CCC:=clang++}"
: "${CFLAGS:=-O1 -fno-omit-frame-pointer -gline-tables-only -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION}"
: "${CXXFLAGS:=$CFLAGS}"

export SRC OUT WORK SANITIZER FUZZING_LANGUAGE FUZZING_ENGINE ARCHITECTURE
export CC CXX CCC CFLAGS CXXFLAGS

mkdir -p "$SRC" "$OUT" "$WORK"

case "$SANITIZER" in
address)
    sanitizer_flags="-fsanitize=address -fsanitize-address-use-after-scope"
    sanitizer_library="asan_with_fuzzer.so"
    ;;
undefined)
    sanitizer_flags="-fsanitize=array-bounds,bool,builtin,enum,function,integer-divide-by-zero,null,object-size,return,returns-nonnull-attribute,shift,signed-integer-overflow,unsigned-integer-overflow,unreachable,vla-bound,vptr -fno-sanitize-recover=array-bounds,bool,builtin,enum,function,integer-divide-by-zero,null,object-size,return,returns-nonnull-attribute,shift,signed-integer-overflow,unreachable,vla-bound,vptr"
    sanitizer_library="ubsan_with_fuzzer.so"
    ;;
coverage | introspector)
    sanitizer_flags=""
    sanitizer_library=""
    ;;
*)
    echo "Unsupported sanitizer for Weblate Python fuzzing: $SANITIZER" >&2
    exit 1
    ;;
esac

if [ "$FUZZING_LANGUAGE" != "python" ]; then
    echo "Unsupported fuzzing language for Weblate fuzzing: $FUZZING_LANGUAGE" >&2
    exit 1
fi

if [ "$FUZZING_ENGINE" != "libfuzzer" ]; then
    echo "Unsupported fuzzing engine for Weblate Python fuzzing: $FUZZING_ENGINE" >&2
    exit 1
fi

export CFLAGS="$CFLAGS ${sanitizer_flags} -fno-sanitize=function,leak"
export CXXFLAGS="$CXXFLAGS ${sanitizer_flags} -fno-sanitize=function,leak,vptr"

if [ -n "$sanitizer_library" ]; then
    atheris_path=$(
        "$SRC/weblate/.venv/bin/python" - << 'PY'
import atheris

print(atheris.path())
PY
    )
    install -m 0755 "$atheris_path/$sanitizer_library" "$OUT/sanitizer_with_fuzzer.so"
fi

if symbolizer_path=$(command -v llvm-symbolizer); then
    install -m 0755 "$symbolizer_path" "$OUT/llvm-symbolizer"
fi

echo "---------------------------------------------------------------"
echo "CC=$CC"
echo "CXX=$CXX"
echo "CFLAGS=$CFLAGS"
echo "CXXFLAGS=$CXXFLAGS"
echo "SANITIZER=$SANITIZER"
echo "FUZZING_LANGUAGE=$FUZZING_LANGUAGE"
echo "---------------------------------------------------------------"

exec bash -eux "$SRC/build.sh" "$@"
