Each release gate is now run against a copy of the project with the property it
defends deliberately broken, and must report failure. A gate that stays green
under its own breaking mutation is not a check, and six times in one session a
check reported a success it could not have withheld — twice a gate battery
piped through a pager so the recorded exit status belonged to the pager, twice a
probe that passed only on a machine already initialised, once a suite that
proved refusals without asking whether ordinary work could still proceed, and
once a contamination grep read as clean when its exit code meant the opposite.
Knowing about the failure mode did not prevent the sixth instance, which is why
it is asserted rather than remembered.

Writing the mutation turned out to matter as much as running it. Three of the
first mutations attempted were wrong — they broke something the gate never
claimed to watch, and three gates were briefly and wrongly suspected of being
blind. A breaking mutation cannot be written for a gate whose contract is not
understood, so the harness doubles as a statement of what each gate is for.
Gates without a proof are listed with the reason, because a harness that
quietly covers a subset reads as covering everything.

Module self-checks are now discovered rather than registered by hand. Six
already existed and had never been wired into the suite, and the action gate —
the classifier deciding whether a destructive command is interrupted — had no
self-check at all while quieter modules did. It has one now, asserting both
directions: the commands a working session issues must pass, and the
destructive forms must not.
