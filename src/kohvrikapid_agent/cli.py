"""Lihtne CLI: kohvrikapid-agent --serial / --reset / --run"""
from __future__ import annotations
import argparse
import sys

from .config import AgentSecrets, SECRETS_PATH, read_or_create_serial


def main() -> int:
    p = argparse.ArgumentParser(prog="kohvrikapid-agent", description="Kohvrikapid Pi agent")
    p.add_argument("--serial", action="store_true", help="Print seerianumber ja välju")
    p.add_argument("--reset", action="store_true", help="Kustuta agent_token ja sunni uus registratsioon")
    p.add_argument("--run", action="store_true", help="Käivita agent (peamine režiim, systemd kasutab seda)")
    args = p.parse_args()

    if args.serial:
        print(read_or_create_serial())
        return 0
    if args.reset:
        SECRETS_PATH.unlink(missing_ok=True)
        print("Saladused kustutatud — agent registreerub järgmise käivituse ajal uuesti.")
        return 0
    if args.run or len(sys.argv) == 1:
        from .main import main as run_main
        return run_main()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
