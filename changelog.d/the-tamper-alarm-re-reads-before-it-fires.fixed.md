The tail-truncation alarm re-reads fresh disk state once, after a short beat, before it fires - a concurrent append no longer reads as tampering, while a real truncation still raises.
