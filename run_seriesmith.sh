#!/usr/bin/env sh
# seriesmith - the editor on this machine only (http://127.0.0.1:8190), as
# run_seriesmith.bat on Windows. --ext opens it to your network (no password:
# trusted networks only). The first start makes the repo's .venv and installs
# seriesmith in it.
cd "$(dirname "$0")" || exit 1
PORT=8190
HOST=127.0.0.1
[ "$1" = "--ext" ] && HOST=0.0.0.0

SM=.venv/bin/seriesmith
if [ ! -x "$SM" ]; then
  echo "First start: setting up seriesmith in $(pwd)/.venv (a minute or two, once)..."
  PY=""
  for p in python3 python; do
    if command -v "$p" >/dev/null 2>&1 && \
       "$p" -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>/dev/null; then
      PY=$p; break
    fi
  done
  [ -n "$PY" ] || { echo "! Python 3.10 or later wasn't found."; exit 1; }
  "$PY" -m venv .venv && .venv/bin/python -m pip install --disable-pip-version-check -q -e . \
    || { echo "seriesmith couldn't be set up (see above)."; exit 1; }
fi

OPEN=--auto-launch
while :; do
  "$SM" serve --host "$HOST" --port "$PORT" $OPEN
  code=$?
  # 3: the editor's Restart (or `seriesmith stop --restart`) - start it again
  [ "$code" -eq 3 ] || exit "$code"
  echo "seriesmith is restarting..."
  OPEN=
done
