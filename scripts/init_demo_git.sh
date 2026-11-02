#!/usr/bin/env bash
# Build a throw-away git repo with two commits (base, then the Lexdiff fix) so you can try
#   python -m lexdiff verify --base .demo_repo@main --head .demo_repo@lexdiff/ftc-safeguards-fix
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .demo_repo && mkdir .demo_repo
git -C .demo_repo init -q -b main
G="git -C .demo_repo -c user.name=lexdiff -c user.email=lexdiff@example.test"
cp -r demo/lendwise_base/. .demo_repo/
find .demo_repo -name __pycache__ -type d -prune -exec rm -rf {} +
$G add -A && $G commit -q -m "base: Lendwise before the FTC Safeguards update"
$G checkout -q -b lexdiff/ftc-safeguards-fix
find .demo_repo -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -r demo/lendwise_fixed/. .demo_repo/
find .demo_repo -name __pycache__ -type d -prune -exec rm -rf {} +
$G add -A && $G commit -q -m "fix: MFA on every route, no customer data in logs/exports, FTC notice handler"
$G checkout -q main
echo "Created .demo_repo with branches: main (base) and lexdiff/ftc-safeguards-fix"
