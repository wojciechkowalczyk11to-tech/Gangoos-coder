# Gangoos-coder — zasady inżynieryjne i bramki testowe

## Cel pliku
Ten dokument definiuje **twarde reguły pracy nad repo** po wejściu do projektu. Nie jest sugestią. Jest kontraktem jakości.

---

## 1. Zasady nadrzędne

### 1.1. Zero placeholderów
Zabronione w ścieżkach produkcyjnych i release-critical:
- `TODO`
- `FIXME`
- `placeholder`
- martwe stuby udające gotową funkcję
- interfejs bez backendu
- fałszywe „temporary pass” w testach

Jeżeli feature nie działa, musi być:
- **albo** poprawnie zaimplementowany,
- **albo** wyłączony z publicznego interfejsu,
- **albo** oznaczony jako `not shipped` poza ścieżką runtime.

---

### 1.2. Wszystkie I/O mają być defensywne
Każdy network/file/process/subprocess/database I/O musi mieć:
- timeout,
- obsługę błędów,
- logging,
- kontrolowany zwrot błędu,
- test porażki.

Brak tych elementów = PR nie przechodzi review.

---

### 1.3. Jeden kontrakt na jedną odpowiedzialność
Jeżeli endpoint, schema, env var albo tool contract istnieje w więcej niż jednym miejscu, muszą być identyczne.

Przykłady niedozwolone:
- `CodeAct` woła inny endpoint niż wystawia `REST gateway`,
- README opisuje inny env niż czyta runtime,
- compose używa innej nazwy niż config,
- testy przechodzą tylko dzięki lokalnemu katalogowi roboczemu.

---

### 1.4. Dokumentacja nie może wyprzedzać rzeczywistości
README, CHANGELOG i docs mogą opisywać tylko to, co jest:
- zaimplementowane,
- przetestowane,
- uruchamialne zgodnie z instrukcją.

Jeżeli feature jest częściowy, opis musi to jasno mówić.

---

### 1.5. Zero hardcoded infra details
Zabronione w repo publicznym i org repo:
- publiczne IP,
- prywatne hosty,
- lokalne ścieżki autora,
- sekretopodobne wartości,
- dane środowiskowe inne niż neutralne przykłady.

---

### 1.6. Każda zmiana ma mieć test regresji
Jeżeli PR naprawia błąd, musi dodać test, który złapałby ten błąd ponownie.

Bez testu regresji bugfix nie jest uznany za domknięty.

---

## 2. Zasady PR

### 2.1. Jeden PR = jedna odpowiedzialność
Każdy PR ma mieć pojedynczy cel główny, np.:
- packaging Python,
- kontrakt `run_mojo`,
- healthcheck remote Ollama,
- env unification,
- smoke test compose.

Nie łączymy w jednym PR:
- refaktoru,
- naprawy runtime,
- migracji docs,
- zmian release policy,

jeżeli nie są nierozdzielne.

---

### 2.2. Każdy PR musi zawierać
1. zakres,
2. listę zmienionych plików i po co zostały zmienione,
3. acceptance criteria,
4. listę uruchomionych testów,
5. wynik manual verification, jeśli dotyczy.

---

### 2.3. Merge policy
PR nie może zostać scalony, jeśli:
- jakikolwiek required check jest czerwony,
- są nierozwiązane review comments blokujące,
- nie ma 6 testów dla fazy,
- dokumentacja została zmieniona, ale runtime nie,
- runtime został zmieniony, ale dokumentacja nie.

---

## 3. Obowiązkowe 6 testów na każdy PR
Każdy PR fazowy ma dostarczyć minimum sześć testów lub checków. Dopuszczalne są testy automatyczne oraz jeden smoke test, jeśli jest deterministyczny i opisany.

### T1. Boot / import test
Potwierdza, że moduł startuje i importuje się poprawnie.

### T2. Config / env contract test
Sprawdza poprawne czytanie env, wartości domyślne i błąd przy złych danych.

### T3. Happy-path unit test
Sprawdza podstawowe działanie funkcji albo endpointu.

### T4. Failure-path unit test
Sprawdza timeout, brak zależności, niepoprawny input albo brak toola.

### T5. Boundary / integration test
Sprawdza granicę między modułami: np. `Rust -> REST`, `server -> tool`, `agent -> Ollama`.

### T6. Regression test
Zabezpiecza dokładnie ten bug, który PR naprawia.

---

## 4. Required command gates
Poniższe komendy mają być utrzymywane jako obowiązkowe bramki projektu. Jeśli któraś nie działa stabilnie, należy to naprawić zamiast omijać.

## 4.1. Rust
```bash
cargo fmt --all -- --check
cargo clippy -p goose -p goose-cli -p goose-mcp -p goose-server -p goose-acp --no-default-features --features aws-providers,telemetry,otel,rustls-tls -- -D warnings
cargo test -p goose --no-default-features --features aws-providers,telemetry,otel,rustls-tls -- --nocapture
```

## 4.2. Python MCP server
```bash
python -m pip install -r mcp-server/requirements.txt
pytest mcp-server/tests -q
```

Jeżeli Python wymaga `working-directory`, to workflow i docs mają to jawnie pokazywać. Nie może to być ukryta wiedza autora.

## 4.3. Docker / compose smoke
```bash
docker compose config
```

Dla faz dotyczących runtime additionally:
```bash
docker compose up -d mcp-server gangus-agent
curl -fsS http://localhost:8080/health
```

Jeżeli dana faza dotyczy remote Ollama:
```bash
curl -fsS "$OLLAMA_HOST/api/tags"
```

---

## 5. Review checklist
Reviewer odrzuca PR, jeśli zobaczy którykolwiek z poniższych sygnałów:
- feature opisany jako gotowy, ale bez działającej ścieżki E2E,
- testy oparte wyłącznie na mockach przy braku smoke testu,
- nowy env var bez aktualizacji `.env.example` i README,
- endpoint zmieniony bez testu kontraktu,
- retry bez limitów,
- subprocess bez timeoutu,
- logowanie bez kontekstu błędu,
- `except Exception` bez sensownego komunikatu i bez testu,
- brak cleanup w testach,
- dodane publiczne IP lub host autora.

---

## 6. Definicja green PR
PR jest green tylko wtedy, gdy jednocześnie spełnia wszystkie warunki:
1. required checks zielone,
2. 6 testów istnieje i przechodzi,
3. docs zgadzają się z runtime,
4. brak nowych TODO/stubów,
5. reviewer może odtworzyć wynik z repo,
6. zmiana nie psuje poprzedniej fazy.

---

## 7. Definicja `v1.0.0-ready`
Repo może dostać `v1.0.0` dopiero gdy:
- wszystkie fazy 0-5 zamknięte,
- CI jest stale zielone,
- główna ścieżka produktu ma test E2E,
- brak blockerów `Critical`,
- org repo ma branch protection,
- release notes opisują wyłącznie realnie dowiezione funkcje.
