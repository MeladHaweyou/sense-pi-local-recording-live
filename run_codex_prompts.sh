#!/usr/bin/env bash
set -euo pipefail

# Always run from the directory where this script lives (repo root)
cd "$(dirname "$0")"

PROMPTS_DIR="codex-prompts"

if [[ ! -d "$PROMPTS_DIR" ]]; then
  echo "Error: directory '$PROMPTS_DIR' not found" >&2
  exit 1
fi

# Collect all .md files in codex-prompts, sorted alphabetically
mapfile -t files < <(find "$PROMPTS_DIR" -maxdepth 1 -type f -name '*.md' | sort)

if (( ${#files[@]} == 0 )); then
  echo "No .md files found in '$PROMPTS_DIR'." >&2
  exit 1
fi

run_prompt() {
  local file="$1"
  local label="$2"

  echo
  echo "=================================================="
  echo "Running: $label"
  echo "Prompt file: $file"
  echo "=================================================="
  echo

  # PROMPT = '-' → codex reads prompt from stdin (the file we redirect)
  codex exec --full-auto - < "$file"
}

for file in "${files[@]}"; do
  label="$(basename "$file")"
  run_prompt "$file" "$label"
done

echo
echo "All Codex prompts finished."
