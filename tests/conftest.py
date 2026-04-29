from dotenv import load_dotenv

# Load .env before any test module imports.  override=True ensures the .env
# file values are used even when the shell already has a stale export (e.g.
# from a previous `source .env` when the file had different values).
# Safe for CI: .env is in .gitignore so it does not exist there, and
# load_dotenv() silently does nothing when the file is absent.
load_dotenv(override=True)
