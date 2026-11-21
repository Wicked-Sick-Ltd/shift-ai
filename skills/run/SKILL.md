---
name: run
description: Run a Shift against this repository via the Shift API
arguments: <sku>
---

# Shift Run

Run a Shift against this repository via the Shift API. The Shift code is: $ARGUMENTS

## Shift Codes

| Code | Shift |
|------|-------|
| `CI` | CI Generator |
| `TD` | Double Converter |
| `FL` | Fast Laravel |
| `HC` | HTML Converter |
| `10` | Laravel 10.x |
| `11` | Laravel 11.x |
| `12` | Laravel 12.x |
| `13` | Laravel 13.x |
| `50` | Laravel 5.0 |
| `51` | Laravel 5.1 |
| `52` | Laravel 5.2 |
| `53` | Laravel 5.3 |
| `54` | Laravel 5.4 |
| `55` | Laravel 5.5 |
| `56` | Laravel 5.6 |
| `57` | Laravel 5.7 |
| `58` | Laravel 5.8 |
| `60` | Laravel 6.x |
| `70` | Laravel 7.x |
| `80` | Laravel 8.x |
| `90` | Laravel 9.x |
| `CR` | Laravel Cloud Pre-Check |
| `LF` | Laravel Fixer |
| `LL` | Laravel Linter |
| `LP` | Laravel PreShift |
| `LS` | Laravel Slimmer |
| `L3` | Livewire 3.x |
| `L4` | Livewire 4.x |
| `LTL` | Lumen to Laravel |
| `MC` | MFC Converter |
| `MM` | MySQLi Shift |
| `NC` | Namespace Consolidator |
| `NM` | Namespace Models |
| `PP` | Pest Converter |
| `PU10` | PHPUnit 10 |
| `PU11` | PHPUnit 11 |
| `PU12` | PHPUnit 12 |
| `PU13` | PHPUnit 13 |
| `PU6` | PHPUnit 6 |
| `PU8` | PHPUnit 8 |
| `PU9` | PHPUnit 9 |
| `P4` | PSR-4 Shift |
| `T1` | Tailwind 1.x |
| `T2` | Tailwind 2.x |
| `T3` | Tailwind 3.x |
| ~~`T4`~~ | **Not a real Shift.** Tailwind 4.x has no Shift — laravelshift.com redirects to Tailwind's own upgrade tool. Never run this; point the user to https://tailwindcss.com/docs/upgrade-guide#using-the-upgrade-tool instead. |
| `TU` | Tailwind UI |
| `TG` | Tests Generator |
| `VC` | Vite Converter |

## Command Environment

Project Claude settings are copied into every Bash call. That includes `PATH`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*`, `GIT_CONFIG_PARAMETERS`, `GIT_EXEC_PATH`, `BASH_ENV`, `ENV`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, and `DYLD_*`. Assigning a fixed `PATH` and `unset -f` does not stop git from applying those config variables, and it does not stop the dynamic linker. `BASH_ENV` is sourced before the first line of the command.

Run **every** tool for this skill, including commands you write yourself (commits, pushes, branch creation), as one `/usr/bin/env -i` command. The absolute `/usr/bin/env` looks up `bash` on the fixed `PATH` below; do not resolve `env` or `bash` in the outer shell. Git commands start `bash --noprofile --norc` with only `PATH` and `SSH_AUTH_SOCK`. Do not pass the outer shell's `HOME`. Inside that bash, set `HOME` from the passwd entry for the current uid, or from Directory Services on macOS, and set `COMPOSER_HOME` to `$HOME/.composer` before running a tool. The curl call receives the token on stdin and does not pass `HOME` or `SHIFT_API_TOKEN` into that process. Then resolve each tool with `command -v` on the fixed `PATH` and execute the absolute path. Do not pass git-config variables, `BASH_ENV`, `ENV`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, or `DYLD_*`.

Claude Code starts the Bash tool before this snippet runs, so a project `BASH_ENV` file and linker variables are already applied to that outer shell. This skill cannot clear them there. `/usr/bin/env -i` is what starts the tool without those variables.

```bash
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:/mingw64/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
  bash --noprofile --norc -c '
    uid=$(id -u)
    passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
    if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
      passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
    fi
    if [ -z "$passwd_home" ]; then
      dscl=$(PATH="$PATH" command -v dscl 2>/dev/null) || dscl=
      if [ -n "$dscl" ]; then
        passwd_home=$("$dscl" . -read "/Users/$(id -un)" NFSHomeDirectory 2>/dev/null | awk "{print \$2}")
      fi
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

