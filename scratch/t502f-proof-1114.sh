#!/usr/bin/env bash
# SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's follow-up
# round (`l5/007-T502-followup-1925`), on lane 3's rulings on spec#47's points
# 20, 21 and 25 and on the two exit comments those rulings route to the round
# (opensoft/openRepoTools#165 comment 6879754335; lane 3's rulings, never
# Brett's). The contract is T501's `bind-record.md`, draft 11 at `a2e0e3e6`.
# Lane 2 writes the permanent AT-F6 cases. The same cases, as pytest, are
# `tests/test_t502f_scratch_1114.py` (`tests/run.sh -k t502f`).
#
#   bash scratch/t502f-proof-1114.sh <lanes-edit.sh to test> [<work dir>]
#
# Each case runs the given `lanes-edit.sh` on a record written directly into a
# sandbox of its own (HOME, CLAUDE_CONFIG_DIR, XDG_STATE_HOME, env -i), with a
# stand-in body through `LANES_BIND_BODY` (R48), or runs the real body with a
# stand-in `lane-start`. Where the outer's own `pid_start_of $$` must exit 2, it
# runs a TEST-ONLY COPY whose `pid_start_of` answers 2 for the caller's own
# pid (lane 3's point 23: no seam in the shipped script). A change inside the
# outer's window is made by a stand-in `awk` or `mktemp` first on PATH: after
# the body has ended (it leaves a trigger file), the first call changes the
# record once, and every call runs the real tool. The sandbox is left in the
# work dir; nothing is removed.
#
# Prints PASS or FAIL per case and a count; exits 0 only where all pass.
set -u

[ "$#" -ge 1 ] && [ -f "$1" ] || { printf 'usage: %s <lanes-edit.sh> [<work dir>]\n' "$0" >&2; exit 2; }
S="$(cd "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
W="${2:-${TMPDIR:-/tmp}}"
ROOT="$(mktemp -d "$W/t502f-proof.XXXXXX")" || exit 2
BASE_PATH=/usr/local/bin:/usr/bin:/bin
U=aaaa1111-2222-3333-4444-555566667777
NOT_OWN="is no longer this bind's own"
pass=0; fail=0

ok()  { pass=$((pass + 1)); printf 'PASS %s\n' "$1"; }
bad() { fail=$((fail + 1)); printf 'FAIL %s: %s\n' "$1" "$2"; }

box() {   # <name>
  B="$ROOT/$1"
  mkdir -p "$B/home" "$B/cfg/lanes/offers" "$B/state" "$B/fakes"
  OFF="$B/cfg/lanes/offers"; REC="$OFF/$U"; OUT="$REC.bind.1.out"; FACTS="$REC.bind.1.facts"
  TRIG="$B/body-ended"; STUB="$B/stub-body"; REC_OUT="$OUT"
}

record() {
  rd_now="$(date -u +%s)"
  printf '%s\n' mode=binding from=repoA-2 to=repoA-3 session=repoA-3 "uuid=$U" window=@1 pane=%1 \
    utc=2026-11-14T00:00:00Z bind=1 started_utc=2026-11-14T00:00:00Z bound_s=500 bounded=yes \
    "deadline_epoch=$((rd_now + 505))" host=Eagle container=g-box "out=$REC_OUT" detach=setsid > "$REC"
  chmod 600 "$REC"
}

get() { sed -n "s/^$1=//p" "${2:-$REC}" 2>/dev/null | head -n 1; }
has() { grep -q "^$1=" "${2:-$REC}" 2>/dev/null; }
said_has() { case "$SAID" in *"$1"*) return 0 ;; esac; return 1; }
temps() { ls -A "$OFF" | grep -F ".$U." | grep '^\.' || :; }

body() {   # <sed expression, or -> <exit code> <facts text>
  {
    printf '#!/bin/bash\n'
    [ "$1" = - ] || printf 'sed -e %q %q > %q && mv -f %q %q\n' "$1" "$REC" "$REC.mut" "$REC.mut" "$REC"
    printf '[ -z "${LANES_BIND_FACTS:-}" ] || printf %%s %q > "$LANES_BIND_FACTS"\n' "$3"
    printf ': > %q\nexit %s\n' "$TRIG" "$2"
  } > "$STUB"
  chmod 755 "$STUB"
}

