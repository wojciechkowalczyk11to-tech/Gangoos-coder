//! Comprehensive unit tests for the goose crate's public API.
//! All tests are self-contained — no network calls, no API keys, no env vars.

mod model_config_tests {
    use goose::model::{ModelConfig, DEFAULT_CONTEXT_LIMIT};
    use std::collections::HashMap;

    #[test]
    fn default_has_empty_model_name() {
        let config = ModelConfig::default();
        assert_eq!(config.model_name, "");
    }

    #[test]
    fn default_context_limit_field_is_none() {
        let config = ModelConfig::default();
        assert!(config.context_limit.is_none());
    }

    #[test]
    fn context_limit_method_returns_default_when_none() {
        let config = ModelConfig::default();
        assert_eq!(config.context_limit(), DEFAULT_CONTEXT_LIMIT);
    }

    #[test]
    fn context_limit_method_returns_custom_when_set() {
        let config = ModelConfig {
            context_limit: Some(8192),
            ..Default::default()
        };
        assert_eq!(config.context_limit(), 8192);
    }

    #[test]
    fn with_context_limit_sets_value() {
        let config = ModelConfig::default().with_context_limit(Some(16384));
        assert_eq!(config.context_limit, Some(16384));
    }

    #[test]
    fn with_context_limit_none_does_not_override() {
        let config = ModelConfig {
            context_limit: Some(8192),
            ..Default::default()
        }
        .with_context_limit(None);
        assert_eq!(config.context_limit, Some(8192));
    }

    #[test]
    fn with_temperature_sets_and_clears() {
        let config = ModelConfig::default().with_temperature(Some(0.7));
        assert_eq!(config.temperature, Some(0.7));

        let config = config.with_temperature(None);
        assert_eq!(config.temperature, None);
    }

    #[test]
    fn with_max_tokens_sets_value() {
        let config = ModelConfig::default().with_max_tokens(Some(4096));
        assert_eq!(config.max_tokens, Some(4096));
    }

    #[test]
    fn max_output_tokens_returns_custom_when_set() {
        let config = ModelConfig {
            max_tokens: Some(8192),
            ..Default::default()
        };
        assert_eq!(config.max_output_tokens(), 8192);
    }

    #[test]
    fn max_output_tokens_returns_4096_when_none() {
        let config = ModelConfig::default();
        assert_eq!(config.max_output_tokens(), 4096);
    }

    #[test]
    fn with_toolshim_enables() {
        let config = ModelConfig::default().with_toolshim(true);
        assert!(config.toolshim);
    }

    #[test]
    fn with_toolshim_model_sets_model_name() {
        let config = ModelConfig::default()
            .with_toolshim_model(Some("llama-3".to_string()));
        assert_eq!(config.toolshim_model, Some("llama-3".to_string()));
    }

    #[test]
    fn is_openai_reasoning_model_detects_o1() {
        let config = ModelConfig {
            model_name: "o1-preview".to_string(),
            ..Default::default()
        };
        assert!(config.is_openai_reasoning_model());
    }

    #[test]
    fn is_openai_reasoning_model_detects_o3() {
        let config = ModelConfig {
            model_name: "o3-mini".to_string(),
            ..Default::default()
        };
        assert!(config.is_openai_reasoning_model());
    }

    #[test]
    fn is_openai_reasoning_model_detects_o4() {
        let config = ModelConfig {
            model_name: "o4-mini".to_string(),
            ..Default::default()
        };
        assert!(config.is_openai_reasoning_model());
    }

    #[test]
    fn is_openai_reasoning_model_detects_gpt5() {
        let config = ModelConfig {
            model_name: "gpt-5".to_string(),
            ..Default::default()
        };
        assert!(config.is_openai_reasoning_model());
    }

    #[test]
    fn is_not_reasoning_model_for_gpt4o() {
        let config = ModelConfig {
            model_name: "gpt-4o".to_string(),
            ..Default::default()
        };
        assert!(!config.is_openai_reasoning_model());
    }

    #[test]
    fn is_not_reasoning_model_for_claude() {
        let config = ModelConfig {
            model_name: "claude-sonnet-4".to_string(),
            ..Default::default()
        };
        assert!(!config.is_openai_reasoning_model());
    }

