import json
from pathlib import Path

FLAGS_PATH = Path("runtime_data/feature_flags.json")

DEFAULT_FLAGS = {
    "hero_header": True,
    "kpi_cards": True,
    "reference_faq": True,
    "suggest_questions": True,
    "sidebar_simulator": True,
    "admin_tools": True
}

def load_flags():

    if FLAGS_PATH.exists():
        return json.loads(FLAGS_PATH.read_text())

    return DEFAULT_FLAGS

def save_flags(flags):

    FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAGS_PATH.write_text(json.dumps(flags, indent=2))

FLAGS = load_flags()

def ff(key):

    return FLAGS.get(key, True)