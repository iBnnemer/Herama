/** Detects a model that has started repeating the same passage over and over. */

const TAIL = 3000;
const CHECK_EVERY = 40;   // characters of new text between checks

const meaningful = (s: string) => /[\p{L}\p{N}]/u.test(s);

/** Index in `text` where the repeated passage first ends (keep everything before it), or -1 when there is no loop. */
export function findLoop(text: string): number {
  const tail = text.length > TAIL ? text.slice(-TAIL) : text;
  const offset = text.length - tail.length;
  for (let p = 6; p <= 800 && p * 3 <= tail.length; p++) {
    const unit = tail.slice(-p);
    if (!meaningful(unit)) continue;
    let reps = 1;
    while ((reps + 1) * p <= tail.length && tail.slice(-(reps + 1) * p, -reps * p) === unit) reps++;
    const need = p < 30 ? 8 : p < 120 ? 4 : 3;   // short phrases must repeat more often to count
    if (reps >= need && reps * p >= 120) return offset + tail.length - (reps - 1) * p;   // keep one copy
  }
  return -1;
}

/** Call with the whole text so far after every chunk; returns the cut position once a loop is found, otherwise -1. */
export function makeLoopGuard() {
  let last = 0;
  return (text: string): number => {
    if (text.length - last < CHECK_EVERY) return -1;
    last = text.length;
    return findLoop(text);
  };
}