fake() {   # <tool> <command its first call after the trigger makes>
  fk_real="$(PATH="$BASE_PATH" command -v "$1")"
  {
    printf '#!/bin/bash\n'
    printf 'if [ -e %q ]; then\n' "$TRIG"
    printf '  printf "%%s\\n" "$*" >> %q\n' "$B/$1-calls"
    printf '  if mkdir %q 2>/dev/null; then\n    %s\n  fi\nfi\n' "$B/once-$1" "$2"
    printf 'exec %q "$@"\n' "$fk_real"
  } > "$B/fakes/$1"
  chmod 755 "$B/fakes/$1"
}

drift() { printf "sed -e 's/^mode=binding\$/mode=name-drift/' %q > %q && mv -f %q %q" "$REC" "$REC.mut" "$REC.mut" "$REC"; }

run_env() {
  env -i HOME="$B/home" PATH="$B/fakes:$BASE_PATH" TMPDIR="$B" CLAUDE_CONFIG_DIR="$B/cfg" \
    XDG_STATE_HOME="$B/state" LANES_WORKSTATION=Eagle LANES_CONTAINER=g-box LANES_BIND_BOUND_S=15 \
    LC_ALL=C "$@"
}

outer() {   # [<script>]: `guard-bind <uuid>`, its output in the attempt's `.out`
  ORC=0
  run_env LANES_BIND_BODY="$STUB" timeout 60 bash "${1:-$S}" guard-bind "$U" </dev/null >>"$OUT" 2>&1 || ORC=$?
  SAID="$(cat -- "$OUT" 2>/dev/null)"
}

run_body() {   # <stand-in lane-start>: `guard-bind --body <uuid>`
  ORC=0
  run_env LANES_LANE_START="$1" LANES_BIND_FACTS="$FACTS" timeout 60 bash "$S" guard-bind --body "$U" \
    </dev/null >>"$OUT" 2>&1 || ORC=$?
  SAID="$(cat -- "$OUT" 2>/dev/null)"
}

copy() {   # lane 3's point 23: a test-only copy, the outer's own start unread
  cp_c="$B/lanes-edit-copy.sh"
  awk '{ print } $0 == "pid_start_of() {   # <pid>" { print "  [ \"${1-}\" != \"$$\" ] || return 2"; n++ }
       END { exit (n == 1 ? 0 : 1) }' "$S" > "$cp_c" || printf 'copy: pid_start_of head not found once\n' >&2
  chmod 755 "$cp_c"
  printf '%s\n' "$cp_c"
}

state() { printf 'rc=%s mode=%s host=%s container=%s pid=%s pidstart=%s rc-key=%s' "$ORC" \
  "$(get mode)" "$(get host)" "$(get container)" "$(get pid)" "$(get pidstart)" "$(get rc)"; }

# ---- POINT 20, (a): the outcome's test also matches `host` and `container`.
box p20-host; record
body 's/^host=Eagle$/host=Other-host/' 0 ''
outer
if [ "$ORC" = 0 ] && [ "$(get mode)" = binding ] && [ "$(get host)" = Other-host ] && ! has rc &&
   said_has "$NOT_OWN"; then ok p20-host-changed-not-written-over
else bad p20-host-changed-not-written-over "$(state)"; fi

box p20-container-pid-alone; record
C="$(copy)"
body 's/^container=g-box$/container=other-box/' 0 ''
outer "$C"
if [ "$ORC" = 0 ] && has pid && ! has pidstart && [ "$(get mode)" = binding ] &&
   [ "$(get container)" = other-box ] && ! has rc && said_has "$NOT_OWN"; then
  ok p20-pid-alone-container-changed-not-written-over
else bad p20-pid-alone-container-changed-not-written-over "$(state)"; fi

