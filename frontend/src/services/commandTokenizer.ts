/**
 * Command tokenizer for GraphPilot.
 *
 * Supports:
 *  1. Natural shell-like commands with quoted arguments (e.g. `python -m unittest "test files/check.py"`)
 *  2. JSON string arrays (e.g. `["python", "-m", "unittest"]`)
 *
 * Security & robustness boundaries:
 *  - Disallows unquoted shell operators (pipes, redirection, chaining) because execution is directly via subprocess argv, not a shell.
 *  - Distinguishes malformed JSON from natural commands with clear error feedback.
 */

export function parseCommand(input: string): string[] {
  const trimmed = input.trim()
  if (!trimmed) {
    throw new Error('Command cannot be empty. Enter a command like "python -m unittest test_db_schema.py".')
  }

  // 1. Handle JSON array format if the user initiated JSON syntax
  if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      throw new Error(
        'Malformed JSON command. Provide valid JSON syntax like ["python", "-m", "unittest"] or enter a natural command without brackets.'
      )
    }

    if (!Array.isArray(parsed) || parsed.length === 0 || !parsed.every((item) => typeof item === 'string' && item.trim().length > 0)) {
      throw new Error(
        'JSON command must be a non-empty array of strings, for example ["python", "-m", "unittest"].'
      )
    }

    return parsed
  }

  // 2. Tokenize natural command line with quote handling and unquoted operator checking
  return tokenizeCommandLine(trimmed)
}

function tokenizeCommandLine(command: string): string[] {
  const tokens: string[] = []
  let currentToken = ''
  let inDoubleQuote = false
  let inSingleQuote = false

  for (let i = 0; i < command.length; i++) {
    const char = command[i]
    const nextChar = i + 1 < command.length ? command[i + 1] : ''

    // Quote toggling
    if (char === '"' && !inSingleQuote) {
      inDoubleQuote = !inDoubleQuote
      continue
    }

    if (char === "'" && !inDoubleQuote) {
      inSingleQuote = !inSingleQuote
      continue
    }

    // Unquoted shell operator checks
    if (!inDoubleQuote && !inSingleQuote) {
      if (char === '|' && nextChar === '|') {
        throw new Error("Shell operator '||' is disabled for safety. Commands are executed directly as a subprocess argument list without a shell.")
      }
      if (char === '&' && nextChar === '&') {
        throw new Error("Shell operator '&&' is disabled for safety. Commands are executed directly as a subprocess argument list without a shell.")
      }
      if (char === '|' || char === ';' || char === '<') {
        throw new Error(`Shell operator '${char}' is disabled for safety. Commands are executed directly as a subprocess argument list without a shell.`)
      }
      if (char === '>') {
        throw new Error("Shell operator '>' is disabled for safety. Commands are executed directly as a subprocess argument list without a shell.")
      }

      // Whitespace separation
      if (char === ' ' || char === '\t') {
        if (currentToken.length > 0) {
          tokens.push(currentToken)
          currentToken = ''
        }
        continue
      }
    }

    currentToken += char
  }

  if (inDoubleQuote || inSingleQuote) {
    throw new Error('Unclosed quote in command. Ensure all single or double quotes are closed.')
  }

  if (currentToken.length > 0) {
    tokens.push(currentToken)
  }

  if (tokens.length === 0) {
    throw new Error('Command cannot be empty.')
  }

  return tokens
}
