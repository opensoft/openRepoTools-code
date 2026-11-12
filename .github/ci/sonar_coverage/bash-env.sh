# SPDX-License-Identifier: Apache-2.0
# Bash 4+ CI collector. Emit hashes and line numbers, never expanded commands.
# A copied source earns hits only if its complete bytes match the inventory.
if [[ -n ${ORT_SONAR_SHELL_HITS:-} && -n ${ORT_SONAR_SHELL_HASHES:-} ]]; then
  declare -A _ort_sonar_hashes=()
  _ort_sonar_trace() {
    local _ort_path="${BASH_SOURCE[1]:-}" _ort_line="${BASH_LINENO[0]:-0}"
    local _ort_hash
    [[ -f "$_ort_path" && "$_ort_line" -gt 0 ]] || return 0
    if [[ ! ${_ort_sonar_hashes["$_ort_path"]+known} ]]; then
      _ort_hash="$(sha256sum < "$_ort_path" 2>/dev/null)" || return 0
      _ort_hash="${_ort_hash:0:64}"
      case ":$ORT_SONAR_SHELL_HASHES:" in
        *:"$_ort_hash":*) _ort_sonar_hashes["$_ort_path"]="$_ort_hash" ;;
        *) _ort_sonar_hashes["$_ort_path"]="" ;;
      esac
    fi
    _ort_hash="${_ort_sonar_hashes["$_ort_path"]}"
    if [[ -n "$_ort_hash" ]]; then
      printf '%s\t%s\n' "$_ort_hash" "$_ort_line" >> "$ORT_SONAR_SHELL_HITS"
    fi
    return 0
  }
  set -T
  trap '_ort_sonar_trace' DEBUG
fi
