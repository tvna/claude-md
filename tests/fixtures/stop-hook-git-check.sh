#!/bin/bash

# Read the JSON input from stdin
input=$(cat)

# Check if stop hook is already active (recursion prevention)
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active')
if [[ "$stop_hook_active" = "true" ]]; then
  exit 0
fi

# Check if we're in a git repository - bail if not
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

# Bail if there's no remote to push to. Every error path below asks the user
# to "push to the remote branch" - meaningless without a remote, and
# unsatisfiable if signing also requires a source. This case arises when CCR
# was launched against a local repo with no github remote (sources=[]) and
# the container's cwd has a leftover .git from a cached resume.
if [[ -z "$(git remote)" ]]; then
  exit 0
fi

# Check for uncommitted changes (both staged and unstaged)
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "There are uncommitted changes in the repository. Please commit and push these changes to the remote branch." >&2
  exit 2
fi

# Check for untracked files that might be important
untracked_files=$(git ls-files --others --exclude-standard)
if [[ -n "$untracked_files" ]]; then
  echo "There are untracked files in the repository. Please commit and push these changes to the remote branch." >&2
  exit 2
fi

current_branch=$(git branch --show-current)
if [[ -n "$current_branch" ]]; then
  # Resolve the repository's default branch ref (e.g. origin/main). The commit
  # inspections below are scoped to commits UNIQUE to this branch
  # (default_ref..HEAD). Commits already reachable from the default branch are
  # upstream history - typically squash-merge commits authored by the repo
  # owner or a GitHub merge bot, whose committer is noreply@github.com - and
  # MUST NOT be flagged or rewritten by this hook: proposing
  # 'git commit --amend --reset-author' on them would silently rewrite the
  # author of someone else's merged commit (a destructive, out-of-scope change).
  # Prefer origin/main; fall back to the symbolic default ref (origin/HEAD); if
  # neither resolves (detached, no default branch), skip the inspections.
  default_ref=""
  if git rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
    default_ref="origin/main"
  elif resolved=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null); then
    default_ref="${resolved#refs/remotes/}"
  fi

  if [[ -n "$default_ref" ]] && git rev-parse --verify --quiet "$default_ref" >/dev/null 2>&1; then
    # Check for local commits that GitHub will show as "Unverified": either no
    # signature at all (%G? == N), or signed with a committer email other than
    # noreply@anthropic.com (the identity CCR's signing key is registered to).
    # Only run when commit signing is configured. Note: %G? is N for unsigned
    # commits; signed-but-locally-unverifiable commits report B/U/E, so this is
    # a reliable presence check even though CCR doesn't configure local
    # verification. The range is limited to default_ref..HEAD so only commits
    # unique to this branch are inspected (see the comment above).
    if [[ "$(git config --type=bool commit.gpgsign 2>/dev/null)" == "true" ]]; then
      unverifiable=$(git log --format='%h %G? %ce' "$default_ref..HEAD" 2>/dev/null | awk '$2 == "N" || ($3 != "" && $3 != "noreply@anthropic.com")')
      if [[ -n "$unverifiable" ]]; then
        echo "There are commit(s) on branch '$current_branch' that GitHub will show as Unverified (missing signature, or committer email is not noreply@anthropic.com):" >&2
        echo "$unverifiable" >&2
        echo "Please run 'git config user.email noreply@anthropic.com && git config user.name Claude', then 'git commit --amend --no-edit --reset-author' for the tip commit, or 'git rebase --exec \"git commit --amend --no-edit --reset-author\" $default_ref' for earlier commits, then push." >&2
        exit 2
      fi
    fi

    # Check for unpushed commits. Determine the ref the branch's commits should
    # already be on, in priority order so genuinely unpushed work is reported
    # without false positives:
    #   1. the branch's configured upstream, so a branch that tracks a
    #      differently-named remote ref (e.g. localwork tracking
    #      origin/remote-name) is compared against its real upstream rather than
    #      a non-existent same-named ref;
    #   2. a same-named origin/$current_branch, for a branch pushed without an
    #      upstream configured;
    #   3. the default branch, for a never-pushed branch, so a branch that
    #      merely sits on the default branch (no commits of its own) stays silent
    #      instead of being told to push upstream history that is not its own.
    if upstream_ref=$(git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" 2>/dev/null); then
      unpushed=$(git rev-list "$upstream_ref..HEAD" --count 2>/dev/null) || unpushed=0
      remote_branch_exists=1
    elif git rev-parse --verify --quiet "origin/$current_branch" >/dev/null 2>&1; then
      unpushed=$(git rev-list "origin/$current_branch..HEAD" --count 2>/dev/null) || unpushed=0
      remote_branch_exists=1
    else
      unpushed=$(git rev-list "$default_ref..HEAD" --count 2>/dev/null) || unpushed=0
      remote_branch_exists=0
    fi
    if [[ "$unpushed" -gt 0 ]]; then
      if [[ "$remote_branch_exists" -eq 1 ]]; then
        echo "There are $unpushed unpushed commit(s) on branch '$current_branch'. Please push these changes to the remote repository." >&2
      else
        echo "Branch '$current_branch' has $unpushed unpushed commit(s) and no remote branch. Please push these changes to the remote repository." >&2
      fi
      exit 2
    fi
  fi
fi

exit 0