    #[test]
    fn reasoning_detection_with_goose_prefix() {
        let config = ModelConfig {
            model_name: "goose-o3-mini".to_string(),
            ..Default::default()
        };
        assert!(config.is_openai_reasoning_model());
    }

    #[test]
    fn reasoning_detection_with_databricks_prefix() {
        let config = ModelConfig {
            model_name: "databricks-gpt-5".to_string(),
            ..Default::default()
        };
        assert!(config.is_openai_reasoning_model());
    }

    #[test]
    fn use_fast_model_returns_clone_when_no_fast_config() {
        let config = ModelConfig {
            model_name: "main-model".to_string(),
            ..Default::default()
        };
        let fast = config.use_fast_model();
        assert_eq!(fast.model_name, "main-model");
    }

    #[test]
    fn clone_preserves_all_fields() {
        let config = ModelConfig {
            model_name: "test".to_string(),
            context_limit: Some(4096),
            temperature: Some(0.5),
            max_tokens: Some(1024),
            toolshim: true,
            ..Default::default()
        };
        let cloned = config.clone();
        assert_eq!(config.model_name, cloned.model_name);
        assert_eq!(config.context_limit, cloned.context_limit);
        assert_eq!(config.temperature, cloned.temperature);
        assert_eq!(config.max_tokens, cloned.max_tokens);
        assert_eq!(config.toolshim, cloned.toolshim);
    }

    #[test]
    fn with_request_params_sets_params() {
        let mut params = HashMap::new();
        params.insert(
            "key".to_string(),
            serde_json::Value::String("value".to_string()),
        );
        let config = ModelConfig::default().with_request_params(Some(params));
        assert!(config.request_params.is_some());
        assert_eq!(config.request_params.unwrap().len(), 1);
    }

    #[test]
    fn serialization_roundtrip() {
        let config = ModelConfig {
            model_name: "test-model".to_string(),
            context_limit: Some(16384),
            temperature: Some(0.8),
            max_tokens: Some(2048),
            toolshim: false,
            ..Default::default()
        };
        let json = serde_json::to_string(&config).unwrap();
        let deserialized: ModelConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.model_name, "test-model");
        assert_eq!(deserialized.context_limit, Some(16384));
        assert_eq!(deserialized.temperature, Some(0.8));
        assert_eq!(deserialized.max_tokens, Some(2048));
    }
}

mod message_tests {
    use goose::conversation::message::{Message, MessageContent};
    use rmcp::model::Role;

    #[test]
    fn user_message_has_user_role() {
        let msg = Message::user();
        assert_eq!(msg.role, Role::User);
    }

    #[test]
    fn assistant_message_has_assistant_role() {
        let msg = Message::assistant();
        assert_eq!(msg.role, Role::Assistant);
    }

    #[test]
    fn user_message_starts_with_empty_content() {
        let msg = Message::user();
        assert!(msg.content.is_empty());
    }

    #[test]
    fn with_text_adds_text_content() {
        let msg = Message::user().with_text("hello world");
        assert_eq!(msg.content.len(), 1);
        assert_eq!(msg.content[0].as_text().unwrap(), "hello world");
    }

    #[test]
    fn with_text_chaining_adds_multiple() {
        let msg = Message::user().with_text("first").with_text("second");
        assert_eq!(msg.content.len(), 2);
    }

    #[test]
    fn with_id_sets_message_id() {
        let msg = Message::user().with_id("msg_123");
        assert_eq!(msg.id, Some("msg_123".to_string()));
    }

    #[test]
    fn with_generated_id_sets_uuid_prefixed_id() {
        let msg = Message::user().with_generated_id();
        assert!(msg.id.is_some());
        assert!(msg.id.unwrap().starts_with("msg_"));
    }

    #[test]
    fn message_has_positive_timestamp() {
        let msg = Message::user();
        assert!(msg.created > 0);
    }

    #[test]
    fn with_image_adds_image_content() {
        let msg = Message::user().with_image("base64data", "image/png");
        assert_eq!(msg.content.len(), 1);
    }

