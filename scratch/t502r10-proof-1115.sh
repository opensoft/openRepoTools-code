#!/usr/bin/env bash
# SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's parts 42 to 47
# (`l5/007-T502-followup-1925`): Codex's S1, S2, S3 and S6 and NITs 1 to 3 on
# spec#47's draft 17 (lane 3's Codex delta review at 8bc6b29e), lane 5's final
# check of 6253b0ed (C, E and H) and lane 5's wording note to lane 2 (#165
# 6888777622) (BRIEF-T502P42-1115.md; Codex's findings and lane 5's, not lane 3's
# rulings and not Brett's). This is a NEW copy of `scratch/t502r9-proof-1115.sh`'s
# construction (round 9's file is left as it is): every case of rounds 3 to 9,
# then the round 10 cases before the comment checks at the end. The same cases, as
# pytest, are `tests/test_t502r10_scratch_1115.py` (`tests/run.sh -k t502r10`).
#
#   bash scratch/t502r10-proof-1115.sh <lanes-edit.sh to test> [<work dir>]
#
# Run it hermetically: `env -i HOME=$HOME PATH=/usr/bin:/bin TMPDIR=/tmp bash ...`.
# The earlier headers follow; the round 7 hooks are described above `r7_copy`, the
# round 8 ones above `r8_copy`, the round 9 ones above `r9_copy` and the round 10
# ones above `r10_copy`. Cases named `r10-red-*` fail at `6253b0ed` (part 41) and
# pass at part 47; `r10-control-*` pass at both; every case of rounds 7 to 9 still
# passes at part 47. The four `r10-red-p48-*` cases (BRIEF-T502P48-1115.md) also
# fail at `1c61300e` (part 47), and pass at part 48.
#
# Each case runs the given `lanes-edit.sh` on a record written directly into a
# sandbox of its own (HOME, CLAUDE_CONFIG_DIR, XDG_STATE_HOME, env -i), with a
# stand-in body through `LANES_BIND_BODY` (R48), or runs the real body with a
# stand-in `lane-start`. Where the outer's own `pid_start_of $$` must exit 2, it
# runs a TEST-ONLY COPY whose `pid_start_of` answers 2 for the caller's own
# pid (lane 3's point 23: no seam in the shipped script). A change inside the
# outer's window is made by a stand-in `awk` or `mktemp` first on PATH: after
# the body has ended (it leaves a trigger file), the first call changes the
# record once, and every call runs the real tool. The S3 cases run the REAL
# outer and the REAL body from a copy of the script beside a stand-in
# `lanes-index` whose lookup answers LR007 `another-write`; the settle fails
# where a stand-in `rm` first on PATH refuses the pending record and runs the
# real `rm` for every other call. The sandbox is left in the work dir; nothing
# is removed.
#
# HERMETIC (CI run 43622597182 failed the pytest form of the S3 cases with
# `lane-start: command not found`, rc 127): PATH is /usr/bin:/bin only, so no
# installed `lane-start` or `lanes-index` is reached; the S3 cases pin
# `LANES_HOST` and `LANES_IN_CONTAINER=0`, so the host `guard_bind_copies`
# compares is the pending record's whatever the runner's `/.dockerenv` and
# `hostname` say (a runner with no `/.dockerenv` read its own `hostname -s`,
# found no copies, and went on to `lane-start`); and `LANES_LANE_START` names
# a stand-in in the box that the cases require was never called.
#
# Prints PASS or FAIL per case and a count; exits 0 only where all pass.
set -u

[ "$#" -ge 1 ] && [ -f "$1" ] || { printf 'usage: %s <lanes-edit.sh> [<work dir>]\n' "$0" >&2; exit 2; }
S="$(cd "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
W="${2:-${TMPDIR:-/tmp}}"
ROOT="$(mktemp -d "$W/t502r10-proof.XXXXXX")" || exit 2
BASE_PATH=/usr/bin:/bin   # nothing installed under /usr/local/bin is ever reached
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

# ---- S3 of lane 3's Codex delta review of spec#47's draft 13 at cd578400 (#165
# 6880978929): at LR007 `another-write` the body's diagnostic says what the
# settle did. The pending record and the copies go only where
# `guard_bind_settle` succeeds, and stay where it fails; the body returns 2 on
# both. THE REAL OUTER RUNS THE REAL BODY, from a copy of the script beside a
# stand-in `lanes-index` whose lookup answers LR007 `another-write`.
WID=11111111-2222-3333-4444-555566667777
GEN=99999999-8888-7777-6666-555544443333
DGST="$(printf 'd%.0s' $(seq 64))"
FILES="$(printf 'e%.0s' $(seq 64))"
S3_REMOVED='its pending record is removed'
S3_KEPT='could not be settled, so it and its copies are kept'

s3_box() {   # <name>
  box "$1"
  PEND="$B/state/openRepoTools/register-pending/$DGST"
  mkdir -p "$B/bin" "$B/state/openRepoTools/register-pending"
  chmod 700 "$B/state/openRepoTools/register-pending"
  cp -- "$S" "$B/bin/lanes-edit.sh"; chmod 755 "$B/bin/lanes-edit.sh"
  printf '#!/bin/bash\nprintf "ERROR:  LR007: another-write\\nDETAIL:  another-write\\n" >&2\nexit 2\n' > "$B/bin/lanes-index"
  chmod 755 "$B/bin/lanes-index"
  printf '#!/bin/bash\n: > %q\nexit 99\n' "$B/lane-start-called" > "$B/bin/lane-start"
  chmod 755 "$B/bin/lane-start"
  record
  printf '%s\n' "write_id=$WID" "generation=$GEN" not_after=1794700000 write_lane=repoA-2 \
    "args_sha256=$DGST" ended_utc=2026-01-01T00:00:00Z >> "$REC"
  printf '%s\n' format=1 "write_id=$WID" "generation=$GEN" lane=repoA-2 "session=$U" verb=start-record \
    "args_sha256=$DGST" 'cmdline=lanes-edit.sh start-record repoA-3' created_utc=2026-11-14T00:00:00Z \
    updated_utc=2026-11-14T00:00:01Z pid=999999 host=Eagle container=g-box attempts=1 \
    "call=1 0 1794700000 $FILES $B/state/openRepoTools/register-writes/$DGST/r/c" > "$PEND"
  chmod 600 "$PEND"
}

s3_refuse_rm() {   # a stand-in `rm`: the pending record is refused, every other call is the real one
  s3_real="$(PATH="$BASE_PATH" command -v rm)"
  {
    printf '#!/bin/bash\nfor a in "$@"; do\n  case "$a" in */register-pending/%s) exit 1 ;; esac\ndone\n' "$DGST"
    printf 'exec %q "$@"\n' "$s3_real"
  } > "$B/fakes/rm"
  chmod 755 "$B/fakes/rm"
}

s3_outer() {   # the REAL outer and the REAL body: `guard-bind <uuid>`, its output in the attempt's `.out`
  ORC=0
  run_env LANES_HOST=Eagle LANES_IN_CONTAINER=0 LANES_LANE_START="$B/bin/lane-start" LANES_BIND_BOUND_S=60 \
    timeout 120 bash "$B/bin/lanes-edit.sh" guard-bind "$U" </dev/null >>"$OUT" 2>&1 || ORC=$?
  SAID="$(cat -- "$OUT" 2>/dev/null)"
}

s3_state() { printf 'rc=%s mode=%s rc-key=%s write_id=%s pending=%s lane-start=%s why=[%s]' "$ORC" "$(get mode)" "$(get rc)" \
  "$(get write_id)" "$([ -e "$PEND" ] && echo kept || echo gone)" "$([ -e "$B/lane-start-called" ] && echo CALLED || echo not-called)" "$(get why)"; }

# RED: a settle that FAILS. Behaviour as lane 3 rules it: the body's 2 ends the
# outer's outcome `bind-failed rc=2`, the pending record is still there, and
# the copies are in the outcome. The diagnostic, which is what was false, does
# not claim the removal and says the record was not settled and is kept.
s3_box s3-settle-fails; s3_refuse_rm
s3_outer
S3_WHY="$(get why)"
case "$S3_WHY" in *"$S3_REMOVED"*) s3_claims=1 ;; *) s3_claims=0 ;; esac
case "$S3_WHY" in *"$S3_KEPT"*) s3_says=1 ;; *) s3_says=0 ;; esac
case "$SAID" in *"$S3_REMOVED"*) s3_out_claims=1 ;; *) s3_out_claims=0 ;; esac
if [ "$ORC" = 0 ] && [ "$(get mode)" = bind-failed ] && [ "$(get rc)" = 2 ] && [ -e "$PEND" ] &&
   [ ! -e "$B/lane-start-called" ] && [ "$(get write_id)" = "$WID" ] && [ "$s3_claims" = 0 ] && [ "$s3_out_claims" = 0 ] && [ "$s3_says" = 1 ]; then
  ok s3-settle-fails-diagnostic-does-not-claim-the-removal-pending-record-and-copies-kept
else bad s3-settle-fails-diagnostic-does-not-claim-the-removal-pending-record-and-copies-kept \
  "$(s3_state) claims-removal=$s3_claims says-kept=$s3_says out-claims-removal=$s3_out_claims"; fi

# CONTROL: a settle that SUCCEEDS. The pending record is gone, the copies go
# with it, and the diagnostic says so, as it has.
s3_box s3-settle-succeeds
s3_outer
S3_WHY="$(get why)"
case "$S3_WHY" in *"$S3_REMOVED, and the next"*"binds anew"*) s3_says=1 ;; *) s3_says=0 ;; esac
case "$S3_WHY" in *"could not be settled"*) s3_denies=1 ;; *) s3_denies=0 ;; esac
if [ "$ORC" = 0 ] && [ "$(get mode)" = bind-failed ] && [ "$(get rc)" = 2 ] && [ ! -e "$PEND" ] &&
   [ ! -e "$B/lane-start-called" ] && ! has write_id && [ "$s3_says" = 1 ] && [ "$s3_denies" = 0 ]; then
  ok s3-control-settle-succeeds-record-gone-copies-gone-diagnostic-says-removed
else bad s3-control-settle-succeeds-record-gone-copies-gone-diagnostic-says-removed \
  "$(s3_state) says-removed=$s3_says says-unsettled=$s3_denies"; fi

# ---- ROUND 4: T502's parts 16 to 19, lane 3's Codex code review of `12eddddf`
# (report lane5-code-12eddddf-88b50886.md, sha256 caa3641e; opensoft/
# openRepoTools#165 6882203066; lane 3's routing, not Brett's). Findings 1 and
# 4 are the behaviour, 8 and 10 the NITs; finding 5 is part 14's, proved above.
#
# EVERY CASE RUNS A TEST-ONLY COPY of the script under test (lane 3's point 23:
# no seam in the shipped script), made by `r4_copy` with three hooks, each
# anchored on one line that every version has once:
#   * the `guard-bind` arm answers `guard-bind --t502r4-rewrite <args>` with
#     `guard_bind_rewrite <args>` and its code, and `--t502r4-index-ok <n>`
#     with `guard_bind_index_ok`;
#   * a `printf` function in front of `guard_bind_rewrite`, which fails the
#     `T502R4_FAIL_PRINTF_N`th call made from `guard_bind_rewrite` (only from
#     its `--own` call where `T502R4_ONLY_OWN=1`) and runs the builtin for every
#     other, so one write fails while the later ones succeed, as in the
#     review's probe;
#   * the line after the rewrite's `-e` test moves the record away where
#     `T502R4_VANISH` says (`any`, or `own` for a `--own` call only), the
#     record that goes between the test and the open.
r4_copy() {
  r4_c="$B/lanes-edit-r4.sh"
  {
    printf '%s\n' 'printf() {' \
      '  if [ -n "${T502R4_FAIL_PRINTF_N:-}" ] && [ "${FUNCNAME[1]-}" = guard_bind_rewrite ] &&' \
      '     { [ "${T502R4_ONLY_OWN:-}" != 1 ] || [ "${gbw_own-}" = 1 ]; }; then' \
      '    T502R4_N=$(( ${T502R4_N:-0} + 1 ))' \
      '    [ "$T502R4_N" != "$T502R4_FAIL_PRINTF_N" ] || return 1' \
      '  fi' \
      '  builtin printf "$@"' \
      '}'
  } > "$B/hook-printf.sh"
  printf '%s\n' '        case "${T502R4_VANISH:-}:${gbw_own-}" in any:*|own:1) mv -f -- "$gbw_f" "$gbw_f.gone" ;; esac' > "$B/hook-vanish.sh"
  {
    printf '%s\n' '    if [ "${1-}" = --t502r4-rewrite ]; then shift; guard_bind_rewrite "$@"; echo "rewrite-rc=$?"; exit 0; fi'
    printf '%s\n' '    if [ "${1-}" = --t502r4-index-ok ]; then if guard_bind_index_ok "${2-}"; then echo ok; else echo refused; fi; exit 0; fi'
  } > "$B/hook-arm.sh"
  awk -v pf="$B/hook-printf.sh" -v vn="$B/hook-vanish.sh" -v am="$B/hook-arm.sh" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    index($0, "guard_bind_rewrite() {") == 1 { cat(pf); a++ }
    { print }
    $0 == "  guard-bind)" { cat(am); b++ }
    $0 == "      if [ -e \"$gbw_f\" ]; then" { cat(vn); c++ }
    END { exit (a == 1 && b == 1 && c == 1 ? 0 : 1) }' "$S" > "$r4_c" || printf 'r4_copy: an anchor was not found exactly once\n' >&2
  chmod 755 "$r4_c"
}

r4_temps() { ls -A "$B" | grep '^\.rec4\.' || :; }

r4_rewrite() {   # <env assignments, one word each, or ''> <guard_bind_rewrite's arguments>
  r4_e="$1"; shift
  # shellcheck disable=SC2086
  RW_OUT="$(run_env $r4_e bash "$B/lanes-edit-r4.sh" guard-bind --t502r4-rewrite "$@" 2>/dev/null)"
  RW_RC="${RW_OUT##*rewrite-rc=}"
}

r4_rec4() {   # the record the direct cases rewrite
  R4="$B/rec4"
  printf '%s\n' mode=binding keep1=a keep2=b keep3=c > "$R4"
  R4_WANT="$(printf '%s\n' mode=bound keep1=a keep2=b keep3=c rc=0)"
  R4_WAS="$(cat -- "$R4")"
}

r4_unchanged() { [ -e "$R4" ] && [ "$(cat -- "$R4")" = "$R4_WAS" ]; }

# FINDING 1: a write that fails is a 1, wherever it is, and the record is left
# alone. The review's probe: only the FIRST output printf fails, the rest work.
for r4_n in 1 3; do
  box "r4-f1-printf-$r4_n"; r4_copy; r4_rec4
  r4_rewrite "T502R4_FAIL_PRINTF_N=$r4_n" "$R4" "mode rc" mode=bound rc=0
  if [ "$RW_RC" = 1 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok "r4-f1-write-number-$r4_n-fails-result-1-record-unchanged"
  else bad "r4-f1-write-number-$r4_n-fails-result-1-record-unchanged" "rc=$RW_RC record=[$(cat -- "$R4" 2>/dev/null | tr '\n' ' ')] temps=[$(r4_temps)]"; fi
done

# CONTROLS: the LAST write failing was already a 1 (the loop's status), and a
# rewrite where nothing fails is the same bytes as ever.
box r4-f1-control-last-write; r4_copy; r4_rec4
r4_rewrite "T502R4_FAIL_PRINTF_N=5" "$R4" "mode rc" mode=bound rc=0
if [ "$RW_RC" = 1 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r4-f1-control-last-write-fails-result-1-record-unchanged
else bad r4-f1-control-last-write-fails-result-1-record-unchanged "rc=$RW_RC record=[$(cat -- "$R4" 2>/dev/null | tr '\n' ' ')] temps=[$(r4_temps)]"; fi

box r4-f1-control-clean; r4_copy; r4_rec4
r4_rewrite '' "$R4" "mode rc" mode=bound rc=0
if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$R4_WANT" ] && [ -z "$(r4_temps)" ]; then ok r4-f1-control-no-failure-written-as-ever
else bad r4-f1-control-no-failure-written-as-ever "rc=$RW_RC record=[$(cat -- "$R4" 2>/dev/null | tr '\n' ' ')] temps=[$(r4_temps)]"; fi

# THE LINES OF A RECORD ARE THE SAME BYTES: no final newline, a blank line, a
# line with no `=`.
for r4_odd in nofinalnl blank noequals; do
  box "r4-f1-control-$r4_odd"; r4_copy; R4="$B/rec4"
  case "$r4_odd" in
    nofinalnl) printf 'mode=binding\nkeep1=a\nkeep2=b\nkeep3=c' > "$R4" ;;
    blank)     printf 'mode=binding\n\nkeep1=a\n' > "$R4" ;;
    noequals)  printf 'mode=binding\nnoequals\nkeep1=a\n' > "$R4" ;;
  esac
  r4_rewrite '' "$R4" "mode rc" mode=bound rc=0
  case "$r4_odd" in
    nofinalnl) r4_want="$(printf 'mode=bound\nkeep1=a\nkeep2=b\nkeep3=c\nrc=0\n')" ;;
    blank)     r4_want="$(printf 'mode=bound\n\nkeep1=a\nrc=0\n')" ;;
    noequals)  r4_want="$(printf 'mode=bound\nnoequals\nkeep1=a\nrc=0\n')" ;;
  esac
  if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$r4_want" ]; then ok "r4-f1-control-record-with-$r4_odd-rewritten-as-ever"
  else bad "r4-f1-control-record-with-$r4_odd-rewritten-as-ever" "rc=$RW_RC record=[$(cat -- "$R4" 2>/dev/null | tr '\n' ' ')]"; fi
done

# FINDING 4: under `--own`, a record that goes between the `-e` and the open is
# a 2, nothing written and nothing made; where it is still there and cannot be
# read it is a 1; without `--own` it stays a 1.
box r4-f2-vanish-own; r4_copy; r4_rec4
r4_rewrite "T502R4_VANISH=own" --own "$R4" "mode rc" mode=bound rc=0
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ "$(cat -- "$R4.gone" 2>/dev/null)" = "$R4_WAS" ] && [ -z "$(r4_temps)" ]; then
  ok r4-f2-own-record-gone-at-the-open-result-2-nothing-made
else bad r4-f2-own-record-gone-at-the-open-result-2-nothing-made "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)]"; fi

box r4-f2-control-vanish-not-own; r4_copy; r4_rec4
r4_rewrite "T502R4_VANISH=any" "$R4" "mode rc" mode=bound rc=0
if [ "$RW_RC" = 1 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ]; then ok r4-f2-control-without-own-record-gone-at-the-open-stays-result-1
else bad r4-f2-control-without-own-record-gone-at-the-open-stays-result-1 "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)]"; fi

box r4-f2-control-absent-own; r4_copy; R4="$B/rec4"
r4_rewrite '' --own "$R4" "mode rc" mode=bound rc=0
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ]; then ok r4-f2-control-own-record-absent-from-the-start-result-2
else bad r4-f2-control-own-record-absent-from-the-start-result-2 "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)]"; fi

if [ "$(id -u)" = 0 ]; then printf 'SKIP r4-f2-control-own-record-there-but-unreadable-result-1 (runs as root, which reads any file)\n'
else
  box r4-f2-control-unreadable-own; r4_copy; r4_rec4; chmod 000 "$R4"
  r4_rewrite '' --own "$R4" "mode rc" mode=bound rc=0
  chmod 600 "$R4"
  if [ "$RW_RC" = 1 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r4-f2-control-own-record-there-but-unreadable-result-1
  else bad r4-f2-control-own-record-there-but-unreadable-result-1 "rc=$RW_RC record=[$(cat -- "$R4" 2>/dev/null | tr '\n' ' ')] temps=[$(r4_temps)]"; fi
fi

# THE SAME TWO, THROUGH THE REAL OUTER with a stand-in body: its `--own`
# rewrite's 1 is the outer's exit 1 with the record still the outer's own
# `binding` and the outcome in the `.out` alone; its 2 is the outer's exit 0,
# the outcome in the `.out` alone, whatever became of the record.
r4_outer() {   # <env assignments, one word each>
  ORC=0
  # shellcheck disable=SC2086
  run_env LANES_BIND_BODY="$STUB" $1 timeout 60 bash "$B/lanes-edit-r4.sh" guard-bind "$U" </dev/null >>"$OUT" 2>&1 || ORC=$?
  SAID="$(cat -- "$OUT" 2>/dev/null)"
}

box r4-f1-outer-a-write-fails; record; r4_copy; body - 0 ''
r4_outer "T502R4_FAIL_PRINTF_N=3 T502R4_ONLY_OWN=1"
if [ "$ORC" = 1 ] && [ "$(get mode)" = binding ] && has pid && ! has rc && ! has ended_utc && [ ! -e "$FACTS" ] &&
   said_has "the outcome could not be written"; then
  ok r4-f1-outer-a-failed-write-is-exit-1-record-still-binding-outcome-in-out-only
else bad r4-f1-outer-a-failed-write-is-exit-1-record-still-binding-outcome-in-out-only "$(state) lines=$(wc -l < "$REC")"; fi

box r4-f2-outer-record-gone-at-the-open; record; r4_copy; body - 0 ''
r4_outer "T502R4_VANISH=own"
if [ "$ORC" = 0 ] && [ ! -e "$REC" ] && [ "$(get mode "$REC.gone")" = binding ] && [ ! -e "$FACTS" ] && [ -z "$(temps)" ] &&
   said_has "$NOT_OWN"; then
  ok r4-f2-outer-record-gone-at-the-open-is-exit-0-nothing-made-outcome-in-out-only
else bad r4-f2-outer-record-gone-at-the-open-is-exit-0-nothing-made-outcome-in-out-only "rc=$ORC exists=$([ -e "$REC" ] && echo yes || echo no) temps=[$(temps)] said=[$(printf '%s' "$SAID" | tail -n 2 | cut -c1-160 | tr '\n' ' ')]"; fi

# FINDING 8 (NIT): the three comments no longer promise a record "as it was" or
# a change "after this read" left alone. Each block is cut out by its first and
# last line, which every version has once.
r4_block() {   # <first line's start> <last line's start>
  awk -v a="$1" -v z="$2" '!f && index($0, a) == 1 { f = 1 } f { sub(/^[ ]*#[ ]*/, ""); printf "%s ", $0 } f && index($0, z) == 1 { exit }' "$S"
}
r4_hdr="$(r4_block '# WITH `--own`, THE OUTER' 'guard_bind_rewrite() {')"
r4_win="$(r4_block '  # THE WINDOW IS KEPT, AND NARROWED IN CODE' '  gbo_wrc=2')"
r4_n8=1
case "$r4_hdr" in *"1 not, and the record is as it was"*|*"and the record is as it was"*) r4_n8=0 ;; esac
case "$r4_hdr" in *"as another writer may have left it"*) : ;; *) r4_n8=0 ;; esac
case "$r4_hdr" in *"can still be overwritten"*) : ;; *) r4_n8=0 ;; esac
case "$r4_win" in *"a record changed after this read is still left as it is"*) r4_n8=0 ;; esac
case "$r4_win" in *"can still be overwritten"*) : ;; *) r4_n8=0 ;; esac
case "$r4_win" in *"nothing written by this rewrite"*) : ;; *) r4_n8=0 ;; esac
if [ "$r4_n8" = 1 ]; then ok r4-nit8-comments-say-the-rewrite-did-not-change-the-record-and-the-window-can-overwrite
else bad r4-nit8-comments-say-the-rewrite-did-not-change-the-record-and-the-window-can-overwrite "header=[${r4_hdr:0:300}] window=[${r4_win:0:200}]"; fi

