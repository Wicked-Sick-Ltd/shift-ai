---
name: refactor
description: Run a Shift Workbench task against this repository
arguments: [task-slug]
---

# Shift Workbench

Run a Shift Workbench task against this repository. The task slug is: $ARGUMENTS

## Available Tasks

- **Class based factories** (`adopt-class-based-factories`): Convert model factories to namespaced, class based factories. (Premium Task)
- **Remove down migration** (`remove-down-migration`): Remove the down method from your database migrations.
- **Adopt anonymous migrations** (`adopt-anonymous-migrations`): Convert your migrations to anonymous classes.
- **Declare strict types** (`declare-strict-types`): Add the `strict_types` declaration to your PHP files. (Premium Task)
- **Format test cases** (`format-test-cases`): Apply a common format to your test cases. (Premium Task)
- **Native Enums** (`convert-to-native-enums`): Convert `spatie/enum` to use native Enums in PHP 8.1. (Premium Task)
- **Global Facades** (`replace-global-facades`): Replace Facade references using the global namespace with their FQCN.
- **Common Helpers** (`adopt-common-helpers`): Convert common Facade chains to helper functions.
- **Model Table Name** (`remove-redundant-table-name`): Remove unnecessary table name properties from models.
- **Convert dates property** (`convert-dates-property`): Convert the model `$dates` property.
- **Streamline order methods** (`streamline-order-methods`): Streamline query builder order methods.
- **Form Request array syntax** (`adopt-validation-arrays`): Convert string based validation rules into arrays.
- **array/string Helpers** (`convert-array-string-helpers`): Convert old array and string helpers into their modern class-based methods.
- **optional to nullsafe** (`convert-optional-to-nullsafe`): Convert simple calls to Laravel's `optional` helper to use the nullsafe operator in PHP 8.
- **Separate Model Factory** (`separate-model-factory`): Separate a generic model factory into individual model factories.
- **Upgrade to Mix 6** (`upgrade-to-mix-6`): Upgrade your Laravel Mix dependencies and configuration to version 6.
- **Use latest/oldest** (`use-latest-oldest`): Convert to `latest` and `oldest` methods.
- **Use Laravel Carbon** (`use-laravel-carbon`): Reference `Carbon` through Laravel's class.
- **Adopt redirect helpers** (`adopt-redirect-helpers`): Adopt redirect helpers.
- **resolve helper** (`resolve-helper`): Use `resolve` helper.
- **Guess factory model** (`guess-factory-model`): Remove guessable `$model` property from model factories.
- **Request injection** (`leverage-request-injection`): Leverage the injected request object in Controllers and Middleware. (Premium Task)
- **Request data access** (`normalize-request-access`): Normalize request data access within your application. (Premium Task)
- **View data** (`normalize-view-data`): Normalize passing view data within your application. (Premium Task)
- **Command Autoloading** (`leverage-command-autoloading`): Remove unnecessary references by autoloading your application commands. (Premium Task)
- **Fluent Responses** (`adopt-fluent-responses`): Convert response and redirect calls to use Laravel's expressive method chains. (Premium Task)
- **Fluent Routes** (`adopt-fluent-routes`): Convert routes options using the old, array syntax. (Premium Task)
- **Blade Directives** (`modernize-blade-directives`): Modernize outdated HTML and Blade directives. (Premium Task)
- **Controller Validation** (`convert-controller-validation`): Convert inline controller validation into Form Request objects. (Premium Task)
- **Validation Rules** (`convert-validation-rules`): Convert string validation rules into the new, expressive `Rule` builder. (Premium Task)
- **env to config** (`convert-env-to-config`): Convert calls to the `env` helper to use the `config` helper with a new custom configuration file. (Premium Task)

- **Class based routes** (`adopt-class-based-routes`): Register routes using static class references instead of strings. (Premium Task)
- **actions to tuples** (`convert-actions-to-tuples`): Convert your route controller actions from strings to array "tuples". (Premium Task)
- **Adopt unguarded models** (`adopt-unguarded-models`): Convert your models from "fillable" to "unguarded". (Premium Task)
- **Expand resource routes** (`expand-resource-routes`): Expand resource routes. (Premium Task)
- **Adopt stringables** (`adopt-stringables`): Convert `Str` calls to stringables. (Premium Task)
- **Adopt attribute accessors/mutators** (`adopt-attribute-accessors-mutators`): Convert accessor/mutator methods to single method. (Premium Task)
- **Adopt if helpers** (`adopt-if-helpers`): Adopt `if` helpers. (Premium Task)
- **Adopt ObservedBy attribute** (`laravel-observedby-attribute`): Adopt `#[ObservedBy]` attribute.
- **Adopt ScopedBy attribute** (`laravel-global-scope-attribute`): Adopt `#[ScopedBy]` attribute.
- **Adopt Scope attribute** (`laravel-local-scope-attribute`): Adopt `#[Scope]` attribute.
- **Adopt property attributes** (`laravel-property-attributes`): Adopt PHP attributes for Laravel class properties. (Premium Task)
- **Adopt Laravel type hints** (`type-hints`): Add type hints to Laravel application code. (Premium Task)
- **Compare core files** (`compare-core-files`): Compare and upgrade core files. (Premium Task)

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

