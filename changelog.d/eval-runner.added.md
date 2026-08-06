The authored skill evals now execute: a deterministic routing runner scores every
positive and near-negative prompt leave-one-out with stable tie-breaks, snapshot
fixtures under `evals/fixtures/` turn any routing change into a field-level diff, and
an adversarial grid attacks each control with real probes - breaches included.
