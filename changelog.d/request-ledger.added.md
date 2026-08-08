A ledger of what the operator actually asked for.

Everything else this runtime governs leaves an artefact: a command leaves a
run, a fix leaves a commit, a conclusion leaves a claim that must cite one. A
request leaves the agent's recollection and nothing else, which is the one
substrate this product exists to distrust — so an ask made while the agent was
already working is the thing that goes missing, and afterwards nobody can point
at what was dropped because there was never a list.

Recorded live, because it cannot be reconstructed. Both signals that would have
allowed reconstruction were tested against a real 9,777-event transcript and
both are absent: the host's "sent a new message while you were working" notice
appears twice in the whole file, once because the agent quoted it, and zero of
113 human inputs carry a timestamp inside a tool call's span, because the
stored time is delivery rather than typing. After the fact an interruption is
indistinguishable from an ordinary turn.

So a `UserPromptSubmit` hook writes each prompt as a `request` record as it
arrives, with whether tool calls were already in flight. `checkpoint --review`
reports the ones nothing visibly answered, interruptions first, and closure is
the same explicit act obligations use — findings, never closures, because an
agent that could close its own requests would close them the way it currently
forgets them.

The prompt goes through the ordinary append, so the secret scan every record
gets applies: a pasted token is refused, and the hook swallows the refusal so
the operator's turn continues. The subject is truncated rather than stored
whole; the host already keeps a transcript and a second copy is a second thing
to leak.
