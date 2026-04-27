from dataclasses import asdict
from pprint import pprint

from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_base_profile

cfg = load_config("config.toml")

ruleset = build_ruleset_from_base_profile(cfg, "standard_pt")

print("\n=== STANDARD PT RULESET ===")
pprint(asdict(ruleset), sort_dicts=False)

playoff_ruleset = build_ruleset_from_base_profile(cfg, "playoff_pt")

print("\n=== PLAYOFF PT RULESET ===")
pprint(asdict(playoff_ruleset), sort_dicts=False)
