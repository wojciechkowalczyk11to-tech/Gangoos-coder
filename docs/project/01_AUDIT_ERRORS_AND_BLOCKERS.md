# Gangoos-coder — audit błędów i blockerów

## Cel pliku
Ten dokument jest **źródłem prawdy dla obecnych blockerów** przed przepisywaniem repo do nowej organizacji i przed jakimkolwiek tagiem `v1.0.0`.

Zakres: stan repo po scaleniu `gangoos + mcp-server + Qwen placeholder + CodeAct/Mojo`.

## Zasada nadrzędna
Dopóki choć jeden blocker z sekcji **Critical** jest otwarty, repo **nie jest ukończone**, **nie jest release-ready** i **nie może być kopiowane do org jako finalne źródło prawdy**.

---

## Status ogólny
- Architektura repo jest obiecująca.
- Monorepo ma realne komponenty, nie jest pustym szkieletem.
- Jednak obecny stan to **integracja częściowo domknięta**, a nie skończony produkt.

---

## Critical blockers

### C1. CI nie jest green end-to-end
**Objaw:** workflow CI nie może być traktowany jako release gate, dopóki wszystkie joby nie przechodzą bez warunków specjalnych.

**Dowody do sprawdzenia w repo:**
- `.github/workflows/ci.yml`
- `mcp-server/tests/*`
- workspace Rust `crates/*`

**Ryzyko:**
- fałszywe poczucie „repo gotowe”,
- brak wiarygodnej bazy pod PR-per-phase,
- migracja do org z czerwonym baseline.

**Wyjście z blokera:**
1. każdy job w CI ma przejść na czystym runnerze,
2. bez ręcznego ustawiania `PYTHONPATH` poza workflow,
3. bez pomijania testów krytycznych,
4. bez `allow-failure`.

**Status docelowy:** `CI = required check`.

---

### C2. Python test path / packaging dla `mcp-server` jest niespójny
**Objaw:** testy w `mcp-server/tests` importują moduły jako:
- `from config import Settings`
- `from server import build_combined_app, mcp`

przy odpalaniu z root repo przez `pytest mcp-server/tests`.

**Problem:** ten układ jest wrażliwy na katalog roboczy i packaging; obecna struktura nie gwarantuje stabilnej kolekcji testów w CI.

**Dodatkowe ryzyko:** `mcp-server/server.py` importuje `dotenv`, a `python-dotenv` nie jest wpisany explicite do `mcp-server/requirements.txt`.

**Wyjście z blokera — do wyboru jedna ścieżka i trzymanie się jej konsekwentnie:**
- **Opcja A (zalecana):** zrobić z `mcp-server` poprawny package Python i testować po package importach,
- **Opcja B:** w workflow uruchamiać testy z `working-directory: mcp-server` i dopasować importy/test discovery,
- **Opcja C:** dodać jawny bootstrap test runnera, ale tylko jeśli A/B są niemożliwe.

**Definicja done:**
- `pytest` działa lokalnie i w CI z jednego, opisanego entrypointu,
- testy nie zależą od przypadkowego katalogu uruchomienia,
- `requirements.txt` zawiera wszystkie rzeczywiście wymagane importy.

---

### C3. Kontrakt `CodeAct -> NEXUS -> mojo_exec` nie jest domknięty
**Objaw:** część Rust `codeact` woła `POST {NEXUS_URL}/tools/call`, natomiast REST gateway po stronie MCP wystawia narzędzia jako `POST /api/v1/tools/{tool_name}`.

**Dodatkowo:** w `mcp-server` brak jawnej rejestracji narzędzia `mojo_exec`, mimo że `CodeAct` opisuje `run_mojo -> NEXUS mojo_exec` jako gotowy przepływ.

**Ryzyko:**
- główna funkcja repo jest deklarowana, ale nie działa E2E,
- agent może raportować gotowość bez działającego wykonania Mojo,
- wysokie ryzyko runtime failure po deployu.

**Wyjście z blokera:**
1. wybrać **jeden** prawidłowy kontrakt transportowy,
2. dopisać realny backend `mojo_exec` albo jawnie wycofać feature,
3. dodać testy kontraktu na request/response,
4. dodać test regresji: `run_mojo` zwraca poprawny błąd, gdy backend nie istnieje,
5. dodać smoke test sukcesu dla prawdziwej ścieżki.

**Definicja done:** `run_mojo` działa albo jest usunięty z publicznego interfejsu. Nie może zostać w stanie pół-stuba.

---

### C4. Placeholder Qwena istnieje jako infra, ale nie jako pełny flow 2-VM
**Objaw:** repo ma `OLLAMA_HOST`, `llm/setup.sh`, `docker-compose --profile llm`, ale nie ma twardo zamkniętego przepływu dla Twojej topologii:
- VM1: `gangus-agent + mcp-server`
- VM2: `Ollama + qwen3:8b`

