# Preamble for every module agent (prepend to the kit prompt)

You are building ONE Odoo 18 Community module for the Zyra Garment ERP, unattended overnight. Rahul is asleep;
do not ask questions — decide, write the decision in the module README under "Decisions", and continue.

- Work ONLY in your worktree: `WT` (given below). Main repo: `/home/rahul/Personal/Garnaments` (read-only for you).
- Read `WT/CLAUDE.md` first, then the kit prompt below, then the READMEs of the modules you depend on.
- Odoo: `O=/home/rahul/Personal/Garnaments/odoo18` (source + venv, Python 3.12). Run Odoo from `WT`:
  ```bash
  cd WT; O=/home/rahul/Personal/Garnaments/odoo18; P=$(grep -Po '^db_password = \K.*' $O/odoo.conf)
  PGPASSWORD=$P dropdb -h localhost -U odoo --if-exists DB
  timeout 1500 $O/venv/bin/python $O/odoo-bin -c $O/odoo.conf --logfile= --without-demo= \
    --addons-path=$O/addons,$O/odoo/addons,$PWD/addons --db-filter='.*' -d DB \
    -i MODULE --test-tags=/MODULE --stop-after-init --log-level=test 2>&1 | tail -150
  ```
  Also pass `--http-port=PORT` (your own port, given below; 8089 is in use).
  Known harmless log line: `<string>:38: (ERROR/3) Unexpected indentation` / docutils WARNING from Odoo core
  `mail` — ignore it; set `description` in your manifest so your README isn't parsed as RST.
  Use ONLY your database `DB`. Never touch `garments` or any other database. Never put the DB password in a file.
  Scan the full log for `WARNING`, `ERROR`, `FAIL`; the module is done only with none of them from your module.
- Screens: `WT/docs/screens/sNNN.jpg` (+ `captions.json`). Open each screen named in your prompt with the Read tool
  and match its fields, columns, order, labels, states, KPI tiles and buttons. Demo data must make every screen
  look populated like the image (invented names only).
- Look: use `zyra_garment_theme` classes (`o_zyra_kpis`, `o_zyra_kpi o_zyra_kpi_good|_warn|_bad`, etc. — read
  `WT/addons/zyra_garment_theme/static/src/scss/theme.scss`).
- Clean-room: never copy anything from mn_garment. Domain rules/formulas: `WT/.agents/skills/garment-domain/SKILL.md`.
  Odoo 18 rules: `WT/.agents/skills/odoo18-module-dev/SKILL.md`.
- Need a change in another module? Write `WT/docs/requests/<that_module>.md`; never edit it.
- Soft dependencies (read a model only if installed): `if 'garment.x' in self.env:`.
- Commit often on your branch with clear messages; final commit message lists what's done. Commits end with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never merge, rebase main, push, or remove worktrees.
- Keep the job inside its scope; a good, tested, installed module beats a bigger broken one. If time runs long,
  finish the core models + tests + README first, then views/screens, then extras, and list what's left in the
  README under "Not done yet".
- Final reply (your report to the orchestrator, ≤ 25 lines): install result, tests passed/failed counts, screens
  covered, decisions, not-done items, any docs/requests written, last commit hash.
