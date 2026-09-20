from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_settings(path=None):
    config_path = Path(path) if path else ROOT / "config" / "settings.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        settings = yaml.safe_load(handle)
    settings["root"] = ROOT
    return settings