for alone in no yes; do
  box "p20-control-$alone"; record
  body 's/^host=Eagle$/host=EAGLE/;s/^container=g-box$/container=G-BOX/' 0 ''
  if [ "$alone" = yes ]; then outer "$(copy)"; else outer; fi
  ps_ok=1
  if [ "$alone" = yes ]; then has pidstart && ps_ok=0; else has pidstart || ps_ok=0; fi
  if [ "$ORC" = 0 ] && [ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && [ "$ps_ok" = 1 ]; then
    ok "p20-control-own-host-container-other-case-ends-bound-pid-alone-$alone"
  else bad "p20-control-own-host-container-other-case-ends-bound-pid-alone-$alone" "$(state)"; fi
done

# ---- POINT 21: the window kept, and narrowed in code.
box p21-copies; record
mkdir -p "$B/state/openRepoTools/register-pending"
printf 'verb=start-record\nsession=%s\n' "$U" > "$B/state/openRepoTools/register-pending/$(printf 'a%.0s' $(seq 64))"
fake awk "$(drift)"
fake mktemp :
body - 3 $'why=the stand-in body refused\n'
outer
if [ -d "$B/once-awk" ] && [ "$ORC" = 0 ] && [ "$(get mode)" = name-drift ] && ! has rc &&
   [ ! -s "$B/mktemp-calls" ] && said_has "$NOT_OWN"; then
  ok p21-change-while-copies-gathered-seen-by-the-read
else bad p21-change-while-copies-gathered-seen-by-the-read "$(state) awk-fired=$([ -d "$B/once-awk" ] && echo yes || echo no) mktemp-after-body=$(cat -- "$B/mktemp-calls" 2>/dev/null | wc -l)"; fi

box p21-copy-loop; record
fake mktemp "$(drift)"
body - 0 ''
outer
if [ -d "$B/once-mktemp" ] && [ "$ORC" = 0 ] && [ "$(get mode)" = name-drift ] && ! has rc &&
   [ -z "$(temps)" ] && said_has "$NOT_OWN"; then
  ok p21-change-after-the-read-seen-by-the-copy-loop
else bad p21-change-after-the-read-seen-by-the-copy-loop "$(state) temps=[$(temps)]"; fi

box p21-dropped; record
fake mktemp "$(printf 'mv -f %q %q' "$REC" "$REC.gone")"
body - 0 ''
outer
if [ -d "$B/once-mktemp" ] && [ "$ORC" = 0 ] && [ ! -e "$REC" ] && [ "$(get mode "$REC.gone")" = binding ] &&
   [ -z "$(temps)" ] && said_has "$NOT_OWN"; then
  ok p21-record-dropped-after-the-read-not-made-again
else bad p21-record-dropped-after-the-read-not-made-again "rc=$ORC record-exists=$([ -e "$REC" ] && echo "yes, mode=$(get mode)" || echo no) temps=[$(temps)]"; fi

# ---- POINT 25: the body reads its own words back only from an `out` of the
# record's own form.
box p25-foreign
FOREIGN="$B/elsewhere.log"
printf 'a line from before\n' > "$FOREIGN"
REC_OUT="$FOREIGN"; record
printf '#!/bin/bash\nprintf "FOREIGN-WORDS-NOT-THIS-ATTEMPTS\\n" >> %q\nprintf "lane-start: REFUSED for the scratch case\\n" >&2\nexit 5\n' "$FOREIGN" > "$B/stub-lane-start"
chmod 755 "$B/stub-lane-start"
run_body "$B/stub-lane-start"
P25_WHY="$(get why "$FACTS")"
case "$P25_WHY" in *FOREIGN*) p25_foreign=1 ;; *) p25_foreign=0 ;; esac
case "$P25_WHY" in *"could not be read back"*) p25_said=1 ;; *) p25_said=0 ;; esac
if [ "$ORC" = 5 ] && [ "$p25_foreign" = 0 ] && [ "$p25_said" = 1 ]; then
  ok p25-no-words-read-back-from-an-out-not-of-its-form
else bad p25-no-words-read-back-from-an-out-not-of-its-form "rc=$ORC why=$P25_WHY"; fi

box p25-control; record
printf '#!/bin/bash\nprintf "lane-start: REFUSED for the scratch case\\n" >&2\nexit 5\n' > "$B/stub-lane-start"
chmod 755 "$B/stub-lane-start"
run_body "$B/stub-lane-start"
if [ "$ORC" = 5 ] && [ "$(get why "$FACTS")" = "lane-start: REFUSED for the scratch case" ]; then
  ok p25-control-its-own-out-read-back
else bad p25-control-its-own-out-read-back "rc=$ORC why=$(get why "$FACTS")"; fi

