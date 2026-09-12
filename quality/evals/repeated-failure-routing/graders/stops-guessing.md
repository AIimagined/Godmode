---
type: llm
focus: last_message
---

The user has had two fixes fail in a row on the same failing test.

PASS if the reply treats the two failed fixes as a signal that the current explanation is wrong, and directs the next step at gathering evidence — reading the failure output, reproducing it, or instrumenting it — before proposing another fix.

FAIL if the reply proposes a third candidate fix as its main answer, or asks the user to try something else without first establishing what the failure actually is.
