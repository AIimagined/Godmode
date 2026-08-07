`checkpoint --review` reports obligations that a later handoff may have made
moot. Recording what must not be forgotten was always here; nothing ever asked
whether a carried obligation was still worth doing, so an item recorded validly
and superseded by a later release was restated in every handover until a human
asked why it was still there. Both are continuity failures and only one was
implemented.

Two signals, deliberately dull. An obligation restated across three or more
handovers without changing is reported, which needs no understanding of the
text at all. An obligation about a version, recorded again later about a higher
version, is reported as pointing at a release nobody will install.

Findings, never closures — the fix for carrying something too long must not
become dropping it too early, so each finding is phrased as the question a
reader should answer.

The first implementation grouped obligations by exact wording and found nothing
in twenty-two real handovers, because real obligations are compound sentences
that drift while meaning the same thing. They are now split on the joins that
separate them and grouped by word overlap, and the test corpus is taken from
the archive rather than written to suit the matcher.
