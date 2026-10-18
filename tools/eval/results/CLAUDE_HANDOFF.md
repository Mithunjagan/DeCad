# Claude → Codex handoff (2026-10-18)

The user asked Claude to help speed up Codex's queue without colliding. Claude has
**not edited any live file** (`backend/app/*`, README, frontend, CODEX_LOG) and ran **no
recognition/OCR job** while the `codex-snapping` gate was running. Everything below is
staged in `backend/.state/claude-20261018/` for Codex to apply, reject or adapt.

Staged against `digital_vision.py` md5 `a5fbe5fd84d1d975621d703fa01411c4` (the Task 2
candidate under gate). Base copy: `digital_vision.base.py`; patched copy:
`digital_vision.staged.py`; diff: `task3-task4.patch` (66 lines).

## Task 3: duplicate body assignment (root cause found, patch staged)

S1 in `codex-layout-stable` has three ref pairs at *identical* coordinates:
U13/U16, U14/U15, U62/U64. Pin-debug extents show each pair is two stacked bodies:

| Pair | Pin y-extent A | Pin y-extent B | Shared "centre" y |
|---|---|---|---|
| U15 / U14 | 2152–2504 | 2592–3027 | 2539 (between them) |
| U64 / U62 | 3092–3399 | 3793–4103 | 3601 (between them) |

Mechanism: `_bridge` joins collinear pieces with gaps < 0.9 ch, so the side edges of two
bodies drawn edge to edge become one long line. `seg_boxes` then emits one outline around
both, and `_merge_boxes` (largest first, drops anything > 70% inside a kept box) discards
the real per-body boxes. Both refs bind to the composite: same centre, and the divider
lines inside it are not outline, so they are also treated as **wires** (possible spurious
connectivity).

Fix (`_split_stacked`, called on the merged boxes before the `named` filter): a box that
holds ≥ 2 distinct IC references is cut at full-width interior lines (≥ 80% of its width,
≥ 2.5 ch from its edges); the cut is accepted only if every piece holds ≤ 1 reference and
no reference is lost. Otherwise the box is unchanged. Works for both axes.

## Task 4: missing large central IC (S1 root cause found, patch staged)

S1 `ocr-tokens.json`: `U43` is read at conf 0.99, but its part number is read as
**`Idf7210L`** (conf 0.68). `PART_RE` requires `IDT\w+`, so it is not a part; the
`UNKNOWN` fallback also needs an enclosing box, so U43 is dropped entirely.

Fix (`part_prefix`): in the token-role loop, `[I1L|][DO0][TF7]` followed by a part-number
tail (3–5 digits, ≤ 2 letters, ≤ 3 digits) becomes `IDT…`. Only those three prefix letters
change. Applies to clear sheets too (`lowres_text` only runs on soft pages).

Not yet verified: whether U43's large body gets a box and its pins attach. That needs the
replay below.

Other missing parts, for the next round (diagnosed from cached tokens only):
- S5: three `2148` tokens (conf 1.0) are pure digits, so `PART_RE`'s `[A-Z]` check sends
  them to `numbers`; no `U18` ref token was read at all.
- S1: R1, R3, S1 refs read at ≥ 0.97 but are dropped (no value nearby); U1 ref at 0.52.
- S3 U66 / S4 U14 (`PROM`): no ref tokens in the cache; likely OCR, not assembly.

## Verification done / still needed

- Done: `test_staged.py` (synthetic, no image): **4 passed**. Covers the split, the
  divider becoming outline, single-ref bodies with internal lines kept whole, no-divider
  boxes kept, and `part_prefix` positives/negatives (INDA5, DD16, 74F244, ID07 unchanged).
- Needed (a recognition job, so only after the current gate and with nothing else running):
  token + strip replay of S1–S5 against the staged module, then the full fresh gate.
  Suggested: copy `digital_vision.staged.py` over `backend/app/digital_vision.py` (after
  backing up as usual) and run `tools/eval/replay_tokens.py` with `--strips` per sample,
  as for Task 2. Accept only if no sample regresses on parts, values or exact pins.

Claude will not touch `backend/app/` or run recognition unless the user or Codex asks.
If Codex prefers, Claude can run the replays sequentially once Codex says the machine is free.
