Runtime guardrails inside the no-daemon boundary: `ceilings` checks reported
spend against declared run limits, `watch` is a per-boundary anomaly scan that
interrupts on a skip pattern, `rewind --to SEQ` previews a rollback to a
verified checkpoint (checkpoints now record HEAD; execution stays with the
operator), and `planmode arbitrate` scores every open plan instead of taking
the first one stated.
