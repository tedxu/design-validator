# Audit instructions

Check whether serious findings are established by the evidence they
cite. Do not add findings, change severities or propose fixes.

1. Read every `<run_dir>/results/*.json` and select each finding whose
   `severity` is `BLOCKER` or `MAJOR`.
2. For each, read its statement, its checks and every evidence item it
   cites, and open the cited lines yourself (at the baseline:
   `git show <commit>:<path> | cat -n`).
3. Decide, with a one-sentence `reason`:
   - `confirmed`: the evidence, read in context, establishes the
     statement;
   - `disputed`: it does not — e.g. the excerpt is out of context,
     another branch handles the case, the statement overreaches, or the
     problem is pre-existing and the design neither causes nor depends
     on it.
4. For each `external` item a selected finding cites, open its `url`;
   `confirmed: true` only if the page says what the excerpt claims for
   the cited version.
5. Write `<run_dir>/audit.json`, reviewing each selected finding once
   and omitting empty `external_checks`:

    {"reviews": [
      {"finding_id": "fact-check.F1", "verdict": "confirmed", "reason": "…",
       "external_checks": [{"evidence_id": "fact-check.E4", "confirmed": false, "note": "page covers v3.6 only"}]}
    ]}
