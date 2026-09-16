# Shared PostgreSQL startup helper, used by setup.sh and start.sh.
# Sourced, not run directly.

# Name of the installed Homebrew PostgreSQL formula (falls back to a sensible one).
pg_formula() {
  brew list --formula 2>/dev/null | grep -m1 '^postgresql@' || echo "postgresql@18"
}

# Try to get PostgreSQL accepting connections. Returns 0 if it is up.
#
# We try the normal Homebrew route first, then fall back to starting the data
# directory directly: "brew services" is broken on some Homebrew installs, and
# some Macs run the official PostgreSQL installer instead, which Homebrew does
# not manage at all.
pg_ensure_running() {
  local formula datadir logfile

  # Already serving - whoever started it, we do not care.
  pg_isready -q 2>/dev/null && return 0

  formula="$(pg_formula)"
  brew services start "$formula" >/dev/null 2>&1 || true

  local i
  for i in $(seq 1 10); do
    pg_isready -q 2>/dev/null && return 0
    sleep 1
  done

  # Fallback: start the cluster ourselves.
  for datadir in "$(brew --prefix 2>/dev/null)/var/$formula" \
                 "$(brew --prefix 2>/dev/null)/var/postgresql"; do
    [ -d "$datadir" ] || continue
    logfile="$(brew --prefix 2>/dev/null)/var/log/$formula.log"
    pg_ctl -D "$datadir" -l "$logfile" start >/dev/null 2>&1 || true
    for i in $(seq 1 10); do
      pg_isready -q 2>/dev/null && return 0
      sleep 1
    done
  done

  return 1
}

# Printed when we cannot get it running, so the user has somewhere to go next.
pg_failure_help() {
  local formula; formula="$(pg_formula)"
  echo "Could not start PostgreSQL."
  echo
  echo "Try these, in order:"
  echo "  1.  brew services restart $formula"
  echo "  2.  pg_ctl -D $(brew --prefix 2>/dev/null)/var/$formula start"
  echo "  3.  If you installed PostgreSQL from postgresql.org rather than"
  echo "      Homebrew, start it from System Settings, or reboot your Mac."
  echo
  echo "If it says a lock file already exists, a previous server did not shut"
  echo "down cleanly. Rebooting your Mac clears that safely."
}
