#!/usr/bin/env bash
# Run from any directory with: bash scripts/purge_sqlite_history.sh
# Rewrites local history only; prints guarded push commands for changed branches.
set -euo pipefail

cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'Commit or stash changes before running this script.' >&2
  exit 1
fi
if [[ -n "$(git for-each-ref --format='%(refname)' refs/original/)" ]]; then
  echo 'Existing refs/original backups found; resolve those before rewriting history.' >&2
  exit 1
fi

git_dir=$(git rev-parse --absolute-git-dir)
for state in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD; do
  if [[ -e "$git_dir/$state" ]]; then
    echo "Finish or abort the active Git operation ($state) first." >&2
    exit 1
  fi
done

backup_dir=$(mktemp -d "$git_dir/sqlite-history-backup-XXXXXXXX")
git for-each-ref --format='%(refname) %(objectname)' > "$backup_dir/refs-before.txt"
cp "$git_dir/config" "$backup_dir/config-before"
git bundle create "$backup_dir/before-cleanup.bundle" --all
git bundle verify "$backup_dir/before-cleanup.bundle"
echo "Recovery backup: $backup_dir"

# --cached changes historical indexes without deleting local database files.
# Preserve merge structure and empty commits; only remove database paths.
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch \
  --index-filter "git rm -r --cached --ignore-unmatch -- '*.sqlite' '*.sqlite-*' '*.sqlite3' '*.sqlite3-*' '*.db' '*.db-*' '*.db3' '*.db3-*'" \
  --commit-filter '
    new_tree=$1
    shift
    old_tree=$(git rev-parse "$GIT_COMMIT^{tree}")
    old_parents=$(git show --no-show-signature -s --format=%P "$GIT_COMMIT")
    new_parents=
    for arg do
      if [ "$arg" != -p ]; then
        new_parents="${new_parents:+$new_parents }$arg"
      fi
    done
    if [ "$new_tree" = "$old_tree" ] && [ "$new_parents" = "$old_parents" ]; then
      cat > /dev/null
      echo "$GIT_COMMIT"
    else
      git commit-tree "$new_tree" "$@"
    fi
  ' \
  --tag-name-filter cat -- --all

# The bundle is the recovery copy. Old refs must not keep the databases reachable.
while IFS= read -r ref; do
  git update-ref -d "$ref"
done < <(git for-each-ref --format='%(refname)' refs/original/)

remaining=$(git log --all --format= --name-only -- \
  '*.sqlite' '*.sqlite-*' '*.sqlite3' '*.sqlite3-*' \
  '*.db' '*.db-*' '*.db3' '*.db3-*')
if [[ -n "$remaining" ]]; then
  echo 'Verification failed: database paths remain in history.' >&2
  exit 1
fi

echo 'Verified: no matching database paths remain in local ref history.'
echo 'GitHub is unchanged. Push changed published branches using these guarded commands:'
while read -r ref expected; do
  case "$ref" in
    refs/remotes/origin/HEAD) continue ;;
    refs/remotes/origin/*)
      branch=${ref#refs/remotes/origin/}
      local_ref="refs/heads/$branch"
      if git show-ref --verify --quiet "$local_ref"; then
        current=$(git rev-parse "$local_ref")
        if [[ "$current" != "$expected" ]]; then
          printf 'git push --force-with-lease=%q:%q origin %q:%q\n' \
            "refs/heads/$branch" "$expected" "$local_ref" "refs/heads/$branch"
        fi
      fi
      ;;
  esac
done < "$backup_dir/refs-before.txt"
