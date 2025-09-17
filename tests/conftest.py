import os
import sys
from pathlib import Path

# ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# default env vars for tests
os.environ.setdefault("YOUTUBE_API_KEY", "x")
os.environ.setdefault("OPENAI_API_KEY", "x")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "secrets/test_creds.json")
os.environ.setdefault("REGION_CODE", "RU")
os.environ.setdefault("DEFAULT_PUBLISHED_AFTER", "2025-08-01T00:00:00Z")
