# Agent instructions

## GitHub: work on the fork only

This clone has two remotes:

- `origin` → `rehanhaider/adhan` (the fork, the only repo to act on)
- `upstream` → `achaudhry/adhan` (the original project, read-only)

Only comment, open or close issues, or open PRs on `rehanhaider/adhan`. Never
post anything to `achaudhry/adhan` or any other repo.

Because `upstream` exists, `gh` may resolve to `achaudhry/adhan` by default.
Always pass `--repo rehanhaider/adhan` explicitly, e.g.
`gh issue view 5 --repo rehanhaider/adhan`. Issue and PR numbers like "#5"
refer to the fork.
