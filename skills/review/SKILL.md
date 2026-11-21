---
name: review
description: Review and process the pull request created by Laravel Shift
arguments: <shift-number>
---

# Review Laravel Shift #$ARGUMENTS

Review and process the pull request created by Laravel Shift #$ARGUMENTS.

## Important: Respect Shift's Changes

**Never revert or undo any changes made by Shift in this PR.** Shift's changes are intentional and authoritative. If you believe a change made by Shift is incorrect or needs to be different, do NOT make any changes — instead, flag it to the user with your findings and let them decide how to proceed.

## Important: Commands That Contact the Git Remote

Every command in this skill that fetches, checks out the PR, pushes, or merges is written out in full below. Run it exactly as written, in one shell call. The project's `.claude/settings.json` is copied into each Bash call and can otherwise choose the program git runs instead of `ssh`, the askpass program git runs (`GIT_ASKPASS` or `core.askPass`; git does not consult `SSH_ASKPASS_REQUIRE`), or a `credential.helper` whose value starts with `!`.

Each command resolves `env`, `ssh`, and `git` on `/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin` and starts that absolute `env` with `-i`. The child receives only `PATH`, `GIT_SSH_COMMAND` set to that `ssh` plus `-F /dev/null -o BatchMode=yes`, `GIT_ALLOW_PROTOCOL`, and `SSH_ASKPASS_REQUIRE`. `GIT_EXEC_PATH` is left unset so git uses the libexec compiled into that binary. It does not receive `HOME`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, or linker variables. Direct `git` commands also pass `-c credential.helper= -c core.askPass= -c alias.fetch= -c alias.push= -c alias.checkout= -c core.fsmonitor=`. `gh pr checkout` and `gh pr merge` create the git shim with `TMPDIR=/tmp`, refuse the directory unless it is an absolute path outside the workspace with no colon or newline, and put only that directory first on `PATH`. Never drop any of that, split it across calls, or run another remote `git` or `gh` command without it.

## Step 1: Detect Platform

Run:
```bash
git remote get-url origin
```

Parse the URL to detect the platform and extract `owner/repo` (handle both SSH and HTTPS formats, strip `.git`):
- `github.com` → **GitHub**
- `gitlab.com` or any other non-Bitbucket host → **GitLab**
- `bitbucket.org` → **Bitbucket**

**GitHub only**: Check that `gh` is installed (`gh --version`). If not, tell the user to install it from https://cli.github.com and stop.

**GitHub only**: Every `gh` command in this skill must target the `origin` repository. Pass `--repo` from `git remote get-url origin`, using `git` resolved on the fixed PATH when the command already resolves it. Commands that are not inside `env -i` are prefixed with `env -u GH_REPO -u GH_HOST`; `env -i` does not pass those variables. Never drop `--repo` or substitute another repository. Project settings and the shell environment can set `GH_REPO` or `GH_HOST`, which would otherwise point `gh` at a different repository or host.

## Step 2: Find the PR and Fetch Details

**GitHub:**
```bash
env -u GH_REPO -u GH_HOST gh pr list --head "shift-$ARGUMENTS" --json number,title,body,url,headRefName,baseRefName --repo "$(git remote get-url origin)"
```

If no PR is found, try the fallback branch name:
```bash
env -u GH_REPO -u GH_HOST gh pr list --head "shift-build-$ARGUMENTS" --json number,title,body,url,headRefName,baseRefName --repo "$(git remote get-url origin)"
```

If still no PR is found, tell the user and stop. If multiple PRs are found, show the list and ask which one to use. Store the PR number, its head branch (`headRefName`) and its base branch (`baseRefName`) for subsequent steps.

Then fetch the description, comments, and diff:
```bash
env -u GH_REPO -u GH_HOST gh pr view {PR_NUMBER} --comments --repo "$(git remote get-url origin)"
env -u GH_REPO -u GH_HOST gh pr diff {PR_NUMBER} --repo "$(git remote get-url origin)"
```

**GitLab and Bitbucket:**