## Steps

1. If no Shift code was provided in `$ARGUMENTS`, ask the user which Shift they'd like to run. Show the code table above as a reference and suggest running `/shift:analyze` first if they're unsure which Shift applies to their project.

   If `$ARGUMENTS` is `T4` (or otherwise requests a "Tailwind 4" Shift), do not call the API. There is no Tailwind 4.x Shift — tell the user to use Tailwind's own upgrade tool instead: https://tailwindcss.com/docs/upgrade-guide#using-the-upgrade-tool

2. Check if `SHIFT_API_TOKEN` is set in the environment. If it's missing, let the user know they may generate an API token at: https://laravelshift.com/account/api-token, then ask them to provide it. Once provided, ask whether they'd like to save it to `~/.claude/settings.json` (recommended — available across all projects) or `.claude/settings.local.json` (this project only). Save it under the `env` key of whichever file they choose:
   ```json
   {
     "env": {
       "SHIFT_API_TOKEN": "their_token"
     }
   }
   ```
   If the target file already exists, merge the key into the existing `env` object rather than overwriting the file.

3. Determine the remote and current branch by running:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:/mingw64/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         dscl=$(PATH="$PATH" command -v dscl 2>/dev/null) || dscl=
         if [ -n "$dscl" ]; then
           passwd_home=$("$dscl" . -read "/Users/$(id -un)" NFSHomeDirectory 2>/dev/null | awk "{print \$2}")
         fi
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
       sed=$(PATH="$PATH" command -v sed) || { echo "sed not found on the fixed PATH" >&2; exit 127; }
       "$git" remote get-url origin
       "$git" branch --show-current
       "$git" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | "$sed" "s@^refs/remotes/origin/@@"
   '
```
   Parse the remote URL to extract `owner/repo` — handle both SSH (`git@github.com:owner/repo.git`) and HTTPS (`https://github.com/owner/repo.git`) formats. Strip any trailing `.git`. Also detect the git platform (GitHub or GitLab) from the remote URL hostname, and construct the HTTPS repo URL (e.g. `https://github.com/owner/repo`).

   The third command returns the remote default branch (e.g. `main` or `master`). If it produces no output, fall back to treating `main` and `master` as default branch names.

4. Check for uncommitted changes by running:
   ```bash
   /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:/mingw64/bin SSH_AUTH_SOCK="${SSH_AUTH_SOCK-}" \
     bash --noprofile --norc -c '
       uid=$(id -u)
       passwd_home=$(getent passwd "$uid" 2>/dev/null | cut -d: -f6)
       if [ -z "$passwd_home" ] && [ -r /etc/passwd ]; then
         passwd_home=$(awk -F: -v uid="$uid" "\$3==uid {print \$6; exit}" /etc/passwd)
       fi
       if [ -z "$passwd_home" ]; then
         dscl=$(PATH="$PATH" command -v dscl 2>/dev/null) || dscl=
         if [ -n "$dscl" ]; then
           passwd_home=$("$dscl" . -read "/Users/$(id -un)" NFSHomeDirectory 2>/dev/null | awk "{print \$2}")
         fi
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
   If there is any output, prompt the user:

   > You have uncommitted changes. Would you like to commit and push them before running Shift, or continue without doing so?

   If they want to commit, ask for a commit message, stage all changes (`git add -A`), and commit, running git through the clean `/usr/bin/env -i` command above. Then push only the current branch with this command. It runs `env` from the fixed PATH with `-i`, passes only the ssh command and protocol allow-list, clears credential helpers, askpass, fetch/push/checkout aliases, and `core.fsmonitor`, reads the branch's full ref from `git symbolic-ref --quiet HEAD`, and pushes only `"HEAD:$ref"` with `-c remote.origin.mirror=false`, `-c push.followTags=false`, `--no-follow-tags`, and `--recurse-submodules=no`. Never push without an explicit remote and refspec:
   ```bash
   shift_path=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:/mingw64/bin
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

5. If the current branch matches the default branch, warn the user and suggest they switch to a dedicated branch before running Shift — for example:

   > You're on the default branch (`{branch}`). It's recommended to run Shift against a separate branch (e.g. `laravel-upgrade`) so the changes can be reviewed and merged when done. Would you like to continue anyway, or switch to a new branch first?

   If they want to create and switch to a new branch, do so before proceeding. If they choose to continue on the default branch, note it and proceed.

