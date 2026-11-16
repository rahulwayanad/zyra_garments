# .agents — project knowledge for every coding agent

```
.agents/
  docs/
    project-plan.md            plan, 4 build days, rollout, risks (mirror of the Claude Doc)
    architecture.md            15 modules, dependencies, Odoo touch-points, roles, backlog
    modules/                   one spec per module, written in the Spec step (template: _TEMPLATE.md)
    design/
      light-theme.md           Zyra light theme spec
      mockups/*.dc.html        design canvas sources (https://claude.ai/artifact/V5fPbqrDv1kJZf6gwNuCVt)
    reference/
      feature-reference.md     reference app features, our words, MVP/LATER
      screenshots-index.md     screenshot → caption index
      screenshots/             p<page>-<n>.jpg
      reference-app-store-page.pdf
  skills/
    odoo18-module-dev/         build loop, Odoo 18 rules, tests, daily gate
    garment-domain/            glossary, formulas, hard business rules
    zyra-light-theme/          theme usage in Odoo + tokens.scss
    reference-app/             clean-room use of the reference app
```

Entry point: `/CLAUDE.md` (also `/AGENTS.md`). Claude Code finds the skills through `/.claude/skills` → `.agents/skills`.
