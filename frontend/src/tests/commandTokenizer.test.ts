import { describe, it, expect } from 'vitest'
import { parseCommand } from '../services/commandTokenizer'

describe('parseCommand', () => {
  it('parses simple natural command string', () => {
    const result = parseCommand('python -m unittest test_db_schema.py')
    expect(result).toEqual(['python', '-m', 'unittest', 'test_db_schema.py'])
  })

  it('parses natural commands with double-quoted paths containing spaces', () => {
    const result = parseCommand('python "my test files/run_tests.py" -v')
    expect(result).toEqual(['python', 'my test files/run_tests.py', '-v'])
  })

  it('parses natural commands with single-quoted arguments', () => {
    const result = parseCommand("python -c 'import sys; sys.exit(0)'")
    expect(result).toEqual(['python', '-c', 'import sys; sys.exit(0)'])
  })

  it('parses valid JSON array syntax', () => {
    const result = parseCommand('["python", "-m", "unittest", "-v"]')
    expect(result).toEqual(['python', '-m', 'unittest', '-v'])
  })

  it('throws descriptive error on malformed JSON array', () => {
    expect(() => parseCommand('["python", -m]')).toThrowError(/Malformed JSON command/)
  })

  it('throws descriptive error on non-array or empty JSON', () => {
    expect(() => parseCommand('[]')).toThrowError(/JSON command must be a non-empty array of strings/)
    expect(() => parseCommand('{"command": "test"}')).toThrowError(/JSON command must be a non-empty array of strings/)
  })

  it('rejects commands containing shell pipes or redirection', () => {
    expect(() => parseCommand('python test.py | grep FAIL')).toThrowError(/Shell operator '\|' is disabled for safety/)
    expect(() => parseCommand('python test.py > output.txt')).toThrowError(/Shell operator '>' is disabled for safety/)
    expect(() => parseCommand('python test.py && rm -rf /')).toThrowError(/Shell operator '&&' is disabled for safety/)
    expect(() => parseCommand('python test.py; echo done')).toThrowError(/Shell operator ';' is disabled for safety/)
  })

  it('rejects unclosed quotes', () => {
    expect(() => parseCommand('python "unclosed test')).toThrowError(/Unclosed quote in command/)
  })

  it('rejects empty strings', () => {
    expect(() => parseCommand('   ')).toThrowError(/Command cannot be empty/)
  })
})