    #[test]
    fn with_content_adds_arbitrary_content() {
        let content = MessageContent::text("test content");
        let msg = Message::assistant().with_content(content);
        assert_eq!(msg.content.len(), 1);
        assert_eq!(msg.content[0].as_text().unwrap(), "test content");
    }
}

mod message_content_tests {
    use goose::conversation::message::MessageContent;

    #[test]
    fn text_creates_text_content() {
        let content = MessageContent::text("hello");
        assert_eq!(content.as_text(), Some("hello"));
    }

    #[test]
    fn as_text_returns_none_for_non_text() {
        let content = MessageContent::image("data", "image/png");
        assert!(content.as_text().is_none());
    }

    #[test]
    fn thinking_creates_thinking_content() {
        let content = MessageContent::thinking("reasoning here", "sig123");
        let thinking = content.as_thinking().unwrap();
        assert_eq!(thinking.thinking, "reasoning here");
        assert_eq!(thinking.signature, "sig123");
    }

    #[test]
    fn as_thinking_returns_none_for_text() {
        let content = MessageContent::text("not thinking");
        assert!(content.as_thinking().is_none());
    }

    #[test]
    fn redacted_thinking_creates_content() {
        let content = MessageContent::redacted_thinking("redacted data");
        assert!(content.as_redacted_thinking().is_some());
    }

    #[test]
    fn display_text_content() {
        let content = MessageContent::text("hello world");
        let displayed = format!("{}", content);
        assert_eq!(displayed, "hello world");
    }

    #[test]
    fn display_thinking_content() {
        let content = MessageContent::thinking("my thoughts", "");
        let displayed = format!("{}", content);
        assert!(displayed.contains("my thoughts"));
    }
}

mod message_metadata_tests {
    use goose::conversation::message::MessageMetadata;

    #[test]
    fn default_is_visible_to_both() {
        let meta = MessageMetadata::default();
        assert!(meta.user_visible);
        assert!(meta.agent_visible);
    }

    #[test]
    fn agent_only_hides_from_user() {
        let meta = MessageMetadata::agent_only();
        assert!(!meta.user_visible);
        assert!(meta.agent_visible);
    }

    #[test]
    fn user_only_hides_from_agent() {
        let meta = MessageMetadata::user_only();
        assert!(meta.user_visible);
        assert!(!meta.agent_visible);
    }

    #[test]
    fn invisible_hides_from_both() {
        let meta = MessageMetadata::invisible();
        assert!(!meta.user_visible);
        assert!(!meta.agent_visible);
    }

    #[test]
    fn with_agent_invisible_preserves_user_visible() {
        let meta = MessageMetadata::default().with_agent_invisible();
        assert!(meta.user_visible);
        assert!(!meta.agent_visible);
    }

    #[test]
    fn with_user_invisible_preserves_agent_visible() {
        let meta = MessageMetadata::default().with_user_invisible();
        assert!(!meta.user_visible);
        assert!(meta.agent_visible);
    }

    #[test]
    fn chaining_visibility_modifiers() {
        let meta = MessageMetadata::invisible()
            .with_agent_visible()
            .with_user_visible();
        assert!(meta.user_visible);
        assert!(meta.agent_visible);
    }
}

mod conversation_tests {
    use goose::conversation::message::Message;
    use goose::conversation::Conversation;

    #[test]
    fn empty_conversation_is_empty() {
        let conv = Conversation::empty();
        assert!(conv.is_empty());
        assert_eq!(conv.len(), 0);
    }

