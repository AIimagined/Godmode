`skill lifecycle`/`skill retire` give every skill a state and a recorded
reason; `godmode lessons` runs the promote-or-retire pipeline (a lesson either
gets its guard observed running or is retired — never appended forever); and
`godmode experiment` executes the bounded loop declared in
`.godmode-experiment.json`, recording every run and refusing to pass the bound.
