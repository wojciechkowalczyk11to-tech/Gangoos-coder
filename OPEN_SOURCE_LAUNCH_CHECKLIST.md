# Open Source Launch Checklist — gangus-coder

Plan: prywatne konto dev (obecne) + nowa organizacja GitHub (publiczna wizytowka).

---

## FAZA 1: Nowe konto GitHub (publiczna wizytowka)

### 1.1 Stworzenie konta organizacji

**Problem z Enterprise trial:** GitHub Enterprise trial blokuje tworzenie org bo zajmuje "slot". Rozwiazanie:

```
Opcja A (zalecana): Zakoncz/anuluj Enterprise trial PRZED tworzeniem org
  → Settings → Billing → Cancel trial
  → Potem: github.com/organizations/new (Free plan)

Opcja B: Stworz org z INNEGO konta (nowego osobistego)
  → Zaloz nowe konto osobiste (np. wojciech-kowalczyk-dev)
  → Z niego stworz org (np. gangus-labs lub wojciech-labs)
  → Dodaj obecne konto jako member/owner

Opcja C: Skontaktuj sie z GitHub Support
  → support.github.com → "I can't create an organization"
  → Wyjasnienie: trial blokuje slot, chcesz free org
```

### 1.2 Nazewnictwo

| Element | Przyklad | Zasada |
|---|---|---|
| Konto osobiste (dev) | wojciechkowalczyk11to-tech | Zostaje jak jest, prywatne repo, eksperymenty |
| Organizacja (public) | gangus-labs / gangus-dev | Czysta, profesjonalna, zero sekretow |
| Konto do CV/rekrutacji | wojciech-kowalczyk-dev | Opcjonalne — mozna uzyc org |

### 1.3 Koszty po trial

| Plan | Cena | Co daje | Rekomendacja |
|---|---|---|---|
| GitHub Free (osobiste) | $0 | Unlimited private/public repos, 500MB packages | Wystarczy do dev |
| GitHub Pro (osobiste) | $4/msc | Advanced code review, required reviewers, Pages | Warte jesli chcesz Pages |
| GitHub Free (org) | $0 | Unlimited public repos, 3 collaborators private | START TUTAJ |
| GitHub Team (org) | $4/user/msc | Branch protection, code owners, audit log | Dopiero jak beda ludzie |
| GitHub Copilot Individual | $10/msc | AI assistant | Opcjonalne — masz Claude Code |

**Rekomendacja:** GitHub Free (org) + GitHub Pro (osobiste) = $4/msc total. Copilot zbedny jesli masz Claude Code.

---

## FAZA 2: Przygotowanie repo do open source

### 2.1 Security audit PRZED upublicznieniem

```
[ ] git log --all --oneline | wc -l  — sprawdz ile commitow
[ ] git log --all -p | grep -iE "sk-ant|ghp_|AKIA|token.*=|password.*=" — ZERO WYNIKOW wymagane
[ ] Jesli cos znajdziesz: BFG Repo-Cleaner lub git filter-repo
    → pip install git-filter-repo
    → git filter-repo --replace-text secrets.txt
[ ] Sprawdz KAZDY plik rucznie lub agentem: .env, .json, .toml, .yml
[ ] Sprawdz GROK_REVIEW.md, NOWA_SESJA.md, TODO.md — nie moga byc w historii z sekretami
[ ] Zweryfikuj dwoma niezaleznymi agentami (Claude + GPT/Codex):
    → Agent 1: "Scan this repo for any secrets, tokens, API keys, passwords, IPs"
    → Agent 2: "Independent security review — find anything that shouldn't be public"
    → Oba musza dac ALL CLEAR
```

### 2.2 Czysty fork do organizacji

```bash
# NIE rób fork z prywatnego konta — stworz od zera
git clone --bare https://github.com/wojciechkowalczyk11to-tech/gangus-coder.git
cd gangus-coder.git

# Wyczyszcz sekrety z historii (jesli sa)
# pip install git-filter-repo
# git filter-repo --replace-text <(echo 'stary_token==>REDACTED')

# Push do nowej org
git push --mirror https://github.com/TWOJA-ORG/gangus-coder.git
```