    #[test]
    fn push_adds_message() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("hello"));
        assert_eq!(conv.len(), 1);
        assert!(!conv.is_empty());
    }

    #[test]
    fn push_multiple_messages() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("hi"));
        conv.push(Message::assistant().with_text("hello"));
        conv.push(Message::user().with_text("bye"));
        assert_eq!(conv.len(), 3);
    }

    #[test]
    fn first_returns_first_message() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("first"));
        conv.push(Message::assistant().with_text("second"));
        let first = conv.first().unwrap();
        assert_eq!(first.content[0].as_text(), Some("first"));
    }

    #[test]
    fn last_returns_last_message() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("first"));
        conv.push(Message::assistant().with_text("last"));
        let last = conv.last().unwrap();
        assert_eq!(last.content[0].as_text(), Some("last"));
    }

    #[test]
    fn new_unvalidated_creates_from_vec() {
        let messages = vec![
            Message::user().with_text("test"),
            Message::assistant().with_text("response"),
        ];
        let conv = Conversation::new_unvalidated(messages);
        assert_eq!(conv.len(), 2);
    }

    #[test]
    fn pop_removes_last() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("a"));
        conv.push(Message::assistant().with_text("b"));
        let popped = conv.pop();
        assert!(popped.is_some());
        assert_eq!(conv.len(), 1);
    }

    #[test]
    fn truncate_limits_length() {
        let mut conv = Conversation::empty();
        for i in 0..5 {
            let msg = if i % 2 == 0 {
                Message::user()
            } else {
                Message::assistant()
            };
            conv.push(msg.with_text(&format!("msg {}", i)));
        }
        conv.truncate(2);
        assert_eq!(conv.len(), 2);
    }

    #[test]
    fn clear_empties_conversation() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("test"));
        conv.clear();
        assert!(conv.is_empty());
    }

    #[test]
    fn iter_yields_all_messages() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("a"));
        conv.push(Message::assistant().with_text("b"));
        let count = conv.iter().count();
        assert_eq!(count, 2);
    }

    #[test]
    fn into_iter_consumes_conversation() {
        let mut conv = Conversation::empty();
        conv.push(Message::user().with_text("a"));
        conv.push(Message::assistant().with_text("b"));
        let messages: Vec<_> = conv.into_iter().collect();
        assert_eq!(messages.len(), 2);
    }

    #[test]
    fn default_is_empty() {
        let conv = Conversation::default();
        assert!(conv.is_empty());
    }

    #[test]
    fn extend_adds_multiple_messages() {
        let mut conv = Conversation::empty();
        let new_messages = vec![
            Message::user().with_text("one"),
            Message::assistant().with_text("two"),
        ];
        conv.extend(new_messages);
        assert_eq!(conv.len(), 2);
    }
}

mod provider_metadata_tests {
    use goose::providers::base::{ConfigKey, ModelInfo, ProviderMetadata};

    #[test]
    fn empty_creates_blank_metadata() {
        let meta = ProviderMetadata::empty();
        assert_eq!(meta.name, "");
        assert_eq!(meta.display_name, "");
        assert!(meta.known_models.is_empty());
        assert!(meta.config_keys.is_empty());
    }

    #[test]
    fn new_sets_basic_fields() {
        let meta = ProviderMetadata::new(
            "test-provider",
            "Test Provider",
            "A test provider",
            "default-model",
            vec!["model-a", "model-b"],
            "https://example.com/docs",
            vec![],
        );
        assert_eq!(meta.name, "test-provider");
        assert_eq!(meta.display_name, "Test Provider");
        assert_eq!(meta.default_model, "default-model");
        assert_eq!(meta.known_models.len(), 2);
    }

    #[test]
    fn with_setup_steps_adds_steps() {
        let meta = ProviderMetadata::empty()
            .with_setup_steps(vec!["Step 1: Do this", "Step 2: Do that"]);
        assert_eq!(meta.setup_steps.len(), 2);
        assert_eq!(meta.setup_steps[0], "Step 1: Do this");
    }

    #[test]
    fn with_models_uses_model_info() {
        let models = vec![
            ModelInfo::new("gpt-4", 128_000),
            ModelInfo::with_cost("gpt-4-turbo", 128_000, 0.00001, 0.00003),
        ];
        let meta = ProviderMetadata::with_models(
            "openai",
            "OpenAI",
            "OpenAI provider",
            "gpt-4",
            models,
            "https://openai.com",
            vec![],
        );
        assert_eq!(meta.known_models.len(), 2);
        assert_eq!(meta.known_models[0].name, "gpt-4");
    }