The Shift branch is `shift-$ARGUMENTS`. Fetch it and generate the diff:
```bash
shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin
shift_env=$(PATH="$shift_path" command -v env) || { echo 'env not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_ssh=$(PATH="$shift_path" command -v ssh) || { echo 'ssh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_git=$(PATH="$shift_path" command -v git) || { echo 'git not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
"$shift_env" -i \
  PATH="$shift_path" \
  GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
  GIT_ALLOW_PROTOCOL=ssh:https:http \
  SSH_ASKPASS_REQUIRE=never \
  "$shift_git" \
  -c credential.helper= -c core.askPass= \
  -c alias.fetch= -c alias.push= -c alias.checkout= \
  -c core.fsmonitor= fetch origin shift-$ARGUMENTS
git diff $(git merge-base HEAD origin/shift-$ARGUMENTS)...origin/shift-$ARGUMENTS
```

If that fetch fails, fall back to `shift-build-$ARGUMENTS`:
```bash
shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin
shift_env=$(PATH="$shift_path" command -v env) || { echo 'env not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_ssh=$(PATH="$shift_path" command -v ssh) || { echo 'ssh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_git=$(PATH="$shift_path" command -v git) || { echo 'git not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
"$shift_env" -i \
  PATH="$shift_path" \
  GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
  GIT_ALLOW_PROTOCOL=ssh:https:http \
  SSH_ASKPASS_REQUIRE=never \
  "$shift_git" \
  -c credential.helper= -c core.askPass= \
  -c alias.fetch= -c alias.push= -c alias.checkout= \
  -c core.fsmonitor= fetch origin shift-build-$ARGUMENTS
git diff $(git merge-base HEAD origin/shift-build-$ARGUMENTS)...origin/shift-build-$ARGUMENTS
```


## Step 3: Check for Uncommitted Changes

Before checking out the PR branch, verify the working directory is clean:
```bash
git status --porcelain
```

If there are any uncommitted changes, **STOP immediately** and tell the user:
> "You have uncommitted changes in your working directory. Please commit or discard them before running this skill."

Do NOT stash, reset, or otherwise modify their working directory. Only proceed if `git status --porcelain` returns empty output.

## Step 4: Checkout the PR Branch

**GitHub:**
```bash
shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin
shift_env=$(PATH="$shift_path" command -v env) || { echo 'env not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_ssh=$(PATH="$shift_path" command -v ssh) || { echo 'ssh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_git=$(PATH="$shift_path" command -v git) || { echo 'git not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_gh=$(PATH="$shift_path" command -v gh) || { echo 'gh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_mktemp=$(PATH="$shift_path" command -v mktemp) || { echo 'mktemp not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_chmod=$(PATH="$shift_path" command -v chmod) || { echo 'chmod not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_rm=$(PATH="$shift_path" command -v rm) || { echo 'rm not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_bin=$(TMPDIR=/tmp "$shift_mktemp" -d) || { echo 'mktemp failed; not contacting the remote.' >&2; exit 127; }
case "$shift_bin" in
  /*) ;;
  *) echo 'temp directory is not absolute; not contacting the remote.' >&2; exit 127 ;;
esac
case "$shift_bin" in
  *:*) echo 'temp directory is not a single PATH entry; not contacting the remote.' >&2; exit 127 ;;
esac
case "$shift_bin" in
  *$'\n'*) echo 'temp directory contains a newline; not contacting the remote.' >&2; exit 127 ;;
esac
shift_pwd=$(pwd -P)
if [[ "$shift_bin" = "$shift_pwd" || "$shift_bin" = "$shift_pwd"/* ]]; then
  echo 'temp directory is inside the workspace; not contacting the remote.' >&2
  exit 127
fi
trap '"$shift_rm" -rf "$shift_bin"' EXIT
shift_cat=$(PATH="$shift_path" command -v cat) || { echo 'cat not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
"$shift_cat" > "$shift_bin/git" << EOF
#!/bin/sh
git=$(printf '%q' "$shift_git")
prev=
subcmd=
for arg in "\$@"; do
  if [ "\$prev" = "-c" ] || [ "\$prev" = "-C" ]; then
    prev=
    continue
  fi
  case "\$arg" in
    -c|-C) prev=\$arg ;;
    -*) ;;
    *) subcmd=\$arg; break ;;
  esac
done
if [ -n "\$subcmd" ]; then
  exec "\$git" -c "alias.\${subcmd}=" -c credential.helper= -c core.askPass= -c core.fsmonitor= "\$@"
fi
exec "\$git" -c credential.helper= -c core.askPass= -c core.fsmonitor= "\$@"
EOF
"$shift_chmod" +x "$shift_bin/git"
"$shift_env" -i \
  PATH="$shift_bin:$shift_path" \
  GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
  GIT_ALLOW_PROTOCOL=ssh:https:http \
  SSH_ASKPASS_REQUIRE=never \
  "$shift_gh" pr checkout {PR_NUMBER} --repo "$("$shift_git" remote get-url origin)"
```