# FINDING 10 (NIT): the index predicate spells its digits out; and it is the
# same predicate (a control through the hook).
r4_fn="$(awk '/^guard_bind_index_ok\(\)/ { f = 1 } f { print } f && /^}/ { exit }' "$S")"
case "$r4_fn" in *'[!0123456789]'*) r4_n10=1 ;; *) r4_n10=0 ;; esac
case "$r4_fn" in *'[!0-9]'*) r4_n10=0 ;; esac
if [ "$r4_n10" = 1 ]; then ok r4-nit10-index-predicate-spells-its-digits-out
else bad r4-nit10-index-predicate-spells-its-digits-out "function=[$r4_fn]"; fi

box r4-nit10-control; r4_copy
r4_idx=""
for r4_i in 1 10 123 0 01 1a "" "-1"; do
  r4_idx="$r4_idx[$r4_i]=$(run_env bash "$B/lanes-edit-r4.sh" guard-bind --t502r4-index-ok "$r4_i" 2>/dev/null) "
done
if [ "$r4_idx" = "[1]=ok [10]=ok [123]=ok [0]=refused [01]=refused [1a]=refused []=refused [-1]=refused " ]; then ok r4-nit10-control-index-predicate-answers-as-ever
else bad r4-nit10-control-index-predicate-answers-as-ever "$r4_idx"; fi


# ---- ROUND 5: T502's part 20, choice 1's `mode=allow` record checks every
# write before its `mv`, as part 16 made `guard_bind_rewrite` do (Codex finding
# 1 of lane 3's code review of `12eddddf`, #165 6882203066; T501's check of
# draft 15 against parts 16 to 19, whose :114 was false for this one writer).
#
# THE ANSWER 1 RUNS THROUGH A TEST-ONLY COPY of the script under test (lane 3's
# point 23: no seam in the shipped script), made by `r5_copy` with two hooks,
# each anchored on one line every version has once:
#   * the `guard-bind` arm answers `guard-bind --t502r5-answer <uuid> <lane>
#     <session name> <offer file>` by setting the guard's `G_ID`, `G_LANE` and
#     `G_NAME` and calling `guard_answer <offer file> 1 %1`, the very function
#     the hook's answer reaches, and printing its code;
#   * a `printf` function in front of `guard_answer` fails the
#     `T502R5_FAIL_PRINTF_N`th call it makes with a record line's format (one
#     with an `=`), so one write to the temporary file fails while the later
#     ones succeed, as part 16's proof does for the rewrite.
# Pinned as the part 15 proof is: `LANES_HOST`, `LANES_IN_CONTAINER=0`, and a
# PATH of /usr/bin:/bin with the box's stand-ins first.
r5_copy() {
  r5_c="$B/lanes-edit-r5.sh"
  {
    printf '%s\n' 'printf() {' \
      '  if [ -n "${T502R5_FAIL_PRINTF_N:-}" ] && [ "${FUNCNAME[1]-}" = guard_answer ]; then' \
      '    case "${1-}" in' \
      '      *=*)' \
      '        T502R5_N=$(( ${T502R5_N:-0} + 1 ))' \
      '        [ "$T502R5_N" != "$T502R5_FAIL_PRINTF_N" ] || return 1 ;;' \
      '    esac' \
      '  fi' \
      '  builtin printf "$@"' \
      '}'
  } > "$B/hook5-printf.sh"
  printf '%s\n' '    if [ "${1-}" = --t502r5-answer ]; then G_ID="$2"; G_LANE="$3"; G_NAME="$4"; guard_answer "$5" 1 "%1"; echo "answer-rc=$?"; exit 0; fi' > "$B/hook5-arm.sh"
  awk -v pf="$B/hook5-printf.sh" -v am="$B/hook5-arm.sh" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    index($0, "guard_answer() {") == 1 { cat(pf); a++ }
    { print }
    $0 == "  guard-bind)" { cat(am); b++ }
    END { exit (a == 1 && b == 1 ? 0 : 1) }' "$S" > "$r5_c" || printf 'r5_copy: an anchor was not found exactly once\n' >&2
  chmod 755 "$r5_c"
}

r5_offer() {   # the pending offer the person answers: name-drift, with the bind's output file beside it
  printf '%s\n' mode=name-drift from=repoA-2 to=repoA-3 session=repoA-3 "uuid=$U" \
    utc=2026-11-14T00:00:00Z window=@1 'pane=%1' > "$REC"
  chmod 600 "$REC"
  printf 'an attempt before\n' > "$REC.bind.1.out"
  R5_WAS="$(cat -- "$REC")"
}

r5_answer() {   # <env assignments, one word each, or ''>
  r5_e="$1"
  # shellcheck disable=SC2086
  r5_o="$(run_env LANES_HOST=Eagle LANES_IN_CONTAINER=0 $r5_e bash "$B/lanes-edit-r5.sh" guard-bind --t502r5-answer "$U" repoA-2 repoA-3 "$REC" 2>"$B/r5-err")"
  R5_RC="${r5_o##*answer-rc=}"
  R5_ERR="$(cat -- "$B/r5-err")"
}

r5_temps() { ls -A "$OFF" | grep -F ".$U." | grep '^\.' || :; }

# A WRITE THAT FAILS BEFORE THE LAST ONE: no `mv`, the record as this answer
# found it, the temporary file gone, the offer's `.bind.*` files kept, and the
# guard's refusal with its 2 and its message. The first line, a copied line.
for r5_n in 1 3; do
  box "r5-allow-write-$r5_n-fails"; r5_copy; r5_offer
  r5_answer "T502R5_FAIL_PRINTF_N=$r5_n"
  case "$R5_ERR" in *"the explicit allow could not be recorded"*) r5_says=1 ;; *) r5_says=0 ;; esac
  case "$R5_ERR" in *"ALLOWED:"*) r5_allowed=1 ;; *) r5_allowed=0 ;; esac
  if [ "$R5_RC" = 2 ] && [ "$(cat -- "$REC")" = "$R5_WAS" ] && [ -z "$(r5_temps)" ] && [ -e "$REC.bind.1.out" ] &&
     [ "$r5_says" = 1 ] && [ "$r5_allowed" = 0 ]; then
    ok "r5-choice-1-write-number-$r5_n-fails-refused-2-record-unchanged-temp-gone-bind-files-kept"
  else bad "r5-choice-1-write-number-$r5_n-fails-refused-2-record-unchanged-temp-gone-bind-files-kept" \
    "rc=$R5_RC record=[$(tr '\n' ' ' < "$REC")] temps=[$(r5_temps)] bind-out=$([ -e "$REC.bind.1.out" ] && echo kept || echo GONE) says-refused=$r5_says says-ALLOWED=$r5_allowed"; fi
done

# CONTROLS. The last write failing was already a refusal (the group's status),
# as were a `mktemp` and an `mv` that fail; and an answer 1 where nothing fails
# writes the six lines, moves them into place, takes the `.bind.*` files and
# says it was allowed.
box r5-allow-control-last-write-fails; r5_copy; r5_offer
r5_answer "T502R5_FAIL_PRINTF_N=6"
case "$R5_ERR" in *"the explicit allow could not be recorded"*) r5_says=1 ;; *) r5_says=0 ;; esac
if [ "$R5_RC" = 2 ] && [ "$(cat -- "$REC")" = "$R5_WAS" ] && [ -z "$(r5_temps)" ] && [ -e "$REC.bind.1.out" ] && [ "$r5_says" = 1 ]; then
  ok r5-choice-1-control-last-write-fails-refused-2-record-unchanged
else bad r5-choice-1-control-last-write-fails-refused-2-record-unchanged "rc=$R5_RC record=[$(tr '\n' ' ' < "$REC")] temps=[$(r5_temps)] says-refused=$r5_says"; fi

box r5-allow-control-mktemp-fails; r5_copy; r5_offer
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/mktemp"; chmod 755 "$B/fakes/mktemp"
r5_answer ''
case "$R5_ERR" in *"the explicit allow could not be recorded"*) r5_says=1 ;; *) r5_says=0 ;; esac
if [ "$R5_RC" = 2 ] && [ "$(cat -- "$REC")" = "$R5_WAS" ] && [ -z "$(r5_temps)" ] && [ -e "$REC.bind.1.out" ] && [ "$r5_says" = 1 ]; then
  ok r5-choice-1-control-mktemp-fails-refused-2-record-unchanged
else bad r5-choice-1-control-mktemp-fails-refused-2-record-unchanged "rc=$R5_RC record=[$(tr '\n' ' ' < "$REC")] temps=[$(r5_temps)] says-refused=$r5_says"; fi

box r5-allow-control-mv-fails; r5_copy; r5_offer
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/mv"; chmod 755 "$B/fakes/mv"
r5_answer ''
case "$R5_ERR" in *"the explicit allow could not be recorded"*) r5_says=1 ;; *) r5_says=0 ;; esac
if [ "$R5_RC" = 2 ] && [ "$(cat -- "$REC")" = "$R5_WAS" ] && [ -z "$(r5_temps)" ] && [ -e "$REC.bind.1.out" ] && [ "$r5_says" = 1 ]; then
  ok r5-choice-1-control-mv-fails-refused-2-record-unchanged-temp-gone
else bad r5-choice-1-control-mv-fails-refused-2-record-unchanged-temp-gone "rc=$R5_RC record=[$(tr '\n' ' ' < "$REC")] temps=[$(r5_temps)] says-refused=$r5_says"; fi

box r5-allow-control-success; r5_copy; r5_offer
r5_answer ''
r5_new="$(cat -- "$REC")"
case "$R5_ERR" in *"ALLOWED: this lane/session name mismatch is explicitly allowed"*) r5_allowed=1 ;; *) r5_allowed=0 ;; esac
r5_utc="$(sed -n 's/^utc=//p' "$REC")"
case "$r5_utc" in ????-??-??T??:??:??Z) r5_utc_ok=1 ;; *) r5_utc_ok=0 ;; esac
if [ "$R5_RC" = 2 ] && [ "$(printf '%s\n' "$r5_new" | sed -n '1,5p')" = "$(printf '%s\n' mode=allow from=repoA-2 to=repoA-3 session=repoA-3 "uuid=$U")" ] &&
   [ "$(printf '%s\n' "$r5_new" | wc -l | tr -d ' ')" = 6 ] && [ "$r5_utc_ok" = 1 ] && [ ! -e "$REC.bind.1.out" ] &&
   [ -z "$(r5_temps)" ] && [ "$r5_allowed" = 1 ]; then
  ok r5-choice-1-control-answer-writes-all-six-lines-and-moves-them-into-place
else bad r5-choice-1-control-answer-writes-all-six-lines-and-moves-them-into-place "rc=$R5_RC record=[$(printf '%s' "$r5_new" | tr '\n' ' ')] bind-out=$([ -e "$REC.bind.1.out" ] && echo STILL-THERE || echo gone) temps=[$(r5_temps)] says-ALLOWED=$r5_allowed"; fi


# ---- ROUND 6: T502's part 21, the outer's start rewrite runs only on a record
# that still says `mode=binding`, and where it does not the outer runs nothing
# and returns 2 (lane 5's ruling on lane 2's reader's window, #165 6885568373;
# lane 3's ruling on open point 26, #165 6885378657, as lane 5's brief gives it:
# `guard_offer`'s write is the record's only creation, so a rewrite never makes
# one).
#
# EVERY CASE RUNS A TEST-ONLY COPY (lane 3's point 23: no seam in the shipped
# script): `r6_copy` is round 4's copy, with its rewrite hook, its `printf`
# shim and its vanish hook, plus one hook in the outer, on the line after its
# `gbo_ep=`, which is after its load and before its start rewrite's existence
# test. It stands where a hold would: `T502R6_START=gone` moves the record away
# there, and `T502R6_START=drift` replaces it with a `name-drift` offer, once,
# synchronously, and the outer then goes on to its start rewrite.
r6_copy() {
  r4_copy
  r6_c="$B/lanes-edit-r6.sh"
  printf '%s\n' \
    '  case "${T502R6_START:-}" in' \
    '    gone) mv -f -- "$gbo_f" "$gbo_f.gone" ;;' \
    '    drift) printf "%s\n" mode=name-drift from=repoA-2 to=repoA-3 session=repoA-3 "uuid=$gbo_u" window=@1 pane=%1 > "$gbo_f" ;;' \
    '  esac' > "$B/hook6-start.sh"
  awk -v hk="$B/hook6-start.sh" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    { print }
    $0 == "  gbo_ep=\"${gbo_now%% *}\"" { cat(hk); a++ }
    END { exit (a == 1 ? 0 : 1) }' "$B/lanes-edit-r4.sh" > "$r6_c" || printf 'r6_copy: the gbo_ep anchor was not found exactly once\n' >&2
  chmod 755 "$r6_c"
}

r6_outer() {   # <env assignments, one word each, or ''>
  ORC=0
  # shellcheck disable=SC2086
  run_env LANES_BIND_BODY="$STUB" $1 timeout 60 bash "$B/lanes-edit-r6.sh" guard-bind "$U" </dev/null >>"$OUT" 2>&1 || ORC=$?
  SAID="$(cat -- "$OUT" 2>/dev/null)"
}

R6_NOTE="is gone or no longer says mode=binding"
r6_offer_text() { printf '%s\n' mode=name-drift from=repoA-2 to=repoA-3 session=repoA-3 "uuid=$U" window=@1 'pane=%1'; }

# WHAT IS LEFT, where the outer's start finds its record gone or no longer
# binding: no record made, no temporary file, the body never run (its trigger
# file is never made), no facts file, and in the attempt's `.out` the outer's
# one note and nothing else (it writes nothing there before its start rewrite).
r6_nothing_else() { [ -z "$(temps)" ] && [ ! -e "$TRIG" ] && [ ! -e "$FACTS" ] && [ "$(wc -l < "$OUT" | tr -d ' ')" = 1 ] && said_has "$R6_NOTE" && ! said_has "attempt 1 for transcript"; }

box r6-gone-before-its-start; record; r6_copy; body - 0 ''
r6_outer "T502R6_START=gone"
if [ "$ORC" = 2 ] && [ ! -e "$REC" ] && [ "$(get mode "$REC.gone")" = binding ] && r6_nothing_else; then
  ok r6-gone-before-its-start-exit-2-no-record-made-no-bind
else bad r6-gone-before-its-start-exit-2-no-record-made-no-bind "rc=$ORC record=$([ -e "$REC" ] && echo "MADE, mode=[$(get mode)] keys=[$(grep -c . "$REC")]" || echo none) temps=[$(temps)] body-ran=$([ -e "$TRIG" ] && echo YES || echo no) out-lines=$(wc -l < "$OUT" | tr -d ' ')"; fi

box r6-no-longer-binding-at-its-start; record; r6_copy; body - 0 ''
r6_offer_text > "$B/offer.expected"
r6_outer "T502R6_START=drift"
if [ "$ORC" = 2 ] && [ "$(cat -- "$REC"; printf x)" = "$(cat -- "$B/offer.expected"; printf x)" ] && r6_nothing_else; then
  ok r6-no-longer-binding-at-its-start-exit-2-offer-unchanged-no-bind
else bad r6-no-longer-binding-at-its-start-exit-2-offer-unchanged-no-bind "rc=$ORC record=[$(tr '\n' ' ' < "$REC")] temps=[$(temps)] body-ran=$([ -e "$TRIG" ] && echo YES || echo no) out-lines=$(wc -l < "$OUT" | tr -d ' ')"; fi

# THE OPEN: the record goes between the rewrite's existence test and its open
# (round 4's vanish hook, `any`, which fires in the start rewrite).
box r6-gone-at-the-open-of-its-start; record; r6_copy; body - 0 ''
r6_outer "T502R4_VANISH=any"
if [ "$ORC" = 2 ] && [ ! -e "$REC" ] && [ "$(get mode "$REC.gone")" = binding ] && r6_nothing_else; then
  ok r6-gone-at-the-open-of-its-start-exit-2-no-record-made-no-bind
else bad r6-gone-at-the-open-of-its-start-exit-2-no-record-made-no-bind "rc=$ORC record=$([ -e "$REC" ] && echo MADE || echo none) temps=[$(temps)] body-ran=$([ -e "$TRIG" ] && echo YES || echo no) said=[$(printf '%s' "$SAID" | tail -n 1 | cut -c1-140)]"; fi

# CONTROL: an ordinary start still writes its six keys and the bind runs.
box r6-control-ordinary-start; record; r6_copy; body - 0 ''
r6_outer ''
r6_keys=1
for r6_k in started_utc bound_s bounded deadline_epoch pid pidstart; do has "$r6_k" || r6_keys=0; done
if [ "$ORC" = 0 ] && [ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && [ "$r6_keys" = 1 ] && [ -e "$TRIG" ] && said_has "attempt 1 for transcript"; then
  ok r6-control-ordinary-start-writes-its-six-keys-and-the-bind-runs
else bad r6-control-ordinary-start-writes-its-six-keys-and-the-bind-runs "$(state) six-keys=$r6_keys body-ran=$([ -e "$TRIG" ] && echo yes || echo NO)"; fi

# THE REWRITE'S OWN FLAG, DIRECT, through round 4's hook.
r6_rec() { R4="$B/rec4"; printf '%s\n' "$@" > "$R4"; R4_WAS="$(cat -- "$R4")"; }

box r6-binding-on-binding; r4_copy; r6_rec mode=binding keep=a
r4_rewrite '' --binding "$R4" "pid pidstart" started_utc=2026-11-14T00:00:00Z pid=1234
if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$(printf '%s\n' mode=binding keep=a started_utc=2026-11-14T00:00:00Z pid=1234)" ] && [ -z "$(r4_temps)" ]; then
  ok r6-flag-binding-on-a-binding-record-writes-and-returns-0
else bad r6-flag-binding-on-a-binding-record-writes-and-returns-0 "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)]"; fi

box r6-binding-on-name-drift; r4_copy; r6_rec mode=name-drift keep=a
r4_rewrite '' --binding "$R4" "pid pidstart" started_utc=2026-11-14T00:00:00Z pid=1234
if [ "$RW_RC" = 2 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r6-flag-binding-on-a-name-drift-record-returns-2-unchanged
else bad r6-flag-binding-on-a-name-drift-record-returns-2-unchanged "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)]"; fi

box r6-binding-on-no-mode; r4_copy; r6_rec keep=a other=b
r4_rewrite '' --binding "$R4" "pid pidstart" started_utc=2026-11-14T00:00:00Z pid=1234
if [ "$RW_RC" = 2 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r6-flag-binding-on-a-record-with-no-mode-returns-2-unchanged
else bad r6-flag-binding-on-a-record-with-no-mode-returns-2-unchanged "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)]"; fi

box r6-binding-first-mode-wins; r4_copy; r6_rec mode=name-drift mode=binding
r4_rewrite '' --binding "$R4" "pid pidstart" pid=1234
r6_first_drift="$RW_RC:$(r4_unchanged && echo same || echo changed)"
r6_rec mode=binding mode=name-drift
r4_rewrite '' --binding "$R4" "pid pidstart" pid=1234
if [ "$r6_first_drift" = 2:same ] && [ "$RW_RC" = 0 ]; then ok r6-flag-binding-reads-the-first-mode-line-as-the-loader-does
else bad r6-flag-binding-reads-the-first-mode-line-as-the-loader-does "name-drift-first=$r6_first_drift binding-first-rc=$RW_RC"; fi

box r6-binding-on-absent; r4_copy; R4="$B/rec4"
r4_rewrite '' --binding "$R4" "pid pidstart" started_utc=2026-11-14T00:00:00Z pid=1234
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ]; then ok r6-flag-binding-on-an-absent-record-returns-2-nothing-made
else bad r6-flag-binding-on-an-absent-record-returns-2-nothing-made "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)]"; fi

box r6-binding-gone-at-open; r4_copy; r6_rec mode=binding keep=a
r4_rewrite "T502R4_VANISH=any" --binding "$R4" "pid pidstart" pid=1234
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ]; then ok r6-flag-binding-record-gone-at-the-open-returns-2
else bad r6-flag-binding-record-gone-at-the-open-returns-2 "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)]"; fi

box r6-binding-failed-write; r4_copy; r6_rec mode=binding keep=a
r4_rewrite "T502R4_FAIL_PRINTF_N=2" --binding "$R4" "pid pidstart" started_utc=2026-11-14T00:00:00Z pid=1234
if [ "$RW_RC" = 1 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r6-flag-binding-a-failed-write-returns-1-unchanged
else bad r6-flag-binding-a-failed-write-returns-1-unchanged "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)]"; fi

# CONTROL: without a flag the rewrite is as it was, on a record of any mode.
box r6-control-no-flag; r4_copy; r6_rec mode=name-drift keep=a
r4_rewrite '' "$R4" "pid pidstart" started_utc=2026-11-14T00:00:00Z pid=1234
if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$(printf '%s\n' mode=name-drift keep=a started_utc=2026-11-14T00:00:00Z pid=1234)" ]; then
  ok r6-control-no-flag-rewrites-a-name-drift-record-as-ever
else bad r6-control-no-flag-rewrites-a-name-drift-record-as-ever "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")]"; fi



