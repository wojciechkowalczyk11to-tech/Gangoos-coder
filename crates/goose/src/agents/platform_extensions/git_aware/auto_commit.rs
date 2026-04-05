pub fn suggest_commit_message(changed_files: &[String]) -> String {
    if changed_files.is_empty() {
        return "chore: minor updates".to_string();
    }

    let rs_count = changed_files.iter().filter(|f| f.ends_with(".rs")).count();
    let total = changed_files.len();

    if rs_count > 0 && rs_count == total {
        format!("feat: update {rs_count} Rust files")
    } else if total > 5 {
        format!("chore: update {total} files")
    } else {
        "chore: workspace changes".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_suggest_commit_message_empty() {
        assert_eq!(suggest_commit_message(&[]), "chore: minor updates");
    }

    #[test]
    fn test_suggest_commit_message_rust_only() {
        let files = vec!["src/main.rs".to_string(), "lib.rs".to_string()];
        assert_eq!(suggest_commit_message(&files), "feat: update 2 Rust files");
    }

    #[test]
    fn test_suggest_commit_message_many() {
        let files = vec!["file.txt".to_string(); 6];
        assert_eq!(suggest_commit_message(&files), "chore: update 6 files");
    }

    #[test]
    fn test_suggest_commit_message_mixed() {
        let files = vec!["main.rs".to_string(), "README.md".to_string()];
        assert_eq!(suggest_commit_message(&files), "chore: workspace changes");
    }
}
