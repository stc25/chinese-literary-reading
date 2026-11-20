import os

# Explicit opt-in to the test configuration (production never sets this).
os.environ.setdefault("MLC_TESTING", "1")