**GitLab and Bitbucket** — use native git, checking out whichever branch name succeeded in Step 2:
```bash
git checkout {SHIFT_BRANCH}
```

(`git fetch` was already run in Step 2.)

## Step 5: Understand the Changes

Analyze what Laravel Shift has done:
- What Laravel version upgrade is this (if applicable)?
- What packages were updated?
- What code changes were made?
- Are there any breaking changes noted?

## Step 6: Composer Update

First, check whether `composer.json` was changed as part of this PR:

**GitHub:**
```bash
env -u GH_REPO -u GH_HOST gh pr diff {PR_NUMBER} --name-only --repo "$(git remote get-url origin)" | grep -q "^composer\.json$"
```

**GitLab and Bitbucket:**
```bash
git diff $(git merge-base HEAD origin/{SHIFT_BRANCH})...origin/{SHIFT_BRANCH} --name-only | grep -q "^composer\.json$"
```

If `composer.json` was **not** changed, skip the rest of this step entirely and proceed to Step 7.

**Every Composer command in this skill must be run from the repository root, exactly as written: prefixed with `COMPOSER=composer.json` and with `--no-plugins --no-scripts`.** Do this on the same command line every time, including re-runs. The `COMPOSER` environment variable may be inherited from the project's settings and would make Composer read a different manifest than the `composer.json` you reviewed; the flags stop the manifest's scripts and plugins from executing. Never drop the prefix or the flags, and never set or unset `COMPOSER` in a separate command.

If `composer.json` **was** changed, scan it for any `dev-*` version constraints (e.g. `"dev-main"`, `"dev-master"`, `"dev-fix-something"`). For each one found:
1. Look up the package on Packagist to check if a stable release exists: `COMPOSER=composer.json composer show {package} --all --no-plugins --no-scripts`
2. If a compatible stable version is available, update the constraint in `composer.json` to the appropriate semver range (e.g. `^1.2`) and track it as a swapped dependency for the summary in Step 10
3. If no stable release exists, leave the `dev-*` constraint as-is

Then run `COMPOSER=composer.json composer update --no-plugins --no-scripts`.

Because scripts are skipped, if the project has an `artisan` file, run `php artisan package:discover --ansi` after a successful update to refresh Laravel's package manifest.

After running (whether it succeeds or fails):

**GitLab and Bitbucket only** — ask the user to paste the PR comments:
> "Please paste any comments from the pull request here, or let me know if there are none."

Then scan the pasted comments for any linked Shift suggestions — these are typically laravelshift.com URLs mentioned in comments recommending a follow-up Shift to run.

When collecting these suggestions:
- Preserve comment order — surface them in the order they appear
- **Exclude the last comment** if it contains Shift links or "you're now running the latest version of Laravel" — set it aside and surface it in Step 10 instead
- If any remaining (non-last) comments contain Shift suggestions, surface them to the user now:

> "The PR suggests running additional Shifts: [list links in comment order]. Would you like to run any of these before continuing?"

If `composer update` failed, attempt to systematically resolve the incompatibilities before stopping:
1. Read the error output carefully to identify which packages have conflicting version constraints
2. For each conflicting package, check the latest compatible version: `COMPOSER=composer.json composer show {package} --all --no-plugins --no-scripts` or look up the package on packagist.org
3. Update the version constraint in `composer.json` to one that satisfies all dependencies, then re-run `COMPOSER=composer.json composer update --no-plugins --no-scripts`
4. Repeat for any remaining conflicts
5. If a conflict involves a package that has a suggested follow-up Shift (from comments above), surface that to the user as the recommended resolution instead of manually editing constraints
6. If you cannot resolve the incompatibilities after a systematic attempt, stop and explain exactly which packages are conflicting and why, so the user can decide how to proceed

## Step 7: Act on Instructions

Follow any instructions given in the PR description or comments. This typically includes:
- Running migrations
- Updating configuration files
- Making code changes that Shift couldn't automate
- Addressing deprecations

Pay special attention to the "Automate more with AI..." section of each step, since it's specifically directed towards LLM comprehension.

