import sys
from pathlib import Path

# Allow both `python -m server.main_chat` and `python server/main_chat.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.web_app import main  # noqa: E402


if __name__ == "__main__":
    main()
