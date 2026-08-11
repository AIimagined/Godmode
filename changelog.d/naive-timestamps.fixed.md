A timestamp that had lost its offset was read on two different clocks.

Every instant this project writes carries `+00:00`. The ones that do not are
the interesting ones: a record written by hand, or one carried over from a
schema that stored a bare clock. Two readers disagreed about what such a value
meant, and neither disagreed loudly.

The health check crashed on it. `_parse_time` caught `ValueError`, so a
malformed string returned nothing and the check carried on — but a well-formed
string with no offset parsed cleanly into a naive instant, and subtracting that
from an aware one raises `TypeError`, which nothing caught. One unlabelled
timestamp anywhere in the archive took down the whole context report rather
than ageing a single baseline wrongly.

The staleness guard answered wrongly instead, which is worse for being quiet.
It read the file's modification time on whatever clock the start time carried,
so an unlabelled start time meant `tz=None` — the host's local clock — while
the start time itself was meant as UTC. The comparison then ran between two
different clocks and was wrong by the host's offset. Measured on a `+05:30`
host: a process started two hours after the newest source reported `stale`, and
the guard blocked a diagnosis that should have proceeded. West of UTC it fails
the other way and clears a process that really is dead.

Neither timestamp was wrong in its own frame, which is exactly why it read as
plausible and why no self-consistency check could have found it. Both readers
now pin to UTC, an unlabelled value is documented as UTC where it is parsed
rather than assumed separately at each call site, and the reported modification
time states its offset so the next reader cannot repeat the mistake by eye.
