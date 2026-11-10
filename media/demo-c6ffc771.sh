#!/usr/bin/env bash
# Live demo recorded for carbonscott/tiled#4 at its head c6ffc771 (asciinema, 110x32):
#   asciinema rec --cols 110 --rows 32 -c "bash media/demo-c6ffc771.sh" demo-c6ffc771.cast
# Every command below runs for real while the recorder runs; nothing is replayed.
# Each command is printed ("$ ...") exactly as written here, then run with eval.
# The only post-processing of output: step 4 shows the matrix progress lines
# (grep), prefixed with the elapsed seconds, with the workdir path shortened to $W,
# then greps the saved full output ($O = matrix-c6ffc771.out, published next to this script).
set -u

S=/tmp/claude-1000/-home-exedev-projects-TileWright/9177c310-03a3-4680-88bb-34f6874f271a/scratchpad
P=/home/exedev/projects/tiled-lazy-hdf5/proofbranch/proof  # scripts of branch proof-lazy-hdf5
W=/home/exedev/projects/tiled-lazy-hdf5/media2-w           # tiled_e2e.py workdir (builds base, pr2, head)
M=/home/exedev/projects/tiled-lazy-hdf5/proofbranch/media
HEAD_SHA=c6ffc771a5950e20fe01fea5dccc46573df1f603
HOLD=7                                                     # seconds each step's output stays still
export UV_OFFLINE=1 PYTHONUNBUFFERED=1 GIT_PAGER=cat TMPDIR=$S/media-tmp
mkdir -p "$TMPDIR"
cd "$S" || exit 1
T='tests/test_hdf5.py tests/test_slicer.py'
# Step 3 puts the head's two test files into PR #2's tree; put them back whatever happens.
trap 'git -C "$S/wt-fix-pr2" checkout HEAD -- $T' EXIT

cls()    { printf '\033[H\033[2J\033[3J'; }
banner() { printf '\033[1;33m━━ %s\033[0m\n' "$*"; }
say()    { printf '\033[2m%s\033[0m\n' "$*"; }
run()    { printf '\033[1;32m$\033[0m \033[32m%s\033[0m\n' "$1"; eval "$1"; }
hold()   { sleep "${1:-$HOLD}"; }
stamp()  { while IFS= read -r l; do printf '[%3ds] %s\n' $((SECONDS - T0)) "${l//$W/\$W}"; done; }

cls
banner "carbonscott/tiled#4 at ${HEAD_SHA:0:8}: HDF5ArrayAdapter reads only the requested bytes"
say "recorded live on $(hostname) ($(nproc) CPUs), $(date -u '+%Y-%m-%d %H:%M UTC')"
say "S=$S"
say "P=$P"
say "W=$W"
run 'for t in wt-fix-pr2 wt-fix-new; do git -C $t log -1 --format="$t: %h %s"; done'
run 'for b in base pr2 head; do git -C $W/builds/$b log -1 --format="\$W/builds/$b: %h %s"; done'
run 'git -C $P log -1 --format="\$P: branch proof-lazy-hdf5 at %h %s"'
hold

cls
banner "Step 1/4: the issue's reproduction on PR #2 (514dc33a)"
run "wt-fix-pr2/.venv/bin/python -I \$P/issue_repro.py"
rm -rf "${TMPDIR:?}"/*
hold
echo
banner "Step 2/4: the same reproduction on the PR head (${HEAD_SHA:0:8})"
run "wt-fix-new/.venv/bin/python -I \$P/issue_repro.py"
rm -rf "${TMPDIR:?}"/*
hold

cls
banner "Step 3/4: the PR's new tests (test_hdf5.py, test_slicer.py of ${HEAD_SHA:0:8}) on PR #2, then on the PR head"
run "OPTS='-q -o log_cli=false -o asyncio_default_fixture_loop_scope=function --tb=no --disable-warnings'"
run "K='registered_slice_composes or reads_only_requested_elements or single_element or compose_reversed_slice_with_relative_stop or compose_expanded_slices'"
run "git -C wt-fix-pr2 checkout ${HEAD_SHA:0:8} -- \$T && git -C wt-fix-pr2 status --short"
run "(cd wt-fix-pr2 && .venv/bin/pytest \$OPTS -rp \$T -k \"\$K\")"
say "the 6 that pass on PR #2 are the squeezed-dtype guards: PR #2 already keeps the dtype when it squeezes"
echo
run "(cd wt-fix-new && .venv/bin/pytest \$OPTS \$T -k \"\$K\")"
run "git -C wt-fix-pr2 checkout HEAD -- \$T; echo \"files changed in wt-fix-pr2: \$(git -C wt-fix-pr2 status --short | wc -l)\""
hold

cls
banner "Step 4/4: 60-cell matrix through a live \`tiled serve\` per build: base, pr2, head"
say "3 layouts x 2 registrations (whole, row) x 5 requests x 2 dtypes = 60 cells per build"
run 'O=$M/matrix-c6ffc771.out'
T0=$SECONDS
run "uv run --script \$P/tiled_e2e.py matrix --workdir \$W --build base --build pr2 --build head \\
    --require-pass head 2>&1 | tee \$O \\
    | grep --line-buffered -E '^=== build|\\] ready at|^registered' | stamp; st=\${PIPESTATUS[0]}"
run 'echo "matrix exit status: $st"'
hold

cls
banner "Step 4/4 (cont.): results of that run, from its saved output"
run "grep -E '^build|^(base|pr2|head) +contiguous +(whole +(window|negstep)|row +window) +float64' \$O"
echo
run "grep -E '^PASS =|: PASS [0-9]+/' \$O"
hold 9
printf '\033[?25l'   # hide the cursor: also stamps the end of the final hold in the .cast
