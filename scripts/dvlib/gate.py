"""Stage gating: a BLOCKER in a closed stage skips every later stage."""


def close_stage(run, stage, results):
    blockers = sorted(f["id"] for r in results.values() for f in r["findings"]
                      if f["severity"] == "BLOCKER")
    run["stages"][str(stage)] = "COMPLETED"
    if blockers:
        run["blocked_by"] = blockers
        for key in run["stages"]:
            if int(key) > stage:
                run["stages"][key] = "SKIPPED"
    return blockers
