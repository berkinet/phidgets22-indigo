# Phidgets 22 project release reminder

- The authoritative public repository is `berkinet/phidgets22-indigo`.
- Work directly on `main` unless the user or an exceptional risk requires a
  branch.
- When a requested implementation is complete, do not stop after the local
  code change. Unless the user explicitly says the work is local-only, finish
  the release: update the plugin patch version and release notes, run the full
  tests and validation, commit, push `main`, create and push the matching
  annotated version tag, and verify the remote commit and tag.
- Distribution is through GitHub's **Code → Download ZIP** command. Do not
  create or attach a custom ZIP and do not use a GitHub Release asset as the
  download method.
- In the handoff, state the published version, repository, branch, commit,
  verification results, and the **Code → Download ZIP** installation route.
