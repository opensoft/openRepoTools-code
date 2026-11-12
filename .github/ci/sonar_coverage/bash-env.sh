# SPDX-License-Identifier: Apache-2.0
# Bash 3.2+ collector. Emit hashes and line numbers, never expanded commands.
# A copied source earns hits only if its complete bytes match the inventory.
if [[ -n ${ORT_SONAR_SHELL_HITS:-} && -n ${ORT_SONAR_SHELL_HASHES:-} ]]; then
  _ort_sonar_last_path=''
  _ort_sonar_last_hash=''
  _ort_sonar_trace() {
    local _ort_path="${BASH_SOURCE[1]:-}" _ort_line="${BASH_LINENO[0]:-0}"
    local _ort_hash
    [[ -f "$_ort_path" && "$_ort_line" -gt 0 ]] || return 0
    if [[ "$_ort_path" != "$_ort_sonar_last_path" ]]; then
      if command -v sha256sum >/dev/null 2>&1; then
        _ort_hash="$(sha256sum < "$_ort_path" 2>/dev/null)" || return 0
      else
        _ort_hash="$(shasum -a 256 < "$_ort_path" 2>/dev/null)" || return 0
      fi
      _ort_hash="${_ort_hash:0:64}"
      _ort_sonar_last_path="$_ort_path"
      case ":$ORT_SONAR_SHELL_HASHES:" in
        *:"$_ort_hash":*) _ort_sonar_last_hash="$_ort_hash" ;;
        *) _ort_sonar_last_hash='' ;;
      esac
    fi
    if [[ -n "$_ort_sonar_last_hash" ]]; then
      printf '%s\t%s\n' "$_ort_sonar_last_hash" "$_ort_line" >> "$ORT_SONAR_SHELL_HITS"
    fi
    return 0
  }
  set -T
  trap '_ort_sonar_trace' DEBUG
fi
