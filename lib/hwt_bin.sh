#!/usr/bin/env bash
# hwt_bin.sh — Resolve and invoke the hwt-tools Rust helper.
#
# Sourced by install.sh after SCRIPT_DIR is set. Builds the binary on demand
# via scripts/build_hwt_tools.sh.
#
# Public functions:
#   ensure_hwt_bin  — build/locate dist/hwt-tools; sets HWT_BIN
#   hwt_bin         — ensure_hwt_bin then run it with "$@"

# ensure_hwt_bin — Locate or build dist/hwt-tools; export HWT_BIN.
ensure_hwt_bin() {
  local build_script bin root
  root="${SCRIPT_DIR:-${HOTKEY_TOOLS_REPO_DIR:-${HOTKEY_TOOLS_LIB_DIR:-}/..}}"
  root="$(cd "$root" 2>/dev/null && pwd || true)"
  build_script="${root}/scripts/build_hwt_tools.sh"
  if [ -n "${HWT_BIN:-}" ] && [ -x "$HWT_BIN" ]; then
    return 0
  fi
  if [ -x "${HOTKEY_TOOLS_LIB_DIR:-}/hwt-tools" ]; then
    HWT_BIN="$HOTKEY_TOOLS_LIB_DIR/hwt-tools"
    export HWT_BIN
    return 0
  fi
  if [ ! -x "$build_script" ]; then
    if declare -F msg >/dev/null 2>&1; then
      msg "Missing build helper: $build_script"
    else
      printf 'Missing build helper: %s\n' "$build_script" >&2
    fi
    return 1
  fi
  bin="$(bash "$build_script" --print)" || return 1
  HWT_BIN="$bin"
  export HWT_BIN
}

# hwt_bin — Run the helper CLI.
hwt_bin() {
  ensure_hwt_bin || return 1
  "$HWT_BIN" "$@"
}
