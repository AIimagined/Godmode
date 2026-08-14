- `godmode authorize stage --from-last-refusal [--nth N]` (U-E5): the gate's
  own R5 refusal now records itself (kind `refusal`: bounded operation, tool,
  tier, category), and staging reads that record back instead of asking the
  operator to retype the command a refusal already printed verbatim. Nothing
  about the trust model changes - the password is still required, the
  capability is still spent once, it still expires - only the typing does.
  `--nth 2` reaches a refusal before the latest one; with none on record the
  command refuses with "nothing to stage" rather than staging something
  stale. The staged operation is echoed back before the password is checked,
  so a wrong `--nth` is caught by eye. The refusal reason itself gains one
  literal line, `! godmode authorize stage --from-last-refusal`, so a hosted
  session can run it without leaving the conversation.
