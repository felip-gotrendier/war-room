from dotenv import load_dotenv

# Load .env before any test module imports so that PULSE_MCP_URL,
# RELEASE_AGENT_MCP_URL, and ANTHROPIC_API_KEY are available even in a fresh
# terminal that has not manually exported them.  override=False means explicit
# shell exports and CI secrets take precedence over the file.
load_dotenv(override=False)