# ---- ROUND 7: T502's parts 22 to 24, lane 3's ruling 5 and point 26, reopened
# (opensoft/openRepoTools#165 6885771975, taking 6885751796; lane 3's ruling,
# not Brett's). Ruling 5, "No rewrite creates a record": the hook's answer-2
# rewrites (`guard_bind_head_copy`, which wrote c, n_a and w_s_ms into a record
# that was not there, and the rewrite to `binding`) and the back-out write
# nothing where the offer is gone, and the hook's answer is K4's, with "the
# offer was dropped before the bind could be recorded"; `guard_bind_site`'s
# three rewrites write nothing where the record is gone. Point 26, reopened:
# `guard_offer` never writes over a bind record (Codex's review of spec#47's
# draft 16: another invocation installs `binding`, and its outer `bound`, between
# `guard_run`'s read and `guard_offer`'s write).
#
# EVERY CASE RUNS A TEST-ONLY COPY (lane 3's point 23: no seam in the shipped
# script): `r7_copy` is round 6's copy (round 4's three hooks and round 6's), with
# these more, each anchored on one line that beeae571 and the new head both have
# once:
#   * the `guard-bind` arm answers `--t502r7-answer <uuid> <lane> <session> <offer>
#     <prompt>` with `guard_answer` and its code, `--t502r7-site` with
#     `guard_bind_site`, `--t502r7-offer` with the tail `guard_run` ends on
#     (`guard_offer_site` where the script has it, else `guard_offer`, which is
#     what `guard_run` ended on at beeae571) and `--t502r7-offer-only` with
#     `guard_offer`, each printing its code;
#   * the first line of `guard_bind_rewrite` moves the record away, as a drop by
#     another prompt would, where `T502R7_GONE_FROM` names its caller and
#     `T502R7_GONE_NTH` which of that caller's calls: before the existence test
#     (`T502R7_GONE_AT=test`, the default) or, by the line after the test, at
#     the open (`open`);
#   * `T502R7_PUT=<file>` makes that hook put the file in the record's place
#     instead of moving the record away (another invocation's record, made
#     between the hook's read and its write), and `T502R7_C1=gone` or `put` does
#     either for choice 1, on the line before its temporary file;
#   * `T502R7_NOCHILD=1` makes the answer's child unstartable and its `$!` empty,
#     the back-out's one cause;
#   * `T502R7_RACE=<file>` puts that file in place of the record, once, inside
#     `guard_offer`, after the line that reads its `act` and before its create:
#     the window between `guard_run`'s read and `guard_offer`'s write.
# A stand-in `tmux` logs each call, so a rename and its undoing are seen.
r7_copy() {
  R8_COPY=""
  r6_copy
  r7_c="$B/lanes-edit-r7.sh"
  cat > "$B/h7-arm.sh" <<'EOF'
    if [ "${1-}" = --t502r7-answer ]; then G_ID="$2"; G_LANE="$3"; G_NAME="$4"; [ -z "${T502R7_CACHE:-}" ] || SE_CACHE_FILE="$T502R7_CACHE"; guard_answer "$5" "$6" "%1"; echo "answer-rc=$?"; exit 0; fi
    if [ "${1-}" = --t502r7-site ]; then G_ID="$2"; G_LANE="$3"; G_NAME="$4"; G_WINREF=@1; guard_bind_site "$5" "%1"; echo "site-rc=$?"; exit 0; fi
    if [ "${1-}" = --t502r7-offer ]; then
      G_ID="$2"; G_LANE="$3"; G_NAME="$4"; G_SES_LANE="$5"; G_WINREF=@1
      [ "${8-}" != --drop-first ] || guard_offer_drop "$6"
      if declare -F guard_offer_site >/dev/null 2>&1; then guard_offer_site "$6" "%1" "$7"; else guard_offer "$6" "%1"; fi
      echo "offer-rc=$?"; exit 0
    fi
    if [ "${1-}" = --t502r7-offer-only ]; then G_ID="$2"; G_LANE="$3"; G_NAME="$4"; G_SES_LANE="$5"; G_WINREF=@1; guard_offer "$6" "%1"; echo "offer-rc=$?"; exit 0; fi
EOF
  cat > "$B/h7-entry.sh" <<'EOF'
  if [ -n "${T502R7_GONE_FROM:-}" ] && [ "${FUNCNAME[1]-}" = "$T502R7_GONE_FROM" ]; then
    T502R7_CALL=$(( ${T502R7_CALL:-0} + 1 ))
    if [ "$T502R7_CALL" = "${T502R7_GONE_NTH:-1}" ]; then
      T502R7_HIT=1
      if [ "${T502R7_GONE_AT:-test}" = test ]; then
        t7a=("$@"); t7f=""
        while [ "${#t7a[@]}" -gt 0 ]; do
          case "${t7a[0]}" in
            --own|--binding|--exist|--offer) t7a=("${t7a[@]:1}") ;;
            --mode|--match) t7a=("${t7a[@]:2}") ;;
            *) t7f="${t7a[0]}"; break ;;
          esac
        done
        if [ -n "${T502R7_PUT:-}" ]; then cp -p -- "$T502R7_PUT" "$t7f"; else mv -f -- "$t7f" "$t7f.gone"; fi
      fi
    fi
  fi
EOF
  cat > "$B/h7-open.sh" <<'EOF'
        if [ "${T502R7_HIT:-}" = 1 ] && [ "${T502R7_GONE_AT:-}" = open ]; then T502R7_HIT=0; if [ -n "${T502R7_PUT:-}" ]; then cp -p -- "$T502R7_PUT" "$gbw_f"; else mv -f -- "$gbw_f" "$gbw_f.gone"; fi; fi
EOF
  cat > "$B/h7-nochild-a.sh" <<'EOF'
    [ -z "${T502R7_NOCHILD:-}" ] || RESOLVED=/nonexistent-t502r7-no-child
EOF
  cat > "$B/h7-nochild-b.sh" <<'EOF'
    [ -z "${T502R7_NOCHILD:-}" ] || ga_p=''
EOF
  cat > "$B/h7-c1.sh" <<'EOF'
    case "${T502R7_C1:-}" in gone) mv -f -- "$ga_f" "$ga_f.gone" ;; put) cp -p -- "$T502R7_PUT" "$ga_f" ;; esac
EOF
  cat > "$B/h7-race.sh" <<'EOF'
  if [ -n "${T502R7_RACE:-}" ] && mkdir -- "$T502R7_RACE.once" 2>/dev/null; then cp -p -- "$T502R7_RACE" "$go_f"; fi
EOF
  r7_c1a='    ga_t="$(umask 077; mktemp "${ga_f%/*}/.${ga_f##*/}.XXXXXX" 2>/dev/null || printf '"''"')"'   # choice 1's temporary file
  awk -v arm="$B/h7-arm.sh" -v en="$B/h7-entry.sh" -v op="$B/h7-open.sh" -v na="$B/h7-nochild-a.sh" \
      -v nb="$B/h7-nochild-b.sh" -v rc="$B/h7-race.sh" -v c1="$B/h7-c1.sh" -v c1a="$r7_c1a" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    $0 == "    ga_tp=\"${ga_pane:-${TMUX_PANE:-}}\"" { cat(na); a++ }
    $0 == "    case \"$ga_p\" in" { cat(nb); b++ }
    $0 == c1a { cat(c1); g++ }
    { print }
    $0 == "  guard-bind)" { cat(arm); c++ }
    index($0, "guard_bind_rewrite() {") == 1 { cat(en); d++ }
    $0 == "      if [ -e \"$gbw_f\" ]; then" { cat(op); e++ }
    $0 == "  go_act=\"$(guard_offer_act || :)\"" { cat(rc); f++ }
    END { exit (a == 1 && b == 1 && c == 1 && d == 1 && e == 1 && f == 1 && g == 1 ? 0 : 1) }' "$B/lanes-edit-r6.sh" > "$r7_c" ||
    printf 'r7_copy: an anchor was not found exactly once\n' >&2
  chmod 755 "$r7_c"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> %q\nexit 0\n' "$B/tmux-calls" > "$B/fakes/tmux"
  chmod 755 "$B/fakes/tmux"
  printf '#!/bin/bash\nexit 0\n' > "$B/lane-start-stub"
  chmod 755 "$B/lane-start-stub"
  body - 0 ''
}

r7_run() {   # <env assignments, one word each, or ''> <the hook arm and its arguments>
  r7_e="$1"; shift
  # shellcheck disable=SC2086
  r7_o="$(run_env LANES_HOST=Eagle LANES_IN_CONTAINER=0 LANES_LANE_START="$B/lane-start-stub" LANES_BIND_BODY="$STUB" \
    $r7_e bash "${R8_COPY:-$B/lanes-edit-r7.sh}" guard-bind "$@" 2>"$B/r7-err")"
  R7_RC="${r7_o##*-rc=}"
  R7_ERR="$(cat -- "$B/r7-err")"
  # THE ANSWER'S DETACHED OUTER, where one was started, is waited for, never
  # killed: nothing of this case is running when the next begins.
  r7_i=0
  while pgrep -f -- "$B/" >/dev/null 2>&1 && [ "$r7_i" -lt 200 ]; do sleep 0.2; r7_i=$((r7_i + 1)); done
  R7_LEFT="$(pgrep -f -- "$B/" 2>/dev/null | wc -l | tr -d ' ')"
}

r7_err_has() { case "$R7_ERR" in *"$1"*) return 0 ;; esac; return 1; }
r7_tmux() { tr '\n' ';' < "$B/tmux-calls" 2>/dev/null || :; }
r7_save() { cp -p -- "${1:-$REC}" "$B/was"; }
r7_same() { cmp -s -- "$B/was" "${1:-$REC}"; }
r7_ls() { ls -A "$OFF" | tr '\n' ' '; }
r7_state() { printf 'rc=%s left=%s record=%s offers=[%s] tmux=[%s] err=[%s]' "$R7_RC" "$R7_LEFT" \
  "$([ -e "$REC" ] && echo "there,mode=$(get mode)" || echo none)" "$(r7_ls)" "$(r7_tmux)" \
  "$(printf '%s' "$R7_ERR" | tail -n 2 | cut -c1-110 | tr '\n' '|')"; }

r7_now() { date -u +%s; }

# THE RECORDS. Each writes to its target ($1, the record by default).
r7_offer_rec() {   # <target> <session> <to>: a pending name-drift offer
  printf '%s\n' mode=name-drift from=repoA-2 "to=${3:-repoA-3}" "session=${2:-repoA-3}" "uuid=$U" \
    utc=2026-11-14T00:00:00Z window=@1 'pane=%1' > "${1:-$REC}"
  chmod 600 "${1:-$REC}"
}
r7_bind_rec() {   # <target> <mode> <host>: a record of answer 2's bind
  rb_t="${1:-$REC}"; rb_m="$2"; rb_dl="$(( $(r7_now) + 505 ))"
  [ "${4:-}" != past ] || rb_dl="$(( $(r7_now) - 1000 ))"
  printf '%s\n' "mode=$rb_m" from=repoA-2 to=repoA-3 session=repoA-3 "uuid=$U" window=@1 'pane=%1' \
    utc=2026-11-14T00:00:00Z bind=1 started_utc=2026-11-14T00:00:00Z bound_s=500 bounded=yes \
    "deadline_epoch=$rb_dl" "host=${3:-Eagle}" container=g-box "out=$OUT" detach=setsid > "$rb_t"
  case "$rb_m" in
    bound)       printf '%s\n' rc=0 ended_utc=2026-11-14T00:00:30Z >> "$rb_t" ;;
    bind-failed) printf '%s\n' rc=5 'why=the stand-in refused' ended_utc=2026-11-14T00:00:30Z >> "$rb_t" ;;
  esac
  chmod 600 "$rb_t"
}
r7_allow_rec() {   # <target> <session>
  printf '%s\n' mode=allow from=repoA-2 to=repoA-3 "session=${2:-repoA-3}" "uuid=$U" utc=2026-11-14T00:00:00Z > "${1:-$REC}"
  chmod 600 "${1:-$REC}"
}
r7_cache() {   # the prefetch's `.head`, which `guard_bind_head_copy` copies from
  printf '%s\n' c=3 n_a=2 w_s_ms=40 > "$B/cache.head"
}

r7_answer() {   # <env assignments, one word each, or ''>: the person answers 2
  r7_run "$1" --t502r7-answer "$U" repoA-2 repoA-3 "$REC" 2
}
r7_offer_site() {   # <env assignments> <prompt> [--drop-first]
  r7_run "$1" --t502r7-offer "$U" repoA-2 repoA-3 repoA-3 "$REC" "$2" ${3:+"$3"}
}
r7_offer_only() {   # <env assignments>
  r7_run "$1" --t502r7-offer-only "$U" repoA-2 repoA-3 repoA-3 "$REC"
}

R7_DROPPED="the offer was dropped before the bind could be recorded"
R7_ASKED="This prompt is paused until you choose how to repair"

# WHAT IS LEFT where the hook's answer finds the offer gone (result (A), K4's
# path): the original only in `.gone`, nothing made (no record, no temporary file,
# no `.bind.*` file: no outer was started), the window renamed to <to> and back
# to <from>, no BINDING said, and the exit 2.
r7_a_state() { [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ "$(ls -A "$OFF")" = "$U.gone" ] && r7_same "$REC.gone" &&
  [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] && ! r7_err_has "BINDING:"; }

# ---- RULING 5, THE HOOK'S ANSWER 2. Three callers, each with the offer gone.
box r7-answer-head-copy-gone; r7_copy; r7_offer_rec; r7_save; r7_cache
r7_answer "T502R7_CACHE=$B/cache T502R7_GONE_FROM=guard_bind_head_copy"
if r7_a_state && r7_err_has "$R7_DROPPED" && ! r7_err_has "could not be recorded in"; then
  ok r7-red-answer-2-head-copy-offer-gone-refused-nothing-made-window-back
else bad r7-red-answer-2-head-copy-offer-gone-refused-nothing-made-window-back "$(r7_state)"; fi

box r7-answer-binding-rewrite-gone; r7_copy; r7_offer_rec; r7_save
r7_answer "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1"
if r7_a_state && r7_err_has "$R7_DROPPED" && ! r7_err_has "could not be recorded in"; then
  ok r7-red-answer-2-binding-rewrite-offer-gone-refused-nothing-made-window-back
else bad r7-red-answer-2-binding-rewrite-offer-gone-refused-nothing-made-window-back "$(r7_state)"; fi

box r7-answer-binding-rewrite-gone-at-open; r7_copy; r7_offer_rec; r7_save
r7_answer "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1 T502R7_GONE_AT=open"
if r7_a_state && r7_err_has "$R7_DROPPED" && ! r7_err_has "could not be recorded in"; then
  ok r7-red-answer-2-binding-rewrite-offer-gone-at-the-open-refused-nothing-made-window-back
else bad r7-red-answer-2-binding-rewrite-offer-gone-at-the-open-refused-nothing-made-window-back "$(r7_state)"; fi

# THE BACK-OUT, where no child could be started: the offer is gone, so there is
# nothing to back out, nothing is written, and the refusal says so. The one
# record the answer made, `binding`, is the one the hook moved away.
box r7-backout-gone; r7_copy; r7_offer_rec
r7_answer "T502R7_NOCHILD=1 T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=2"
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$REC" ] && [ "$(get mode "$REC.gone")" = binding ] &&
   [ "$(r7_ls)" = "$U.bind.1.out $U.gone " ] && [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] &&
   r7_err_has "the offer was dropped or changed meanwhile, so there is none of this answer's to keep" && ! r7_err_has "The offer is KEPT"; then
  ok r7-red-answer-2-back-out-offer-gone-writes-nothing-says-dropped-window-back
else bad r7-red-answer-2-back-out-offer-gone-writes-nothing-says-dropped-window-back "$(r7_state)"; fi

# CONTROLS: the back-out where the offer is there goes back to the question it
# was (the bind keys dropped), says it is KEPT, and renames the window back; an
# ordinary answer 2 binds, the window stays renamed, and the outer ends bound,
# with or without the prefetch's keys.
box r7-control-backout-kept; r7_copy; r7_offer_rec
r7_answer "T502R7_NOCHILD=1"
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ "$(get mode)" = name-drift ] && ! has bind && ! has host && ! has out &&
   [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] && r7_err_has "The offer is KEPT: answer"; then
  ok r7-control-back-out-offer-there-goes-back-to-the-question-and-is-kept
else bad r7-control-back-out-offer-there-goes-back-to-the-question-and-is-kept "$(r7_state)"; fi

box r7-control-answer-2-binds; r7_copy; r7_offer_rec; : > "$B/stub-body"; body - 0 ''
r7_answer ''
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && [ "$(get bind)" = 1 ] &&
   has pid && [ -e "$OUT" ] && [ -e "$TRIG" ] && [ "$(r7_tmux)" = "rename-window repoA-3;" ] && r7_err_has "BINDING: this window is now named repoA-3"; then
  ok r7-control-ordinary-answer-2-binds-window-stays-renamed-outer-ends-bound
else bad r7-control-ordinary-answer-2-binds-window-stays-renamed-outer-ends-bound "$(r7_state) mode=$(get mode) rc-key=$(get rc) trig=$([ -e "$TRIG" ] && echo yes || echo no)"; fi

box r7-control-answer-2-binds-with-head; r7_copy; r7_offer_rec; r7_cache; body - 0 ''
r7_answer "T502R7_CACHE=$B/cache"
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && [ "$(get c)" = 3 ] &&
   [ "$(get n_a)" = 2 ] && [ "$(get w_s_ms)" = 40 ] && [ "$(r7_tmux)" = "rename-window repoA-3;" ] && r7_err_has "BINDING: this window is now named repoA-3"; then
  ok r7-control-ordinary-answer-2-binds-and-copies-the-prefetch-keys
else bad r7-control-ordinary-answer-2-binds-and-copies-the-prefetch-keys "$(r7_state) c=$(get c) n_a=$(get n_a) w_s_ms=$(get w_s_ms)"; fi


# ---- THE HOOK'S OWN WRITES REQUIRE THE OFFER (lane 5's rule for them, `--offer`,
# which lane 3 confirmed in #165 6886113842): the record is not gone but another
# invocation has made it a bind record, or an allowance, between the hook's read
# and its write. The write is not made, and that record is left byte for byte and
# answered as the guard's first read answers it.
r7_put() {   # <mode>: the record another invocation made, in a file of its own
  r7_bind_rec "$B/put" "$1"
  cp -p -- "$B/put" "$B/was"
}
r7_put_state() { r7_same && [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ]; }

r7_envfor() {   # <head-copy | binding-rewrite>: after the box is made, since it names the box's cache
  case "$1" in
    head-copy) printf '%s' "T502R7_CACHE=$B/cache T502R7_GONE_FROM=guard_bind_head_copy" ;;
    binding-rewrite) printf '%s' "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1" ;;
  esac
}
for r7_where in head-copy binding-rewrite; do
  box "r7-put-binding-$r7_where"; r7_copy; r7_offer_rec; r7_cache; r7_put binding
  r7_answer "$(r7_envfor "$r7_where") T502R7_PUT=$B/put"
  if r7_put_state && [ "$(r7_ls)" = "$U " ] && [ "$(r7_tmux)" = "rename-window repoA-3;" ] &&
     r7_err_has "BINDING IN PROGRESS" && ! r7_err_has "BINDING: this window is now named"; then
    ok "r7-red-answer-2-$r7_where-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress"
  else bad "r7-red-answer-2-$r7_where-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress" \
    "$(r7_state) same=$(r7_same && echo yes || echo NO) out=$([ -e "$OUT" ] && echo STARTED || echo none)"; fi

  box "r7-put-bound-$r7_where"; r7_copy; r7_offer_rec; r7_cache; r7_put bound
  r7_answer "$(r7_envfor "$r7_where") T502R7_PUT=$B/put"
  if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ] && [ -z "$(r7_ls)" ] && [ "$(r7_tmux)" = "rename-window repoA-3;" ] &&
     r7_err_has "MOVED: this window is lane repoA-3" && ! r7_err_has "BINDING: this window is now named"; then
    ok "r7-red-answer-2-$r7_where-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it-and-no-outer-started"
  else bad "r7-red-answer-2-$r7_where-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it-and-no-outer-started" \
    "$(r7_state) out=$([ -e "$OUT" ] && echo STARTED || echo none)"; fi

  box "r7-put-bind-failed-$r7_where"; r7_copy; r7_offer_rec; r7_cache; r7_put bind-failed
  r7_answer "$(r7_envfor "$r7_where") T502R7_PUT=$B/put"
  if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ] && [ "$(get mode)" = name-drift ] && [ "$(get rc)" = 5 ] && [ "$(get bind)" = 1 ] &&
     [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] && r7_err_has "THE BIND TO LANE repoA-3 FAILED (exit 5)" &&
     ! r7_err_has "BINDING: this window is now named"; then
    ok "r7-red-answer-2-$r7_where-a-bind-failed-record-made-meanwhile-is-answered-as-failed-and-no-outer-started"
  else bad "r7-red-answer-2-$r7_where-a-bind-failed-record-made-meanwhile-is-answered-as-failed-and-no-outer-started" \
    "$(r7_state) out=$([ -e "$OUT" ] && echo STARTED || echo none) rc-key=$(get rc)"; fi

  box "r7-put-allow-$r7_where"; r7_copy; r7_offer_rec; r7_cache; r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"
  r7_answer "$(r7_envfor "$r7_where") T502R7_PUT=$B/put"
  if r7_same && [ "$R7_RC" = 3 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ] && [ "$(r7_ls)" = "$U " ] &&
     [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] && ! r7_err_has "BINDING: this window is now named"; then
    ok "r7-red-answer-2-$r7_where-an-allowance-made-meanwhile-is-left-byte-for-byte-window-back-and-3"
  else bad "r7-red-answer-2-$r7_where-an-allowance-made-meanwhile-is-left-byte-for-byte-window-back-and-3" \
    "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi
done

# A record that says anything else is "changed", not "dropped", and is (A) too.
box r7-put-junk-binding-rewrite; r7_copy; r7_offer_rec; printf '%s\n' mode=weird keep=a > "$B/put"; cp -p -- "$B/put" "$B/was"
r7_answer "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1 T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ] && [ "$(r7_ls)" = "$U " ] &&
   [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] &&
   r7_err_has "was changed before the bind could be recorded (it says mode=weird now)" && ! r7_err_has "KEPT"; then
  ok r7-red-answer-2-a-record-with-another-mode-is-left-says-changed-window-back
else bad r7-red-answer-2-a-record-with-another-mode-is-left-says-changed-window-back "$(r7_state)"; fi

# THE BACK-OUT, where the record is no longer the answer's own binding.
box r7-backout-changed; r7_copy; r7_offer_rec; r7_bind_rec "$B/put" bound; cp -p -- "$B/put" "$B/was"
r7_answer "T502R7_NOCHILD=1 T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=2 T502R7_PUT=$B/put"
# LANE 3's NIT-1 AT PART 62 (#165 6898801339; on the lane 5 coordinator's word):
# another attempt's bind record at the back-out keeps the window, and says so.
if r7_same && [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ "$(r7_tmux)" = "rename-window repoA-3;" ] &&
   r7_err_has "this window keeps the name repoA-3 that this answer gave it" &&
   r7_err_has "the offer was dropped or changed meanwhile, so there is none of this answer's to keep" && ! r7_err_has "The offer is KEPT"; then
  ok r7-red-answer-2-back-out-on-a-record-that-is-no-longer-its-binding-writes-nothing
else bad r7-red-answer-2-back-out-on-a-record-that-is-no-longer-its-binding-writes-nothing "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

