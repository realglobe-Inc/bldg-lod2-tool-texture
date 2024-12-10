from pathlib import Path


def fix_relative_path(path):
  # pathlibで統一して簡潔にする
  return str(Path(path).expanduser().resolve())
