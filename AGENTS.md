# Phidgets 22 project release reminder

## Error handling requirement

- The project goal is no unhandled exceptions and no Python-generated error
  output or tracebacks in Indigo's log, including tracebacks explicitly logged
  by exception handlers.
- Handle failures at plugin entry points, callbacks, polling tasks, and other
  runtime boundaries. Report concise, actionable plugin messages with useful
  device and operation context; recover or retry safely where possible.
- Unexpected failures must still be reported clearly. Do not silently swallow
  errors, publish invalid readings, or claim success after a failed operation.
- Review new and changed error paths against this requirement. Existing code
  is not assumed to comply until it has been checked.

## Releases

- The authoritative public repository is `berkinet/phidgets22-indigo`.
- Work directly on `main` unless the user or an exceptional risk requires a
  branch.
- When a requested implementation is complete, do not stop after the local
  code change. Unless the user explicitly says the work is local-only, finish
  the release: update the plugin year.major.minor version and release notes, run the full
  tests and validation, commit, push `main`, create and push the matching
  annotated version tag (exactly matching PluginVersion, without a v prefix),
  create a published GitHub Release, and verify the remote commit, tag, and release.
- Distribution is through GitHub's **Code → Download ZIP** command. Do not
  create or attach a custom ZIP and do not use a GitHub Release asset as the
  download method.
- In the handoff, state the published version, repository, branch, commit,
  verification results, and the **Code → Download ZIP** installation route.