# ---- CHOICE 1's ALLOW WRITE (the same rule, confirmed in #165 6886113842): it
# runs only on an offer that is there and still says `name-drift`. Gone: choice
# 1's own failed-write path (exit 2, nothing renamed or written); made a bind
# record meanwhile: left byte for byte and answered as the first read answers it;
# made an allowance meanwhile: left byte for byte and 3.
r7_choice1() {   # <env assignments>
  r7_run "$1" --t502r7-answer "$U" repoA-2 repoA-3 "$REC" 1
}
box r7-choice-1-gone; r7_copy; r7_offer_rec; r7_save
r7_choice1 "T502R7_C1=gone"
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$REC" ] && [ "$(ls -A "$OFF")" = "$U.gone" ] && r7_same "$REC.gone" && [ -z "$(r7_tmux)" ] &&
   r7_err_has "the offer was dropped before the allow could be recorded, so the mismatch remains unapproved. Nothing was renamed or written" &&
   ! r7_err_has "ALLOWED:"; then
  ok r7-red-choice-1-offer-gone-writes-nothing-says-dropped-nothing-renamed
else bad r7-red-choice-1-offer-gone-writes-nothing-says-dropped-nothing-renamed "$(r7_state)"; fi

box r7-choice-1-binding; r7_copy; r7_offer_rec; r7_put binding
r7_choice1 "T502R7_C1=put T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 2 ] && [ "$(r7_ls)" = "$U " ] && [ -z "$(r7_tmux)" ] && r7_err_has "BINDING IN PROGRESS" && ! r7_err_has "ALLOWED:"; then
  ok r7-red-choice-1-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress
else bad r7-red-choice-1-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

box r7-choice-1-bound; r7_copy; r7_offer_rec; r7_put bound
r7_choice1 "T502R7_C1=put T502R7_PUT=$B/put"
if [ "$R7_RC" = 2 ] && [ -z "$(r7_ls)" ] && [ -z "$(r7_tmux)" ] && r7_err_has "MOVED: this window is lane repoA-3" && ! r7_err_has "ALLOWED:"; then
  ok r7-red-choice-1-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it
else bad r7-red-choice-1-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it "$(r7_state)"; fi

box r7-choice-1-allow; r7_copy; r7_offer_rec; r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"
r7_choice1 "T502R7_C1=put T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 3 ] && [ "$(r7_ls)" = "$U " ] && [ -z "$(r7_tmux)" ] && ! r7_err_has "ALLOWED:"; then
  ok r7-red-choice-1-an-allowance-made-meanwhile-is-left-byte-for-byte-and-3
else bad r7-red-choice-1-an-allowance-made-meanwhile-is-left-byte-for-byte-and-3 "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

box r7-control-choice-1; r7_copy; r7_offer_rec
r7_choice1 ''
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = allow ] && [ "$(wc -l < "$REC" | tr -d ' ')" = 6 ] && [ "$(r7_ls)" = "$U " ] && [ -z "$(r7_tmux)" ] &&
   r7_err_has "ALLOWED: this lane/session name mismatch is explicitly allowed"; then
  ok r7-control-ordinary-choice-1-writes-the-allow-and-says-so
else bad r7-control-ordinary-choice-1-writes-the-allow-and-says-so "$(r7_state) mode=$(get mode)"; fi


# ---- RULING 5, `guard_bind_site`'s THREE REWRITES, each with the record gone
# where it comes to rewrite it: nothing is written, the answer is the refusal for
# a record that is not the site's (the prompt not sent, the question asked afresh),
# and there is no rename-back and there are no choices.
r7_site() {   # <env assignments>
  r7_run "$1" --t502r7-site "$U" repoA-2 repoA-3 "$REC"
}
r7_site_gone() { [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$REC" ] && [ "$(r7_ls)" = "$U.gone " ] && r7_same "$REC.gone" &&
  [ -z "$(r7_tmux)" ] && r7_err_has "was gone when it came to be answered, so nothing was written to it" &&
  ! r7_err_has "The offer is KEPT" && ! r7_err_has "Reply \`1\`"; }

box r7-site-bind-failed-gone; r7_copy; r7_bind_rec "$REC" bind-failed; r7_save
r7_site "T502R7_GONE_FROM=guard_bind_site"
if r7_site_gone; then ok r7-red-bind-site-bind-failed-record-gone-nothing-written-refusal-no-rename-no-choices
else bad r7-red-bind-site-bind-failed-record-gone-nothing-written-refusal-no-rename-no-choices "$(r7_state)"; fi

box r7-site-stale-other-host-gone; r7_copy; r7_bind_rec "$REC" binding Other-host past; r7_save
r7_site "T502R7_GONE_FROM=guard_bind_site"
if r7_site_gone; then ok r7-red-bind-site-stale-other-host-record-gone-nothing-written-refusal-no-rename-no-choices
else bad r7-red-bind-site-stale-other-host-record-gone-nothing-written-refusal-no-rename-no-choices "$(r7_state)"; fi

box r7-site-stale-copies-gone; r7_copy; r7_bind_rec "$REC" binding Eagle past; r7_save
r7_site "T502R7_GONE_FROM=guard_bind_site"
if r7_site_gone; then ok r7-red-bind-site-stale-with-copies-record-gone-nothing-written-refusal-no-rename-no-choices
else bad r7-red-bind-site-stale-with-copies-record-gone-nothing-written-refusal-no-rename-no-choices "$(r7_state)"; fi

# CONTROLS: the same three records, there: each is rewritten to the question
# (`mode=name-drift`), the window is renamed back where the site renames it, and
# the choices are printed.
box r7-control-site-bind-failed; r7_copy; r7_bind_rec "$REC" bind-failed
r7_site ''
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = name-drift ] && [ "$(get rc)" = 5 ] && [ "$(get bind)" = 1 ] &&
   [ "$(r7_tmux)" = "rename-window repoA-2;" ] && r7_err_has "THE BIND TO LANE repoA-3 FAILED (exit 5)" && r7_err_has "Reply \`1\`"; then
  ok r7-control-bind-site-bind-failed-rewritten-to-the-question-window-back-choices-printed
else bad r7-control-bind-site-bind-failed-rewritten-to-the-question-window-back-choices-printed "$(r7_state) mode=$(get mode)"; fi

box r7-control-site-stale-other-host; r7_copy; r7_bind_rec "$REC" binding Other-host past
r7_site ''
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = name-drift ] && [ "$(get rc)" = unknown ] && [ -z "$(r7_tmux)" ] &&
   r7_err_has "ON Other-host/g-box IS NO LONGER RUNNING AND LEFT NO OUTCOME" && r7_err_has "Reply \`1\`"; then
  ok r7-control-bind-site-stale-other-host-rewritten-to-the-question-choices-printed
else bad r7-control-bind-site-stale-other-host-rewritten-to-the-question-choices-printed "$(r7_state) mode=$(get mode) rc-key=$(get rc)"; fi

box r7-control-site-stale-copies; r7_copy; r7_bind_rec "$REC" binding Eagle past
mkdir -p "$B/state/openRepoTools/register-pending"
printf '%s\n' format=1 "write_id=$WID" "generation=$GEN" lane=repoA-2 "session=$U" verb=start-record \
  "args_sha256=$DGST" 'cmdline=lanes-edit.sh start-record repoA-3' created_utc=2026-11-14T00:00:00Z \
  updated_utc=2026-11-14T00:00:01Z pid=999999 host=Eagle container=g-box attempts=1 \
  "call=1 0 1794700000 $FILES $B/state/openRepoTools/register-writes/$DGST/r/c" > "$B/state/openRepoTools/register-pending/$DGST"
chmod 600 "$B/state/openRepoTools/register-pending/$DGST"
r7_site ''
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = name-drift ] && [ "$(get rc)" = unknown ] && [ "$(get write_id)" = "$WID" ] &&
   [ "$(r7_tmux)" = "rename-window repoA-2;" ] && r7_err_has "IS NO LONGER RUNNING AND LEFT NO OUTCOME" && r7_err_has "Reply \`1\`"; then
  ok r7-control-bind-site-stale-with-copies-rewritten-to-the-question-with-its-copies
else bad r7-control-bind-site-stale-with-copies-rewritten-to-the-question-with-its-copies "$(r7_state) mode=$(get mode) write_id=$(get write_id)"; fi

# ---- THE REWRITE'S `--exist` FLAG, DIRECT, through round 4's hook, run from the
# box (a version with no such flag would take `--exist` for a file name).
r7_rw() {   # <env assignments, one word each, or ''> <guard_bind_rewrite's arguments>
  r7_re="$1"; shift
  # shellcheck disable=SC2086
  RW_OUT="$(cd "$B" && run_env $r7_re bash "$B/lanes-edit-r7.sh" guard-bind --t502r4-rewrite "$@" 2>/dev/null)"
  RW_RC="${RW_OUT##*rewrite-rc=}"
}
for r7_mode in binding bound bind-failed name-drift allow nomode; do
  box "r7-exist-$r7_mode"; r7_copy; R4="$B/rec4"
  case "$r7_mode" in nomode) printf '%s\n' keep=a other=b > "$R4" ;; *) printf '%s\n' "mode=$r7_mode" keep=a > "$R4" ;; esac
  r7_want="$(cat -- "$R4"; printf '%s\n' pid=1234)"
  r7_rw '' --exist "$R4" "" pid=1234
  if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$r7_want" ] && [ -z "$(r4_temps)" ]; then ok "r7-flag-exist-on-a-$r7_mode-record-writes-and-returns-0"
  else bad "r7-flag-exist-on-a-$r7_mode-record-writes-and-returns-0" "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)] box=[$(ls -A "$B" | grep -c '^--exist$')]"; fi
done

box r7-exist-absent; r7_copy; R4="$B/rec4"
r7_rw '' --exist "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ] && [ ! -e "$B/--exist" ]; then ok r7-flag-exist-on-an-absent-record-returns-2-nothing-made
else bad r7-flag-exist-on-an-absent-record-returns-2-nothing-made "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)] stray=$([ -e "$B/--exist" ] && echo yes || echo no)"; fi

box r7-exist-gone-at-open; r7_copy; r6_rec mode=name-drift keep=a
r7_rw "T502R4_VANISH=any" --exist "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ] && [ ! -e "$B/--exist" ]; then ok r7-flag-exist-record-gone-at-the-open-returns-2-nothing-made
else bad r7-flag-exist-record-gone-at-the-open-returns-2-nothing-made "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) temps=[$(r4_temps)] stray=$([ -e "$B/--exist" ] && echo yes || echo no)"; fi

box r7-exist-failed-write; r7_copy; r6_rec mode=name-drift keep=a
r7_rw "T502R4_FAIL_PRINTF_N=2" --exist "$R4" "" pid=1234
if [ "$RW_RC" = 1 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r7-control-flag-exist-a-failed-write-returns-1-unchanged
else bad r7-control-flag-exist-a-failed-write-returns-1-unchanged "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)]"; fi


for r7_mode in binding bound bind-failed allow nomode; do
  box "r7-offer-flag-$r7_mode"; r7_copy; R4="$B/rec4"
  case "$r7_mode" in nomode) printf '%s\n' keep=a other=b > "$R4" ;; *) printf '%s\n' "mode=$r7_mode" keep=a > "$R4" ;; esac
  R4_WAS="$(cat -- "$R4")"
  r7_rw '' --offer "$R4" "" pid=1234
  if [ "$RW_RC" = 2 ] && r4_unchanged && [ -z "$(r4_temps)" ] && [ ! -e "$B/--offer" ]; then ok "r7-flag-offer-on-a-$r7_mode-record-returns-2-unchanged"
  else bad "r7-flag-offer-on-a-$r7_mode-record-returns-2-unchanged" "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)] stray=$([ -e "$B/--offer" ] && echo yes || echo no)"; fi
done

box r7-offer-flag-name-drift; r7_copy; r6_rec mode=name-drift keep=a
r7_rw '' --offer "$R4" "" pid=1234
if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$(printf '%s\n' mode=name-drift keep=a pid=1234)" ] && [ -z "$(r4_temps)" ] && [ ! -e "$B/--offer" ]; then
  ok r7-flag-offer-on-a-name-drift-record-writes-and-returns-0
else bad r7-flag-offer-on-a-name-drift-record-writes-and-returns-0 "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] stray=$([ -e "$B/--offer" ] && echo yes || echo no)"; fi

box r7-offer-flag-first-mode-wins; r7_copy; r6_rec mode=binding mode=name-drift
r7_rw '' --offer "$R4" "" pid=1234
r7_first="$RW_RC:$(r4_unchanged && echo same || echo changed)"
r6_rec mode=name-drift mode=binding
r7_rw '' --offer "$R4" "" pid=1234
if [ "$r7_first" = 2:same ] && [ "$RW_RC" = 0 ]; then ok r7-flag-offer-reads-the-first-mode-line-as-the-loader-does
else bad r7-flag-offer-reads-the-first-mode-line-as-the-loader-does "binding-first=$r7_first name-drift-first-rc=$RW_RC"; fi

box r7-offer-flag-absent; r7_copy; R4="$B/rec4"
r7_rw '' --offer "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ] && [ ! -e "$B/--offer" ]; then ok r7-flag-offer-on-an-absent-record-returns-2-nothing-made
else bad r7-flag-offer-on-an-absent-record-returns-2-nothing-made "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) stray=$([ -e "$B/--offer" ] && echo yes || echo no)"; fi

box r7-offer-flag-gone-at-open; r7_copy; r6_rec mode=name-drift keep=a
r7_rw "T502R4_VANISH=any" --offer "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && [ ! -e "$R4" ] && [ -z "$(r4_temps)" ] && [ ! -e "$B/--offer" ]; then ok r7-flag-offer-record-gone-at-the-open-returns-2-nothing-made
else bad r7-flag-offer-record-gone-at-the-open-returns-2-nothing-made "rc=$RW_RC exists=$([ -e "$R4" ] && echo yes || echo no) stray=$([ -e "$B/--offer" ] && echo yes || echo no)"; fi

box r7-offer-flag-failed-write; r7_copy; r6_rec mode=name-drift keep=a
r7_rw "T502R4_FAIL_PRINTF_N=2" --offer "$R4" "" pid=1234
if [ "$RW_RC" = 1 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r7-control-flag-offer-a-failed-write-returns-1-unchanged
else bad r7-control-flag-offer-a-failed-write-returns-1-unchanged "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")] temps=[$(r4_temps)]"; fi

# ---- POINT 26, REOPENED: `guard_offer` never writes over a record.
# CODEX'S RACE, by sequence: `guard_run`'s read saw no record; another invocation
# (B) then makes the offer, answers 2, and its outer ends `bound`; and `guard_run`
# (A) goes on to `guard_offer`. B's whole life is the real code, from the hook arm.
r7_b_life() {   # B: the offer, the answer 2 and the outer's outcome
  r7_offer_site '' hello
  r7_answer ''
}

box r7-race-sequence-offer; r7_copy; body - 0 ''
r7_b_life
r7_b_ok="$([ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && echo yes || echo no)"
r7_save
r7_offer_only ''
if [ "$r7_b_ok" = yes ] && [ "$R7_RC" = 3 ] && r7_same && [ -z "$(temps)" ] && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-race-guard-offer-after-the-bind-ended-bound-leaves-the-record-byte-for-byte-and-says-nothing
else bad r7-red-race-guard-offer-after-the-bind-ended-bound-leaves-the-record-byte-for-byte-and-says-nothing \
  "b-ended-bound=$r7_b_ok $(r7_state) same=$(r7_same && echo yes || echo NO) record=[$(tr '\n' ' ' < "$REC" | cut -c1-120)]"; fi

box r7-race-sequence-site; r7_copy; body - 0 ''
r7_b_life
r7_b_ok="$([ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && echo yes || echo no)"
r7_offer_site '' hello
if [ "$r7_b_ok" = yes ] && [ "$R7_RC" = 2 ] && [ ! -e "$REC" ] && r7_err_has "MOVED: this window is lane repoA-3, bound to this session" &&
   r7_err_has "it is the one that hears how the bind ended" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-race-guard-run-after-the-bind-ended-bound-hears-the-outcome-and-asks-nothing
else bad r7-red-race-guard-run-after-the-bind-ended-bound-hears-the-outcome-and-asks-nothing "b-ended-bound=$r7_b_ok $(r7_state)"; fi

# THE WINDOW ITSELF, inside `guard_offer`, between its read of the `act` and its
# create, for each mode a bind leaves: the record is put there by the hook, and
# `guard_offer` returns 3, writes nothing and says nothing.
for r7_mode in binding bound bind-failed allow name-drift; do
  box "r7-window-$r7_mode"; r7_copy
  case "$r7_mode" in
    allow) r7_allow_rec "$B/race-record" ;;
    name-drift) r7_offer_rec "$B/race-record" repoA-9 repoA-9 ;;
    *) r7_bind_rec "$B/race-record" "$r7_mode" ;;
  esac
  cp -p -- "$B/race-record" "$B/was"
  r7_offer_only "T502R7_RACE=$B/race-record"
  if [ "$R7_RC" = 3 ] && r7_same && [ "$(r7_ls)" = "$U " ] && ! r7_err_has "$R7_ASKED" && [ -z "$R7_ERR" ]; then
    ok "r7-red-window-a-$r7_mode-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3"
  else bad "r7-red-window-a-$r7_mode-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3" \
    "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi
done

# AND `guard_run` ANSWERS THE RECORD THAT IS THERE as its first read would, for
# each bind mode, with nothing of this prompt's offer written.
box r7-site-binding; r7_copy; r7_bind_rec "$REC" binding; r7_save
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "BINDING IN PROGRESS" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-guard-run-on-a-binding-record-says-in-progress-and-leaves-it
else bad r7-red-guard-run-on-a-binding-record-says-in-progress-and-leaves-it "$(r7_state)"; fi

box r7-site-bound; r7_copy; r7_bind_rec "$REC" bound
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && [ ! -e "$REC" ] && r7_err_has "MOVED: this window is lane repoA-3" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-guard-run-on-a-bound-record-hears-the-outcome-as-the-first-read-would
else bad r7-red-guard-run-on-a-bound-record-hears-the-outcome-as-the-first-read-would "$(r7_state)"; fi

box r7-site-bind-failed; r7_copy; r7_bind_rec "$REC" bind-failed
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = name-drift ] && [ "$(get rc)" = 5 ] && [ "$(get bind)" = 1 ] &&
   r7_err_has "THE BIND TO LANE repoA-3 FAILED (exit 5)" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-guard-run-on-a-bind-failed-record-says-it-failed-and-keeps-its-keys
else bad r7-red-guard-run-on-a-bind-failed-record-says-it-failed-and-keeps-its-keys "$(r7_state) rc-key=$(get rc) bind=$(get bind)"; fi

# AN ALLOWANCE installed meanwhile, which still fits, passes the prompt with its
# warning; the offer record in its place would have asked the question again.
box r7-site-allow-fits; r7_copy; r7_allow_rec "$REC"; r7_save
r7_offer_site '' hello
if [ "$R7_RC" = 0 ] && r7_same && r7_err_has "THE NAME GUARD ALLOWS THIS PROMPT ON AN EXPLICIT CHOICE" &&
   r7_err_has "WARNING: this lane/session name mismatch was explicitly allowed" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-guard-run-on-an-allowance-that-fits-passes-the-prompt-with-its-warning
else bad r7-red-guard-run-on-an-allowance-that-fits-passes-the-prompt-with-its-warning "$(r7_state)"; fi

# A RECORD OF THE OFFER, made meanwhile, is answered with this prompt as the answer.
box r7-site-offer-there; r7_copy; r7_offer_rec; r7_save
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "that is not an answer to the pending question" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-guard-run-on-an-offer-made-meanwhile-answers-it-with-this-prompt
else bad r7-red-guard-run-on-an-offer-made-meanwhile-answers-it-with-this-prompt "$(r7_state)"; fi

# ---- THE STALE ALLOW AND THE STALE OFFER a failed drop leaves. `guard_run` drops
# an allowance that no longer fits and calls the offer; where the drop fails (a
# stand-in `rm` that refuses the record), the leftover is no longer written over:
# the prompt is refused with the question to be asked afresh, and the record is as
# it was. Where the drop works, the offer is made, once, as ever.
r7_rm_refuses() {   # a stand-in `rm`: the record is refused, every other call is the real one
  r7_real="$(PATH="$BASE_PATH" command -v rm)"
  {
    printf '#!/bin/bash\nfor a in "$@"; do\n  case "$a" in */offers/%s) exit 1 ;; esac\ndone\n' "$U"
    printf 'exec %q "$@"\n' "$r7_real"
  } > "$B/fakes/rm"
  chmod 755 "$B/fakes/rm"
}
R7_NOT_RECORDED="a record of this transcript's is at"

box r7-stale-allow-drop-fails; r7_copy; r7_allow_rec "$REC" old-name; r7_save; r7_rm_refuses
r7_offer_site '' hello --drop-first
if [ "$R7_RC" = 2 ] && r7_same && [ "$(r7_ls)" = "$U " ] && r7_err_has "the pending offer could not be recorded" &&
   r7_err_has "$R7_NOT_RECORDED" && r7_err_has "Send your prompt again" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-stale-allow-whose-drop-fails-is-not-written-over-the-prompt-is-refused
else bad r7-red-stale-allow-whose-drop-fails-is-not-written-over-the-prompt-is-refused "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

box r7-stale-offer-drop-fails; r7_copy; r7_offer_rec "$REC" repoA-9 repoA-9; r7_save; r7_rm_refuses
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_same && [ "$(r7_ls)" = "$U " ] && r7_err_has "the pending question was about lane repoA-2 and session 'repoA-9'" &&
   r7_err_has "the pending offer could not be recorded" && ! r7_err_has "$R7_ASKED"; then
  ok r7-red-stale-offer-whose-drop-fails-is-not-written-over-the-prompt-is-refused
else bad r7-red-stale-offer-whose-drop-fails-is-not-written-over-the-prompt-is-refused "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

# THE NEXT PROMPT meets the same record and the same refusal until the drop works.
box r7-stale-allow-drop-fails-twice; r7_copy; r7_allow_rec "$REC" old-name; r7_save; r7_rm_refuses
r7_offer_site '' hello --drop-first
r7_offer_site '' hello --drop-first
if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "the pending offer could not be recorded"; then
  ok r7-red-the-next-prompt-meets-the-same-stale-allow-and-the-same-refusal
else bad r7-red-the-next-prompt-meets-the-same-stale-allow-and-the-same-refusal "$(r7_state)"; fi

# CONTROLS: where the drop works the offer is made, once: the stale allow and the
# stale offer are replaced by this prompt's offer, which asks the question.
r7_fresh() {   # the offer this prompt makes, for the live names
  [ "$(get mode)" = name-drift ] && [ "$(get from)" = repoA-2 ] && [ "$(get to)" = repoA-3 ] && [ "$(get session)" = repoA-3 ] &&
    [ "$(get uuid)" = "$U" ] && [ "$(get utc)" != 2026-11-14T00:00:00Z ] && [ "$(wc -l < "$REC" | tr -d ' ')" = 8 ] &&
    [ "$(r7_ls)" = "$U " ] && r7_err_has "$R7_ASKED"
}
box r7-control-stale-allow-drop-works; r7_copy; r7_allow_rec "$REC" old-name
r7_offer_site '' hello --drop-first
if [ "$R7_RC" = 2 ] && r7_fresh; then ok r7-control-stale-allow-whose-drop-works-is-replaced-by-the-offer-which-asks
else bad r7-control-stale-allow-whose-drop-works-is-replaced-by-the-offer-which-asks "$(r7_state)"; fi