1. If no task slug was provided in `$ARGUMENTS`, display the full task list above, followed by:

   > **Note:** Several tasks have customizable options you may set via the [Shift Workbench](https://laravelshift.com/workbench) before running.

   Then lead with this recommendation before asking the user to choose:

   > **First time?** Shift recommends starting with a curated set of safe, broadly applicable tasks: `replace-global-facades`, `adopt-common-helpers`, `remove-redundant-table-name`, `use-laravel-carbon`, `use-class-constant`, `adopt-short-arrays`, `streamline-order-methods`. Would you like to run the curated set, or choose a specific task?

   If the user accepts the curated set, use `shift-curated` as the task slug. Otherwise ask the user which single task they'd like to run.

2. Validate that the provided slug exists in the table above. If an unrecognised slug is given, tell the user and stop.

3. Check if `SHIFT_API_TOKEN` is set in the environment. If it's missing, let the user know they may generate an API token at: https://laravelshift.com/account/api-token, then ask them to provide it. Once provided, ask whether they'd like to save it to `~/.claude/settings.json` (recommended — available across all projects) or `.claude/settings.local.json` (this project only). Save it under the `env` key of whichever file they choose:
   ```json
   {
     "env": {
       "SHIFT_API_TOKEN": "their_token"
     }
   }
   ```
   If the target file already exists, merge the key into the existing `env` object rather than overwriting the file.

4. Determine the remote and current branch by running:
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
   Parse the remote URL to extract `owner/repo` — handle both SSH (`git@github.com:owner/repo.git`) and HTTPS (`https://github.com/owner/repo.git`) formats. Strip any trailing `.git`. Also detect the git platform (GitHub, GitLab, or Bitbucket) from the remote URL hostname, and construct the HTTPS repo URL (e.g. `https://github.com/owner/repo`).

   The third command returns the remote default branch (e.g. `main` or `master`). If it produces no output, fall back to treating `main` and `master` as default branch names.

5. Check for uncommitted changes by running:
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

   > You have uncommitted changes. Would you like to commit and push them before running this Workbench task, or continue without doing so?

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

6. Build the `scs` connection string in the format `{platform}:owner/repo:branch`, where `{platform}` is `github`, `gitlab`, or `bitbucket` based on the detected remote.

7. Run the task via the API, capturing both the HTTP status code and response body. Run this command exactly as written, only filling in the placeholders. It starts `curl` by an absolute path (Linux, macOS, or Git for Windows under `/mingw64/bin`) with an empty environment and without `.curlrc`, disables proxies, allows only HTTPS, and pins the operating system CA bundle, including the Git Bash bundles under `/usr/ssl` and `/mingw64`. `env` settings from a project cannot route the request elsewhere or substitute a certificate authority. The token is passed on stdin rather than on the command line. If no CA bundle or curl is found, the command exits non-zero and deletes `/tmp/shift_response.json`:
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
     -d "scs={platform}:owner/repo:branch" \
     -d "task={task-slug}" \
     https://laravelshift.com/api/build
   shift_curl_status=$?
   if [ "$shift_curl_status" -ne 0 ]; then
     rm -f /tmp/shift_response.json
     exit "$shift_curl_status"
   fi
   ```
   Keep the request in this form. Project settings can inject proxy, CA bundle, and curl config variables into the environment; `env -i`, `-q`, `--noproxy '*'`, `--proto '=https'`, and `--cacert` keep those from intercepting the token, and piping the token on stdin keeps it out of curl's environment and arguments. The absolute `curl` binary runs inside that `env -i` bash, started with `--noprofile --norc`. The CA search includes the Git for Windows bundles under `/usr/ssl` and `/mingw64`, which is where Git Bash keeps `ca-bundle.crt`.

8. Handle the response based on the HTTP status code. If step 7 exits non-zero, or prints no status, stop and tell the user the request was not sent. Do not read `/tmp/shift_response.json` in that case; step 7 removes it when it cannot send, so a body left by an earlier run is not this request's result.

   - **202** — Success. Parse the response body and extract `build_number`. Display this message exactly:

     > Build #{build_number} has been queued. Most Workbench tasks run within a few minutes. You may monitor its progress at: {pr_url}. Once the {pr_term} is open, you may use the `/shift:review {build_number}` command to automate the review process.

     Where `{pr_url}` is the HTTPS URL to the repository's pull requests page (`{repo_url}/pulls` for GitHub, `{repo_url}/-/merge_requests` for GitLab, `{repo_url}/pull-requests` for Bitbucket) and `{pr_term}` is "pull request" for GitHub or Bitbucket, or "merge request" for GitLab.

   - **400** — Bad code. Tell the user the slug was not recognised by Shift and to double-check the value.

   - **401** — Invalid token. Tell the user their API token was rejected. Prompt them to re-enter it, then save the new value to `.claude/settings.local.json` under `env.SHIFT_API_TOKEN` (merging into any existing file). Retry the request once with the new token, using the same command from step 7.

   - **403** — Not authorised. Tell the user their account does not have access to this task (it may require a premium plan at laravelshift.com).

   - **Any other status** — Show the raw status code and response body and ask the user how they'd like to proceed.