    #[test]
    fn metadata_with_config_keys() {
        let keys = vec![
            ConfigKey::new("API_KEY", true, true, None, true),
            ConfigKey::new(
                "ENDPOINT",
                false,
                false,
                Some("https://api.test.com"),
                false,
            ),
        ];
        let meta = ProviderMetadata::new(
            "custom",
            "Custom",
            "Custom provider",
            "model-1",
            vec!["model-1"],
            "https://docs.test.com",
            keys,
        );
        assert_eq!(meta.config_keys.len(), 2);
        assert!(meta.config_keys[0].required);
        assert!(!meta.config_keys[1].required);
    }
}

mod model_info_tests {
    use goose::providers::base::ModelInfo;

    #[test]
    fn new_creates_with_name_and_limit() {
        let info = ModelInfo::new("test-model", 128_000);
        assert_eq!(info.name, "test-model");
        assert_eq!(info.context_limit, 128_000);
        assert!(info.input_token_cost.is_none());
        assert!(info.output_token_cost.is_none());
    }

    #[test]
    fn with_cost_sets_pricing() {
        let info = ModelInfo::with_cost("gpt-4", 128_000, 0.01, 0.03);
        assert_eq!(info.input_token_cost, Some(0.01));
        assert_eq!(info.output_token_cost, Some(0.03));
        assert_eq!(info.currency, Some("$".to_string()));
    }

    #[test]
    fn model_info_clone_preserves_fields() {
        let info = ModelInfo::with_cost("claude-3", 200_000, 0.003, 0.015);
        let cloned = info.clone();
        assert_eq!(info.name, cloned.name);
        assert_eq!(info.context_limit, cloned.context_limit);
        assert_eq!(info.input_token_cost, cloned.input_token_cost);
    }
}

mod config_key_tests {
    use goose::providers::base::ConfigKey;

    #[test]
    fn new_creates_basic_key() {
        let key = ConfigKey::new("API_KEY", true, true, None, true);
        assert_eq!(key.name, "API_KEY");
        assert!(key.required);
        assert!(key.secret);
        assert!(key.default.is_none());
        assert!(!key.oauth_flow);
        assert!(key.primary);
    }

    #[test]
    fn new_with_default_value() {
        let key = ConfigKey::new(
            "ENDPOINT",
            false,
            false,
            Some("https://api.example.com"),
            false,
        );
        assert_eq!(key.default, Some("https://api.example.com".to_string()));
        assert!(!key.required);
    }

    #[test]
    fn new_oauth_sets_oauth_flow() {
        let key = ConfigKey::new_oauth("OAUTH_TOKEN", true, true, None, true);
        assert!(key.oauth_flow);
        assert!(!key.device_code_flow);
    }

    #[test]
    fn new_oauth_device_code_sets_both_flags() {
        let key = ConfigKey::new_oauth_device_code("DEVICE_TOKEN", true, true, None, true);
        assert!(key.oauth_flow);
        assert!(key.device_code_flow);
    }
}

mod provider_error_tests {
    use goose::providers::errors::ProviderError;
    use std::time::Duration;

    #[test]
    fn telemetry_type_auth() {
        let err = ProviderError::Authentication("bad key".into());
        assert_eq!(err.telemetry_type(), "auth");
    }

    #[test]
    fn telemetry_type_rate_limit() {
        let err = ProviderError::RateLimitExceeded {
            details: "too many".into(),
            retry_delay: None,
        };
        assert_eq!(err.telemetry_type(), "rate_limit");
    }

    #[test]
    fn telemetry_type_context_length() {
        let err = ProviderError::ContextLengthExceeded("too long".into());
        assert_eq!(err.telemetry_type(), "context_length");
    }

    #[test]
    fn telemetry_type_server() {
        let err = ProviderError::ServerError("500 error".into());
        assert_eq!(err.telemetry_type(), "server");
    }

    #[test]
    fn telemetry_type_network() {
        let err = ProviderError::NetworkError("connection refused".into());
        assert_eq!(err.telemetry_type(), "network");
    }

    #[test]
    fn telemetry_type_execution() {
        let err = ProviderError::ExecutionError("failed".into());
        assert_eq!(err.telemetry_type(), "execution");
    }

    #[test]
    fn telemetry_type_not_implemented() {
        let err = ProviderError::NotImplemented("unsupported".into());
        assert_eq!(err.telemetry_type(), "not_implemented");
    }

