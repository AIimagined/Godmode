---
name: godmode-repair
description: Re-pitch an answer that did not land, and record why it did not. Use when the operator says they do not follow, asks for clarity, repeats a question already answered, or asks what is being waited on.
---

# Godmode Repair

## Outcome

Say the thing again in a form the operator can act on, and leave a record that the
first form failed — so the same shape of answer is not produced again next session.

## The signal

Repair is invoked by the operator, not by the agent's own sense that things went
well. Treat any of these as the trigger, without arguing the point:

- "I don't follow", "be clear", "what do you mean"
- A question already answered, asked again
- "What do you want from me", "what is pending", "are you waiting"
- A decision requested twice without an answer arriving

The last two are specific and worth naming: they mean options were presented where a
recommendation was owed. An operator asking what is needed from them is reporting that
the ask was buried, not that they missed it.

## Re-pitch

1. **Lead with the answer.** One sentence, first line, before any qualification. If the
   honest answer is "nothing" or "I don't know yet", that is the sentence.
2. **Cut the options.** Where a choice was offered, decide it and say what was decided
   and why. Reserve the question for the case where the wrong guess is unsafe or wastes
   the work.
3. **Name the single next act.** Whose it is, and what happens if it does not happen.
4. **Drop the qualifications** the first version carried. They are what buried it.

Length is the usual cause. An answer that needs a table of contents has already failed.

## Record it

`godmode remember --kind lesson --subject "<what did not land>" --guard "<the shape to
avoid>"`

Recorded as a lesson rather than a note because the failure is generalisable: what did
not land is almost never this one sentence, it is a shape — options where a decision was
owed, a status buried under evidence, a question asked four ways.

Record the shape, not the exchange. The transcript is the host's; a second copy is a
second thing to leak.

## What repair is not

Not an apology, and not a re-litigation of whether the first answer was correct. It
usually was correct and unusable, and those are different faults with different fixes.
Restating the reasoning in more detail is the failure repeating itself.

Do not close a repair by asking whether it landed. Say it, then continue the work.