## Step 8: Handle Optional Upgrades

For any changes marked as "optional" in the PR:
- **Small changes** (one-liner, simple config tweaks, straightforward updates): Just do them automatically
- **Medium to large changes** (new features, architectural changes, changes requiring decisions): Ask the user before proceeding

## Step 9: Test the Application

After making changes:
1. Run `php artisan test --compact` to verify tests pass
2. Fix code style on changed files: check `composer.json` for `laravel/pint` or `friendsofphp/php-cs-fixer` (in that priority order) and run the first one found. Use the `--dirty` flag for Pint. If none are found, skip this step.
3. If tests fail, investigate and fix the issues

## Important: Do Not Commit or Push

Do NOT commit any changes or push to the remote. Leave all changes as uncommitted modifications in the working directory so the user can review them before committing.

## Step 10: Report Back

Summarize:
- What changes were made by Shift
- What additional changes you made
- Any `dev-*` dependencies that were swapped for a stable release (package name, old constraint → new constraint)
- Any optional upgrades you skipped (and why they need user input)
- Test results
- Any remaining action items

End with: "Would you like to merge this PR?"

If the user confirms they want to merge:
1. Check for any uncommitted local changes: `git status --porcelain`
2. If there are uncommitted changes:
   - Check if the only changed files match `composer.*` (i.e. `composer.json` and/or `composer.lock`). If so, stage and commit them automatically with the message `composer update` — do not prompt the user.
   - Otherwise, offer to commit them:
     > "You have uncommitted local changes. Would you like me to commit them for you with a summary?"
     If the user agrees, stage all changes and commit using "Finalize upgrade" as the subject and the summary from Step 10 as the commit body.
     If the user declines, wait for them to confirm they've committed their changes before proceeding.
3. Once the working directory is clean, check if the branch has unpushed commits: `git log origin/{BRANCH}..HEAD`
4. If there are unpushed commits, confirm `git branch --show-current` still prints the Shift branch checked out in Step 4 (stop if it does not), then push only that branch:
   ```bash
   shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin
   shift_env=$(PATH="$shift_path" command -v env) || { echo 'env not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
   shift_ssh=$(PATH="$shift_path" command -v ssh) || { echo 'ssh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
   shift_git=$(PATH="$shift_path" command -v git) || { echo 'git not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
   ref=$("$shift_git" symbolic-ref --quiet HEAD) || { echo 'HEAD is not a branch; not pushing.' >&2; exit 1; }
   "$shift_env" -i \
     PATH="$shift_path" \
     GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
     GIT_ALLOW_PROTOCOL=ssh:https:http \
     SSH_ASKPASS_REQUIRE=never \
     "$shift_git" \
     -c credential.helper= -c core.askPass= \
     -c alias.fetch= -c alias.push= -c alias.checkout= \
     -c core.fsmonitor= \
     -c remote.origin.mirror=false -c push.followTags=false \
     push --no-follow-tags --recurse-submodules=no origin "HEAD:$ref"
   ```
   Run it exactly as written. Never fall back to a push without an explicit remote and refspec: project settings can set `remote.origin.mirror` or `remote.origin.push` through `GIT_CONFIG_*` environment variables, which turns that into a forced update or deletion of other branches and tags.
5. Merge using the appropriate method for the platform:

