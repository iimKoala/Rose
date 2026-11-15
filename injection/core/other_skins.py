#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The skins the user picked for other players' champions in champ select (the ROSE-OtherSkins panel).

A choice is per champion and lasts one champ select (state.other_skins, emptied by the champ select reset):
the default look, a skin Rose ships, or one of the user's own custom skins. It only changes what this PC
shows: nothing is sent to anyone, and the other player's own choice is not touched.

How it reaches the game: the skin's mod as it is (it sits on the base skin, slot 0), and a small mod made on
the spot that repeats it under every other skin slot of the champion (injection/baseskin/slots.py), since
which of their skins the other player has on is not known for an enemy until the game starts. So the choice
covers every player on that champion.

The steps travel with friends' skins (InjectionTrigger.planned_party_skins), so they are staged during the
countdown and installed by the injection the same way. Design and limits: docs/other-players-skins.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from utils.core.logging import get_logger

from ..baseskin import slots
from ..classic import is_classic_game_mode
from ..mods.mod_source import RoseFile
from .stage_plan import OtherSkinStep

log = get_logger()

DEFAULT, SKIN, CUSTOM = "default", "skin", "custom"
FOLDER_PREFIX = "other_"


def shipped_skin_ids(champion_id: int) -> List[int]:
    """The skins of a champion Rose has a file for (its chromas are not listed: the panel offers skins)."""
    from utils.core.paths import get_skins_dir

    from ..mods.zip_resolver import SKIN_EXTENSIONS

    found = []
    try:
        folders = list((get_skins_dir() / str(champion_id)).iterdir())
    except OSError:
        return []
    for folder in folders:
        if not folder.name.isdigit() or int(folder.name) // 1000 != champion_id or int(folder.name) % 1000 == 0:
            continue
        if any((folder / f"{folder.name}{extension}").is_file() for extension in SKIN_EXTENSIONS):
            found.append(int(folder.name))
    return sorted(found)


def choose(state, champion_id: int, stem: str, kind: str, skin_id: int = 0, mod_path: str = "") -> bool:
    """Remember the user's pick for a champion; any other *kind* ("own") forgets it. Whether it was taken."""
    chosen = dict(getattr(state, "other_skins", None) or {})
    chosen.pop(champion_id, None)
    taken = True
    if kind in (DEFAULT, SKIN, CUSTOM):
        taken = (champion_id > 0 and stem.isalnum()
                 and (kind != SKIN or skin_id // 1000 == champion_id) and (kind != CUSTOM or bool(mod_path)))
        if taken:
            chosen[champion_id] = OtherSkinStep(champion_id, stem, kind, skin_id if kind == SKIN else 0,
                                                mod_path if kind == CUSTOM else "")
    state.other_skins = chosen
    return taken


def planned(state) -> Tuple[OtherSkinStep, ...]:
    """The picks the injection installs, by champion: none for the user's own champion (its skin is the
    user's own pick), and none in Rift Classic (it plays other characters)."""
    chosen = getattr(state, "other_skins", None) or {}
    if not chosen or is_classic_game_mode(getattr(state, "current_game_mode", None)):
        return ()
    mine = getattr(state, "locked_champ_id", None) or getattr(state, "hovered_champ_id", None)
    return tuple(chosen[champion_id] for champion_id in sorted(chosen) if champion_id != mine)


def champions(state) -> set:
    """The champions with a pick: a friend's shared skin is not installed for one of them."""
    return {step.champion_id for step in planned(state)}


def prepare(injector, step: OtherSkinStep, mods_dir: Optional[Path] = None) -> List[str]:
    """Put a pick's mods into *mods_dir* (the injector's by default) and return their folder names; [] when
    its skin is not there, so the player keeps their own."""
    mods_dir = Path(mods_dir) if mods_dir is not None else injector.mods_dir
    folder = f"{FOLDER_PREFIX}{step.champion_id}"
    names: List[str] = []
    skip: tuple = ()
    if step.kind == DEFAULT:
        bins, label = slots.game_base_bins(injector.game_dir, step.stem), "the default skin"
    elif step.kind == SKIN:
        name = f"skin_{step.skin_id}"
        archive = injector._resolve_zip(name, skin_name=name, champion_name=None, champion_id=step.champion_id)
        if not archive or not Path(archive).exists() or RoseFile(Path(archive), folder).put(mods_dir) is None:
            log.info(f"[OTHERS] Skin {step.skin_id} is not in Rose's skins: champion {step.champion_id} keeps their own")
            return []
        names.append(folder)
        # the slot of the skin itself keeps the game's file: it is the one the copies link
        bins, label, skip = slots.mod_base_bins(Path(archive)), Path(archive).name, (step.skin_id % 1000,)
    elif step.kind == CUSTOM:
        from party.discovery.custom_mods import get_mods_root
        from party.integration.injection_hook import _local_custom_mod

        mod = _local_custom_mod(step.mod_path, folder)
        if mod is None or mod.put(mods_dir) is None:
            log.info(f"[OTHERS] The custom skin {step.mod_path} is gone: champion {step.champion_id} keeps their own")
            return []
        names.append(folder)
        file = get_mods_root() / step.mod_path
        bins, label = (slots.mod_base_bins(file) if file.is_file() else []), Path(step.mod_path).name
    else:
        return []
    slot_folder = f"{folder}_slots"
    written = slots.write_mod(injector.game_dir, mods_dir / slot_folder, bins, skip, label) if bins else 0
    if written:
        names.append(slot_folder)
    if not names:
        log.info(f"[OTHERS] Nothing could be made for champion {step.champion_id} ({label}): they keep their own skin")
    elif not written:
        # shortcut: a mod whose base skin Rose cannot read (an unpacked WAD folder) only shows on a player
        # who has no skin on; read such mods in slots.mod_base_bins if that turns out to matter
        log.info(f"[OTHERS] Champion {step.champion_id}: {label} only shows on a player without a skin of their own")
    else:
        log.info(f"[OTHERS] Champion {step.champion_id} will show {label} ({written} skin slots)")
    return names


def prepare_all(injector, state) -> List[str]:
    """Every pick's mods, for an injection (staging prepares them step by step, stage_plan.prepare_plan)."""
    names: List[str] = []
    for step in planned(state):
        try:
            names.extend(prepare(injector, step))
        except Exception as e:  # noqa: BLE001 - another player's skin must never cost the user their own
            log.warning(f"[OTHERS] Could not prepare the skin picked for champion {step.champion_id}: {e}")
    return names