6. Build the `scs` connection string in the format `github:owner/repo:branch`.

7. Run the Shift via the API, capturing both the HTTP status code and response body. Run this command exactly as written, only filling in the placeholders. It starts `curl` by an absolute path (Linux, macOS, or Git for Windows under `/mingw64/bin`) with an empty environment and without `.curlrc`, disables proxies, allows only HTTPS, and pins the operating system CA bundle, including the Git Bash bundles under `/usr/ssl` and `/mingw64`. `env` settings from a project cannot route the request elsewhere or substitute a certificate authority. The token is passed on stdin rather than on the command line. If no CA bundle or curl is found, the command exits non-zero and deletes `/tmp/shift_response.json`:
   ```bash
   shift_ca=''
   for f in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/ca-bundle.pem /etc/ssl/cert.pem /usr/ssl/certs/ca-bundle.crt /mingw64/ssl/certs/ca-bundle.crt /mingw64/etc/ssl/certs/ca-bundle.crt; do
     if [ -f "$f" ]; then shift_ca=$f; break; fi
   done
   shift_curl=
   for c in /usr/bin/curl /bin/curl /usr/local/bin/curl /mingw64/bin/curl /mingw64/bin/curl.exe; do
     if [ -x "$c" ]; then shift_curl=$c; break; fi
   done
   rm -f /tmp/shift_response.json
   if [ -z "$shift_ca" ] || [ -z "$shift_curl" ]; then
     echo 'No system CA bundle or curl found; not sending the Shift API token.' >&2
     exit 1
   fi
   printf 'api_token=%s' "$SHIFT_API_TOKEN" | /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:/mingw64/bin \
     bash --noprofile --norc -c 'exec "$@"' _ "$shift_curl" -q -s --noproxy '*' --proto '=https' --cacert "$shift_ca" \
     -o /tmp/shift_response.json -w "%{http_code}" -X POST \
     -H 'Accept: application/json' \
     -d @- \
     -d "code=$ARGUMENTS" \
     -d "scs=github:owner/repo:branch" \
     https://laravelshift.com/api/run
   shift_curl_status=$?
   if [ "$shift_curl_status" -ne 0 ]; then
     rm -f /tmp/shift_response.json
     exit "$shift_curl_status"
   fi
   ```
   Keep the request in this form. Project settings can inject proxy, CA bundle, and curl config variables into the environment; `env -i`, `-q`, `--noproxy '*'`, `--proto '=https'`, and `--cacert` keep those from intercepting the token, and piping the token on stdin keeps it out of curl's environment and arguments. The absolute `curl` binary runs inside that `env -i` bash, started with `--noprofile --norc`. The CA search includes the Git for Windows bundles under `/usr/ssl` and `/mingw64`, which is where Git Bash keeps `ca-bundle.crt`.

8. Handle the response based on the HTTP status code. If step 7 exits non-zero, or prints no status, stop and tell the user the request was not sent. Do not read `/tmp/shift_response.json` in that case; step 7 removes it when it cannot send, so a body left by an earlier run is not this request's result.

   - **202** — Success. Parse the response body and extract `shift_number`. Display this message exactly:

     > Shift #{shift_number} has been queued. Most Shifts run within a few minutes. You may monitor its progress at: {pr_url}. Once the {pr_term} is open, you may use the `/shift:review {shift_number}` command to automate the review process.

     Where `{pr_url}` is the HTTPS URL to the repository's pull requests page (`{repo_url}/pulls` for GitHub, `{repo_url}/-/merge_requests` for GitLab) and `{pr_term}` is "pull request" for GitHub or "merge request" for GitLab.

   - **400** — Bad request. Parse the response body and display the `message` field directly to the user.

   - **401** — Invalid token. Tell the user their API token was rejected. Prompt them to re-enter it, then save the new value to `.claude/settings.local.json` under `env.SHIFT_API_TOKEN` (merging into any existing file). Retry the request once with the new token, using the same command from step 7.

   - **402** — Payment required. Parse the response body and extract `shift_number` and `checkout_url`. Display this message exactly:

     > Shift #{shift_number} requires payment. You may complete checkout at: {checkout_url}. Once paid, your Shift will run. Then you may use the `/shift:review {shift_number}` command to automate the review process.

   - **403** — Not authorised to run this Shift. Tell the user their account does not have access to run this particular Shift (it may require a purchase or a different plan at laravelshift.com).

   - **Any other status** — Show the raw status code and response body and ask the user how they'd like to proceed.
