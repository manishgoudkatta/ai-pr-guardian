# Project Coding Rules

## Naming Conventions
- All async functions must be prefixed with `async_` or clearly named with verb
- Constants: UPPER_SNAKE_CASE
- Private helpers: prefix with underscore

## Error Handling
- Never use bare `except:` — always catch specific exception types
- All external API calls must have timeout set (max 30s)
- Log errors with context before re-raising

## Security
- Never log secrets, tokens, or PII
- All user inputs must be validated with Pydantic before use
- SQL queries must use parameterized statements (never f-strings)

## Testing
- New features require at least one unit test
- Test files must mirror src structure: src/foo.py → tests/test_foo.py

## Performance
- Avoid N+1 queries — use batch fetching
- Functions touching DB must not be called in a loop without pagination
