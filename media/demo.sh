#!/usr/bin/env bash
# Live demo recorded for carbonscott/tiled#4 (asciinema, 110x32):
#   asciinema rec --cols 110 --rows 32 -c "bash media/demo.sh" demo.cast
# Every command below runs for real while the recorder runs; nothing is replayed.
# Each command is printed ("$ ...") exactly as written here, then run with eval.
# The only post-processing of output: step 4 shows the matrix progress lines
# (grep), prefixed with the elapsed seconds, with the workdir path shortened to $W,
# then greps the saved full output (matrix.out, published next to this script).
set -u

S=/tmp/claude-1000/-home-exedev-projects-TileWright/9177c310-03a3-4680-88bb-34f6874f271a/scratchpad
P=/home/exedev/projects/tiled-lazy-hdf5/media-wt/proof   # scripts from branch proof-lazy-hdf5
W=/home/exedev/projects/tiled-lazy-hdf5/harness-test     # tiled_e2e.py workdir (builds base, pr2, head)
M=/home/exedev/projects/tiled-lazy-hdf5/media-wt/media
HOLD=6                                                   # seconds each step stays on screen
export UV_OFFLINE=1 PYTHONUNBUFFERED=1 GIT_PAGER=cat TMPDIR=$S/media-tmp
mkdir -p "$TMPDIR"
cd "$S" || exit 1

cls()    { printf '\033[H\033[2J\033[3J'; }
banner() { printf '\033[1;33m━━ %s\033[0m\n' "$*"; }
say()    { printf '\033[2m%s\033[0m\n' "$*"; }
run()    { printf '\033[1;32m$\033[0m \033[32m%s\033[0m\n' "$1"; eval "$1"; }
hold()   { sleep "${1:-$HOLD}"; }
stamp()  { while IFS= read -r l; do printf '[%3ds] %s\n' $((SECONDS - T0)) "${l//$W/\$W}"; done; }

cls
banner "carbonscott/tiled#4: HDF5ArrayAdapter reads only the requested bytes"
say "recorded live on $(hostname) ($(nproc) CPUs), $(date -u '+%Y-%m-%d %H:%M UTC')"
say "S=$S"
say "P=$P"
say "W=$W"
run 'for t in wt-pr2 wt-head; do git -C $t log -1 --format="$t: %h %s"; done'
run 'for b in base pr2 head; do git -C $W/builds/$b log -1 --format="\$W/builds/$b: %h %s"; done'
hold

cls
banner "Step 1/4: the issue's reproduction on PR #2 (514dc33a)"
run "wt-pr2/.venv/bin/python -I \$P/issue_repro.py"
rm -rf "${TMPDIR:?}"/*
hold
echo
banner "Step 2/4: the same reproduction on the PR head (421569c4)"
run "wt-head/.venv/bin/python -I \$P/issue_repro.py"
rm -rf "${TMPDIR:?}"/*
hold

cls
banner "Step 3/4: the new unit tests (tests/test_hdf5.py of the PR head) on PR #2, then on the PR head"
run "OPTS='-q -o log_cli=false -o asyncio_default_fixture_loop_scope=function --tb=no -rN --disable-warnings'"
run "K='registered_slice_composes or reads_only_requested_elements'"
run "(cd wt-pr2 && .venv/bin/pytest \$OPTS tests/test_hdf5.py -k \"\$K\")"
echo
run "(cd wt-head && .venv/bin/pytest \$OPTS tests/test_hdf5.py -k \"\$K\")"
hold

cls
banner "Step 4/4: 60-cell matrix through a live \`tiled serve\` per build: base, pr2, head"
say "3 layouts x 2 registrations (whole, row) x 5 requests x 2 dtypes = 60 cells per build"
T0=$SECONDS
run "uv run --script \$P/tiled_e2e.py matrix --workdir \$W --build base --build pr2 --build head \\
    --require-pass head 2>&1 | tee \$M/matrix.out \\
    | grep --line-buffered -E '^=== build|\\] ready at|^registered' | stamp; st=\${PIPESTATUS[0]}"
run 'echo "matrix exit status: $st"'
hold

cls
banner "Step 4/4 (cont.): results of that run, from its saved output"
run "grep -E '^build|^(base|pr2|head) +contiguous +(whole +(window|negstep)|row +window) +float64' \$M/matrix.out"
echo
run "grep -E '^PASS =|: PASS [0-9]+/' \$M/matrix.out"
hold 9
printf '\033[?25l'   # hide the cursor: also stamps the end of the final hold in the .cast
