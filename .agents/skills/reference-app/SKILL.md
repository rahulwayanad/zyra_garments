---
name: reference-app
description: How to use the reference garment ERP (mn_garment app-store page, PDF and screenshots) as a feature reference under clean-room rules — where the material is, how to find the screen for a feature, and what may and may not be taken from it. Use before speccing a module, when Rahul says "like the reference/partner app", or when looking at its screenshots.
---

# Using the reference app (clean-room)

Material in `.agents/docs/reference/`:

| File | What |
|---|---|
| `feature-reference.md` | Features per area, in our own words, tagged MVP / LATER. **Start here.** |
| `screenshots-index.md` | Every screenshot (`screenshots/p<page>-<n>.jpg`) with the captions from its page. |
| `screenshots/` | 128 screenshots from the English part of the page (PDF pages 2–76). |
| `reference-app-store-page.pdf` | The full original app-store page (155 pages; Arabic from p.77). |

Rahul calls it the partner app. The project plan still treats it as **OPL-1, feature reference only**. Until Rahul
confirms in writing that a partnership licence allows reuse, follow the clean-room rules below.

## Finding the screen for a feature

1. Look the feature up in `feature-reference.md` to get the area and rules.
2. `grep -n -i "<keyword>" .agents/docs/reference/screenshots-index.md` → page + image names.
3. Open the image with the Read tool to see the layout and fields.
4. Write what you learned into the module spec (`.agents/docs/modules/<module>.md`) **in your own words**, citing
   the page number, e.g. "Reference p.33: roll inspection tablet."
   Note: a caption can sit on the page after its image — check the neighbouring page too.

Key screens: sewing cockpit p3, production order p3, planning board p4, scan station p4, cockpits p12–20,
merchandising p20–29, materials p29–33, cutting p33–37, sewing floor p37–40, job work & quality p40–44,
packing & shipment p44–49, wages p50–51, compliance p52+ (LATER) (check the index — page boundaries are approximate).

## Allowed

- Learning **what** the factory needs: entities, fields, states, rules, which numbers a screen shows.
- Using the same domain vocabulary (it is industry vocabulary: bundle, lay, DHU, AQL…).
- Matching a workflow (badge → coupon scan) because the factory works that way.

## Not allowed

- Copying or retyping its code, XML ids, model names, labels, help text, sentences, demo names or data.
- Using its screenshots, icons or images in our modules, docs for clients, or marketing.
- Recreating its visual design — we use the Zyra light theme (skill `zyra-light-theme`).
- Claiming compatibility with it.

## Also in scope from the page

Its "does not do" list is ours too: no marker drawing, no licensed time system, no RFID/machine links, not a
payroll, no live customs/bank connections, no printer/RIP control.