# ---- S1 of lane 3's Codex re-review of spec#47 at 746e931c (#165
# 6880414089): the `--own` rewrite's three results, each with the outer's exit
# and the facts file gone.
box s1-written; record
body - 0 'note=a stand-in act still owed'
outer
if [ "$ORC" = 0 ] && [ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && [ ! -e "$FACTS" ]; then
  ok s1-0-written-exit-0-facts-gone
else bad s1-0-written-exit-0-facts-gone "$(state) facts=$([ -e "$FACTS" ] && echo left || echo gone)"; fi

box s1-mismatch; record
fake mktemp "$(drift)"
body - 0 ''
outer
if [ "$ORC" = 0 ] && [ "$(get mode)" = name-drift ] && ! has rc && [ ! -e "$FACTS" ] && said_has "$NOT_OWN"; then
  ok s1-2-not-its-own-exit-0-left-facts-gone
else bad s1-2-not-its-own-exit-0-left-facts-gone "$(state) facts=$([ -e "$FACTS" ] && echo left || echo gone)"; fi

box s1-io; record
fake mktemp 'exit 1'
body - 0 ''
outer
if [ "$ORC" = 1 ] && [ "$(get mode)" = binding ] && has pid && ! has rc && [ ! -e "$FACTS" ] &&
   said_has "the outcome could not be written"; then
  ok s1-1-io-failure-exit-1-binding-kept-facts-gone
else bad s1-1-io-failure-exit-1-binding-kept-facts-gone "$(state) facts=$([ -e "$FACTS" ] && echo left || echo gone)"; fi

# ---- S3: one canonical `out` index, `[1-9][0-9]*`: an `out` at `.bind.0.out`
# or `.bind.01.out` is not the record's own form, so nothing is read back.
for ix in 0 01; do
  box "s3-index-$ix"
  NC="$REC.bind.$ix.out"
  printf 'a line from before\n' > "$NC"
  REC_OUT="$NC"; record
  printf '#!/bin/bash\nprintf "NONCANONICAL-WORDS\\n" >> %q\nprintf "lane-start: REFUSED for the scratch case\\n" >&2\nexit 5\n' "$NC" > "$B/stub-lane-start"
  chmod 755 "$B/stub-lane-start"
  run_body "$B/stub-lane-start"
  S3_WHY="$(get why "$FACTS")"
  case "$S3_WHY" in *NONCANONICAL*) s3_read=1 ;; *) s3_read=0 ;; esac
  if [ "$ORC" = 5 ] && [ "$s3_read" = 0 ] && [ -n "$S3_WHY" ]; then ok "s3-out-bind-$ix-not-read-back"
  else bad "s3-out-bind-$ix-not-read-back" "rc=$ORC why=$S3_WHY"; fi
done

# ---- S4: the files' index compares every canonical index, with no maximum.
# A TEST-ONLY COPY whose `guard-bind` arm (exempt from the workspace refusal)
# prints `guard_bind_next_index`'s answer for `guard-bind --t502f-next-index
# <offer file>` (lane 3's point 23: no seam in the shipped script).
ix_copy() {
  ixc="$B/lanes-edit-index-copy.sh"
  awk '{ print } $0 == "  guard-bind)" { print "    if [ \"${1-}\" = --t502f-next-index ]; then guard_bind_next_index \"$2\"; exit 0; fi"; n++ }
       END { exit (n == 1 ? 0 : 1) }' "$S" > "$ixc" || printf 'ix_copy: guard-bind arm not found once\n' >&2
  chmod 755 "$ixc"
}
for s4 in "999999:1000000" "999999 1000000:1000001" "1000000:1000001" "3 01 007:4"; do
  s4_have="${s4%%:*}"; s4_want="${s4#*:}"
  box "s4-$(printf '%s' "$s4_have" | tr ' ' '-')"; record; ix_copy
  for i in $s4_have; do : > "$REC.bind.$i.out"; done
  s4_got="$(run_env bash "$ixc" guard-bind --t502f-next-index "$REC" 2>/dev/null)"
  if [ "$s4_got" = "$s4_want" ]; then ok "s4-index-after-{$s4_have}-is-$s4_want"
  else bad "s4-index-after-{$s4_have}-is-$s4_want" "got=$s4_got"; fi
done

# ---- S2 and S6, contract-only, as controls: S2's case-only host and container
# and its real mismatches are the p20 cases above; S6's order is
# p21-change-while-copies-gathered-seen-by-the-read, whose change is made
# inside `guard_bind_copies` and seen by the last ownership load, with no
# outcome rewrite after it.

# ---- THE TWO COMMENTS name the exit 1 given where the outcome cannot be written.
joined() {   # <first line's start> <lines>
  awk -v s="$1" -v n="$2" '!f && index($0, s) == 1 { f = 1 } f && c < n { sub(/^#[ ]*/, ""); printf "%s ", $0; c++ }' "$S"
}
case "$(joined '#      AND `guard-bind` (feature 007, T502)' 14)" in
  *"could not write the outcome"*) t1=1 ;; *) t1=0 ;; esac
case "$(joined '# Exits: 0 once the outcome is written' 6)" in
  *"the outcome could not be written"*) t2=1 ;; *) t2=0 ;; esac
if [ "$t1" = 1 ] && [ "$t2" = 1 ]; then ok comments-name-the-outcomes-exit-1
else bad comments-name-the-outcomes-exit-1 "exit-table=$t1 outer-comment=$t2"; fi

printf 'script=%s sandbox=%s passed=%s failed=%s\n' "$S" "$ROOT" "$pass" "$fail"
[ "$fail" = 0 ]