### 2.3 Checklista plikow w repo

```
[ ] README.md — profesjonalny, badges, architektura, install, contributing
[ ] LICENSE — Apache 2.0 (juz jest)
[ ] CONTRIBUTING.md — jak kontrybuowac (juz jest z goose)
[ ] CODE_OF_CONDUCT.md — dodaj (GitHub template: Contributor Covenant)
[ ] SECURITY.md — jak reportowac luki (juz jest z goose)
[ ] CHANGELOG.md — historia zmian (stworzyc)
[ ] .github/ISSUE_TEMPLATE/ — bug report + feature request templates
[ ] .github/PULL_REQUEST_TEMPLATE.md — PR template
[ ] .github/FUNDING.yml — linki do sponsoringu
[ ] .gitignore — bez .env, credentials, internal files
[ ] .env.example — TYLKO nazwy zmiennych, ZERO wartosci
```

### 2.4 GitHub org settings

```
[ ] Profile picture — logo gangus-coder (moze Canva AI)
[ ] Bio — "First Mojo-native CodeAct agent framework"
[ ] Website — github pages lub link do docs
[ ] Pinned repos — gangus-coder jako pierwszy
[ ] Default branch protection — require PR reviews
[ ] Disable force push na main
[ ] Enable Dependabot
[ ] Enable secret scanning
[ ] Enable code scanning (CodeQL)
```

---

## FAZA 3: Monetyzacja i community

### 3.1 FUNDING.yml

Stworz `.github/FUNDING.yml`:
```yaml
github: TWOJA-ORG
ko_fi: twoj_kofi
buy_me_a_coffee: twoj_bmc
custom:
  - https://twoja-strona.pl/support
```

### 3.2 Sponsor button

GitHub automatycznie pokaze "Sponsor" button jesli FUNDING.yml istnieje.
Opcje:
- **GitHub Sponsors** — najlepsze, zero prowizji, direct from GitHub
- **Ko-fi** — prosty, bez subskrypcji wymaganych
- **Buy Me a Coffee** — popularny w dev community
- **Open Collective** — dla org, transparentne finanse

### 3.3 Komunikacja "dla sztuki"

W README dodaj sekcje:

```markdown
## About

gangus-coder is a passion project — built to push the boundaries of what
AI coding agents can do with compiled languages. This is open source because
knowledge should be shared. If you find it useful, consider supporting the
project.

Built solo by [Wojciech Kowalczyk](link-do-profilu).
```

### 3.4 Przyciaganie ludzi

```
[ ] Napisz post na Reddit: r/rust, r/programming, r/MachineLearning
    — "I built the first Mojo-native CodeAct agent framework"
[ ] Post na Hacker News (Show HN)
[ ] Post na X/Twitter z demo GIF
[ ] Dev.to / Hashnode blog post — architektura + motywacja
[ ] Discord server dla community (opcjonalnie)
[ ] Dodaj "good first issue" labels na GitHub Issues
```

### 3.5 Profil do rekrutacji / inwestorow

Na nowym koncie/org:
```
[ ] Pinned: gangus-coder (gwiazdka projektu)
[ ] Pinned: osobny repo z portfolio/CV (opcjonalnie)
[ ] README profilu: krotki opis, linki, stack technologiczny
[ ] Contributions graph — aktywny (commituj regularnie)
[ ] LinkedIn — link do GitHub org
[ ] CV/portfolio — link do org, nie do prywatnego konta
```

---

## FAZA 4: Zasada dwoch agentow (bezpieczenstwo)

Przed KAZDYM pushdem do publicznego repo:

```
1. Agent A (np. Claude): "Review this diff for secrets, quality, professionalism"
2. Agent B (np. GPT/Codex): "Independent review — same diff, same criteria"
3. OBAJ musza dac APPROVE
4. Dopiero wtedy: git push
```

Mozna to zautomatyzowac jako pre-push hook:
```bash
# .git/hooks/pre-push
#!/bin/bash
echo "STOP: Did two independent agents approve this push?"
echo "Type YES to confirm:"
read answer
if [ "$answer" != "YES" ]; then
  echo "Push cancelled."
  exit 1
fi
```

---

## FAZA 5: Pliki biznesowe i karierowe w repo

