The refusal message named the wrong remedy, and recommended the worst one.

It told the operator that no capability can be attached to a host tool call, so
there is no in-session approval — and offered disabling the plugin instead.
Twenty lines above that sentence, in the same function, a staged capability is
consumed and the call proceeds. `authorize stage` shipped in v0.2.6 to answer
exactly this refusal, and the message was never revisited.

So every refusal denied the existence of its own remedy, and the advice most
likely to be taken was the one that removes the guard. The refusal now names
the staged-capability path and quotes the exact operation to authorise.
