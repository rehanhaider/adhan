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

## Tests

Run the full suite with:

```bash
python3 -m unittest discover tests
```

It uses only the Python standard library. You do not have to install
anything on the Pi. There is no CI: run the suite yourself.

The tests protect these promises (see #16):

| # | Promise |
|---|---|
| C1 | The times are correct for the location, method, date and timezone. |
| C2 | Each prayer has exactly one job at its time, with the correct audio file, volume and player. |
| C3 | The schedule renews itself, and a second run does not add jobs. Other cron jobs stay. |
| C4 | Bad input or a time that cannot be calculated stops the script. The crontab and `adhan.toml` do not change. |
| C5 | Each setting comes from the command line, then `adhan.toml`, then the default. |
| C6 | `playAzaan.sh` plays the file with the selected player at the correct gain, and runs the hooks. |

Rules:

1. A bug fix starts with a test that fails. The PR shows that the test
   fails before the fix and passes after it.
2. A new setting (#10 to #14) adds rows to the C5 and C4 tables in
   `tests/test_core.py` and `tests/test_main.py`. If the setting changes the
   schedule, it also adds one line to the first-run/nightly scenario in
   `tests/test_main.py`.
3. Run the full suite before a merge. Do not merge if a test fails.
4. Each new test names the promise (C1 to C6) that it protects.
5. No test may read or write the real crontab, the real `adhan.toml` or the
   speakers. Use the fakes in `tests/fakes.py`: temporary folders, an
   in-memory `CronTab(tab=...)` and a fake `cvlc` on `PATH`. Do not use
   `mock.patch` on the functions of the app.