### 5.1 Licencja (juz jest Apache 2.0 — dobry wybor)

Apache 2.0 pozwala:
- Firmom uzywac komercyjnie (przyciaga adopcje)
- Wymaga attribution (Twoje imie zostaje)
- Chroni patenty (patent grant clause)
- NIE wymaga open-sourcowania derivatow (w przeciwienstwie do GPL)

Alternatywy do rozwazenia:
- **Dual licensing** — Apache 2.0 dla community + komercyjna licencja dla firm
  chcacych support/SLA. Przyklad: dodaj plik `LICENSE-COMMERCIAL.md`:
  ```
  For commercial licensing, enterprise support, or custom deployments,
  contact: wojciech@twoja-domena.pl
  ```
- **CLA (Contributor License Agreement)** — jesli chcesz moc zmienic licencje w przyszlosci,
  wymagaj CLA od kontrybutorów. GitHub ma CLA Assistant (bot).

### 5.2 Pliki pod kariere/biznes

```
[ ] SPONSORS.md — lista sponsorow/patronow (pusta na start, motywuje ludzi)
[ ] ROADMAP.md — publiczny plan rozwoju:
    - Q2 2026: local Mojo fallback (bez NEXUS), integration tests
    - Q3 2026: Qwen 9B fine-tuned model, TUI improvements
    - Q4 2026: plugin marketplace, multi-language CodeAct
[ ] ARCHITECTURE.md — glebszy opis architektury (dla rekruterow/inwestorow
    ktory pokazuje ze rozumiesz systemy)
[ ] .github/FUNDING.yml — sponsoring
[ ] NOTICE — wymagany przez Apache 2.0, lista attribution:
    ```
    gangus-coder
    Copyright 2026 Wojciech Kowalczyk

    This product includes software developed by Block, Inc. (goose).
    Original project: https://github.com/block/goose
    Licensed under Apache License 2.0.
    ```
```

### 5.3 GitHub Pages / dokumentacja

Repo ma juz `docs/` z Docusaurus. Mozesz:
```
[ ] Wlaczyc GitHub Pages (Settings → Pages → Deploy from branch: gh-pages)
[ ] Dodac custom domain (opcjonalnie)
[ ] Albo: deploy na Vercel/Cloudflare Pages (szybsze, free tier)
```

### 5.4 Metryki i social proof

```
[ ] Shields.io badges w README:
    - Stars, forks, issues, last commit
    - License badge (juz jest)
    - "Built with Rust" badge
    - "Mojo powered" badge
[ ] GitHub Discussions — wlacz (Settings → Features → Discussions)
    — pokazuje ze jest community
[ ] GitHub Projects — board z taskami (widoczny publicznie)
[ ] Releases — taguj wersje (v1.0.0, v1.1.0)
    — generuje automatyczne release notes
    — mozna dodac binaries do pobrania
```

### 5.5 Pod rekrutacje / kontrakt / inwestorow

W profilu org lub README:
```markdown
## Hire / Collaborate

I'm available for:
- Contract work (AI agents, Rust, systems programming)
- Technical consulting (LLM integration, CodeAct architectures)
- Full-time roles (AI/ML engineering, backend systems)

Contact: wojciech@twoja-domena.pl | [LinkedIn](link)
```

W CV/portfolio pisz:
- "Architect and sole developer of gangus-coder — first Mojo-native CodeAct agent"
- "Managed full-stack: Rust core, MCP protocol, CI/CD, dataset curation (1162 examples)"
- Link do org, nie do prywatnego konta

---

## KOLEJNOSC KROKOW

1. Anuluj Enterprise trial (Settings → Billing)
2. Stworz org (github.com/organizations/new, Free plan)
3. Dokonczenie repo (Codex: CODEX_HANDOFF.md)
4. Security scan (2x agent)
5. git filter-repo jesli trzeba
6. Push --mirror do org
7. Wlacz branch protection, secret scanning, CodeQL
8. Dodaj FUNDING.yml, CODE_OF_CONDUCT.md, issue templates
9. Napisz CHANGELOG.md
10. Post na Reddit/HN/X
11. Linkuj z CV/LinkedIn
