"""
Generator zadań Mojo — rosnące trudności, samodoskonalenie.
"""
import random

# Kategorie zadań od łatwych do trudnych
TASK_CATEGORIES = [
    # POZIOM 1 — podstawy
    {
        'level': 1,
        'category': 'basics',
        'tasks': [
            "Write a Mojo function that computes fibonacci(n) iteratively using SIMD-friendly loops.",
            "Implement a Mojo function to reverse a String in-place.",
            "Write Mojo code that sums a list of integers and measures time vs Python equivalent.",
            "Implement bubble sort in Mojo with explicit type annotations.",
            "Write a Mojo struct `Point` with x, y Float64 fields and a distance() method.",
        ]
    },
    # POZIOM 2 — wydajność
    {
        'level': 2,
        'category': 'performance',
        'tasks': [
            "Use Mojo SIMD to vectorize addition of two Float32 arrays of size 1024.",
            "Implement a Mojo matmul using tiling for cache efficiency. Compare with naive approach.",
            "Write a Mojo function using `parallelize` to compute dot product on multiple cores.",
            "Use `UnsafePointer` in Mojo to implement a zero-copy string slice view.",
            "Implement a memory pool allocator in Mojo using `UnsafePointer[UInt8]`.",
        ]
    },
    # POZIOM 3 — zaawansowane
    {
        'level': 3,
        'category': 'advanced',
        'tasks': [
            "Implement a lock-free ring buffer in Mojo using atomic operations.",
            "Write a Mojo generic `Stack[T]` struct with push/pop and capacity doubling.",
            "Build a Mojo tensor operation: 2D convolution with stride and padding support.",
            "Implement Mojo trait `Hashable` for a custom struct and use it in a HashMap.",
            "Write a Mojo async generator that streams tokens from a byte buffer.",
        ]
    },
    # POZIOM 4 — systemy
    {
        'level': 4,
        'category': 'systems',
        'tasks': [
            "Implement a Mojo HTTP parser that reads raw bytes and extracts headers without allocation.",
            "Write a Mojo SIMD-accelerated UTF-8 validator.",
            "Build a Mojo arena allocator with O(1) alloc and batch-free.",
            "Implement a Mojo B-tree node with split/merge operations.",
            "Write Mojo bindings to call a C function via `external_call`.",
        ]
    },
]


def get_task(level: int = None, error_context: str = None) -> dict:
    """
    Zwraca zadanie. Jeśli error_context podany — generuje trudniejszą wariację.
    """
    if level is None:
        level = 1

    level = min(level, 4)
    cat = TASK_CATEGORIES[level - 1]
    task_text = random.choice(cat['tasks'])

    if error_context:
        # Trudniejsza wariacja na podstawie poprzedniego błędu
        task_text = _make_harder(task_text, error_context)

    return {
        'level': level,
        'category': cat['category'],
        'task': task_text
    }


def _make_harder(base_task: str, error_context: str) -> str:
    """Dołącza kontekst błędu jako dodatkowe wymaganie."""
    harder_suffix = (
        f"\n\nADDITIONAL CONSTRAINT based on previous failure:\n"
        f"The previous attempt failed with: {error_context[:200]}\n"
        "Fix this specific issue AND add error handling for it."
    )
    return base_task + harder_suffix


def get_self_improvement_prompt(history: list[dict]) -> str:
    """
    Na podstawie historii błędów generuje meta-prompt do samodoskonalenia.
    """
    errors = [h for h in history if not h.get('success')]
    if not errors:
        return ""

    error_summary = "\n".join(
        f"- Task level {e['level']}: {e.get('error', 'unknown error')[:100]}"
        for e in errors[-5:]
    )

    return (
        "You have been failing on these types of Mojo tasks:\n"
        f"{error_summary}\n\n"
        "Analyze the pattern of failures. What Mojo concepts are you missing? "
        "What should the next task focus on to address these weaknesses?"
    )
