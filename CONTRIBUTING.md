# Contributing

## Setup

Repositories that ship a `mise.toml` install their tools with [mise](https://mise.jdx.dev):

```sh
mise install
mise run setup
```

Otherwise the README says how to set up.

## Tasks

```sh
mise tasks              # list every task the repository defines
mise run check          # lint and tests, the same as CI
```

Repositories without mise list their checks in the README or in `.github/workflows`.

## Changes

Changes reach `main` through pull requests that pass CI. Keep one fix or one feature per pull request. Match the existing style and do not reformat code you did not change. Add or update tests when the repository has them.

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org): `feat(cli):`, `fix(app):`, `docs:`, `chore:`. Repositories that release use [release-please](https://github.com/googleapis/release-please); it turns those commits into the changelog and the version bump. Until 1.0, a feature bumps the minor version and a fix bumps the patch version.

## Layout

The README describes the repository layout. Open an issue before a change that moves things around.