box r7-control-stale-offer-drop-works; r7_copy; r7_offer_rec "$REC" repoA-9 repoA-9
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_fresh; then ok r7-control-stale-offer-whose-drop-works-is-replaced-by-the-offer-which-asks
else bad r7-control-stale-offer-whose-drop-works-is-replaced-by-the-offer-which-asks "$(r7_state)"; fi

# ---- THE ORDINARY OFFER, and the fallback where hard links are refused.
box r7-control-ordinary-offer; r7_copy
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_fresh && [ "$(stat -c %a "$REC")" = 600 ]; then ok r7-control-ordinary-offer-is-made-eight-lines-mode-0600-and-asks
else bad r7-control-ordinary-offer-is-made-eight-lines-mode-0600-and-asks "$(r7_state) perm=$(stat -c %a "$REC" 2>/dev/null)"; fi

box r7-control-ordinary-offer-new-dir; r7_copy
OFF="$B/cfg2/lanes/offers"; REC="$OFF/$U"   # an offers/ that is not there yet
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_fresh && [ "$(stat -c %a "$OFF")" = 700 ]; then ok r7-control-ordinary-offer-makes-offers-dir-0700
else bad r7-control-ordinary-offer-makes-offers-dir-0700 "$(r7_state) dirperm=$(stat -c %a "$OFF" 2>/dev/null)"; fi

box r7-control-no-hard-links-offer; r7_copy
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_fresh && [ "$(stat -c %a "$REC")" = 600 ]; then ok r7-control-where-hard-links-are-refused-the-offer-is-made-by-noclobber
else bad r7-control-where-hard-links-are-refused-the-offer-is-made-by-noclobber "$(r7_state) perm=$(stat -c %a "$REC" 2>/dev/null)"; fi

box r7-no-hard-links-bound; r7_copy; r7_bind_rec "$REC" bound; r7_save
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
r7_offer_only ''
if [ "$R7_RC" = 3 ] && r7_same && [ "$(r7_ls)" = "$U " ] && [ -z "$R7_ERR" ]; then
  ok r7-red-where-hard-links-are-refused-noclobber-leaves-a-bound-record-byte-for-byte
else bad r7-red-where-hard-links-are-refused-noclobber-leaves-a-bound-record-byte-for-byte "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi


# ---- PART 24: the three comments on the body's facts say that `why=` and `note=`
# reach the outcome only where the body ended on its own, and that the outcome is
# in the record only on the rewrite's 0. Each block is cut out by its first and
# last line, which every version has once.
r7_c1="$(r4_block '# ITS FILES: the record, ' '# not the attempt, which `bind=` counts')"
r7_c2="$(r4_block "  # (lane 3's ruling on S1 of its Codex delta review of spec#47's draft 13," '  gbo_wrc=2')"
r7_c3="$(r4_block "# THE BODY'S FACTS, which the outer folds" 'guard_bind_facts() {')"
r7_ok1=1; r7_ok2=1; r7_ok3=1
case "$r7_c1" in *"only where the body ended on its own"*) : ;; *) r7_ok1=0 ;; esac
case "$r7_c1" in *"which the outer folds into the record and removes"*) r7_ok1=0 ;; esac
case "$r7_c2" in *"only where the body ended on its own"*"only on the rewrite's 0"*"alone on a 1 or a 2"*) : ;; *) r7_ok2=0 ;; esac
case "$r7_c2" in *"which is in the record or, where it is not written"*) r7_ok2=0 ;; esac
case "$r7_c3" in *"folds into its outcome where the body ended on its own"*) : ;; *) r7_ok3=0 ;; esac
case "$r7_c3" in *"folds into the record (lane 3's ruling"*) r7_ok3=0 ;; esac
if [ "$r7_ok1" = 1 ]; then ok r7-red-comment-files-list-says-the-facts-reach-the-outcome-only-where-the-body-ended-on-its-own
else bad r7-red-comment-files-list-says-the-facts-reach-the-outcome-only-where-the-body-ended-on-its-own "block=[${r7_c1:0:300}]"; fi
if [ "$r7_ok2" = 1 ]; then ok r7-red-comment-three-results-says-the-outcome-is-in-the-record-only-on-the-rewrites-0
else bad r7-red-comment-three-results-says-the-outcome-is-in-the-record-only-on-the-rewrites-0 "block=[${r7_c2:0:400}]"; fi
if [ "$r7_ok3" = 1 ]; then ok r7-red-comment-facts-says-the-outer-folds-them-where-the-body-ended-on-its-own
else bad r7-red-comment-facts-says-the-outer-folds-them-where-the-body-ended-on-its-own "block=[${r7_c3:0:300}]"; fi


# ---- ROUND 8: T502's parts 27 to 34, lane 5's adversarial review of parts 22 to 26
# (T502P22ADV-REPORT-1115.md; lane 5's review, not lane 3's ruling and not
# Brett's): F1 (no drop of a record on `guard_run`'s stale first read of
# `allow`), F2 (a record there where `offers/` cannot take the temporary file),
# F3 (a record that vanishes after the failed create), F4 (`guard_bind_site`'s
# rewrites require what they loaded), F5 (the rename back first), F6(b) (the
# noclobber line itself), NIT 1 (a directory at the record's path), NIT 2 (the
# answered offer's identity), and NITs 3, 4, 5, 6 and 8. Cases named `r8-red-*`
# fail at `2497b864` (part 26) and pass at part 34; `r8-control-*` pass at both.
#
# F1 RUNS THE REAL `guard` HOOK, `guard_run` itself, in a sandbox with a register
# row, a session record held by a live process, and the suite's own fake `tmux`
# (extracted at run time from `tests/test_lane_helpers.sh`, or from `R8_SUITE`).
# A TEST-ONLY COPY (lane 3's point 23: no seam in the shipped script) pauses it on
# the line after its read of the record's mode: `T502R8_PEER=bound|binding` runs
# another invocation then (the `--t502r8-peer` arm), once: it drops the
# allowance, makes the offer, answers 2, and waits for its outer to end `bound`,
# or to be running (`.bind.1.out` written, its body held until `$B/release`
# exists), and takes a copy of the record and the `.out` for the byte-for-byte
# comparison. The copy has these more:
#   * `r8_race_hook`, called on the noclobber line, which puts `T502R8_NC_RACE`'s
#     file in the record's place just before the noclobber create (F6(b));
#   * `T502R8_C1=chmod` makes the record unreadable on the line before choice 1's
#     temporary file (NIT 8).
R8_SUITE="${R8_SUITE:-$(cd "$(dirname -- "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/tests/test_lane_helpers.sh}"

r8_copy() {
  r7_copy
  r8_c="$B/lanes-edit-r8.sh"
  cat > "$B/h8-arm.sh" <<'EOF'
    if [ "${1-}" = --t502r8-peer ]; then
      G_ID="$2"; G_LANE="$3"; G_NAME="$4"; G_SES_LANE="$5"; G_WINREF=gdsess:@12
      guard_offer_drop "$6"
      guard_offer "$6" "%12" >/dev/null 2>&1
      guard_answer "$6" 2 "%12" >/dev/null 2>&1
      r8_i=0
      while [ "$r8_i" -lt 150 ]; do
        case "$7" in
          bound) [ "$(sed -n -e 's/^mode=//p' "$6" 2>/dev/null | head -n1)" != bound ] || break ;;
          binding) ! grep -q 'attempt 1 for transcript' "$6.bind.1.out" 2>/dev/null || break ;;
        esac
        sleep 0.2; r8_i=$((r8_i + 1))
      done
      cp -p -- "$6" "$T502R8_SNAP.rec"; cp -p -- "$6.bind.1.out" "$T502R8_SNAP.out"
      exit 0
    fi
EOF
  cat > "$B/h8-pause.sh" <<'EOF'
  if [ -n "${T502R8_PEER:-}" ] && mkdir -- "$T502R8_SNAP.once" 2>/dev/null; then
    bash "$RESOLVED" guard-bind --t502r8-peer "$G_ID" "$G_LANE" "$G_NAME" "$G_SES_LANE" "$gr_off" "$T502R8_PEER" </dev/null >> "$T502R8_SNAP.log" 2>&1 || :
  fi
EOF
  cat > "$B/h8-race.sh" <<'EOF'
r8_race_hook() { [ -n "${T502R8_NC_RACE:-}" ] && mkdir -- "$T502R8_NC_RACE.once" 2>/dev/null && cp -p -- "$T502R8_NC_RACE" "$go_f"; return 0; }
EOF
  cat > "$B/h8-c1.sh" <<'EOF'
    [ "${T502R8_C1:-}" != chmod ] || chmod 000 "$ga_f"
EOF
  r8_a1='  [ -f "$gr_off" ] && gr_mode="$(sed -n -e '"'"'s/^mode=//p'"'"' "$gr_off" 2>/dev/null | head -n1)"'
  awk -v arm="$B/h8-arm.sh" -v ps="$B/h8-pause.sh" -v rc="$B/h8-race.sh" -v c1="$B/h8-c1.sh" -v a1="$r8_a1" -v c1a="$r7_c1a" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    index($0, "guard_offer() {   # <offer file> <pane>") == 1 { cat(rc); a++ }
    $0 == c1a { cat(c1); b++ }
    index($0, "( set -C; umask 077;") > 0 { i = index($0, "( set -C"); $0 = substr($0, 1, i - 1) "r8_race_hook && " substr($0, i); c++ }
    { print }
    $0 == "  guard-bind)" { cat(arm); d++ }
    $0 == a1 { cat(ps); e++ }
    END { exit (a == 1 && b == 1 && c == 1 && d == 1 && e == 1 ? 0 : 1) }' "$B/lanes-edit-r7.sh" > "$r8_c" ||
    printf 'r8_copy: an anchor was not found exactly once\n' >&2
  chmod 755 "$r8_c"
  R8_COPY="$r8_c"
}

r8_settle() {
  r8_i=0
  while pgrep -f -- "$B/" >/dev/null 2>&1 && [ "$r8_i" -lt 200 ]; do sleep 0.2; r8_i=$((r8_i + 1)); done
  R7_LEFT="$(pgrep -f -- "$B/" 2>/dev/null | wc -l | tr -d ' ')"
}

r8_fx() {   # <the session's name>: the register, a session record a live process holds, the suite's fake tmux, the hook's JSON
  mkdir -p "$B/home/projects/repoA" "$B/home/.claude/sessions" "$B/reg/lanes" "$B/tmp"
  {
    printf '# LANES.md - sandbox\n\n'
    printf '| lane | session id | workstation / env / user | started (UTC) | objects owned | handoff path | state |\n'
    printf '|---|---|---|---|---|---|---|\n'
    printf '| `repoA-2` | harness `%s` | Eagle / test / brett | 2026-09-11T00:00Z | none | handoffs/repoA/x.md | ACTIVE |\n' "$U"
  } > "$B/reg/lanes/LANES.md"
  awk '/^cat > "\$SANDBOX\/fakebin\/tmux" <<.FAKE.$/ { f = 1; next } f && /^FAKE$/ { exit } f { print }' "$R8_SUITE" > "$B/fakes/tmux"
  chmod 755 "$B/fakes/tmux"
  sleep 120 & R8_LIVE=$!
  r8_start="$(cut -d' ' -f22 "/proc/$R8_LIVE/stat")"
  printf '{"pid":%s,"sessionId":"%s","cwd":"%s/home/projects/repoA","procStart":"%s","kind":"interactive","tmux":"gdsess:@12.%%12","name":"%s","nameSource":"user","nameSince":1000,"status":"busy","updatedAt":9000}\n' \
    "$R8_LIVE" "$U" "$B" "$r8_start" "$1" > "$B/home/.claude/sessions/gd.json"
  printf '{"session_id":"%s","cwd":"%s/home/projects/repoA","prompt":"hello","hook_event_name":"UserPromptSubmit"}' "$U" "$B" > "$B/hook.json"
}

r8_guard() {   # <env assignments, one word each, or ''>: the REAL hook, `guard`, from the test-only copy
  r8_e="$1"
  # shellcheck disable=SC2086
  ( cd "$B" && env -i HOME="$B/home" PATH="$B/fakes:$BASE_PATH" TMPDIR="$B/tmp" CLAUDE_CONFIG_DIR="$B/cfg" XDG_STATE_HOME="$B/state" \
      PROJECTS_ROOT="$B/home/projects" LANES_REPO="$B/reg" LANES_FILE="$B/reg/lanes/LANES.md" LANES_WORKSTATION=Eagle LANES_CONTAINER=g-box \
      LANES_HOST=Eagle LANES_IN_CONTAINER=0 LANES_NO_GITHUB=1 LANES_INDEX=off LC_ALL=C LANES_BIND_BOUND_S=15 \
      LANES_LANE_START="$B/lane-start-stub" LANES_BIND_BODY="$STUB" TMUX=/tmp/x,1,0 \
      FAKE_TMUX_WINDOW=gdsess:@12 FAKE_TMUX_WINDOW_NAME=repoA-2 FAKE_TMUX_WINDOWS="$(printf 'gdsess:0\t@12\trepoA-2\t%%12\tclaude')" \
      FAKE_TMUX_LOG="$B/tmux.log" T502R8_SNAP="$B/snap" $r8_e \
      timeout 120 bash "$B/lanes-edit-r8.sh" guard < "$B/hook.json" > "$B/r8-out" 2>"$B/r7-err" )
  R7_RC=$?
  R7_ERR="$(cat -- "$B/r7-err")"
  kill "$R8_LIVE" 2>/dev/null; wait "$R8_LIVE" 2>/dev/null
}

r8_block_body() {   # a stand-in body that waits for `$B/release`
  {
    printf '#!/bin/bash\nn=0\nwhile [ ! -e %q ] && [ "$n" -lt 600 ]; do sleep 0.2; n=$((n + 1)); done\n' "$B/release"
    printf ': > %q\nexit 0\n' "$TRIG"
  } > "$STUB"
  chmod 755 "$STUB"
}

# ---- F1: `guard_run` with the first read `allow`, and another invocation having
# made the record a bind record since. The mismatch row, then the three-agree row.
box r8-f1-bound; r8_copy; r8_fx repoA-3; body - 0 'note=a stand-in act still owed'; r7_allow_rec
r8_guard "T502R8_PEER=bound"; r8_settle
if [ "$R7_RC" = 2 ] && r7_err_has "MOVED: this window is lane repoA-3, bound to this session" && r7_err_has "still owed: a stand-in act still owed" &&
   ! r7_err_has "$R7_ASKED" && [ ! -e "$REC" ]; then
  ok r8-red-f1-guard-run-stale-allow-then-bound-hears-moved-and-the-owed-note-and-asks-nothing
else bad r8-red-f1-guard-run-stale-allow-then-bound-hears-moved-and-the-owed-note-and-asks-nothing "$(r7_state) record-mode=$(get mode) lines=$(wc -l < "$REC" 2>/dev/null)"; fi

box r8-f1-binding; r8_copy; r8_fx repoA-3; r8_block_body; r7_allow_rec
r8_guard "T502R8_PEER=binding"
r8_same_rec=no; cmp -s -- "$B/snap.rec" "$REC" && r8_same_rec=yes
r8_same_out=no; cmp -s -- "$B/snap.out" "$OUT" && r8_same_out=yes
r8_mid="$R7_ERR"
: > "$B/release"; r8_settle
if [ "$R7_RC" = 2 ] && [ "$r8_same_rec" = yes ] && [ "$r8_same_out" = yes ] && [ "$(get mode)" = bound ] && [ "$R7_LEFT" = 0 ]; then
  case "$r8_mid" in *"BINDING IN PROGRESS"*) r8_prog=yes ;; *) r8_prog=no ;; esac
  case "$r8_mid" in *"$R7_ASKED"*) r8_asked=yes ;; *) r8_asked=no ;; esac
  if [ "$r8_prog" = yes ] && [ "$r8_asked" = no ]; then ok r8-red-f1-guard-run-stale-allow-then-binding-keeps-the-record-and-the-live-out-and-says-in-progress
  else bad r8-red-f1-guard-run-stale-allow-then-binding-keeps-the-record-and-the-live-out-and-says-in-progress "in-progress=$r8_prog asked=$r8_asked"; fi
else bad r8-red-f1-guard-run-stale-allow-then-binding-keeps-the-record-and-the-live-out-and-says-in-progress \
  "rc=$R7_RC record-same=$r8_same_rec out-same=$r8_same_out final-mode=$(get mode) left=$R7_LEFT err=[$(printf '%s' "$r8_mid" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi

box r8-f1-agree; r8_copy; r8_fx repoA-2; body - 0 'note=a stand-in act still owed'; r7_allow_rec
r8_guard "T502R8_PEER=bound"; r8_settle
if [ "$R7_RC" = 0 ] && cmp -s -- "$B/snap.rec" "$REC" && cmp -s -- "$B/snap.out" "$OUT" && [ "$(get mode)" = bound ] && [ "$(get note)" = "a stand-in act still owed" ]; then
  ok r8-red-f1-guard-run-three-agree-row-keeps-a-bound-record-and-its-out-byte-for-byte
else bad r8-red-f1-guard-run-three-agree-row-keeps-a-bound-record-and-its-out-byte-for-byte \
  "rc=$R7_RC record=$([ -e "$REC" ] && echo "there,mode=$(get mode)" || echo GONE) out=$([ -e "$OUT" ] && echo there || echo GONE) err=[$(printf '%s' "$R7_ERR" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi

# CONTROLS: where the allowance is still there and fits, guard_run passes it; where
# it no longer fits and nothing else has happened, it is dropped and the question
# is asked once.
box r8-control-allow-fits; r8_copy; r8_fx repoA-3; r7_allow_rec; r7_save
r8_guard ''
if [ "$R7_RC" = 0 ] && r7_same && r7_err_has "THE NAME GUARD ALLOWS THIS PROMPT ON AN EXPLICIT CHOICE" && ! r7_err_has "$R7_ASKED"; then
  ok r8-control-guard-run-passes-an-allowance-that-fits
else bad r8-control-guard-run-passes-an-allowance-that-fits "$(r7_state)"; fi

box r8-control-allow-stale; r8_copy; r8_fx repoA-3; r7_allow_rec "$REC" old-name
r8_guard ''
if [ "$R7_RC" = 2 ] && r7_fresh; then ok r8-control-guard-run-drops-a-stale-allowance-and-asks-once
else bad r8-control-guard-run-drops-a-stale-allowance-and-asks-once "$(r7_state)"; fi

# ---- F2: `offers/` 0500 with a stale allow 0600: the question must not be asked
# with an answer that can never be recorded.
if [ "$(id -u)" = 0 ]; then printf 'SKIP r8-red-f2 (runs as root, for whom a 0500 directory takes writes)\n'
else
  box r8-f2; r8_copy; r8_fx repoA-3; r7_allow_rec "$REC" old-name; r7_save; chmod 500 "$OFF"
  r8_guard ''
  chmod 700 "$OFF"
  if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "the pending offer could not be recorded: a record of this transcript's is at" && ! r7_err_has "$R7_ASKED"; then
    ok r8-red-f2-offers-not-writable-with-a-stale-allow-refuses-with-no-question-and-leaves-the-record
  else bad r8-red-f2-offers-not-writable-with-a-stale-allow-refuses-with-no-question-and-leaves-the-record "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi
fi

# ---- F3: the record vanishes after the failed create (a stand-in `rm` moves it
# away when `guard_offer` removes its temporary file).
box r8-f3; r8_copy; r7_offer_rec "$REC" repoA-3 repoA-3
r7_real="$(PATH="$BASE_PATH" command -v rm)"
{
  printf '#!/bin/bash\nfor a in "$@"; do\n  case "$a" in */offers/.%s.*) mkdir %q 2>/dev/null && mv -f %q %q ;; esac\ndone\n' "$U" "$B/once-rm" "$REC" "$REC.gone"
  printf 'exec %q "$@"\n' "$r7_real"
} > "$B/fakes/rm"; chmod 755 "$B/fakes/rm"
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && [ -d "$B/once-rm" ] && [ "$(get mode)" = name-drift ] && [ "$(get utc)" != 2026-11-14T00:00:00Z ] &&
   r7_err_has "$R7_ASKED" && ! r7_err_has "could not be read" && ! r7_err_has "has been dropped"; then
  ok r8-red-f3-a-record-that-vanishes-after-the-failed-create-is-not-answered-as-unreadable-and-the-offer-is-made
else bad r8-red-f3-a-record-that-vanishes-after-the-failed-create-is-not-answered-as-unreadable-and-the-offer-is-made "$(r7_state) hook=$([ -d "$B/once-rm" ] && echo fired || echo NOT-fired)"; fi

# ---- F4: guard_bind_site's rewrites require what they loaded.
box r8-f4-bind-failed; r7_copy; r7_bind_rec "$REC" bind-failed; r7_put binding
r7_site "T502R7_GONE_FROM=guard_bind_site T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ "$(r7_ls)" = "$U " ] && [ -z "$(r7_tmux)" ] && r7_err_has "BINDING IN PROGRESS" && ! r7_err_has "THE BIND TO LANE"; then
  ok r8-red-f4-case-6-7-a-bind-failed-record-changed-to-a-newer-binding-is-not-written-over
else bad r8-red-f4-case-6-7-a-bind-failed-record-changed-to-a-newer-binding-is-not-written-over "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

box r8-f4-other-host; r7_copy; r7_bind_rec "$REC" binding Other-host past; r7_bind_rec "$B/put" bound Other-host; cp -p -- "$B/put" "$B/was"
r7_site "T502R7_GONE_FROM=guard_bind_site T502R7_PUT=$B/put"
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && r7_err_has "MOVED: this window is lane repoA-3" && ! r7_err_has "IS NO LONGER RUNNING" && ! r7_err_has "Reply \`1\`"; then
  ok r8-red-f4-case-10-a-bound-record-written-meanwhile-by-another-hosts-outer-is-heard-not-made-stale
else bad r8-red-f4-case-10-a-bound-record-written-meanwhile-by-another-hosts-outer-is-heard-not-made-stale "$(r7_state) mode=$(get mode) rc-key=$(get rc)"; fi

box r8-f4-same-host-other-attempt; r7_copy; r7_bind_rec "$REC" binding Eagle past; r7_bind_rec "$B/put" binding Eagle
sed -i 's/^bind=1$/bind=2/' "$B/put"; cp -p -- "$B/put" "$B/was"
r7_site "T502R7_GONE_FROM=guard_bind_site T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 2 ] && ! r7_err_has "IS NO LONGER RUNNING" && r7_err_has "BINDING IN PROGRESS"; then
  ok r8-red-f4-case-9-a-record-of-another-attempt-is-not-made-stale
