`godmode roi` now counts real denials. `godmode_roi.roi_report` folded only
`kind="action"` records carrying `data.roi_event == "gate:denied"` into
`gate.denied` - a convention no shipped writer has ever emitted a record
for. `godmode_session_hook.py` has, since the stage-from-refusal unit,
written a real `kind="refusal"` record at every R5 deny (`stage_from_refusal`
reads them back the same way), and `roi` never read that kind at all: this
repo's own archive holds hundreds of real refusals, all reported as
`gate.denied=0`. `gate.denied` now folds `kind="refusal"` records
unconditionally - every refusal record IS a denial, since the hook's `ask`
branch never appends one - alongside the pre-existing `action`/`roi_event`
convention, which stays as an additional source; the two are disjoint by
kind, so no dedupe is needed between them.
