# abide — read the Bible today, and still know it in a year.
# Sourced from ~/.zshrc. Delete that source line to remove it.
#
#   bible            start it (or open it, if it is already up)
#   bible today      today's reading, in the terminal
#   bible read rom 8 any passage
#   bible review     the verses that are due
#   bible log        what you read, and when
#   bible stats      the week, the streak, the coverage
#   bible restart    stop and start again
#   bible stop       stop the server
#   bible tail       watch the server's output

ABIDE_HOME="${ABIDE_HOME:-$HOME/code/abide}"
ABIDE_PORT="${ABIDE_PORT:-7847}"
ABIDE_LOG="${ABIDE_LOG:-$ABIDE_HOME/data/serve.log}"

_abide_pid() { lsof -nP -tiTCP:"${ABIDE_PORT}" -sTCP:LISTEN 2>/dev/null | head -1; }

# abide.py is the running process; app.html is read from disk every request. If the
# script has been edited since the server started, the page and the server disagree -
# so start fresh rather than serving a confidently wrong answer.
_abide_stale() {
  curl -s -m 2 "http://127.0.0.1:${ABIDE_PORT}/api/boot" 2>/dev/null \
    | python3 -c 'import json,sys
try: sys.exit(0 if json.load(sys.stdin).get("stale") else 1)
except Exception: sys.exit(1)' 2>/dev/null
}

_abide_up() {
  local url="http://127.0.0.1:${ABIDE_PORT}"
  mkdir -p "$(dirname "${ABIDE_LOG}")"
  ( cd "${ABIDE_HOME}" && nohup python3 -u abide.py serve --port "${ABIDE_PORT}" \
      --no-open >>"${ABIDE_LOG}" 2>&1 & )
  local i=0
  while (( i < 40 )); do
    [[ -n "$(_abide_pid)" ]] && break
    sleep 0.1; (( i++ ))
  done
  if [[ -z "$(_abide_pid)" ]]; then
    echo "abide: did not come up — see ${ABIDE_LOG}" >&2
    tail -5 "${ABIDE_LOG}" >&2
    return 1
  fi
  echo "abide is up at ${url}"
  command open "${url}" 2>/dev/null
}

bible() {
  [[ -d "${ABIDE_HOME}" ]] || { echo "abide: no such directory: ${ABIDE_HOME}" >&2; return 1; }
  local pid; pid="$(_abide_pid)"

  case "$1" in
    stop)
      [[ -z "$pid" ]] && { echo "abide is not running"; return 0; }
      kill "$pid" 2>/dev/null && echo "abide stopped"
      return 0 ;;
    restart)
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null && sleep 0.4
      _abide_up; return $? ;;
    tail)
      tail -f "${ABIDE_LOG}"; return 0 ;;
    "" | serve | up | open)
      if [[ -n "$pid" ]]; then
        if _abide_stale; then
          echo "abide.py has changed since the server started — restarting"
          kill "$pid" 2>/dev/null; sleep 0.4
          _abide_up
        else
          echo "abide is already up — opening http://127.0.0.1:${ABIDE_PORT}"
          command open "http://127.0.0.1:${ABIDE_PORT}" 2>/dev/null
        fi
      else
        _abide_up
      fi
      return $? ;;
  esac

  # anything else is a subcommand, and runs against the same database whether or not
  # a server happens to be up
  ( cd "${ABIDE_HOME}" && python3 abide.py "$@" )
}

alias abide=bible     # the app's own name
alias ab=bible        # in a hurry
