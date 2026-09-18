# Review records

One file per reviewer, named `reviewer_<n>_<bundle>_<date>.md`. A record holds: your name and the date; the commit you read (`git rev-parse HEAD`) and the result of `python tools/make_release_manifest.py --check`; every line of your checklist (manual chapters 15 to 19) with what you saw; the output of your sanity-check cell (`cell 17`); your questions and how each was resolved. A reviewer never reviews a bundle they wrote. Every bundle of version 0.0.1 was written in Claude sessions.