**Braki funkcjonalne:**
- brak obowiązkowego healthcheck VM2,
- brak retry/backoff policy opisanego i przetestowanego,
- brak timeout matrix,
- brak testu fallback,
- brak smoke testu `VM1 -> VM2 -> odpowiedź modelu`.

**Wyjście z blokera:**
1. jawna specyfikacja remote Ollama contract,
2. health endpoint check przed użyciem modelu,
3. retry policy z loggingiem,
4. fallback policy (np. Groq/xAI) z testem,
5. docker/dev oraz remote VM mają ten sam kontrakt env.

**Definicja done:** zewnętrzny Qwen nie jest tylko placeholderem, ale wspieraną ścieżką runtime.

---

### C5. Repo nadal zawiera publiczny drift konfiguracyjny i ślady środowiska
**Objaw:** `.env.example` zawiera konkretny host `OLLAMA_HOST=http://164.90.217.149:11434` zamiast neutralnego przykładu.

**Dodatkowy drift:**
- `server.py` używa `MCP_ALLOWED_HOSTS`,
- `config.py` definiuje `ALLOWED_SSH_HOSTS`.

To znaczy, że konfiguracja nie jest w pełni zunifikowana.

**Ryzyko:**
- wyciek architektury środowiska,
- trudny onboarding,
- konfiguracja „działa tylko u autora”,
- błędne przekonanie, że env jest już uporządkowane.

**Wyjście z blokera:**
1. `.env.example` ma być całkowicie neutralny,
2. jedna nazwa env na jedną odpowiedzialność,
3. README, compose i runtime czytają te same klucze,
4. żadnych publicznych IP ani prywatnych aliasów w przykładach.

---

### C6. Release governance nie istnieje jeszcze w formie twardych bramek
**Objaw:** repo ma dokumenty typu README/CHANGELOG/NOTICE/FUNDING, ale to nie jest jeszcze governance release’u.

**Brakuje:**
- reguły „zero merge na czerwonym CI”,
- wymaganych checks jako branch protection,
- definicji release candidate,
- checklisty `v1.0.0 gate` opartej o testy i smoke testy,
- polityki kopiowania do org.

**Wyjście z blokera:**
1. dodać dokument release gates,
2. włączyć branch protection,
3. wymusić squash merge albo rebase merge według jednej polityki,
4. tag `v1.0.0` tylko po pełnym Phase Gate.

---

## High-priority defects

### H1. W repo nadal są `TODO` i testy ignorowane
To łamie zasadę „zero placeholderów” dla krytycznych ścieżek i obniża wiarygodność stanu projektu.

**Minimalny wymóg:**
- brak `todo!()` w ścieżkach release-critical,
- brak `#[ignore = "TODO: ..."]` dla funkcji wymaganych do `v1.0.0`.

### H2. Brak obowiązkowego testu E2E dla głównej obietnicy repo
Główna obietnica repo to nie pojedyncze moduły, tylko ich współpraca. Bez jednego testu end-to-end łatwo mieć „zielone unit testy” i martwy produkt.

### H3. Mieszanie zakresów produktu bez jawnego ownership
Repo zawiera kilka obszarów (`mcp-server`, `goose`, `ui`, `services`, `mojo-battle-generator`, inne katalogi). Bez przypisania ownera/fazy te części będą gnily równolegle.

---

## Non-blocking, ale ważne
- README jest ambitne i marketingowo mocne; teraz musi zostać dociągnięte do prawdy runtime.
- `mojo-battle-generator` ma sens jako osobny przyszły tor prac, ale **nie może** blokować podstawowego `v1.0.0` repo.
- future dataset / fine-tune dla Qwena należy traktować jako osobny milestone po ustabilizowaniu kontraktów i testów bazowych.

---

## Phase 0 exit criteria
Ten dokument można oznaczyć jako „Phase 0 zamknięta” dopiero gdy:
1. wszystkie pozycje `C1-C6` mają przypisanego właściciela,
2. każda pozycja ma PR lub issue z acceptance criteria,
3. zdefiniowany jest zestaw 6 testów obowiązkowych na każdy PR,
4. repo nie jest przepisywane do org jako „final”, dopóki Phase 1-5 nie będą green.

---

## Zasada migracji
**Migracja do organizacji ma być skutkiem jakości, nie jej substytutem.**

Najpierw:
- stabilny baseline,
- green CI,
- domknięte kontrakty,
- smoke testy,
- release gates.

Dopiero potem:
- copy/mirror do org,
- branch protection,
- `v1.0.0-rc1`.