else bad r8-red-f4-case-9-a-record-of-another-attempt-is-not-made-stale "$(r7_state) bind=$(get bind) same=$(r7_same && echo yes || echo NO)"; fi

# ---- F5: the rename back is tried first and the refusal is worded on its result.
r8_tmux_back_fails() {   # the first rename-window succeeds, every later one fails
  {
    printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> %q\n' "$B/tmux-calls"
    printf 'if [ "${1-}" = rename-window ]; then\n  if [ -e %q ]; then exit 1; fi\n  : > %q\nfi\nexit 0\n' "$B/renamed-once" "$B/renamed-once"
  } > "$B/fakes/tmux"
  chmod 755 "$B/fakes/tmux"
}
box r8-f5-answer; r7_copy; r7_offer_rec; r7_cache; r8_tmux_back_fails
r7_answer "T502R7_CACHE=$B/cache T502R7_GONE_FROM=guard_bind_head_copy"
if [ "$R7_RC" = 2 ] && r7_err_has "could NOT be renamed back to repoA-2" && r7_err_has "this window was renamed to repoA-3 by this answer" &&
   ! r7_err_has "is undone just below" && ! r7_err_has "this window has NOT moved to repoA-3"; then
  ok r8-red-f5-answer-2-refusal-says-could-not-be-renamed-back-where-the-rename-back-fails
else bad r8-red-f5-answer-2-refusal-says-could-not-be-renamed-back-where-the-rename-back-fails "$(r7_state)"; fi

box r8-f5-backout; r7_copy; r7_offer_rec; r8_tmux_back_fails
r7_answer "T502R7_NOCHILD=1 T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=2"
if [ "$R7_RC" = 2 ] && r7_err_has "could NOT be renamed back to repoA-2" && ! r7_err_has "so this window has NOT moved to repoA-3"; then
  ok r8-red-f5-back-out-refusal-says-could-not-be-renamed-back-where-the-rename-back-fails
else bad r8-red-f5-back-out-refusal-says-could-not-be-renamed-back-where-the-rename-back-fails "$(r7_state)"; fi

box r8-f5-renamed-back; r7_copy; r7_offer_rec; r7_cache
r7_answer "T502R7_CACHE=$B/cache T502R7_GONE_FROM=guard_bind_head_copy"
if [ "$R7_RC" = 2 ] && r7_err_has "this answer renamed it, and it was renamed back to repoA-2" && ! r7_err_has "is undone just below"; then
  ok r8-red-f5-answer-2-refusal-says-renamed-back-only-after-it-was
else bad r8-red-f5-answer-2-refusal-says-renamed-back-only-after-it-was "$(r7_state)"; fi

# ---- NIT 1: a directory, or a link to one, at the record's path.
for r8_kind in dir link; do
  box "r8-nit1-$r8_kind"; r7_copy
  case "$r8_kind" in
    dir) mkdir "$REC" ;;
    link) mkdir "$B/linkdir"; ln -s "$B/linkdir" "$REC" ;;
  esac
  r7_offer_site '' hello
  r8_inside="$(ls -A "$REC" 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$R7_RC" = 2 ] && [ "$r8_inside" = 0 ] && r7_err_has "the pending offer could not be recorded: a record of this transcript's is at" && ! r7_err_has "$R7_ASKED"; then
    ok "r8-red-nit1-a-$r8_kind-at-the-records-path-is-a-record-there-and-nothing-is-left-inside-it"
  else bad "r8-red-nit1-a-$r8_kind-at-the-records-path-is-a-record-there-and-nothing-is-left-inside-it" "$(r7_state) inside=$r8_inside"; fi
done

# ---- NIT 2: an offer re-made since, for another `to`, is not the answered offer.
box r8-nit2-answer; r7_copy; r7_offer_rec; r7_cache; r7_offer_rec "$B/put" repoA-3 repoA-9; cp -p -- "$B/put" "$B/was"
r7_answer "T502R7_CACHE=$B/cache T502R7_GONE_FROM=guard_bind_head_copy T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ] && [ "$(r7_ls)" = "$U " ] && ! has bind && r7_err_has "it is another offer now, not the one that was answered"; then
  ok r8-red-nit2-answer-2-a-re-made-offer-for-another-to-is-left-and-no-outer-is-started
else bad r8-red-nit2-answer-2-a-re-made-offer-for-another-to-is-left-and-no-outer-is-started "$(r7_state) same=$(r7_same && echo yes || echo NO) out=$([ -e "$OUT" ] && echo STARTED || echo none)"; fi

box r8-nit2-choice-1; r7_copy; r7_offer_rec; r7_offer_rec "$B/put" repoA-3 repoA-9; cp -p -- "$B/put" "$B/was"
r7_choice1 "T502R7_C1=put T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 2 ] && ! r7_err_has "ALLOWED:" && r7_err_has "it is another offer now, not the one that was answered"; then
  ok r8-red-nit2-choice-1-a-re-made-offer-for-another-to-is-left-and-no-allow-is-written
else bad r8-red-nit2-choice-1-a-re-made-offer-for-another-to-is-left-and-no-allow-is-written "$(r7_state)"; fi

# ---- F6(b): the noclobber line itself. The record is put in place between the
# test and the noclobber create (`ln` is refused, so the create is the noclobber
# one), and passes only with `set -C`; a copy with `set -C` removed is overwritten.
box r8-f6b; r8_copy; r7_bind_rec "$B/race-record" bound; cp -p -- "$B/race-record" "$B/was"
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
r7_run "T502R8_NC_RACE=$B/race-record" --t502r7-offer-only "$U" repoA-2 repoA-3 repoA-3 "$REC"
if [ "$R7_RC" = 3 ] && r7_same && [ -d "$B/race-record.once" ] && [ "$(r7_ls)" = "$U " ]; then
  ok r8-control-f6b-a-record-put-in-place-just-before-the-noclobber-create-survives-byte-for-byte
else bad r8-control-f6b-a-record-put-in-place-just-before-the-noclobber-create-survives-byte-for-byte "$(r7_state) hook=$([ -d "$B/race-record.once" ] && echo fired || echo NOT-fired)"; fi

box r8-f6b-mutant; r8_copy; r7_bind_rec "$B/race-record" bound; cp -p -- "$B/race-record" "$B/was"
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
sed 's/( set -C; umask 077;/( umask 077;/' "$B/lanes-edit-r8.sh" > "$B/lanes-edit-r8m.sh"; chmod 755 "$B/lanes-edit-r8m.sh"
R8_COPY="$B/lanes-edit-r8m.sh"
r7_run "T502R8_NC_RACE=$B/race-record" --t502r7-offer-only "$U" repoA-2 repoA-3 repoA-3 "$REC"
R8_COPY="$B/lanes-edit-r8.sh"
if [ -d "$B/race-record.once" ] && ! r7_same; then ok r8-control-f6b-without-set-C-the-same-case-overwrites-the-record-so-the-case-needs-it
else bad r8-control-f6b-without-set-C-the-same-case-overwrites-the-record-so-the-case-needs-it "$(r7_state) hook=$([ -d "$B/race-record.once" ] && echo fired || echo NOT-fired)"; fi

# ---- NIT 4: a `cat` that fails after the noclobber create is this writer's own
# partial file: it is removed, and the offer is asked with the note that it could
# not be written, instead of the empty file being taken for another's record.
box r8-nit4; r8_copy
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/cat"; chmod 755 "$B/fakes/cat"
r7_run '' --t502r7-offer-only "$U" repoA-2 repoA-3 repoA-3 "$REC"
if [ "$R7_RC" = 2 ] && [ ! -e "$REC" ] && r7_err_has "the offer could not be written to"; then
  ok r8-red-nit4-a-failed-cat-after-the-noclobber-create-is-this-writers-own-partial-file-and-is-removed
else bad r8-red-nit4-a-failed-cat-after-the-noclobber-create-is-this-writers-own-partial-file-and-is-removed "$(r7_state) size=$(stat -c %s "$REC" 2>/dev/null)"; fi

# ---- NIT 3: inside the site an allowance answer passes: `guard_answer`, called by
# the site on an offer, finds an allowance where it meant to write, and returns 3.
box r8-nit3; r8_copy; r7_offer_rec; r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"
r7_run "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1 T502R7_PUT=$B/put" --t502r7-offer "$U" repoA-2 repoA-3 repoA-3 "$REC" 2
if [ "$R7_RC" = 0 ] && r7_same && r7_err_has "THE NAME GUARD ALLOWS THIS PROMPT ON AN EXPLICIT CHOICE" && ! r7_err_has "could not be recorded"; then
  ok r8-red-nit3-inside-the-site-an-allowance-that-guard-answer-found-passes
else bad r8-red-nit3-inside-the-site-an-allowance-that-guard-answer-found-passes "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

# ---- NIT 5: the back-out's I/O failure says the record still says binding.
box r8-nit5; r7_copy; r7_offer_rec
r7_real="$(PATH="$BASE_PATH" command -v mv)"
{
  printf '#!/bin/bash\nif [ -e %q ]; then exit 1; fi\n: > %q\nexec %q "$@"\n' "$B/mv-once" "$B/mv-once" "$r7_real"
} > "$B/fakes/mv"; chmod 755 "$B/fakes/mv"
r7_answer "T502R7_NOCHILD=1"
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = binding ] && r7_err_has "it still says binding" && ! r7_err_has "The offer is KEPT"; then
  ok r8-red-nit5-back-out-io-failure-says-the-record-still-says-binding-and-not-kept
else bad r8-red-nit5-back-out-io-failure-says-the-record-still-says-binding-and-not-kept "$(r7_state) mode=$(get mode)"; fi

# ---- NIT 6: guard_bind_gone says the prompt is read afresh, not that the question is asked afresh.
box r8-nit6; r7_copy; r7_bind_rec "$REC" bind-failed
r7_site "T502R7_GONE_FROM=guard_bind_site"
if [ "$R7_RC" = 2 ] && r7_err_has "was gone when it came to be answered, so nothing was written to it. Send your prompt again and it will be read afresh." &&
   ! r7_err_has "question will be asked afresh"; then
  ok r8-red-nit6-bind-gone-says-the-prompt-is-read-afresh
else bad r8-red-nit6-bind-gone-says-the-prompt-is-read-afresh "$(r7_state)"; fi

# ---- NIT 8: choice 1 on a record that is there and cannot be read is K4's 1.
if [ "$(id -u)" = 0 ]; then printf 'SKIP r8-red-nit8 (runs as root, which reads any file)\n'
else
  box r8-nit8; r8_copy; r7_offer_rec
  r7_choice1 "T502R8_C1=chmod"
  chmod 600 "$REC"
  if [ "$R7_RC" = 2 ] && r7_err_has "the explicit allow could not be recorded" && ! r7_err_has "was changed before the allow could be recorded"; then
    ok r8-red-nit8-choice-1-on-an-unreadable-record-takes-k4s-1-path
  else bad r8-red-nit8-choice-1-on-an-unreadable-record-takes-k4s-1-path "$(r7_state)"; fi
fi

# ---- ROUND 9: T502's parts 35 to 41, lane 5's re-check of parts 27 to 34 at
# `c57303d9` (BRIEF-T502P35-1115.md; lane 5's re-check, not lane 3's ruling and not
# Brett's): A (no here-string in the `--mode`/`--match` check), B (the back-out's
# I/O-failure words), C (the noclobber content written through the descriptor
# opened exclusively), NIT 1's rest (an `ln` that fails after making the link), D
# (case 6/7 matches the attempt), E (a dangling link, and a directory, at the
# record's path), F (`GBT_MOVED` at file scope), H (an allowance that became a bind
# record) and the narrowed `guard_drop_if`. Cases named `r9-red-*` fail at
# `c57303d9` (part 34) and pass at part 41; `r9-control-*` pass at both.
#
# `r9_copy` is round 8's copy with three more hooks, each anchored on a line that
# the version has once (the first is called at the old fallback's `cat`, a line
# `c57303d9` has and part 37 removed, so the call is made only where it is there):
#   * `r9_gap_hook`, the instant the noclobber fallback has the record created and
#     empty: `T502R9_GAP=remove` removes the record, as a case-11 reader does, and
#     `replace` puts `T502R9_RACE`'s file in its place by a rename, as another
#     invocation's write does, once (`T502R9_ONCE` is the marker). At part 41 the
#     instant is inside the subshell, after the `3>` open and before the `cat`
#     writes, so `r9_cat_fake`, a stand-in `cat` whose first call on the temporary
#     file does the same, is the hook there;
#   * `T502R9_FLIP=<file>` puts that file in place of the record on the first line
#     of `guard_allow_drop`, before its re-read;
#   * `T502R9_FRESH=1` makes a new `.bind.9.out` appear in `guard_drop_if` between
#     its re-read and its `rm`.
r9_copy() {
  r8_copy
  r9_c="$B/lanes-edit-r9.sh"
  cat > "$B/h9-gap.sh" <<'EOF'
r9_gap_hook() {
  [ -n "${T502R9_GAP:-}" ] && mkdir -- "$T502R9_ONCE" 2>/dev/null || return 0
  case "$T502R9_GAP" in
    remove) rm -f -- "$go_f" ;;
    replace) cp -p -- "$T502R9_RACE" "$go_f.new" && mv -f -- "$go_f.new" "$go_f" ;;
  esac
  return 0
}
EOF
  printf '%s\n' '        r9_gap_hook' > "$B/h9-gapcall.sh"
  printf '%s\n' '  [ -z "${T502R9_FLIP:-}" ] || ! mkdir -- "$T502R9_FLIP.once" 2>/dev/null || cp -p -- "$T502R9_FLIP" "${1-}"' > "$B/h9-flip.sh"
  printf '%s\n' '  [ -z "${T502R9_FRESH:-}" ] || : > "$gdi_f.bind.9.out"' > "$B/h9-fresh.sh"
  r9_ad='guard_allow_drop() {   # <offer file>: an allowance, only while it still says `allow`'
  r9_af='  if [ "${3-}" = record ]; then'
  r9_ac='        if cat -- "$go_t" > "$go_f" 2>/dev/null; then'
  awk -v gap="$B/h9-gap.sh" -v gc="$B/h9-gapcall.sh" -v fl="$B/h9-flip.sh" -v fr="$B/h9-fresh.sh" \
      -v ad="$r9_ad" -v af="$r9_af" -v ac="$r9_ac" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    index($0, "guard_offer() {   # <offer file> <pane>") == 1 { cat(gap); a++ }
    $0 == ac { cat(gc); b++ }
    $0 == af { cat(fr); c++ }
    { print }
    $0 == ad { cat(fl); d++ }
    END { exit (a == 1 && b <= 1 && c == 1 && d == 1 ? 0 : 1) }' "$B/lanes-edit-r8.sh" > "$r9_c" ||
    printf 'r9_copy: an anchor was not found exactly once\n' >&2
  chmod 755 "$r9_c"
  R8_COPY="$r9_c"
}

r9_cat_fake() {   # a stand-in `cat`: its first call on the offer's temporary file changes the record, then runs the real one
  r9_real_cat="$(PATH="$BASE_PATH" command -v cat)"
  {
    cat <<'EOF'
#!/bin/bash
case "${2-}" in
  "$T502R9_OFF"/.*)
    if [ -n "${T502R9_GAP:-}" ] && mkdir -- "$T502R9_ONCE" 2>/dev/null; then
      case "$T502R9_GAP" in
        remove) rm -f -- "$T502R9_REC" ;;
        replace) cp -p -- "$T502R9_RACE" "$T502R9_REC.new" && mv -f -- "$T502R9_REC.new" "$T502R9_REC" ;;
      esac
    fi ;;
esac
EOF
    printf 'exec %q "$@"\n' "$r9_real_cat"
  } > "$B/fakes/cat"
  chmod 755 "$B/fakes/cat"
}

# ---- A: no here-string in the rewrite. A here-string is written to a file in
# TMPDIR by bash before 5.1 and not by 5.1 and after, so a TMPDIR that cannot take
# a file cannot fail it on this bash: the case is the code's own text, which has
# no here-string in the function, and the controls hold the new loop's answers.
r9_fn="$(awk '/^guard_bind_rewrite\(\) \{/ { f = 1 } f { print } f && /^}/ { exit }' "$S")"
case "$r9_fn" in *'<<<'*) r9_here=yes ;; *) r9_here=no ;; esac
if [ -n "$r9_fn" ] && [ "$r9_here" = no ]; then ok r9-red-a-guard-bind-rewrite-has-no-here-string
else bad r9-red-a-guard-bind-rewrite-has-no-here-string "here-string-in-function=$r9_here lines=$(printf '%s\n' "$r9_fn" | wc -l | tr -d ' ')"; fi

box r9-a-tmpdir; r7_copy; r6_rec mode=binding keep=a
r7_rw "TMPDIR=$B/no-such-dir" --mode bind-failed "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r9-control-a-mode-check-holds-with-a-tmpdir-that-cannot-take-a-file
else bad r9-control-a-mode-check-holds-with-a-tmpdir-that-cannot-take-a-file "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")]"; fi

box r9-a-match-both; r7_copy; r6_rec mode=binding a=1 b=2 keep=c
r9_want="$(cat -- "$R4"; printf '%s\n' pid=1234)"
r7_rw '' --mode binding --match a=1 --match b=2 "$R4" "" pid=1234
if [ "$RW_RC" = 0 ] && [ "$(cat -- "$R4")" = "$r9_want" ] && [ -z "$(r4_temps)" ]; then ok r9-control-a-two-matches-both-held-writes-and-returns-0
else bad r9-control-a-two-matches-both-held-writes-and-returns-0 "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")]"; fi

box r9-a-match-second; r7_copy; r6_rec mode=binding a=1 b=3 keep=c
r7_rw '' --mode binding --match a=1 --match b=2 "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r9-control-a-second-match-not-held-returns-2-unchanged
else bad r9-control-a-second-match-not-held-returns-2-unchanged "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")]"; fi

box r9-a-first-line; r7_copy; r6_rec mode=binding bind=1 bind=2 keep=c
r7_rw '' --mode binding --match bind=2 "$R4" "" pid=1234
if [ "$RW_RC" = 2 ] && r4_unchanged && [ -z "$(r4_temps)" ]; then ok r9-control-a-the-first-line-of-a-key-is-the-one-matched
else bad r9-control-a-the-first-line-of-a-key-is-the-one-matched "rc=$RW_RC record=[$(tr '\n' ' ' < "$R4")]"; fi

# ---- B: the back-out's I/O failure leaves a record that says binding, and the
# words say what the next prompts do with it, and they do it.
box r9-b; r7_copy; r7_offer_rec
r9_real_mv="$(PATH="$BASE_PATH" command -v mv)"
printf '#!/bin/bash\nif [ -e %q ]; then exit 1; fi\n: > %q\nexec %q "$@"\n' "$B/mv-once" "$B/mv-once" "$r9_real_mv" > "$B/fakes/mv"; chmod 755 "$B/fakes/mv"
r7_answer "T502R7_NOCHILD=1"
r9_b_rc="$R7_RC"; r9_b_err="$R7_ERR"; r9_b_mode="$(get mode)"
r7_site ''
r9_b_next="$R7_ERR"
r9_b_words=no; r9_b_false=no; r9_b_next_says=no
case "$r9_b_err" in *"so it still says binding: the next prompts say BINDING IN PROGRESS until its deadline, and the first after it finds the record stale and asks afresh."*) r9_b_words=yes ;; esac
case "$r9_b_err" in *"the next prompt finds that stale"*) r9_b_false=yes ;; esac
case "$r9_b_next" in *"BINDING IN PROGRESS"*) r9_b_next_says=yes ;; esac
if [ "$r9_b_rc" = 2 ] && [ "$r9_b_mode" = binding ] && [ "$r9_b_words" = yes ] && [ "$r9_b_false" = no ] && [ "$r9_b_next_says" = yes ]; then
  ok r9-red-b-back-out-io-failure-words-say-what-the-next-prompts-do-and-they-do-it
else bad r9-red-b-back-out-io-failure-words-say-what-the-next-prompts-do-and-they-do-it "rc=$r9_b_rc mode=$r9_b_mode words=$r9_b_words false-words=$r9_b_false next-prompt-says-in-progress=$r9_b_next_says"; fi

# ---- C: in the fallback's empty instant the record is removed, or replaced, and
# nothing is recreated at another mode or written over.
for r9_gap in remove replace; do
  box "r9-c-$r9_gap"; r9_copy; r7_bind_rec "$B/race-record" bound; cp -p -- "$B/race-record" "$B/was"
  printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
  r9_cat_fake
  r7_run "T502R9_GAP=$r9_gap T502R9_ONCE=$B/gap.once T502R9_OFF=$OFF T502R9_REC=$REC T502R9_RACE=$B/race-record" --t502r7-offer-only "$U" repoA-2 repoA-3 repoA-3 "$REC"
  r9_ok=0
  case "$r9_gap" in
    remove) [ ! -e "$REC" ] && [ ! -L "$REC" ] && [ "$R7_RC" = 2 ] && r7_err_has "the offer could not be written to" && r9_ok=1 ;;
    replace) r7_same && [ "$(stat -c %a "$REC")" = 600 ] && r9_ok=1 ;;
  esac
  if [ "$r9_ok" = 1 ] && [ -d "$B/gap.once" ]; then
    ok "r9-red-c-noclobber-empty-instant-record-$r9_gap-d-is-not-recreated-or-written-over"
  else bad "r9-red-c-noclobber-empty-instant-record-$r9_gap-d-is-not-recreated-or-written-over" \
    "$(r7_state) hook=$([ -d "$B/gap.once" ] && echo fired || echo NOT-fired) record=$([ -e "$REC" ] && echo "there,perm=$(stat -c %a "$REC"),bytes=$(stat -c %s "$REC")" || echo none) same-as-race=$(r7_same && echo yes || echo NO)"; fi
done

# ---- NIT 1, the rest: an `ln` that reports failure after making the link.
box r9-nit1-ln; r9_copy
r9_real_ln="$(PATH="$BASE_PATH" command -v ln)"
printf '#!/bin/bash\n%q "$@"\nexit 1\n' "$r9_real_ln" > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
r7_run '' --t502r7-offer-only "$U" repoA-2 repoA-3 repoA-3 "$REC"
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = name-drift ] && [ "$(get from)" = repoA-2 ] && r7_err_has "$R7_ASKED" && ! r7_err_has "the offer could not be written to"; then
  ok r9-red-nit1-an-ln-that-fails-after-making-the-link-is-this-writers-create
else bad r9-red-nit1-an-ln-that-fails-after-making-the-link-is-this-writers-create "$(r7_state)"; fi

