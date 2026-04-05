use std::path::Path;
use std::process::Command;

pub fn get_git_status(working_dir: &Path) -> Option<String> {
    let output = Command::new("git")
        .current_dir(working_dir)
        .args(["status", "--short", "--porcelain"])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout.is_empty() {
        return Some("Git working tree is clean.".to_string());
    }

    let mut formatted = Vec::new();
    for line in stdout.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if let Some(rest) = line.strip_prefix("M ") {
            formatted.push(format!("modified: {rest}"));
        } else if let Some(rest) = line.strip_prefix("?? ") {
            formatted.push(format!("untracked: {rest}"));
        } else if let Some(rest) = line.strip_prefix("D ") {
            formatted.push(format!("deleted: {rest}"));
        } else if let Some(rest) = line.strip_prefix("A ") {
            formatted.push(format!("added: {rest}"));
        } else {
            formatted.push(line.to_string());
        }
    }

    Some(formatted.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_git_status_non_repo() {
        // temp_dir is never a git repo
        let dir = std::env::temp_dir();
        let result = get_git_status(&dir);
        assert!(result.is_none());
    }
}
