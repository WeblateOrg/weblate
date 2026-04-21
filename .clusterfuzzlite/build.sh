#!/bin/bash

# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

cd "$SRC/weblate"

mkdir -p "$OUT"

# Bundle a relocatable Python runtime instead of freezing the whole Django app
# with PyInstaller. That keeps the fuzz targets much closer to the normal
# Python execution model and avoids hidden-import/package-data breakage during
# ClusterFuzzLite bad-build checks.
python_executable="$PWD/.venv/bin/python"
python_home=$(
    "$python_executable" - << 'PY'
import sys

print(sys.base_prefix)
PY
)
site_packages=$(
    "$python_executable" - << 'PY'
import sysconfig

print(sysconfig.get_path("purelib"))
PY
)

rm -rf "$OUT/python" "$OUT/site-packages" "$OUT/src"
install -d "$OUT/python" "$OUT/site-packages" "$OUT/src"
cp -a "$python_home"/. "$OUT/python/"
cp -a "$site_packages"/. "$OUT/site-packages/"
cp -a weblate fuzzing "$OUT/src/"
# Keep the shared runner in the packaged sources for the shell wrappers, but do
# not leave it executable. ClusterFuzzLite recursively treats every executable
# under $OUT as a fuzz target and will otherwise invoke runner.py directly
# without a target name.
runner_path="$OUT/src/fuzzing/runner.py"
runner_tmp=$(mktemp /tmp/weblate-fuzz-runner-XXXXXX)
{
    printf '#!%s/python/bin/python3.12\n' "$OUT"
    tail -n +2 "$runner_path"
} > "$runner_tmp"
install -m 0644 "$runner_tmp" "$runner_path"
rm -f "$runner_tmp"

# ClusterFuzzLite recursively treats executables under $OUT as fuzz targets.
# Keep the actual interpreter binary for the wrappers, but drop convenience
# symlinks that would otherwise be mistaken for standalone fuzzers.
rm -f "$OUT/python/bin/python" "$OUT/python/bin/python3"

# The local checkout is installed in editable mode during the build. Strip the
# editable hook from the packaged site-packages tree so the runtime bundle uses
# the copied project sources under $OUT/src instead of the build path.
find "$OUT/site-packages" -maxdepth 1 -type f \( \
    -name "__editable__.weblate-*.pth" -o \
    -name "__editable___weblate_*_finder.py" \
    \) -delete

# ClusterFuzzLite's Python bad-build check expects a sidecar "<target>.pkg"
# binary for every wrapper script. Keep the shared Python runner, but provide a
# tiny sanitized ELF so the check has an architecture-tagged binary to inspect.
pkg_stub_source=$(mktemp /tmp/weblate-fuzz-pkg-stub-XXXXXX.c)
pkg_stub_binary=$(mktemp /tmp/weblate-fuzz-pkg-stub-XXXXXX)
cat > "$pkg_stub_source" << 'EOF'
int main(void) {
    return 0;
}
EOF
# shellcheck disable=SC2086
"$CC" $CFLAGS -o "$pkg_stub_binary" "$pkg_stub_source"
rm -f "$pkg_stub_source"

for target in backups markup memory_import ssh translation_formats webhooks; do
    cat > "$OUT/src/fuzzing/$target" << EOF
#!/bin/sh
set -eu
this_dir=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)
root_dir=\$(CDPATH= cd -- "\$this_dir/../.." && pwd)

export PYTHONHOME="\$root_dir/python"
export PYTHONNOUSERSITE=1
export PYTHONPATH="\$root_dir/src:\$root_dir/site-packages\${PYTHONPATH:+:\$PYTHONPATH}"

if [ -f "\$root_dir/sanitizer_with_fuzzer.so" ]; then
  export LD_PRELOAD="\$root_dir/sanitizer_with_fuzzer.so\${LD_PRELOAD:+:\$LD_PRELOAD}"
fi

symbolizer_path=
if command -v llvm-symbolizer >/dev/null 2>&1; then
  symbolizer_path=\$(command -v llvm-symbolizer)
fi
if [ -n "\$symbolizer_path" ] && ! "\$symbolizer_path" --version >/dev/null 2>&1; then
  symbolizer_path=
fi
if [ -z "\$symbolizer_path" ] && [ -x "\$root_dir/llvm-symbolizer" ] && "\$root_dir/llvm-symbolizer" --version >/dev/null 2>&1; then
  symbolizer_path="\$root_dir/llvm-symbolizer"
fi

if [ -n "\$symbolizer_path" ]; then
  export ASAN_OPTIONS="\${ASAN_OPTIONS:+\$ASAN_OPTIONS:}symbolize=1:external_symbolizer_path=\$symbolizer_path:detect_leaks=0"
else
  export ASAN_OPTIONS="\${ASAN_OPTIONS:+\$ASAN_OPTIONS:}detect_leaks=0"
fi

exec "\$root_dir/python/bin/python3.12" -P "\$this_dir/runner.py" $target "\$@"
EOF
    chmod +x "$OUT/src/fuzzing/$target"

    cat > "$OUT/$target" << EOF
#!/bin/sh
# LLVMFuzzerTestOneInput
set -eu
this_dir=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)
exec "\$this_dir/src/fuzzing/$target" "\$@"
EOF
    chmod +x "$OUT/$target"
    install -m 0755 "$pkg_stub_binary" "$OUT/$target.pkg"

    mapfile -t seed_files < <(
        find "fuzzing/corpus/$target" -maxdepth 1 -type f ! -name "*.license" | sort
    )
    if [ "${#seed_files[@]}" -gt 0 ]; then
        zip -q -j "$OUT/${target}_seed_corpus.zip" "${seed_files[@]}"
    fi
done

rm -f "$pkg_stub_binary"