# ---- D: case 6/7 also matches the attempt it loaded.
box r9-d; r9_copy; r7_bind_rec "$REC" bind-failed; r7_bind_rec "$B/put0" bind-failed
sed -e 's/^bind=1$/bind=2/' -e 's/^why=.*/why=the second attempt refused/' "$B/put0" > "$B/put"
r7_site "T502R7_GONE_FROM=guard_bind_site T502R7_PUT=$B/put"
if [ "$R7_RC" = 2 ] && [ "$(get bind)" = 2 ] && [ "$(get mode)" = name-drift ] && r7_err_has "the second attempt refused" && r7_err_has "is attempt 3 of 3" &&
   ! r7_err_has "the stand-in refused" && ! r7_err_has "is attempt 2 of 3"; then
  ok r9-red-d-case-6-7-a-bind-failed-record-of-another-attempt-is-answered-as-that-attempt
else bad r9-red-d-case-6-7-a-bind-failed-record-of-another-attempt-is-answered-as-that-attempt "$(r7_state) bind=$(get bind) why=$(get why)"; fi

# ---- E: a dangling link is dropped and the offer made; a directory is for the
# person to remove.
box r9-e-dangling; r9_copy; ln -s "$B/nowhere" "$REC"
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && [ -f "$REC" ] && [ ! -L "$REC" ] && [ "$(get mode)" = name-drift ] && r7_err_has "$R7_ASKED" && ! r7_err_has "could not be replaced"; then
  ok r9-red-e-a-dangling-link-at-the-records-path-is-dropped-and-the-offer-made
else bad r9-red-e-a-dangling-link-at-the-records-path-is-dropped-and-the-offer-made "$(r7_state) link=$([ -L "$REC" ] && echo still || echo no)"; fi

box r9-e-dir; r9_copy; mkdir "$REC"
r7_offer_site '' hello
if [ "$R7_RC" = 2 ] && r7_err_has "It is a directory, or a link to one: remove it, then send your prompt again." && ! r7_err_has "question will be asked afresh" && [ -z "$(ls -A "$REC")" ]; then
  ok r9-red-e-a-directory-at-the-records-path-is-for-the-person-to-remove
else bad r9-red-e-a-directory-at-the-records-path-is-for-the-person-to-remove "$(r7_state)"; fi

# ---- F: a GBT_MOVED the environment carries does not skip the first round.
box r9-f; r9_copy; r7_bind_rec "$REC" bind-failed; r7_put binding
r7_site "T502R7_GONE_FROM=guard_bind_site T502R7_PUT=$B/put GBT_MOVED=1"
if r7_same && [ "$R7_RC" = 2 ] && r7_err_has "BINDING IN PROGRESS" && ! r7_err_has "was changed while it was being answered"; then
  ok r9-red-f-an-inherited-gbt-moved-does-not-skip-the-first-round
else bad r9-red-f-an-inherited-gbt-moved-does-not-skip-the-first-round "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

# ---- H: the allowance becomes a bind record between the site's read and its drop.
box r9-h; r9_copy; r7_allow_rec "$REC" old-name; r7_put binding
r7_offer_site "T502R9_FLIP=$B/put" hello
if r7_same && [ "$R7_RC" = 2 ] && r7_err_has "BINDING IN PROGRESS" && ! r7_err_has "could not be replaced"; then
  ok r9-red-h-an-allowance-that-became-a-bind-record-is-answered-once-and-not-refused
else bad r9-red-h-an-allowance-that-became-a-bind-record-is-answered-once-and-not-refused "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

# ---- The window: only the `.bind.*` names listed before the re-read are removed.
box r9-fresh; r9_copy; r7_offer_rec "$REC" repoA-9 repoA-9
r7_answer "T502R9_FRESH=1"
if [ "$R7_RC" = 3 ] && [ ! -e "$REC" ] && [ -e "$REC.bind.9.out" ]; then
  ok r9-red-window-a-fresh-out-that-appears-after-the-re-read-survives-the-drop
else bad r9-red-window-a-fresh-out-that-appears-after-the-re-read-survives-the-drop "$(r7_state) fresh=$([ -e "$REC.bind.9.out" ] && echo kept || echo GONE)"; fi

# ---- A control for the window: a `.bind.*` listed before the re-read goes with
# the offer it belonged to (the drop's old work, kept).
box r9-fresh-control; r9_copy; r7_offer_rec "$REC" repoA-9 repoA-9; : > "$REC.bind.1.out"
r7_answer ''
if [ "$R7_RC" = 3 ] && [ ! -e "$REC" ] && [ ! -e "$REC.bind.1.out" ]; then
  ok r9-control-window-a-bind-file-listed-before-the-re-read-is-removed-with-the-offer
else bad r9-control-window-a-bind-file-listed-before-the-re-read-is-removed-with-the-offer "$(r7_state) out=$([ -e "$REC.bind.1.out" ] && echo kept || echo gone)"; fi


# ---- ROUND 10: T502's parts 42 to 47, Codex's S1, S2, S3 and S6 and NITs 1 to 3
# on spec#47's draft 17 (lane 3's Codex delta review at 8bc6b29e, report
# spec-47-8bc6b29e.md), lane 5's final check of 6253b0ed (C, E and H) and lane 5's
# wording note to lane 2 (#165 6888777622); BRIEF-T502P42-1115.md. Codex's findings
# and lane 5's, not lane 3's rulings and not Brett's. Cases named `r10-red-*` fail
# at `6253b0ed` (part 41) and pass at part 47; `r10-control-*` pass at both.
#
# `r10_copy` is round 9's copy with four more hooks, each anchored on one line
# that 6253b0ed and part 47 both have once. Every window is opened at a line by a
# hook, never by a sleep; a peer that starts a detached outer is waited for by
# polling its `.out` for the outer's start line, as round 8's peer is:
#   * after `guard_bind_site`'s `gbt_bs=` line, which follows its load:
#     `T502R10_PEER5=<marker>` runs round 8's peer once (`--t502r8-peer`, with
#     `binding`): it drops the loaded `bound`, makes the offer, answers 2 and
#     returns once its outer has started, its body held until `$B/release`;
#   * before choice 1's `mv`, as an `elif` arm that is never taken:
#     `T502R10_PEER2=<marker>` runs, once, an answer 2 to the same offer
#     (`--t502r10-answer2`), which returns once its outer has started;
#   * before `guard_offer`'s `ln`, as an `elif` arm that is never taken:
#     `T502R10_MKDIR=1` makes a directory at the record's path;
#   * the arm `--t502r10-answer2 <uuid> <lane> <session> <offer>`;
#   * (part 49) before choice 1's `mv`, as another `elif` arm that is never taken:
#     `T502R10_NEWOUT=<marker>` puts, once, an answer 2's `binding` and its
#     `.bind.1.out` in place with no outer started;
#   * (part 49) just before the noclobber open, after round 8's hook:
#     `T502R10_NC_LINK=<marker>` puts, once, a link to `/dev/null` at the
#     record's path.
# The other stand-ins are tools first on PATH: an `mv` whose nth call naming the
# record puts another file there and fails (an I/O failure while another writer
# changes the record), and a `cat` that writes and then replaces the record.
r10_copy() {
  r9_copy
  r10_c="$B/lanes-edit-r10.sh"
  cat > "$B/h10-arm.sh" <<'EOF'
    if [ "${1-}" = --t502r10-answer2 ]; then
      G_ID="$2"; G_LANE="$3"; G_NAME="$4"; G_WINREF=@1
      guard_answer "$5" 2 "%1" >/dev/null 2>&1
      r10_i=0
      while [ "$r10_i" -lt 150 ] && ! grep -q 'attempt 1 for transcript' "$5".bind.*.out 2>/dev/null; do sleep 0.2; r10_i=$((r10_i + 1)); done
      exit 0
    fi
EOF
  printf '%s\n' '  [ -z "${T502R10_PEER5:-}" ] || ! mkdir -- "$T502R10_PEER5.once" 2>/dev/null || bash "$RESOLVED" guard-bind --t502r8-peer "$G_ID" "$G_LANE" "$G_NAME" "$GBR_TO" "$gbt_f" binding </dev/null >> "$T502R10_PEER5.log" 2>&1 || :' > "$B/h10-peer5.sh"
  printf '%s\n' '    elif [ -n "${T502R10_PEER2:-}" ] && mkdir -- "$T502R10_PEER2.once" 2>/dev/null && { bash "$RESOLVED" guard-bind --t502r10-answer2 "$G_ID" "$G_LANE" "$G_NAME" "$ga_f" </dev/null >> "$T502R10_PEER2.log" 2>&1; false; }; then' '      :' > "$B/h10-peer2.sh"
  printf '%s\n' '      elif [ -n "${T502R10_MKDIR:-}" ] && mkdir -- "$go_f" 2>/dev/null && false; then' '        :' > "$B/h10-mkdir.sh"
  # PART 49's TWO: an answer 2's `binding` and `.out` with no outer started yet,
  # put in place before choice 1's `mv`; and a link to `/dev/null` put at the
  # record's path just before the noclobber open (`command -p`, past the fakes).
  printf '%s\n' '    elif [ -n "${T502R10_NEWOUT:-}" ] && mkdir -- "$T502R10_NEWOUT.once" 2>/dev/null && { { printf '"'"'mode=binding\n'"'"'; grep -v '"'"'^mode='"'"' "$ga_f"; printf '"'"'out=%s\n'"'"' "$ga_f.bind.1.out"; } > "$ga_f.p49" && mv -f -- "$ga_f.p49" "$ga_f" && : > "$ga_f.bind.1.out"; false; }; then' '      :' > "$B/h10-newout.sh"
  printf '%s\n' 'r10_nc_hook() { [ -n "${T502R10_NC_LINK:-}" ] && mkdir -- "$T502R10_NC_LINK.once" 2>/dev/null && command -p ln -s /dev/null "$go_f"; return 0; }' > "$B/h10-nc.sh"
  r10_a5='  gbt_bs="${GBR_BOUND:-its}"'
  r10_a2='    elif ! mv -f -- "$ga_t" "$ga_f" 2>/dev/null; then'
  r10_a1='      elif ln -- "$go_t" "$go_f" 2>/dev/null; then'
  awk -v arm="$B/h10-arm.sh" -v p5="$B/h10-peer5.sh" -v p2="$B/h10-peer2.sh" -v mk="$B/h10-mkdir.sh" \
      -v nw="$B/h10-newout.sh" -v nc="$B/h10-nc.sh" \
      -v a5="$r10_a5" -v a2="$r10_a2" -v a1="$r10_a1" '
    function cat(f,   l) { while ((getline l < f) > 0) print l; close(f) }
    $0 == a2 { cat(p2); cat(nw); b++ }
    $0 == a1 { cat(mk); c++ }
    index($0, "guard_offer() {   # <offer file> <pane>") == 1 { cat(nc); e++ }
    index($0, "r8_race_hook && ( set -C; umask 077;") > 0 { i = index($0, "( set -C"); $0 = substr($0, 1, i - 1) "r10_nc_hook && " substr($0, i); f++ }
    { print }
    $0 == a5 { cat(p5); a++ }
    $0 == "  guard-bind)" { cat(arm); d++ }
    END { exit (a == 1 && b == 1 && c == 1 && d == 1 && e == 1 && f == 1 ? 0 : 1) }' "$B/lanes-edit-r9.sh" > "$r10_c" ||
    printf 'r10_copy: an anchor was not found exactly once\n' >&2
  chmod 755 "$r10_c"
  R8_COPY="$r10_c"
}

# THE HOOK, NOT WAITED FOR: a case whose outer is held runs this, then releases
# the body and waits for the box's processes (`r8_settle`). Bounded by `timeout`,
# since a FIFO at the record's path would block any read of it.
r10_run() {   # <env assignments, one word each, or ''> <the hook arm and its arguments>
  r10_e="$1"; shift
  # shellcheck disable=SC2086
  r10_o="$(run_env LANES_HOST=Eagle LANES_IN_CONTAINER=0 LANES_LANE_START="$B/lane-start-stub" LANES_BIND_BODY="$STUB" \
    T502R8_SNAP="$B/snap" $r10_e timeout 120 bash "$B/lanes-edit-r10.sh" guard-bind "$@" 2>"$B/r7-err")"
  R7_RC="${r10_o##*-rc=}"
  R7_ERR="$(cat -- "$B/r7-err")"
}
r10_has() { case "${1-}" in *"$2"*) return 0 ;; esac; return 1; }

# A STAND-IN `mv`: its <n>th call that names the record as its target puts <file>
# in the record's place, as another writer's write would land, and fails, as an
# I/O failure of this writer's rewrite would; every other call is the real one.
r10_mv_put() {   # <n> <file>
  r10_real_mv="$(PATH="$BASE_PATH" command -v mv)"; r10_real_cat="$(PATH="$BASE_PATH" command -v cat)"
  {
    printf '#!/bin/bash\nlast=""\nfor a in "$@"; do last="$a"; done\n'
    printf 'if [ "$last" = %q ]; then\n' "$REC"
    printf '  n=$(( $(%q %q 2>/dev/null || echo 0) + 1 )); echo "$n" > %q\n' "$r10_real_cat" "$B/mv-n" "$B/mv-n"
    printf '  if [ "$n" = %q ]; then cp -p -- %q %q; exit 1; fi\nfi\n' "$1" "$2" "$REC"
    printf 'exec %q "$@"\n' "$r10_real_mv"
  } > "$B/fakes/mv"
  chmod 755 "$B/fakes/mv"
}

# ---- S2: a pause after case 5's load. Another invocation hears the old `bound`,
# drops it, makes the offer and answers 2, and its outer is running; case 5 then
# resumes. At 6253b0ed its unconditional drop removed the newer `binding` and the
# live outer's `.out`; now the record is not the one loaded, nothing is removed,
# and the newer bind is answered once: BINDING IN PROGRESS.
box r10-s2; r10_copy; r8_block_body; r7_bind_rec "$REC" bound; printf 'the old attempt\n' > "$OUT"
r10_run "T502R10_PEER5=$B/peer5" --t502r7-site "$U" repoA-2 repoA-3 "$REC"
r10_rc="$R7_RC"; r10_err="$R7_ERR"; r10_fired=no; [ -d "$B/peer5.once" ] && r10_fired=yes
r10_rec=no; cmp -s -- "$B/snap.rec" "$REC" && r10_rec=yes
r10_out=no; cmp -s -- "$B/snap.out" "$OUT" && r10_out=yes
: > "$B/release"; r8_settle
if [ "$r10_rc" = 2 ] && [ "$r10_fired" = yes ] && [ "$r10_rec" = yes ] && [ "$r10_out" = yes ] && [ "$R7_LEFT" = 0 ] &&
   r10_has "$r10_err" "BINDING IN PROGRESS" && ! r10_has "$r10_err" "MOVED: this window"; then
  ok r10-red-s2-case-5-paused-after-its-load-leaves-a-newer-live-bind-and-its-out-and-answers-it
else bad r10-red-s2-case-5-paused-after-its-load-leaves-a-newer-live-bind-and-its-out-and-answers-it \
  "rc=$r10_rc peer=$r10_fired record-same=$r10_rec out-same=$r10_out left=$R7_LEFT err=[$(printf '%s' "$r10_err" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi

# ---- S3: answers 1 and 2 at once. Choice 1 passes its check; an answer 2 to the
# same offer then rewrites it to `binding` and starts its outer; choice 1's `mv`
# then replaces that record. At 6253b0ed its sweep unlinked the live outer's
# `.out`; now the `.out` is kept, the person is told plainly, and the outer, finding
# the record no longer its own, writes how it ended to that `.out`.
box r10-s3; r10_copy; r8_block_body; r7_offer_rec
r10_run "T502R10_PEER2=$B/peer2" --t502r7-answer "$U" repoA-2 repoA-3 "$REC" 1
r10_rc="$R7_RC"; r10_err="$R7_ERR"; r10_fired=no; [ -d "$B/peer2.once" ] && r10_fired=yes
r10_mode="$(get mode)"; r10_mid=GONE; [ -e "$OUT" ] && r10_mid=there
: > "$B/release"; r8_settle
r10_end=GONE; [ -e "$OUT" ] && r10_end=there
r10_said=no; grep -q -F "$NOT_OWN" "$OUT" 2>/dev/null && r10_said=yes
if [ "$r10_rc" = 2 ] && [ "$r10_fired" = yes ] && [ "$r10_mode" = allow ] && [ "$r10_mid" = there ] && [ "$r10_end" = there ] && [ "$r10_said" = yes ] &&
   [ "$R7_LEFT" = 0 ] && r10_has "$r10_err" "THIS ANSWER \`1\` MET AN ANSWER \`2\` MADE AT THE SAME MOMENT" &&
   r10_has "$r10_err" "(its output is $OUT)" && ! r10_has "$r10_err" "ALLOWED: this lane/session"; then
  ok r10-red-s3-answers-1-and-2-at-once-keep-the-live-out-and-say-so-plainly
else bad r10-red-s3-answers-1-and-2-at-once-keep-the-live-out-and-say-so-plainly \
  "rc=$r10_rc peer=$r10_fired mode=$r10_mode out-mid=$r10_mid out-end=$r10_end outer-said-not-own=$r10_said left=$R7_LEFT err=[$(printf '%s' "$r10_err" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi

# THE SWEEP TAKES ONLY THE OFFER'S OWN: a name listed before the check whose index
# is above the `out` the offer names is not swept (red), and the offer's own are
# (a control).
box r10-s3-above; r10_copy; r7_offer_rec; printf '%s\n' "out=$REC.bind.1.out" bind=1 >> "$REC"
printf 'own\n' > "$REC.bind.1.out"; printf 'not its own\n' > "$REC.bind.3.out"
r7_choice1 ''
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = allow ] && [ ! -e "$REC.bind.1.out" ] && [ -e "$REC.bind.3.out" ] && r7_err_has "ALLOWED: this lane/session"; then
  ok r10-red-s3-choice-1-never-sweeps-a-name-above-the-offers-own-attempt
else bad r10-red-s3-choice-1-never-sweeps-a-name-above-the-offers-own-attempt "$(r7_state) own=$([ -e "$REC.bind.1.out" ] && echo kept || echo swept) above=$([ -e "$REC.bind.3.out" ] && echo kept || echo SWEPT)"; fi

box r10-s3-own; r10_copy; r7_offer_rec; printf '%s\n' "out=$REC.bind.2.out" bind=2 >> "$REC"
printf 'first\n' > "$REC.bind.1.out"; printf 'second\n' > "$REC.bind.2.out"; : > "$REC.bind.2.facts"
r7_choice1 ''
if [ "$R7_RC" = 2 ] && [ "$(get mode)" = allow ] && [ "$(r7_ls)" = "$U " ] && r7_err_has "ALLOWED: this lane/session"; then
  ok r10-control-s3-choice-1-sweeps-the-offers-own-attempts-files
else bad r10-control-s3-choice-1-sweeps-the-offers-own-attempts-files "$(r7_state)"; fi

# ---- S1: a directory made between `guard_offer`'s `-d` test and its `ln`. At
# 6253b0ed the link was left inside it; now it is removed, and the path is
# answered as a directory, which is not a regular file.
box r10-s1; r10_copy
r7_offer_site "T502R10_MKDIR=1" hello
r10_in="$(ls -A "$REC" 2>/dev/null | wc -l | tr -d ' ')"
if [ "$R7_RC" = 2 ] && [ -d "$REC" ] && [ "$r10_in" = 0 ] && [ -z "$(temps)" ] &&
   r7_err_has "It is not a regular file. It is a directory, or a link to one: remove it, then send your prompt again." && ! r7_err_has "$R7_ASKED"; then
  ok r10-red-s1-a-directory-made-between-the-test-and-ln-keeps-no-link-inside-it
else bad r10-red-s1-a-directory-made-between-the-test-and-ln-keeps-no-link-inside-it "$(r7_state) dir=$([ -d "$REC" ] && echo yes || echo no) inside=$r10_in"; fi

# ---- S6: an I/O failure in each message path, while another writer puts an
# allowance in the record's place. At 6253b0ed each message said the old record
# remained; now each says this writer changed nothing and the next prompt reads
# whatever is there, and the allowance is left byte for byte.
R10_NOW="(it says mode=allow now)"
for r10_case in 6 9 10; do
  box "r10-s6-case-$r10_case"; r10_copy
  case "$r10_case" in
    6)  r7_bind_rec "$REC" bind-failed ;;
    9)  r7_bind_rec "$REC" binding Eagle past ;;
    10) r7_bind_rec "$REC" binding Other-host past ;;
  esac
  r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"; r10_mv_put 1 "$B/put"
  r7_site ''
  if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "…and the offer could not be restored in $REC. This prompt changed nothing there, and the record is no longer the one it read $R10_NOW, so the next prompt reads whatever is there." &&
     ! r7_err_has "so this prompt's answer is the same as the last one's"; then
    ok "r10-red-s6-case-$r10_case-io-failure-is-worded-on-the-record-read-again"
  else bad "r10-red-s6-case-$r10_case-io-failure-is-worded-on-the-record-read-again" "$(r7_state) same=$(r7_same && echo yes || echo NO) mv-calls=$(cat "$B/mv-n" 2>/dev/null)"; fi
done

for r10_where in head-copy binding-rewrite; do
  box "r10-s6-$r10_where"; r10_copy; r7_offer_rec; r7_cache
  r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"; r10_mv_put 1 "$B/put"
  case "$r10_where" in head-copy) r7_answer "T502R7_CACHE=$B/cache" ;; *) r7_answer '' ;; esac
  if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && r7_same && [ ! -e "$OUT" ] &&
     r7_err_has "the bind could not be recorded in $REC, so it was NOT started: NOTHING has been written to the register, and this answer changed nothing at $REC, where the record is no longer the offer that was answered $R10_NOW." &&
     r7_err_has "the lane it was before the answer \`2\`, which started no bind." && ! r7_err_has "the offer is KEPT"; then
    ok "r10-red-s6-answer-2-$r10_where-io-failure-is-worded-on-the-record-read-again"
  else bad "r10-red-s6-answer-2-$r10_where-io-failure-is-worded-on-the-record-read-again" "$(r7_state) same=$(r7_same && echo yes || echo NO) mv-calls=$(cat "$B/mv-n" 2>/dev/null)"; fi
done

box r10-s6-back-out; r10_copy; r7_offer_rec
r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"; r10_mv_put 2 "$B/put"
r7_answer "T502R7_NOCHILD=1"
if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "the record could not be written back to the question, and it is no longer this answer's binding (it says mode=allow now): this answer changed nothing more there, and the next prompt reads whatever is there." &&
   r7_err_has "the lane it was before the answer \`2\`, which started no bind." && ! r7_err_has "so it still says binding"; then
  ok r10-red-s6-back-out-io-failure-is-worded-on-the-record-read-again
else bad r10-red-s6-back-out-io-failure-is-worded-on-the-record-read-again "$(r7_state) same=$(r7_same && echo yes || echo NO) mv-calls=$(cat "$B/mv-n" 2>/dev/null)"; fi

