from dataclasses import asdict
from pprint import pprint

from ootp_opt.config import load_config
from ootp_opt.roster.rules import load_roster_profile

cfg = load_config("config.toml")
ruleset = load_roster_profile(cfg, "standard_pt")

print("\n=== RULESET AS DICT ===")
pprint(asdict(ruleset), sort_dicts=False)
