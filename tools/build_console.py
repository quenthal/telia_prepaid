#!/usr/bin/env python3
"""Kokoaa yhden tiedoston konsolitestin: api.py + tools/console_part.py.

    python3 tools/build_console.py   ->  dist/telia_prepaid_test.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "custom_components" / "telia_prepaid" / "api.py"
PART = ROOT / "tools" / "console_part.py"
OUT = ROOT / "dist" / "telia_prepaid_test.py"

HEADER = '''#!/usr/bin/env python3
# Telia Prepaid – konsolitesti. Vaatii vain Python 3.10+, ei lisäkirjastoja.
#
#   python3 telia_prepaid_test.py oma@sahkoposti.fi
#   python3 telia_prepaid_test.py oma@sahkoposti.fi -v --dump
#   TELIA_PASSWORD=... python3 telia_prepaid_test.py oma@sahkoposti.fi --json
#
# Tämä tiedosto on koottu automaattisesti (tools/build_console.py), ja sen
# kirjautumis- ja lukulogiikka on täsmälleen sama kuin HA-integraation api.py:ssä.
'''


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(HEADER + API.read_text(encoding="utf-8") + "\n\n" + PART.read_text(encoding="utf-8"),
                   encoding="utf-8")
    OUT.chmod(0o755)
    print(f"Kirjoitettu {OUT}")


if __name__ == "__main__":
    main()