    #[test]
    fn is_endpoint_not_found_true() {
        let err = ProviderError::EndpointNotFound("404 not found".into());
        assert!(err.is_endpoint_not_found());
    }

    #[test]
    fn is_endpoint_not_found_false_for_other() {
        let err = ProviderError::ServerError("500 error".into());
        assert!(!err.is_endpoint_not_found());
    }

    #[test]
    fn error_display_includes_message() {
        let err = ProviderError::Authentication("invalid token".into());
        let display = format!("{}", err);
        assert!(display.contains("invalid token"));
    }

    #[test]
    fn rate_limit_with_retry_delay() {
        let err = ProviderError::RateLimitExceeded {
            details: "slow down".into(),
            retry_delay: Some(Duration::from_secs(30)),
        };
        if let ProviderError::RateLimitExceeded { retry_delay, .. } = err {
            assert_eq!(retry_delay, Some(Duration::from_secs(30)));
        }
    }

    #[test]
    fn credits_exhausted_with_url() {
        let err = ProviderError::CreditsExhausted {
            details: "no credits".into(),
            top_up_url: Some("https://example.com/billing".into()),
        };
        assert_eq!(err.telemetry_type(), "credits_exhausted");
    }
}

mod usage_tests {
    use goose::providers::base::Usage;

    #[test]
    fn new_with_all_tokens() {
        let usage = Usage::new(Some(100), Some(50), Some(150));
        assert_eq!(usage.input_tokens, Some(100));
        assert_eq!(usage.output_tokens, Some(50));
        assert_eq!(usage.total_tokens, Some(150));
    }

    #[test]
    fn new_calculates_total_when_not_provided() {
        let usage = Usage::new(Some(100), Some(50), None);
        assert_eq!(usage.total_tokens, Some(150));
    }

    #[test]
    fn new_with_only_input() {
        let usage = Usage::new(Some(100), None, None);
        assert_eq!(usage.total_tokens, Some(100));
    }

    #[test]
    fn new_with_only_output() {
        let usage = Usage::new(None, Some(50), None);
        assert_eq!(usage.total_tokens, Some(50));
    }

    #[test]
    fn new_all_none() {
        let usage = Usage::new(None, None, None);
        assert_eq!(usage.total_tokens, None);
    }

    #[test]
    fn add_combines_tokens() {
        let a = Usage::new(Some(100), Some(50), None);
        let b = Usage::new(Some(200), Some(100), None);
        let c = a + b;
        assert_eq!(c.input_tokens, Some(300));
        assert_eq!(c.output_tokens, Some(150));
        assert_eq!(c.total_tokens, Some(450));
    }

    #[test]
    fn add_with_none_fields() {
        let a = Usage::new(Some(100), None, None);
        let b = Usage::new(None, Some(50), None);
        let c = a + b;
        assert_eq!(c.input_tokens, Some(100));
        assert_eq!(c.output_tokens, Some(50));
    }

    #[test]
    fn with_cache_tokens_sets_values() {
        let usage = Usage::new(Some(100), Some(50), None).with_cache_tokens(Some(20), Some(30));
        assert_eq!(usage.cache_read_input_tokens, Some(20));
        assert_eq!(usage.cache_write_input_tokens, Some(30));
    }

    #[test]
    fn add_assign_works() {
        let mut usage = Usage::new(Some(10), Some(5), None);
        usage += Usage::new(Some(20), Some(10), None);
        assert_eq!(usage.input_tokens, Some(30));
        assert_eq!(usage.output_tokens, Some(15));
    }

    #[test]
    fn default_usage_is_all_none() {
        let usage = Usage::default();
        assert_eq!(usage.input_tokens, None);
        assert_eq!(usage.output_tokens, None);
        assert_eq!(usage.total_tokens, None);
    }

    #[test]
    fn add_preserves_cache_tokens() {
        let a = Usage::new(Some(10), Some(5), None).with_cache_tokens(Some(3), Some(2));
        let b = Usage::new(Some(20), Some(10), None).with_cache_tokens(Some(7), Some(8));
        let c = a + b;
        assert_eq!(c.cache_read_input_tokens, Some(10));
        assert_eq!(c.cache_write_input_tokens, Some(10));
    }
}