**GitHub** — `--match-head-commit` makes the merge fail if the pull request's head is not the commit you reviewed, tested, and pushed:
```bash
shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin
shift_env=$(PATH="$shift_path" command -v env) || { echo 'env not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_ssh=$(PATH="$shift_path" command -v ssh) || { echo 'ssh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_git=$(PATH="$shift_path" command -v git) || { echo 'git not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_gh=$(PATH="$shift_path" command -v gh) || { echo 'gh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_mktemp=$(PATH="$shift_path" command -v mktemp) || { echo 'mktemp not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_chmod=$(PATH="$shift_path" command -v chmod) || { echo 'chmod not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_rm=$(PATH="$shift_path" command -v rm) || { echo 'rm not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_bin=$(TMPDIR=/tmp "$shift_mktemp" -d) || { echo 'mktemp failed; not contacting the remote.' >&2; exit 127; }
case "$shift_bin" in
  /*) ;;
  *) echo 'temp directory is not absolute; not contacting the remote.' >&2; exit 127 ;;
esac
case "$shift_bin" in
  *:*) echo 'temp directory is not a single PATH entry; not contacting the remote.' >&2; exit 127 ;;
esac
case "$shift_bin" in
  *$'\n'*) echo 'temp directory contains a newline; not contacting the remote.' >&2; exit 127 ;;
esac
shift_pwd=$(pwd -P)
if [[ "$shift_bin" = "$shift_pwd" || "$shift_bin" = "$shift_pwd"/* ]]; then
  echo 'temp directory is inside the workspace; not contacting the remote.' >&2
  exit 127
fi
trap '"$shift_rm" -rf "$shift_bin"' EXIT
shift_cat=$(PATH="$shift_path" command -v cat) || { echo 'cat not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
"$shift_cat" > "$shift_bin/git" << EOF
#!/bin/sh
git=$(printf '%q' "$shift_git")
prev=
subcmd=
for arg in "\$@"; do
  if [ "\$prev" = "-c" ] || [ "\$prev" = "-C" ]; then
    prev=
    continue
  fi
  case "\$arg" in
    -c|-C) prev=\$arg ;;
    -*) ;;
    *) subcmd=\$arg; break ;;
  esac
done
if [ -n "\$subcmd" ]; then
  exec "\$git" -c "alias.\${subcmd}=" -c credential.helper= -c core.askPass= -c core.fsmonitor= "\$@"
fi
exec "\$git" -c credential.helper= -c core.askPass= -c core.fsmonitor= "\$@"
EOF
"$shift_chmod" +x "$shift_bin/git"
head=$("$shift_git" rev-parse HEAD)
"$shift_env" -i \
  PATH="$shift_bin:$shift_path" \
  GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
  GIT_ALLOW_PROTOCOL=ssh:https:http \
  SSH_ASKPASS_REQUIRE=never \
  "$shift_gh" pr merge {PR_NUMBER} --merge --delete-branch --match-head-commit "$head" --repo "$("$shift_git" remote get-url origin)"
```

If the merge fails, report the error to the user and stop. Once it succeeds, `gh` has deleted the remote branch but, because `--repo` is set, leaves the local branch in place. Switch back to the base branch from Step 2 and delete the local Shift branch. `git pull` contacts the remote, so it uses the same pinned ssh:
```bash
shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin
shift_env=$(PATH="$shift_path" command -v env) || { echo 'env not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_ssh=$(PATH="$shift_path" command -v ssh) || { echo 'ssh not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
shift_git=$(PATH="$shift_path" command -v git) || { echo 'git not found on the fixed PATH; not contacting the remote.' >&2; exit 127; }
"$shift_env" -i \
  PATH="$shift_path" \
  GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
  GIT_ALLOW_PROTOCOL=ssh:https:http \
  SSH_ASKPASS_REQUIRE=never \
  "$shift_git" \
  -c credential.helper= -c core.askPass= \
  -c alias.fetch= -c alias.push= -c alias.checkout= \
  -c core.fsmonitor= checkout {BASE_BRANCH}
"$shift_env" -i \
  PATH="$shift_path" \
  GIT_SSH_COMMAND="$(printf '%q' "$shift_ssh") -F /dev/null -o BatchMode=yes" \
  GIT_ALLOW_PROTOCOL=ssh:https:http \
  SSH_ASKPASS_REQUIRE=never \
  "$shift_git" \
  -c credential.helper= -c core.askPass= \
  -c alias.fetch= -c alias.push= -c alias.checkout= \
  -c core.fsmonitor= pull --ff-only
"$shift_git" branch -d {BRANCH}
```

**GitLab and Bitbucket** — the branch has already been pushed. Tell the user:
> "Please merge the pull request on {platform} and delete the source branch."

If the last PR comment contained Shift links (set aside in Step 6):
- If the comment contains "you're now running the latest version of Laravel":
  - If there were Shift suggestions from non-last comments (surfaced in Step 6), append:
    > "Congratulations, you're now running the latest version of Laravel!"
    >
    > "Once merged, the next suggested Shifts to run are: [link(s) from non-last comments, in comment order]."
  - Otherwise, append:
    > "Congratulations, you're now running the latest version of Laravel!"
    >
    > "Once merged, consider running the [Laravel Fixer](https://laravelshift.com/laravel-fixer) to clean up any remaining issues."
- Otherwise, append:
  > "Once merged, the next suggested Shift to run is: [link(s)]"
