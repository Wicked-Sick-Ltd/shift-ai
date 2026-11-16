---
name: review
description: Review and process the pull request created by Laravel Shift
arguments: <shift-number>
---

# Review Laravel Shift #$ARGUMENTS

Review and process the pull request created by Laravel Shift #$ARGUMENTS.

## Important: Respect Shift's Changes

**Never revert or undo any changes made by Shift in this PR.** Shift's changes are intentional and authoritative. If you believe a change made by Shift is incorrect or needs to be different, do NOT make any changes — instead, flag it to the user with your findings and let them decide how to proceed.

## Command Environment

Project Claude settings are copied into every Bash call. That includes `PATH`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*`, `GIT_CONFIG_PARAMETERS`, `GIT_EXEC_PATH`, `BASH_ENV`, `ENV`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, and `DYLD_*`. Assigning a fixed `PATH` and `unset -f` does not stop git from applying those config variables (for example `alias.status` or `core.fsmonitor`), and it does not stop the dynamic linker. `BASH_ENV` is sourced before the first line of the command, so a trap set there survives `unset -f`.

Run **every** tool for this skill, including commands you write yourself (commits, migrations, code style fixers), as one `/usr/bin/env -i` command. The absolute `/usr/bin/env` looks up `bash` on the fixed `PATH` below; do not resolve `env` or `bash` in the outer shell. That bash is `bash --noprofile --norc` with only `PATH` and `SSH_AUTH_SOCK`. Do not pass the outer shell's `HOME`. Inside the bash, set `HOME` from the passwd entry for the current uid and set `COMPOSER_HOME` to `$HOME/.composer` before running a tool. Then resolve each tool with `command -v` on that `PATH` and execute the absolute path. Do not pass git-config variables, `BASH_ENV`, `ENV`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, or `DYLD_*`.

Claude Code starts the Bash tool before this snippet runs, so a project `BASH_ENV` file and linker variables are already applied to that outer shell. This skill cannot clear them there. `/usr/bin/env -i` is what starts the tool without those variables.

```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    "$git" status --porcelain
'
```

Each Bash call starts from the project environment again, so every call repeats `/usr/bin/env -i`. Never add directories from the current `PATH`, the project, or its settings. If `command -v` fails inside that bash, ask the user for that tool's absolute path and use it in place of the `command -v` result.

## Step 1: Detect Platform

Run:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    "$git" remote get-url origin
'
```

Parse the URL to detect the platform and extract `owner/repo` (handle both SSH and HTTPS formats, strip `.git`):
- `github.com` → **GitHub**
- `gitlab.com` or any other non-Bitbucket host → **GitLab**
- `bitbucket.org` → **Bitbucket**

**GitHub only**: Check that `gh` is installed:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    "$gh" --version
'
```
If not, tell the user to install it from https://cli.github.com and stop.

## Step 2: Find the PR and Fetch Details

**GitHub:**
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    "$gh" pr list --head "shift-$1" --json number,title,body,url
' _ "$ARGUMENTS"
```

If no PR is found, try the fallback branch name:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    "$gh" pr list --head "shift-build-$1" --json number,title,body,url
' _ "$ARGUMENTS"
```

If still no PR is found, tell the user and stop. If multiple PRs are found, show the list and ask which one to use. Store the PR number for subsequent steps.

Then fetch the description, comments, and diff:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    "$gh" pr view {PR_NUMBER} --comments
    "$gh" pr diff {PR_NUMBER}
'
```

**GitLab and Bitbucket:**

The Shift branch is `shift-$ARGUMENTS`. Fetch it and generate the diff:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    "$git" fetch origin "shift-$1"
    "$git" diff "$("$git" merge-base HEAD "origin/shift-$1")...origin/shift-$1"
' _ "$ARGUMENTS"
```

If that fetch fails, fall back to `shift-build-$ARGUMENTS`:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    "$git" fetch origin "shift-build-$1"
    "$git" diff "$("$git" merge-base HEAD "origin/shift-build-$1")...origin/shift-build-$1"
' _ "$ARGUMENTS"
```


## Step 3: Check for Uncommitted Changes

Before checking out the PR branch, verify the working directory is clean:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    "$git" status --porcelain
'
```

If there are any uncommitted changes, **STOP immediately** and tell the user:
> "You have uncommitted changes in your working directory. Please commit or discard them before running this skill."

Do NOT stash, reset, or otherwise modify their working directory. Only proceed if that command returns empty output.

## Step 4: Checkout the PR Branch

**GitHub:**
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    "$gh" pr checkout {PR_NUMBER}
'
```

**GitLab and Bitbucket** — use native git, checking out whichever branch name succeeded in Step 2:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    "$git" checkout {SHIFT_BRANCH}
'
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
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    grep=$(PATH="$PATH" command -v grep) || { echo "grep not found on the fixed PATH" >&2; exit 127; }
    "$gh" pr diff {PR_NUMBER} --name-only | "$grep" -q "^composer\.json$"
