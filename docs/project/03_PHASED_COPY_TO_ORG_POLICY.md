# Gangoos-coder — polityka pracy fazami i kopiowania do org repo

## Cel pliku
Ten dokument definiuje, **jak przepisać repo do nowej organizacji bez utraty jakości**. Kopiowanie do org nie jest etapem „naprawimy później”, tylko skutkiem osiągnięcia jakości.

---

## Zasada główna
Nowe org repo powstaje dopiero wtedy, gdy mamy:
- ustalony baseline,
- zamknięte najcięższe blokery,
- zielone required checks,
- powtarzalne testy,
- jasną odpowiedzialność za kolejne fazy.

Nie kopiujemy chaosu. Kopiujemy stan kontrolowany.

---

## Model pracy
- praca fazami,
- jeden PR na jedną fazę lub podfazę,
- minimum 6 testów na PR,
- po każdym PR: review, green checks, merge,
- dopiero potem następna faza.

---

## Faza 0 — Audit freeze
### Cel
Zamrozić stan wejściowy i spisać prawdę o repo.

### Output
- dokument blockerów,
- dokument zasad inżynieryjnych,
- dokument polityki faz,
- lista ownerów dla krytycznych ścieżek.

### Gate
- brak przepisywania do org,
- brak tagów release,
- brak marketingowego ogłaszania repo jako ukończonego.

---

## Faza 1 — CI i packaging baseline
### Cel
Doprowadzić repo do stanu, w którym CI jest wiarygodnym gate’em.

### Zakres
- naprawa Python test discovery / import paths,
- uzupełnienie brakujących dependency,
- naprawa Rust check / clippy / test baseline,
- stabilizacja workflow.

### Obowiązkowe testy
1. Python import/boot,
2. Python config contract,
3. Python server build,
4. Rust compile gate,
5. Rust selected tests gate,
6. regression test dla obecnego CI failure.

### Exit criteria
- wszystkie joby w `.github/workflows/ci.yml` są zielone,
- brak ręcznych hacków lokalnych wymaganych do CI,
- repo ma pierwszy stabilny baseline.

---

## Faza 2 — Contract repair
### Cel
Domknąć wszystkie publiczne kontrakty runtime.

### Zakres
- `CodeAct -> NEXUS` endpoint alignment,
- decyzja: REST czy MCP transport dla `run_mojo`,
- realna implementacja `mojo_exec` albo usunięcie feature z interfejsu,
- ujednolicenie request/response schema.

### Obowiązkowe testy
1. tool registration test,
2. success contract test,
3. 404/not-found contract test,
4. invalid payload test,
5. timeout/error propagation test,
6. regression test dla mismatch endpointu.

### Exit criteria
- `run_mojo` nie jest już pół-stubem,
- kontrakt jest jeden i spójny w kodzie, docs i testach.

---

## Faza 3 — 2-VM Qwen runtime
### Cel
Zamienić placeholder zdalnego Qwena w wspierany runtime.

### Zakres
- jawny remote Ollama contract,
- healthcheck przed inference,
- retry/backoff,
- fallback policy,
- smoke test `VM1 -> VM2`.

### Obowiązkowe testy
1. env parsing dla `OLLAMA_HOST`,
2. healthcheck success,
3. healthcheck failure,
4. timeout path,
5. fallback path,
6. integration smoke test na zewnętrznym hoście testowym lub kontrolowanym mocku.

### Exit criteria
- repo wspiera Twoją topologię dwóch VM nie tylko w README, ale w runtime.

---

## Faza 4 — Security i config scrub
### Cel
Wyczyścić repo z driftu środowiskowego i ustabilizować konfigurację.

### Zakres
- neutralne `.env.example`,
- jedna nazwa env dla jednej funkcji,
- usunięcie publicznych IP/hostów,
- dopięcie secret scanning rules,
- sanity check docs.

### Obowiązkowe testy/checki
1. `.env.example` lint,
2. brak publicznych IP grep check,
3. config consistency test,
4. README env table consistency check,
5. compose/env consistency check,
6. regression test dla poprzedniego hardcoded hosta.

### Exit criteria
- repo jest gotowe do publicznego org mirror bez wstydu i bez śladów prywatnego środowiska.

---

## Faza 5 — Release gates i smoke tests
### Cel
Przygotować repo na pierwszy prawdziwy release candidate.

### Zakres
- smoke test compose,
- health endpoint gate,
- branch protection rules,
- required checks,
- release checklist,
- wersjonowanie `v1.0.0-rc1`.

### Obowiązkowe testy/checki
1. compose config,
2. compose up smoke,
3. `/health` check,
4. główna ścieżka agentowa smoke,
5. CI required checks verification,
6. regression test dla dowolnej awarii z faz 1-4.

### Exit criteria
- repo jest `release-candidate ready`.

---

## Faza 6 — Copy to org
### Cel
Przenieść ustabilizowane repo do organizacji bez przenoszenia długu jako baseline.

### Zasady
- copy/mirror dopiero po zamknięciu faz 0-5,
- branch protection włączone od razu,
- `main` chroniony,
- wymagane checki ustawione przed pierwszym merge w org,
- tag dopiero po pierwszym green build w org.

### Wymagane działania
1. mirror/copy repo,
2. ustawić secrets i variables w org,
3. włączyć required checks,
4. odpalić pełne CI,
5. zrobić `v1.0.0-rc1`,
6. dopiero po potwierdzeniu — `v1.0.0`.

---

## Faza 7 — Post-v1 roadmap (nie blokuje v1)
To jest miejsce na rzeczy ważne, ale **nie będące blockerami pierwszego release’u**:
- dataset Mojo dla future CodeAct agenta,
- fine-tune Qwen pod własny benchmark,
- rozszerzona orkiestracja modeli,
- większa liczba usług pobocznych,
- kolejne interfejsy UI/CLI.

Te rzeczy mają trafić do roadmapy po ustabilizowaniu rdzenia.

---

## Reguła przejścia między fazami
Nie ma skoku do kolejnej fazy, jeśli poprzednia nie spełniła wszystkich warunków:
- code complete,
- docs updated,
- tests green,
- review closed,
- brak czerwonych blockerów z poprzedniej fazy.

---

## Definicja sukcesu
Sukces to nie „dużo plików” ani „Claude powiedział, że gotowe”.

Sukces to stan, w którym:
- repo buduje się powtarzalnie,
- główne kontrakty są prawdziwe,
- testy są zielone,
- nowa organizacja dostaje czysty baseline,
- `v1.0.0` znaczy coś realnego.
