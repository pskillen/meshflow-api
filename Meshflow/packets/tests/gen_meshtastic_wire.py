"""Write the ingest bodies the bot would send for the labelled 2.7/2.8 capture subset.

Run by hand (not in CI) against a checkout of meshflow-bot that holds ``docs/meshtastic_packets/2.8/subset.json``
and ``tools/meshtastic_fixtures/load.py``::

    python packets/tests/gen_meshtastic_wire.py --bot /path/to/meshflow-bot

Output goes to ``docs/packets/meshtastic-2.8/``: ``wire/<key>.json`` (default mode), ``wire/<key>+flag.json`` for
replay entries (bot flag mode sends ``{**packet, "replayed": True}``) and ``manifest.json``. ``time.time`` is patched
to the entry's ``t_host`` so the bot's ``rxTime`` fallback is reproducible. Needs only the standard library plus the
bot's own stdlib-only modules.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "docs" / "packets" / "meshtastic-2.8"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot", required=True, type=Path, help="meshflow-bot checkout")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    bot = args.bot.resolve()
    sys.path.insert(0, str(bot))
    from src.meshtastic.serializers import MeshtasticPacketSerializer
    from tools.meshtastic_fixtures.load import lib_packet, load_subset

    bot_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=bot, check=True, capture_output=True, text=True
    ).stdout.strip()
    subset = load_subset(bot / "docs" / "meshtastic_packets" / "2.8")
    serialiser = MeshtasticPacketSerializer()

    manifest = []
    for entry in subset:
        with mock.patch("time.time", return_value=int(entry["t_host"])):
            body = serialiser.serialise_raw_packet(lib_packet(entry))
        write_json(args.out / "wire" / f"{entry['key']}.json", body)
        if entry["kind"] == "replay":
            write_json(args.out / "wire" / f"{entry['key']}+flag.json", {**body, "replayed": True})
        manifest.append(
            {
                "key": entry["key"],
                "labels": entry["labels"],
                "kind": entry["kind"],
                "feeder_num": entry["feeder_num"],
                "bot_ref": bot_ref,
            }
        )
    write_json(args.out / "manifest.json", manifest)
    print(f"wrote {len(manifest)} entries from bot {bot_ref}")


if __name__ == "__main__":
    main()