'
```

**GitLab and Bitbucket:**
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
    grep=$(PATH="$PATH" command -v grep) || { echo "grep not found on the fixed PATH" >&2; exit 127; }
    "$git" diff "$("$git" merge-base HEAD "origin/{SHIFT_BRANCH}")...origin/{SHIFT_BRANCH}" --name-only | "$grep" -q "^composer\.json$"
'
```

If `composer.json` was **not** changed, skip the rest of this step entirely and proceed to Step 7.

If `composer.json` **was** changed, scan it for any `dev-*` version constraints (e.g. `"dev-main"`, `"dev-master"`, `"dev-fix-something"`). For each one found:
1. Look up the package on Packagist to check if a stable release exists:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         echo "could not resolve the passwd home; not running the command" >&2
         exit 127
       fi
       HOME=$passwd_home
       export HOME
       COMPOSER_HOME=$HOME/.composer
       export COMPOSER_HOME
       composer=$(PATH="$PATH" command -v composer) || { echo "composer not found on the fixed PATH" >&2; exit 127; }
       "$composer" show {package} --all
   '
```
2. If a compatible stable version is available, update the constraint in `composer.json` to the appropriate semver range (e.g. `^1.2`) and track it as a swapped dependency for the summary in Step 10
3. If no stable release exists, leave the `dev-*` constraint as-is

Then run:
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    composer=$(PATH="$PATH" command -v composer) || { echo "composer not found on the fixed PATH" >&2; exit 127; }
    "$composer" update
'
```

After running (whether it succeeds or fails):

**GitLab and Bitbucket only** — ask the user to paste the PR comments:
> "Please paste any comments from the pull request here, or let me know if there are none."

Then scan the pasted comments for any linked Shift suggestions — these are typically laravelshift.com URLs mentioned in comments recommending a follow-up Shift to run.

When collecting these suggestions:
- Preserve comment order — surface them in the order they appear
- **Exclude the last comment** if it contains Shift links or "you're now running the latest version of Laravel" — set it aside and surface it in Step 10 instead
- If any remaining (non-last) comments contain Shift suggestions, surface them to the user now:

> "The PR suggests running additional Shifts: [list links in comment order]. Would you like to run any of these before continuing?"

If the Composer update failed, attempt to systematically resolve the incompatibilities before stopping:
1. Read the error output carefully to identify which packages have conflicting version constraints
2. For each conflicting package, check the latest compatible version with the pinned Composer `show` command above, or look up the package on packagist.org
3. Update the version constraint in `composer.json` to one that satisfies all dependencies, then re-run the pinned Composer `update` command above
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
1. Verify tests pass:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         echo "could not resolve the passwd home; not running the command" >&2
         exit 127
       fi
       HOME=$passwd_home
       export HOME
       COMPOSER_HOME=$HOME/.composer
       export COMPOSER_HOME
       php=$(PATH="$PATH" command -v php) || { echo "php not found on the fixed PATH" >&2; exit 127; }
       "$php" artisan test --compact
   '
```
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
1. Check for any uncommitted local changes:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         echo "could not resolve the passwd home; not running the command" >&2
         exit 127
       fi
       HOME=$passwd_home
       export HOME
       COMPOSER_HOME=$HOME/.composer
       export COMPOSER_HOME
       git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
       "$git" status --porcelain
   '
```
2. If there are uncommitted changes:
   - Check if the only changed files match `composer.*` (i.e. `composer.json` and/or `composer.lock`). If so, stage and commit them automatically with the message `composer update` — do not prompt the user.
   - Otherwise, offer to commit them:
     > "You have uncommitted local changes. Would you like me to commit them for you with a summary?"
     If the user agrees, stage all changes and commit using "Finalize upgrade" as the subject and the summary from Step 10 as the commit body.
     If the user declines, wait for them to confirm they've committed their changes before proceeding.
3. Once the working directory is clean, check if the branch has unpushed commits:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         echo "could not resolve the passwd home; not running the command" >&2
         exit 127
       fi
       HOME=$passwd_home
       export HOME
       COMPOSER_HOME=$HOME/.composer
       export COMPOSER_HOME
       git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
       "$git" log "origin/{BRANCH}..HEAD"
   '
```
4. If there are unpushed commits, push them:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         echo "could not resolve the passwd home; not running the command" >&2
         exit 127
       fi
       HOME=$passwd_home
       export HOME
       COMPOSER_HOME=$HOME/.composer
       export COMPOSER_HOME
       git=$(PATH="$PATH" command -v git) || { echo "git not found on the fixed PATH" >&2; exit 127; }
       "$git" push
   '
```
5. Merge using the appropriate method for the platform:

**GitHub:**
```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      echo "could not resolve the passwd home; not running the command" >&2
      exit 127
    fi
    HOME=$passwd_home
    export HOME
    COMPOSER_HOME=$HOME/.composer
    export COMPOSER_HOME
    gh=$(PATH="$PATH" command -v gh) || { echo "gh not found on the fixed PATH" >&2; exit 127; }
    "$gh" pr merge {PR_NUMBER} --merge --delete-branch
'
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
