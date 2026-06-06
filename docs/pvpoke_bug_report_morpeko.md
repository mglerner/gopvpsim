# PvPoke bug report draft: Morpeko form change is one-way instead of a true toggle

Status: draft, ready to file (GitHub issue or Discord). ASCII-only,
no em/en-dashes (public-facing). Internal cross-reference:
DEVELOPER_NOTES.md "PvPoke bugs found" #8.

---

**Title:** Morpeko stays in Hangry form after its first Charged Move instead of toggling each Charged Move

**Summary**

In the battle simulator, Morpeko changes from Full Belly to Hangry on
its first Charged Move and then stays Hangry for the rest of the battle.
In the actual game Morpeko toggles Full Belly <-> Hangry after every
Charged Move (Aura Wheel changes between Electric and Dark to match), and
it always re-enters battle in Full Belly. Because Morpeko is stuck in
Hangry after the first throw, every second-or-later Aura Wheel is
simulated as Dark when it should alternate back to Electric, so its type
effectiveness and damage are wrong against many opponents.

**Steps to reproduce**

1. Open the 1v1 battle simulator with Morpeko (Full Belly) using
   Thunder Shock / Aura Wheel / Psychic Fangs.
2. Give it any matchup where it throws two or more Charged Moves.
3. Watch the timeline: after the first Charged Move Morpeko changes to
   Hangry and never changes back. The second Aura Wheel resolves as
   Dark-type.

**Expected**

Morpeko should toggle form after each Charged Move (Full Belly -> Hangry
-> Full Belly -> ...), so its Aura Wheel alternates Electric / Dark /
Electric. It should reset to Full Belly on switch-in (this part already
works via `resetOnSwitch`).

**Root cause**

`morpeko_full_belly`'s `formChange` is `type: "toggle", trigger:
"charged_move", moveId: "ANY", alternativeFormId: "morpeko_hangry"`, but
the `morpeko_hangry` gamemaster entry has no `formChange` block of its
own (`formChange: null`).

`Pokemon.js` `changeForm()` reassigns `this.formChange = form.formChange`
(around line 2356). So once Morpeko changes to `morpeko_hangry`, its
`formChange` becomes null and the post-attack form trigger in `Battle.js`
(around lines 1536-1537) can never fire again:

```js
if(attacker.formChange && attacker.formChange.trigger == "charged_move"
    && attacker.activeFormId != attacker.formChange.alternativeFormId
    && move.energy > 0
    && (attacker.formChange.moveId == "ANY" || attacker.formChange.moveId == move.moveId)){
    attacker.changeForm(attacker.formChange.alternativeFormId);
    ...
}
```

The first clause (`attacker.formChange`) is now falsy, so the block is
skipped. (Even if `morpeko_hangry` did carry a `formChange`, the
`activeFormId != alternativeFormId` guard would still block the
back-toggle unless it also compared against `defaultFormId`. That guard
looks like it was written for genuinely one-way changers such as
Aegislash and Mimikyu, and it does not fit a `type: "toggle"` form.)

**Suggested fix (either or both)**

1. Give `morpeko_hangry` a reciprocal `formChange` in the gamemaster:
   `type: "toggle", trigger: "charged_move", moveId: "ANY",
   defaultFormId: "morpeko_full_belly", alternativeFormId:
   "morpeko_full_belly", resetOnSwitch: true` (so the toggle target is
   Full Belly when in Hangry).
2. Generalize the `Battle.js` toggle guard so a `type: "toggle"` form
   changes back to its `defaultFormId`, rather than only firing when
   `activeFormId != alternativeFormId`.

**Notes**

Verified against the live game: Morpeko enters every battle in Full Belly
(at battle start and on switch-in), fires a Charged Move in its current
form, then changes form, and continues alternating for the rest of the
battle.
