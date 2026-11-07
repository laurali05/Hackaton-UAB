"""Integrate the fictional 40-student degree into a 5.2 timetable.

Run from anywhere:
    python solucions_5_4.py [proposal.csv] [--out proposal-grau-nou.csv]

If no proposal is supplied, the script uses paquet/proposta_partida.csv.
The real 5.2 output can be passed as the first argument.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import pandas as pd


def locate_package(start: Path) -> Path:
    """Find paquet/ beside this script or in an ancestor project folder."""
    for base in (start, *start.parents):
        candidate = base / "paquet"
        if (candidate / "sessions.csv").is_file():
            return candidate
    raise FileNotFoundError(
        "No s'ha trobat paquet/sessions.csv. Desa el script dins del projecte "
        "del repte o passa --paquet amb la ruta de paquet."
    )


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", nargs="?", help="Proposta 5.2 en CSV")
    parser.add_argument("--paquet", type=Path, help="Carpeta paquet")
    parser.add_argument("--out", default="proposta-grau-nou.csv")
    args = parser.parse_args()

    package = args.paquet.resolve() if args.paquet else locate_package(Path(__file__).resolve().parent)
    proposal_path = Path(args.proposal).resolve() if args.proposal else package / "proposta_partida.csv"
    sessions = pd.read_csv(package / "sessions.csv", keep_default_na=False, dtype=str)
    new_path = package / "escenaris" / "grau-nou-40" / "sessions_extra.csv"
    new = pd.read_csv(new_path, keep_default_na=False, dtype=str)
    rooms = pd.read_csv(package / "aules.csv", keep_default_na=False)
    proposal = pd.read_csv(proposal_path, keep_default_na=False, dtype=str)

    required = {"id_sessio", "dia", "h_ini", "aula"}
    if not required.issubset(proposal.columns):
        raise ValueError(f"La proposta necessita les columnes: {', '.join(sorted(required))}")
    if proposal["id_sessio"].duplicated().any():
        raise ValueError("La proposta té id_sessio duplicats.")

    new = new[new["semestre"] == "C/2"].copy()
    if len(new) != 235:
        raise ValueError(f"S'esperaven 235 sessions C/2; se n'han trobat {len(new)}.")
    if set(new.id_sessio) & set(proposal.id_sessio):
        raise ValueError("La proposta ja conté identificadors del grau nou.")

    # Metadata is used for fixed-session dates/durations and the full room occupancy.
    metadata = pd.concat([sessions, new], ignore_index=True).set_index("id_sessio")
    records = {}
    for sid, row in proposal.set_index("id_sessio").iterrows():
        if sid not in metadata.index:
            continue
        meta = metadata.loc[sid]
        if isinstance(meta, pd.DataFrame):
            meta = meta.iloc[0]
        day = row["dia"] or meta["dia"]
        start = row["h_ini"] or meta["h_ini"]
        end = minutes(start) + int(meta["durada_min"])
        records[sid] = {
            "date": meta["data"], "day": day, "start": minutes(start),
            "end": end, "room": row["aula"].strip(),
        }

    room_rows = rooms.set_index("aula").to_dict("index")
    by_date_room = defaultdict(list)
    for sid, r in records.items():
        if r["room"]:
            by_date_room[(r["date"], r["room"])].append((r["start"], r["end"], sid))

    # Group by activity so every weekly meeting of the same group uses one room.
    grouped = list(new.groupby("activitat_id", sort=False))
    grouped.sort(key=lambda item: (-int(item[1]["alumnes"].astype(int).max()), item[0]))
    ordinary = rooms[rooms["ordinaria"].astype(str).eq("1")].sort_values(
        ["capacitat", "aula"], kind="stable"
    )
    room_capacity = dict(zip(rooms.aula, rooms.capacitat.astype(int)))
    assigned = {}
    room_for_activity = {}
    impossible = []

    for activity, rows in grouped:
        candidates = []
        group = rows.iloc[0]["grup"]
        size = int(rows["alumnes"].astype(int).max())
        # Reuse a room already selected for the same fictitious group when feasible.
        preferred = room_for_activity.get(group)
        if preferred:
            candidates.append(preferred)
        candidates.extend(r for r in ordinary["aula"] if r not in candidates)
        selected = None
        for room in candidates:
            if room_capacity[room] < size:
                continue
            conflict = False
            for _, s in rows.iterrows():
                duration = int(s["durada_min"])
                start, end = minutes(s["h_ini"]), minutes(s["h_ini"]) + duration
                for old_start, old_end, _ in by_date_room[(s["data"], room)]:
                    if overlaps(start, end, old_start, old_end):
                        conflict = True
                        break
                if conflict:
                    break
            if not conflict:
                selected = room
                break
        if selected is None:
            impossible.append((activity, group, size, len(rows)))
            selected = "SENSE_AULA"
        else:
            room_for_activity[group] = selected
            for _, s in rows.iterrows():
                start = minutes(s["h_ini"])
                by_date_room[(s["data"], selected)].append(
                    (start, start + int(s["durada_min"]), s["id_sessio"])
                )
        for sid in rows["id_sessio"]:
            assigned[sid] = selected

    additions = pd.DataFrame([
        {"id_sessio": row.id_sessio, "dia": row.dia, "h_ini": row.h_ini,
         "aula": assigned[row.id_sessio]}
        for row in new.itertuples(index=False)
    ], columns=proposal.columns)
    result = pd.concat([proposal, additions], ignore_index=True)
    output = Path(args.out).resolve()
    result.to_csv(output, index=False)

    print(f"Sessions del grau nou (C/2): {len(new)}")
    print(f"Sessions amb aula assignada: {sum(v != 'SENSE_AULA' for v in assigned.values())}")
    print(f"Activitats sense aula: {len(impossible)}")
    print(f"Proposta escrita a: {output}")
    if impossible:
        print("Activitats sense espai (activitat, grup, aforament, sessions):")
        for item in impossible:
            print("  ", *item)


if __name__ == "__main__":
    main()
