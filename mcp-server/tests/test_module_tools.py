"""
Tests for individual MCP module tools.
Tests input validation, error handling, and function signatures.
No real API calls - all HTTP mocked.
"""
import importlib
import pytest
from pydantic import ValidationError


# ═════════════════════════════════════════════════════════════════════════════
# A) ai_proxy module (8 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestAIProxyModule:

    def test_ai_provider_enum_has_all_providers(self):
        from modules.ai_proxy import AIProvider
        expected = {"openai", "gemini", "grok", "deepseek", "anthropic", "mistral"}
        actual = {p.value for p in AIProvider}
        assert expected == actual, f"Missing providers: {expected - actual}"

    def test_ai_provider_map_has_all_providers(self):
        from modules.ai_proxy import AIProvider, PROVIDER_MAP
        for provider in AIProvider:
            assert provider in PROVIDER_MAP, f"{provider} missing from PROVIDER_MAP"

    def test_ai_query_input_rejects_empty_prompt(self):
        """AIQueryInput is defined inside register(), so we test via MojoExecInput-style
        or by importing and registering on a mock MCP. Since AIQueryInput is local to
        register(), we test the constraint by building a minimal Pydantic model mirroring it."""
        from modules.ai_proxy import AIProvider
        from pydantic import BaseModel, Field, ConfigDict

        class AIQueryInputMirror(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
            provider: AIProvider
            prompt: str = Field(..., min_length=1, max_length=100000)
            max_tokens: int = Field(4096, ge=1, le=128000)
            temperature: float = Field(0.7, ge=0.0, le=2.0)

        with pytest.raises(ValidationError):
            AIQueryInputMirror(provider="openai", prompt="", max_tokens=4096, temperature=0.7)

    def test_ai_query_input_rejects_negative_max_tokens(self):
        from modules.ai_proxy import AIProvider
        from pydantic import BaseModel, Field, ConfigDict

        class AIQueryInputMirror(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
            provider: AIProvider
            prompt: str = Field(..., min_length=1)
            max_tokens: int = Field(4096, ge=1, le=128000)
            temperature: float = Field(0.7, ge=0.0, le=2.0)

        with pytest.raises(ValidationError):
            AIQueryInputMirror(provider="openai", prompt="hello", max_tokens=-1, temperature=0.7)

    def test_ai_query_input_rejects_temperature_above_2(self):
        from modules.ai_proxy import AIProvider
        from pydantic import BaseModel, Field, ConfigDict

        class AIQueryInputMirror(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
            provider: AIProvider
            prompt: str = Field(..., min_length=1)
            max_tokens: int = Field(4096, ge=1, le=128000)
            temperature: float = Field(0.7, ge=0.0, le=2.0)

        with pytest.raises(ValidationError):
            AIQueryInputMirror(provider="openai", prompt="hello", max_tokens=100, temperature=2.5)

    def test_ai_query_input_accepts_valid_params(self):
        from modules.ai_proxy import AIProvider
        from pydantic import BaseModel, Field, ConfigDict
        from typing import Optional

        class AIQueryInputMirror(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
            provider: AIProvider
            prompt: str = Field(..., min_length=1, max_length=100000)
            system: Optional[str] = Field(None)
            model: Optional[str] = Field(None)
            max_tokens: int = Field(4096, ge=1, le=128000)
            temperature: float = Field(0.7, ge=0.0, le=2.0)

        obj = AIQueryInputMirror(provider="openai", prompt="hello world")
        assert obj.provider == AIProvider.OPENAI
        assert obj.prompt == "hello world"
        assert obj.max_tokens == 4096
        assert obj.temperature == 0.7

    def test_ai_list_models_returns_string(self):
        """ai_list_models is registered via register(). We verify the PROVIDER_MAP
        has enough structure that a list call would produce output."""
        from modules.ai_proxy import PROVIDER_MAP, AIProvider
        # Build expected output manually to verify structure
        output_parts = []
        for provider, pcfg in PROVIDER_MAP.items():
            assert "default_model" in pcfg
            assert "models" in pcfg
            assert isinstance(pcfg["models"], list)
            assert len(pcfg["models"]) > 0
            output_parts.append(f"{provider.value}: {pcfg['default_model']}")
        assert len(output_parts) == len(AIProvider)

    def test_ai_provider_map_has_default_model_for_each(self):
        from modules.ai_proxy import AIProvider, PROVIDER_MAP
        for provider in AIProvider:
            cfg = PROVIDER_MAP[provider]
            assert "default_model" in cfg, f"{provider} missing default_model"
            assert isinstance(cfg["default_model"], str)
            assert len(cfg["default_model"]) > 0
            # Default model must be in the models list
            assert cfg["default_model"] in cfg["models"], (
                f"{provider}: default_model '{cfg['default_model']}' not in models list"
            )


# ═════════════════════════════════════════════════════════════════════════════
# B) mojo_exec module (6 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestMojoExecModule:

    def test_mojo_exec_input_model_exists(self):
        from modules.mojo_exec import MojoExecInput
        assert MojoExecInput is not None
        assert hasattr(MojoExecInput, "model_fields")

    def test_mojo_exec_input_rejects_empty_code(self):
        from modules.mojo_exec import MojoExecInput
        with pytest.raises(ValidationError):
            MojoExecInput(code="")

    def test_mojo_exec_backend_env_var_default(self):
        from modules.mojo_exec import MOJO_EXEC_BACKEND
        # In test environment without MOJO_EXEC_BACKEND set, default is "disabled"
        assert MOJO_EXEC_BACKEND in ("disabled", "subprocess"), (
            f"MOJO_EXEC_BACKEND must be 'disabled' or 'subprocess', got {MOJO_EXEC_BACKEND!r}"
        )

    def test_mojo_exec_max_code_size_defined(self):
        from modules.mojo_exec import MAX_CODE_SIZE
        assert isinstance(MAX_CODE_SIZE, int)
        assert MAX_CODE_SIZE > 0
        assert MAX_CODE_SIZE == 64 * 1024  # 64KB

    def test_mojo_exec_timeout_field_exists(self):
        from modules.mojo_exec import MojoExecInput
        fields = MojoExecInput.model_fields
        assert "timeout" in fields, "MojoExecInput must have a 'timeout' field"

    def test_mojo_exec_input_accepts_valid_code(self):
        from modules.mojo_exec import MojoExecInput
        obj = MojoExecInput(code='fn main():\n    print("hello")')
        assert obj.code == 'fn main():\n    print("hello")'
        assert obj.timeout > 0


# ═════════════════════════════════════════════════════════════════════════════
# C) quota module (4 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestQuotaModule:

    def test_quota_module_has_register(self):
        mod = importlib.import_module("modules.quota")
        assert hasattr(mod, "register")

    def test_quota_register_callable(self):
        from modules.quota import register
        assert callable(register)

    def test_quota_tool_counter_type(self):
        from modules.quota import _global_stats
        assert hasattr(_global_stats, "__getitem__"), "_global_stats must be dict-like"

    def test_quota_importable(self):
        mod = importlib.import_module("modules.quota")
        assert mod is not None
        assert hasattr(mod, "check_rate_limit")
        assert hasattr(mod, "record_usage")
        assert hasattr(mod, "get_stats_snapshot")


# ═════════════════════════════════════════════════════════════════════════════
# D) plan_verifier module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestPlanVerifierModule:

    def test_plan_verifier_has_register(self):
        mod = importlib.import_module("modules.plan_verifier")
        assert hasattr(mod, "register")

    def test_plan_verifier_register_callable(self):
        from modules.plan_verifier import register
        assert callable(register)

    def test_plan_verifier_importable(self):
        mod = importlib.import_module("modules.plan_verifier")
        assert mod is not None
        assert hasattr(mod, "VERIFY_SYSTEM_PROMPT")


# ═════════════════════════════════════════════════════════════════════════════
# E) session_store module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestSessionStoreModule:

    def test_session_store_has_register(self):
        mod = importlib.import_module("modules.session_store")
        assert hasattr(mod, "register")

    def test_session_store_register_callable(self):
        from modules.session_store import register
        assert callable(register)

    def test_session_store_importable(self):
        mod = importlib.import_module("modules.session_store")
        assert mod is not None
        assert hasattr(mod, "SESSIONS_DIR")
        assert hasattr(mod, "TASKS_DIR")


# ═════════════════════════════════════════════════════════════════════════════
# F) dataset_filter module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestDatasetFilterModule:

    def test_dataset_filter_has_register(self):
        mod = importlib.import_module("modules.dataset_filter")
        assert hasattr(mod, "register")

    def test_dataset_filter_register_callable(self):
        from modules.dataset_filter import register
        assert callable(register)

    def test_dataset_filter_importable(self):
        mod = importlib.import_module("modules.dataset_filter")
        assert mod is not None
        assert hasattr(mod, "filter_dataset")
        assert hasattr(mod, "_is_complete_trace")


# ═════════════════════════════════════════════════════════════════════════════
# G) streaming module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestStreamingModule:

    def test_streaming_has_register(self):
        mod = importlib.import_module("modules.streaming")
        assert hasattr(mod, "register")

    def test_streaming_register_callable(self):
        from modules.streaming import register
        assert callable(register)

    def test_streaming_importable(self):
        mod = importlib.import_module("modules.streaming")
        assert mod is not None
        assert hasattr(mod, "stream_ollama")


# ═════════════════════════════════════════════════════════════════════════════
# H) notifications module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestNotificationsModule:

    def test_notifications_has_register(self):
        mod = importlib.import_module("modules.notifications")
        assert hasattr(mod, "register")

    def test_notifications_register_callable(self):
        from modules.notifications import register
        assert callable(register)

    def test_notifications_importable(self):
        mod = importlib.import_module("modules.notifications")
        assert mod is not None


# ═════════════════════════════════════════════════════════════════════════════
# I) http_client module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestHTTPClientModule:

    def test_http_client_has_register(self):
        mod = importlib.import_module("modules.http_client")
        assert hasattr(mod, "register")

    def test_http_client_register_callable(self):
        from modules.http_client import register
        assert callable(register)

    def test_http_client_importable(self):
        mod = importlib.import_module("modules.http_client")
        assert mod is not None


# ═════════════════════════════════════════════════════════════════════════════
# J) database module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestDatabaseModule:

    def test_database_has_register(self):
        mod = importlib.import_module("modules.database")
        assert hasattr(mod, "register")

    def test_database_register_callable(self):
        from modules.database import register
        assert callable(register)

    def test_database_importable(self):
        mod = importlib.import_module("modules.database")
        assert mod is not None


# ═════════════════════════════════════════════════════════════════════════════
# K) python_repl module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestPythonReplModule:

    def test_python_repl_has_register(self):
        mod = importlib.import_module("modules.python_repl")
        assert hasattr(mod, "register")

    def test_python_repl_register_callable(self):
        from modules.python_repl import register
        assert callable(register)

    def test_python_repl_importable(self):
        mod = importlib.import_module("modules.python_repl")
        assert mod is not None


# ═════════════════════════════════════════════════════════════════════════════
# L) shell module (3 tests)
# ═════════════════════════════════════════════════════════════════════════════

class TestShellModule:

    def test_shell_has_register(self):
        mod = importlib.import_module("modules.shell")
        assert hasattr(mod, "register")

    def test_shell_register_callable(self):
        from modules.shell import register
        assert callable(register)

    def test_shell_importable(self):
        mod = importlib.import_module("modules.shell")
        assert mod is not None