mod provider_usage_tests {
    use goose::providers::base::{ProviderUsage, Usage};

    #[test]
    fn new_creates_with_model() {
        let usage =
            ProviderUsage::new("gpt-4".to_string(), Usage::new(Some(100), Some(50), None));
        assert_eq!(usage.model, "gpt-4");
        assert_eq!(usage.usage.input_tokens, Some(100));
    }

    #[test]
    fn combine_with_adds_usage() {
        let a =
            ProviderUsage::new("gpt-4".to_string(), Usage::new(Some(100), Some(50), None));
        let b =
            ProviderUsage::new("gpt-4".to_string(), Usage::new(Some(200), Some(100), None));
        let combined = a.combine_with(&b);
        assert_eq!(combined.model, "gpt-4");
        assert_eq!(combined.usage.input_tokens, Some(300));
        assert_eq!(combined.usage.output_tokens, Some(150));
    }

    #[test]
    fn combine_with_uses_self_model() {
        let a =
            ProviderUsage::new("model-a".to_string(), Usage::new(Some(10), None, None));
        let b =
            ProviderUsage::new("model-b".to_string(), Usage::new(Some(20), None, None));
        let combined = a.combine_with(&b);
        assert_eq!(combined.model, "model-a");
    }
}

mod retry_config_tests {
    use goose::providers::RetryConfig;

    #[test]
    fn default_has_3_retries() {
        let config = RetryConfig::default();
        assert_eq!(config.max_retries(), 3);
    }

    #[test]
    fn new_sets_custom_values() {
        let config = RetryConfig::new(5, 500, 1.5, 10_000);
        assert_eq!(config.max_retries(), 5);
    }

    #[test]
    fn delay_for_attempt_zero_is_zero() {
        let config = RetryConfig::default();
        let delay = config.delay_for_attempt(0);
        assert_eq!(delay, std::time::Duration::from_millis(0));
    }

    #[test]
    fn delay_for_attempt_one_is_nonzero() {
        let config = RetryConfig::default();
        let delay = config.delay_for_attempt(1);
        assert!(delay.as_millis() > 0);
    }
}

mod prompt_template_tests {
    use goose::prompt_template;
    use std::collections::HashMap;

    #[test]
    fn render_string_with_no_variables() {
        let result =
            prompt_template::render_string("Hello, world!", &HashMap::<String, String>::new());
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "Hello, world!");
    }

    #[test]
    fn render_string_with_variable() {
        let mut ctx = HashMap::new();
        ctx.insert("name".to_string(), "Goose".to_string());
        let result = prompt_template::render_string("Hello, {{ name }}!", &ctx);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "Hello, Goose!");
    }

    #[test]
    fn render_string_preserves_multiline() {
        let template = "Line 1\nLine 2\nLine 3";
        let result = prompt_template::render_string(template, &HashMap::<String, String>::new());
        assert!(result.is_ok());
        let rendered = result.unwrap();
        assert!(rendered.contains("Line 1"));
        assert!(rendered.contains("Line 2"));
        assert!(rendered.contains("Line 3"));
    }

    #[test]
    fn render_string_with_multiple_variables() {
        let mut ctx = HashMap::new();
        ctx.insert("first".to_string(), "Hello".to_string());
        ctx.insert("second".to_string(), "World".to_string());
        let result = prompt_template::render_string("{{ first }}, {{ second }}!", &ctx);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "Hello, World!");
    }
}

mod provider_type_tests {
    use goose::providers::base::ProviderType;

    #[test]
    fn provider_types_are_distinct() {
        assert_ne!(ProviderType::Preferred, ProviderType::Builtin);
        assert_ne!(ProviderType::Builtin, ProviderType::Custom);
        assert_ne!(ProviderType::Declarative, ProviderType::Custom);
    }

    #[test]
    fn provider_type_equality() {
        assert_eq!(ProviderType::Preferred, ProviderType::Preferred);
        assert_eq!(ProviderType::Custom, ProviderType::Custom);
    }

    #[test]
    fn provider_type_clone() {
        let original = ProviderType::Builtin;
        let cloned = original;
        assert_eq!(original, cloned);
    }
}
