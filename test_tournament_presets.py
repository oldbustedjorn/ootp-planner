from ootp_opt.config import load_config
from ootp_opt.roster.rules import build_ruleset_from_tournament_preset

cfg = load_config("config.toml")

for preset_name in cfg.get("tournament_presets", {}):
    ruleset = build_ruleset_from_tournament_preset(cfg, preset_name)

    print(f"\n=== {preset_name} ===")
    print(f"base/mode: {ruleset.mode}")
    print(f"DH: {ruleset.dh_enabled}")
    print(f"tier min/max: {ruleset.tier_min} / {ruleset.tier_max}")
    print(f"card value min/max: {ruleset.card_value_min} / {ruleset.card_value_max}")
    print(f"live mode: {ruleset.live_mode}")
    print(f"card year min/max: {ruleset.card_year_min} / {ruleset.card_year_max}")
