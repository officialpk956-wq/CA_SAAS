#!/bin/bash
# Intentionally does nothing (changed 2026-10-05).
#
# This script used to make PostgreSQL listen on every network interface and accept password logins from
# 0.0.0.0/0 with the default demo password. That exposed the database to the whole network and is not needed:
# WSL2 forwards localhost, so the app reaches PostgreSQL at localhost:5432 with the default configuration.
#
# Start the local database with:
#   wsl -d Codex-PTCG-Validation -u root -- service postgresql start
echo "setup_pg2.sh is disabled: the database does not need to be opened to the network. See comments in this file."
exit 1