# A CONTROL: the same failure with no other writer keeps round 9's words, now
# with the record read again behind them.
box r10-s6-control-case-6; r10_copy; r7_bind_rec "$REC" bind-failed; r7_save
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/mv"; chmod 755 "$B/fakes/mv"
r7_site ''
if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "…and the offer could not be restored in $REC, so this prompt's answer is the same as the last one's until it can"; then
  ok r10-control-s6-case-6-io-failure-with-the-record-unchanged-keeps-its-words
else bad r10-control-s6-case-6-io-failure-with-the-record-unchanged-keeps-its-words "$(r7_state)"; fi

# ---- NIT 2 / E: a FIFO at the record's path is "not a regular file", not a
# directory.
box r10-fifo; r10_copy; mkfifo "$REC"
r10_run '' --t502r7-offer "$U" repoA-2 repoA-3 repoA-3 "$REC" hello
if [ "$R7_RC" = 2 ] && [ -p "$REC" ] && r7_err_has "It is not a regular file (a FIFO, a socket or a device, or a link to one): remove it, then send your prompt again." &&
   ! r7_err_has "It is a directory" && ! r7_err_has "$R7_ASKED"; then
  ok r10-red-nit2-a-fifo-at-the-records-path-is-not-a-regular-file-and-not-a-directory
else bad r10-red-nit2-a-fifo-at-the-records-path-is-not-a-regular-file-and-not-a-directory \
  "rc=$R7_RC fifo=$([ -p "$REC" ] && echo yes || echo no) err=[$(printf '%s' "$R7_ERR" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi   # never `r7_state`, whose read of the record would block on the FIFO

# ---- NIT 1 / C: noclobber's success test. After the content is written, and
# before the test, the record is replaced by another invocation's. At 6253b0ed the
# `-e` test took it for this writer's and asked the question; now it is answered
# as a record that is there (3), and left byte for byte.
box r10-noclobber; r10_copy; r7_bind_rec "$B/race-record" bound; cp -p -- "$B/race-record" "$B/was"
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
r10_real_cat="$(PATH="$BASE_PATH" command -v cat)"
{
  printf '#!/bin/bash\n%q "$@"; st=$?\n' "$r10_real_cat"
  printf 'case "${2-}" in %q/.*) if mkdir %q 2>/dev/null; then cp -p -- %q %q && mv -f -- %q %q; fi ;; esac\n' \
    "$OFF" "$B/cat.once" "$B/race-record" "$REC.new" "$REC.new" "$REC"
  printf 'exit "$st"\n'
} > "$B/fakes/cat"; chmod 755 "$B/fakes/cat"
r7_offer_only ''
if [ "$R7_RC" = 3 ] && r7_same && [ -d "$B/cat.once" ] && ! r7_err_has "$R7_ASKED" && [ -z "$(temps)" ]; then
  ok r10-red-nit1-noclobber-success-is-proved-on-the-descriptor-and-a-replacement-is-not-taken-for-it
else bad r10-red-nit1-noclobber-success-is-proved-on-the-descriptor-and-a-replacement-is-not-taken-for-it "$(r7_state) hook=$([ -d "$B/cat.once" ] && echo fired || echo NOT-fired) same=$(r7_same && echo yes || echo NO)"; fi

# ---- H: the allowance becomes a new `name-drift` offer before the site's drop.
# At 6253b0ed it was refused as "changed"; now it is answered as the first read
# would, with this prompt, and the offer is left as it was.
box r10-h; r10_copy; r7_allow_rec "$REC" old-name; r7_offer_rec "$B/put" repoA-3 repoA-3; cp -p -- "$B/put" "$B/was"
r7_offer_site "T502R9_FLIP=$B/put" hello
if [ "$R7_RC" = 2 ] && r7_same && r7_err_has "that is not an answer to the pending question" && ! r7_err_has "was changed while it was being answered"; then
  ok r10-red-h-an-allowance-that-became-an-offer-is-answered-as-the-first-read-would
else bad r10-red-h-an-allowance-that-became-an-offer-is-answered-as-the-first-read-would "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

# ---- (A)'s rename-back note: the first clause kept, no offer said to be kept.
box r10-a-wording; r10_copy; r7_offer_rec; r7_save; r7_cache
r7_answer "T502R7_CACHE=$B/cache T502R7_GONE_FROM=guard_bind_head_copy"
if r7_a_state && r7_err_has "This window has been renamed back to repoA-2, the lane it was before the answer \`2\`, which started no bind." &&
   ! r7_err_has "so the offer it keeps is still this window's"; then
  ok r10-red-a-the-rename-back-note-keeps-its-first-clause-and-says-no-offer-is-kept
else bad r10-red-a-the-rename-back-note-keeps-its-first-clause-and-says-no-offer-is-kept "$(r7_state)"; fi

# A CONTROL: case 6's rename-back note keeps its text.
box r10-a-wording-control; r10_copy; r7_bind_rec "$REC" bind-failed
r7_site ''
if [ "$R7_RC" = 2 ] && r7_err_has "This window has been renamed back to repoA-2, the lane it was before the answer \`2\`, so the offer it keeps is still this window's."; then
  ok r10-control-a-case-6-keeps-its-rename-back-note
else bad r10-control-a-case-6-keeps-its-rename-back-note "$(r7_state)"; fi

# ---- PART 48 (lane 5's check of parts 42 to 47): the answer 2 that meets an
# allowance keeps no offer, so its rename-back note is `none`'s, and cases 6 and 9
# whose restore fails on a record another writer changed say no offer is kept.
# Red at `1c61300e` (part 47), green at part 48. The allowance is put in the
# record's place before the answer's rewrite to `binding`, by round 7's hook.
box r10-p48-allow; r10_copy; r7_offer_rec; r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"
r7_answer "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1 T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 3 ] && [ "$R7_LEFT" = 0 ] && [ ! -e "$OUT" ] && [ "$(r7_tmux)" = "rename-window repoA-3;rename-window repoA-2;" ] &&
   r7_err_has "This window has been renamed back to repoA-2, the lane it was before the answer \`2\`, which started no bind." &&
   ! r7_err_has "offer it keeps"; then
  ok r10-red-p48-the-answer-2-that-meets-an-allowance-renames-back-in-nones-words
else bad r10-red-p48-the-answer-2-that-meets-an-allowance-renames-back-in-nones-words "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

box r10-p48-allow-back-fails; r10_copy; r7_offer_rec; r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"; r8_tmux_back_fails
r7_answer "T502R7_GONE_FROM=guard_answer T502R7_GONE_NTH=1 T502R7_PUT=$B/put"
if r7_same && [ "$R7_RC" = 3 ] && [ "$R7_LEFT" = 0 ] &&
   r7_err_has "This window could NOT be renamed back to repoA-2, so it still carries repoA-3's name, though the answer \`2\` started no bind." &&
   ! r7_err_has "drop the kept offer"; then
  ok r10-red-p48-the-answer-2-that-meets-an-allowance-and-cannot-rename-back-says-it-started-no-bind
else bad r10-red-p48-the-answer-2-that-meets-an-allowance-and-cannot-rename-back-says-it-started-no-bind "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi

for r10_case in 6 9; do
  box "r10-p48-case-$r10_case"; r10_copy
  case "$r10_case" in
    6) r7_bind_rec "$REC" bind-failed ;;
    9) r7_bind_rec "$REC" binding Eagle past ;;
  esac
  r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"; r10_mv_put 1 "$B/put"
  r7_site ''
  if [ "$R7_RC" = 2 ] && r7_same &&
     r7_err_has "This window has been renamed back to repoA-2, the lane it was before the answer \`2\`; the record no longer holds that answer's offer, so the next prompt reads whatever is there." &&
     ! r7_err_has "offer it keeps"; then
    ok "r10-red-p48-case-$r10_case-whose-restore-fails-on-a-changed-record-says-no-offer-is-kept"
  else bad "r10-red-p48-case-$r10_case-whose-restore-fails-on-a-changed-record-says-no-offer-is-kept" "$(r7_state) same=$(r7_same && echo yes || echo NO)"; fi
done

# ---- PART 49 (lane 5's adversarial review of parts 42 to 47, its NITs 2, 3, 4
# and 6; BRIEF-T502P49-1115.md). Red at `3e6dc617` (part 48), green at part 49.
# NIT-2: on primary the head copy writes the prefetch's keys into the offer (the
# record's first `mv`), and the rewrite to `binding` (its second) then fails while
# another writer puts an allowance in its place. The refusal names that one write,
# and never says this answer changed nothing there.
box r10-p49-nit2; r10_copy; r7_offer_rec; r7_cache
r7_allow_rec "$B/put"; cp -p -- "$B/put" "$B/was"; r10_mv_put 2 "$B/put"
r7_answer "T502R7_CACHE=$B/cache"
if [ "$R7_RC" = 2 ] && [ "$R7_LEFT" = 0 ] && r7_same && [ ! -e "$OUT" ] && [ "$(cat "$B/mv-n" 2>/dev/null)" = 2 ] &&
   r7_err_has "the bind could not be recorded in $REC, so it was NOT started: NOTHING has been written to the register, and this answer's one write at $REC was its copy of the prefetch's \`c\`, \`n_a\` and \`w_s_ms\` into the offer; the record there is no longer the offer that was answered (it says mode=allow now). Send your prompt again: the next prompt reads whatever is there." &&
   r7_err_has "the lane it was before the answer \`2\`, which started no bind." && ! r7_err_has "this answer changed nothing at"; then
  ok r10-red-p49-nit2-a-failed-binding-rewrite-after-the-head-copy-wrote-names-that-write
else bad r10-red-p49-nit2-a-failed-binding-rewrite-after-the-head-copy-wrote-names-that-write "$(r7_state) same=$(r7_same && echo yes || echo NO) mv-calls=$(cat "$B/mv-n" 2>/dev/null)"; fi

# NIT-3: case 6's restore fails, and the record is then there and cannot be read
# (a stand-in `mv` moves it aside and makes a directory in its place). The words
# say only that it could not be read again.
box r10-p49-nit3; r10_copy; r7_bind_rec "$REC" bind-failed
r10_real_mv="$(PATH="$BASE_PATH" command -v mv)"
{
  printf '#!/bin/bash\nlast=""\nfor a in "$@"; do last="$a"; done\n'
  printf 'if [ "$last" = %q ]; then %q -- %q %q && mkdir -- %q; exit 1; fi\n' "$REC" "$r10_real_mv" "$REC" "$B/rec-was" "$REC"
  printf 'exec %q "$@"\n' "$r10_real_mv"
} > "$B/fakes/mv"; chmod 755 "$B/fakes/mv"
r7_site ''
if [ "$R7_RC" = 2 ] && [ -d "$REC" ] && [ -f "$B/rec-was" ] &&
   r7_err_has "…and the offer could not be restored in $REC. This prompt changed nothing there, and the record could not be read again, so the next prompt reads whatever is there." &&
   ! r7_err_has "is no longer the one it read" && ! r7_err_has "cannot be read now"; then
  ok r10-red-p49-nit3-case-6-whose-restore-fails-on-a-record-that-cannot-be-read-again-says-only-that
else bad r10-red-p49-nit3-case-6-whose-restore-fails-on-a-record-that-cannot-be-read-again-says-only-that "$(r7_state) dir=$([ -d "$REC" ] && echo yes || echo no)"; fi

# PART 50 (lane 5's ruling on part 49's doubt): the same failed restore, and the
# rename-back note in `unread`'s words, which claim only that the record could not
# be read again, not that it "no longer holds that answer's offer". Red at
# `88d76394` (part 49), green at part 50.
box r10-p50-unread; r10_copy; r7_bind_rec "$REC" bind-failed
r10_real_mv="$(PATH="$BASE_PATH" command -v mv)"
{
  printf '#!/bin/bash\nlast=""\nfor a in "$@"; do last="$a"; done\n'
  printf 'if [ "$last" = %q ]; then %q -- %q %q && mkdir -- %q; exit 1; fi\n' "$REC" "$r10_real_mv" "$REC" "$B/rec-was" "$REC"
  printf 'exec %q "$@"\n' "$r10_real_mv"
} > "$B/fakes/mv"; chmod 755 "$B/fakes/mv"
r7_site ''
r10_rb_unread="This window has been renamed back to repoA-2, the lane it was before the answer \`2\`; the record could not be read again, so the next prompt reads whatever is there."
if [ "$R7_RC" = 2 ] && [ -d "$REC" ] && [ -f "$B/rec-was" ] && [ "$(r7_tmux)" = "rename-window repoA-2;" ] &&
   r7_err_has "$r10_rb_unread" && ! r7_err_has "the record no longer holds that answer's offer" && ! r7_err_has "offer it keeps"; then
  ok r10-red-p50-case-6-whose-restore-fails-on-a-record-that-cannot-be-read-again-renames-back-in-unreads-words
else bad r10-red-p50-case-6-whose-restore-fails-on-a-record-that-cannot-be-read-again-renames-back-in-unreads-words "$(r7_state) dir=$([ -d "$REC" ] && echo yes || echo no)"; fi

# NIT-4: hard links are refused, so the create is the noclobber one, and a link to
# `/dev/null` is put at the record's path just before its open. `noclobber` opens
# that existing non-regular file without `O_EXCL`; it is not this writer's create,
# so it is answered as a record that is there (3), and the question is not asked.
box r10-p49-nit4; r10_copy
printf '#!/bin/bash\nexit 1\n' > "$B/fakes/ln"; chmod 755 "$B/fakes/ln"
r7_offer_only "T502R10_NC_LINK=$B/nclink"
if [ "$R7_RC" = 3 ] && [ -d "$B/nclink.once" ] && [ -L "$REC" ] && [ "$(readlink -- "$REC")" = /dev/null ] &&
   ! r7_err_has "$R7_ASKED" && [ -z "$(temps)" ]; then
  ok r10-red-p49-nit4-a-link-to-dev-null-put-before-the-noclobber-open-is-not-made
else bad r10-red-p49-nit4-a-link-to-dev-null-put-before-the-noclobber-open-is-not-made \
  "rc=$R7_RC hook=$([ -d "$B/nclink.once" ] && echo fired || echo NOT-fired) link=$(readlink -- "$REC" 2>/dev/null) err=[$(printf '%s' "$R7_ERR" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi

# NIT-6: choice 1 passes its check; an answer 2's `binding` and `.out` are then put
# in place with no outer started, and choice 1's `mv` writes the allowance over
# them. The note says that answer MAY have started a bind; its outer, started only
# now, finds the allowance, runs nothing, and says so in that output.
box r10-p49-nit6; r10_copy; r7_offer_rec
r7_choice1 "T502R10_NEWOUT=$B/newout"
r10_rc="$R7_RC"; r10_err="$R7_ERR"; r10_mode="$(get mode)"
outer
if [ "$r10_rc" = 2 ] && [ -d "$B/newout.once" ] && [ "$r10_mode" = allow ] && [ -e "$OUT" ] &&
   r10_has "$SAID" "says mode=allow, not mode=binding, so nothing was run" &&
   r10_has "$r10_err" "THIS ANSWER \`1\` MET AN ANSWER \`2\` MADE AT THE SAME MOMENT: that answer may have started a bind of this window to lane repoA-3 (its output is $OUT)" &&
   r10_has "$r10_err" "if its outer had not yet made its start rewrite, it runs nothing, and says so there." &&
   ! r10_has "$r10_err" "that answer started a bind" && ! r10_has "$r10_err" "ALLOWED: this lane/session"; then
  ok r10-red-p49-nit6-the-s3-note-says-the-answer-2-may-have-started-a-bind
else bad r10-red-p49-nit6-the-s3-note-says-the-answer-2-may-have-started-a-bind \
  "rc=$r10_rc hook=$([ -d "$B/newout.once" ] && echo fired || echo NOT-fired) mode=$r10_mode outer-said=[$(printf '%s' "$SAID" | tail -n 1 | cut -c1-110)] err=[$(printf '%s' "$r10_err" | tail -n 2 | cut -c1-110 | tr '\n' '|')]"; fi

# ---- THE FOLD (spec#47's draft 19, bind-record.md:458; controls, no code change):
# "the outer folds what it holds into its outcome only where the body ended on its
# own, so that after a stop by the bound or a signal a why= or note= the body
# wrote is not in the outcome". The REAL outer runs a stand-in body that writes
# its facts file (a `why=` and a `note=`), copies it aside as proof that it was
# written, and says it is up; then it waits for `$B/release`, which never comes
# (stopped by its bound: `LANES_BIND_BOUND_S=11`, so `timeout` stops it after
# 1 s), or is stopped by a `TERM` sent to the outer once the body is up (the
# outer's pid is the record's `pid`), or ends on its own with 0 or 3. No window
# is opened by a sleep: the signal waits for the body's own marker.
R10_FWHY="the facts why: the stand-in body refused"
R10_FNOTE="the facts note: a stand-in act still owed"
r10_facts_body() {   # <exit code, or block>
  {
    printf '#!/bin/bash\n'
    printf '[ -z "${LANES_BIND_FACTS:-}" ] || { printf "%%s\\n" %q %q > "$LANES_BIND_FACTS" && cp -- "$LANES_BIND_FACTS" %q; }\n' \
      "why=$R10_FWHY" "note=$R10_FNOTE" "$B/facts-seen"
    printf ': > %q\n' "$B/body-up"
    if [ "$1" = block ]; then
      printf 'n=0\nwhile [ ! -e %q ] && [ "$n" -lt 600 ]; do sleep 0.2; n=$((n + 1)); done\nexit 0\n' "$B/release"
    else
      printf ': > %q\nexit %s\n' "$TRIG" "$1"
    fi
  } > "$STUB"
  chmod 755 "$STUB"
}
r10_fold_run() {   # <env assignments, one word each, or ''>: the REAL outer, waited for
  r10_fe="$1"; ORC=0
  # shellcheck disable=SC2086
  run_env LANES_BIND_BODY="$STUB" $r10_fe timeout 60 bash "$S" guard-bind "$U" </dev/null >>"$OUT" 2>&1 || ORC=$?
  SAID="$(cat -- "$OUT" 2>/dev/null)"
}
r10_facts_written() { [ -f "$B/facts-seen" ] && grep -q -x -F "why=$R10_FWHY" "$B/facts-seen" && grep -q -x -F "note=$R10_FNOTE" "$B/facts-seen"; }
r10_fold_none() { ! grep -q -F "$R10_FWHY" "$REC" && ! grep -q -F "$R10_FNOTE" "$REC" && ! has note; }
r10_fold_state() { printf '%s why=[%s] notes=%s facts-written=%s facts-left=%s' "$(state)" "$(get why)" \
  "$(grep -c '^note=' "$REC" 2>/dev/null)" "$(r10_facts_written && echo yes || echo NO)" "$([ -e "$FACTS" ] && echo yes || echo no)"; }

box r10-fold-bound; record; r10_facts_body block
r10_fold_run "LANES_BIND_BOUND_S=11"
r8_settle
if r10_facts_written && [ "$(get mode)" = bind-failed ] && { [ "$(get rc)" = 124 ] || [ "$(get rc)" = 137 ]; } &&
   [ "$(get why)" = "stopped by its bound; what it wrote is not known" ] && r10_fold_none && [ ! -e "$FACTS" ] &&
   [ ! -e "$B/release" ] && [ "$R7_LEFT" = 0 ]; then
  ok r10-control-fold-a-body-stopped-by-its-bound-has-neither-its-facts-why-nor-its-note-in-the-outcome
else bad r10-control-fold-a-body-stopped-by-its-bound-has-neither-its-facts-why-nor-its-note-in-the-outcome "$(r10_fold_state) left=$R7_LEFT"; fi

box r10-fold-signal; record; r10_facts_body block
( r10_fold_run "LANES_BIND_BOUND_S=60" ) &
r10_bg=$!
r10_i=0
while [ ! -e "$B/body-up" ] && [ "$r10_i" -lt 300 ]; do sleep 0.1; r10_i=$((r10_i + 1)); done
r10_opid="$(get pid)"; r10_sent=no
case "$r10_opid" in ''|*[!0-9]*) : ;; *) [ -e "$B/body-up" ] && kill -TERM "$r10_opid" 2>/dev/null && r10_sent=yes ;; esac
wait "$r10_bg" 2>/dev/null || :
r8_settle
if [ "$r10_sent" = yes ] && r10_facts_written && [ "$(get mode)" = bind-failed ] &&
   [ "$(get why)" = "stopped by a signal; what it wrote is not known" ] && r10_fold_none && [ ! -e "$FACTS" ] &&
   [ ! -e "$B/release" ] && [ "$R7_LEFT" = 0 ]; then
  ok r10-control-fold-a-body-stopped-by-a-signal-has-neither-its-facts-why-nor-its-note-in-the-outcome
else bad r10-control-fold-a-body-stopped-by-a-signal-has-neither-its-facts-why-nor-its-note-in-the-outcome "$(r10_fold_state) term-sent=$r10_sent outer-pid=$r10_opid left=$R7_LEFT"; fi

# THE CONTROLS: the same body, ending on its own. The outer folds what it holds:
# with 0 the record ends `bound` and keeps the `note=`; with 3 it ends
# `bind-failed` and the facts' `why=` is its `why`.
box r10-fold-self-0; record; r10_facts_body 0
r10_fold_run ''
if r10_facts_written && [ "$(get mode)" = bound ] && [ "$(get rc)" = 0 ] && grep -q -x -F "note=$R10_FNOTE" "$REC" && [ ! -e "$FACTS" ]; then
  ok r10-control-fold-a-body-that-ends-on-its-own-with-0-has-its-facts-note-in-the-outcome
else bad r10-control-fold-a-body-that-ends-on-its-own-with-0-has-its-facts-note-in-the-outcome "$(r10_fold_state)"; fi

box r10-fold-self-3; record; r10_facts_body 3
r10_fold_run ''
if r10_facts_written && [ "$(get mode)" = bind-failed ] && [ "$(get rc)" = 3 ] && [ "$(get why)" = "$R10_FWHY" ] && [ ! -e "$FACTS" ]; then
  ok r10-control-fold-a-body-that-ends-on-its-own-nonzero-has-its-facts-why-in-the-outcome
else bad r10-control-fold-a-body-that-ends-on-its-own-nonzero-has-its-facts-why-in-the-outcome "$(r10_fold_state)"; fi

# ---- NIT 3: the three comments.
r10_n1="$(grep -c "lane 5's ruling on lane 2's reader's window" "$S")"
r10_n2="$(grep -c 'NO CALLER USES IT NOW' "$S")"
r10_n3="$(grep -c -F '`--exist`, `--offer`, `--mode` or `--match` only' "$S")"
if [ "$r10_n1" = 0 ] && [ "$r10_n2" = 1 ] && [ "$r10_n3" = 1 ]; then ok r10-red-nit3-the-three-comments-are-corrected
else bad r10-red-nit3-the-three-comments-are-corrected "lane-5-ruling=$r10_n1 no-caller=$r10_n2 result-2=$r10_n3"; fi

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
