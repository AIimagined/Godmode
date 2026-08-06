`atlas diagnose` now reports per-suffix support — a suffix whose files yield no
symbols is "counted, not understood" and makes the atlas untrustworthy for
structural claims — and `atlas duplicates` compares approximate symbol bodies
as well as names, so one behaviour implemented twice under unrelated names is
reported with `basis: body`.
