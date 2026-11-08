"""Assign rooms to the new degree's C/2 sessions without changing the 5.2 timetable.

Usage:
    python solucions_5_4.py [proposta-5-2.csv] --out proposta-grau-nou.csv --check

If the proposal is omitted, use proposal-torns.csv beside paquet when available,
otherwise use paquet/proposta_partida.csv.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from horaris.check import _espai_ok
from horaris.model import DIES, carrega_base


def locate_package(start: Path) -> Path:
    for base in (start, *start.parents):
        candidate = base / "paquet"
        if (candidate / "sessions.csv").is_file():
            return candidate
    raise FileNotFoundError(
        "No s'ha trobat paquet/sessions.csv. Desa el script dins del projecte "
        "del repte o passa --paquet amb la ruta de paquet."
    )


def overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", nargs="?", help="Proposta 5.2 en CSV")
    parser.add_argument("--paquet", type=Path, help="Carpeta paquet")
    parser.add_argument("--escenari", type=Path, help="Carpeta de l'escenari grau-nou-40")
    parser.add_argument("--out", default="proposta-grau-nou.csv")
    parser.add_argument("--check", action="store_true", help="Executa el verificador oficial")
    parser.add_argument("--relaxacions", type=Path, help="CSV d'excepcions declarades de la proposta base")
    args = parser.parse_args()

    package = args.paquet.resolve() if args.paquet else locate_package(Path(__file__).resolve().parent)
    scenario = args.escenari.resolve() if args.escenari else package / "escenaris" / "grau-nou-40"
    project = package.parent
    if args.proposal:
        proposal_path = Path(args.proposal).resolve()
    else:
        proposal_path = project / "proposta-torns.csv"
        if not proposal_path.is_file():
            proposal_path = package / "proposta_partida.csv"
    if not proposal_path.is_file():
        raise FileNotFoundError(f"No es troba la proposta base: {proposal_path}")

    sessions = pd.read_csv(package / "sessions.csv", keep_default_na=False, dtype=str)
    scenario_cfg = json.loads((scenario / "escenari.json").read_text(encoding="utf-8"))
    new_path = scenario / scenario_cfg.get("sessions_extra", "sessions_extra.csv")
    new = pd.read_csv(new_path, keep_default_na=False, dtype=str)
    rooms = pd.read_csv(package / "aules.csv", keep_default_na=False, dtype=str)
    proposal = pd.read_csv(proposal_path, keep_default_na=False, dtype=str)

    required = {"id_sessio", "dia", "h_ini", "aula"}
    if not required.issubset(proposal.columns):
        raise ValueError(f"La proposta necessita les columnes: {', '.join(sorted(required))}")
    if proposal["id_sessio"].duplicated().any():
        raise ValueError("La proposta té id_sessio duplicats.")
    new = new[new["semestre"].eq("C/2")].copy()
    if len(new) != 235:
        raise ValueError(f"S'esperaven 235 sessions C/2; se n'han trobat {len(new)}.")
    if set(new.id_sessio) & set(proposal.id_sessio):
        raise ValueError("La proposta ja conté identificadors del grau nou.")

    base = carrega_base(package, semestre=2, escenari=scenario)
    sessions_by_id = sessions.set_index("id_sessio")
    day_to_index = {day: DIES.index(day) for day in DIES}
    room_rows = rooms.set_index("aula").to_dict("index")
    room_capacity = {room: int(float(info["capacitat"])) for room, info in room_rows.items()}
    ordinary = sorted(room for room, info in room_rows.items() if str(info.get("ordinaria", "0")) == "1")
    if not ordinary:
        raise ValueError("No s'han trobat aules ordinàries a paquet/aules.csv")

    # Occupancy uses the actual proposed weekday, not the original weekday in sessions.csv.
    # The verifier derives each date from source date + proposed weekday in the same week.
    by_date_room: dict[tuple[str, str], list[tuple[int, int, str]]] = defaultdict(list)
    proposal_ids = set(proposal.id_sessio)
    unknown = proposal_ids - set(sessions_by_id.index)
    if unknown:
        raise ValueError(f"La proposta conté sessions desconegudes: {sorted(unknown)[:8]}")
    for row in proposal.itertuples(index=False):
        sid = row.id_sessio
        meta = sessions_by_id.loc[sid]
        day = row.dia or meta["dia"]
        if day not in day_to_index:
            raise ValueError(f"Dia no reconegut per {sid}: {day}")
        source_date = pd.Timestamp(meta["data"])
        date = source_date + pd.Timedelta(days=day_to_index[day] - source_date.weekday())
        start_text = row.h_ini or meta["h_ini"]
        start = minutes(start_text)
        end = start + int(meta["durada_min"])
        room = row.aula.strip()
        no_room = str(meta.get("sense_espai", "")).strip().lower() in {"1", "true", "si", "sí"}
        if room and not no_room:
            by_date_room[(date.strftime("%Y-%m-%d"), room)].append((start, end, sid))

    # Empty activitat_id values in sessions_extra.csv are intentional. Fall back to
    # course + activity type + subgroup so repeated meetings share one room correctly.
    new["_key"] = [
        f"A:{row.activitat_id}" if row.activitat_id else f"G:{row.codi}|{row.tipus}|{row.grup}"
        for row in new.itertuples(index=False)
    ]
    groups = list(new.groupby("_key", sort=False))
    groups.sort(key=lambda item: (
        -int(item[1]["alumnes"].astype(int).max()),
        -len(item[1]),
        item[0],
    ))

    room_for_group: dict[str, str] = {}
    assigned: dict[str, str] = {}
    impossible = []
    slots = range(510, 1260, 60)

    def reserve_ok(date: str, start: int, end: int, candidate_room: str,
                   staged: list[tuple[str, int, int]]) -> bool:
        for slot in slots:
            slot_end = slot + 60
            if not overlaps(start, end, slot, slot_end):
                continue
            occupied = set()
            for room in ordinary:
                entries = by_date_room.get((date, room), ())
                if any(overlaps(a, b, slot, slot_end) for a, b, _ in entries):
                    occupied.add(room)
            for staged_date, staged_start, staged_end in staged:
                if staged_date == date and overlaps(staged_start, staged_end, slot, slot_end):
                    occupied.add(candidate_room)
            occupied.add(candidate_room)
            if len(ordinary) - len(occupied) < 2:
                return False
        return True

    for key, rows in groups:
        group_name = rows.iloc[0]["grup"]
        max_size = int(rows["alumnes"].astype(int).max())
        preferred = room_for_group.get(group_name)
        candidates = ([preferred] if preferred else []) + [r for r in ordinary if r != preferred]
        selected = None
        staged: list[tuple[str, int, int]] = []
        for room in candidates:
            if room_capacity[room] < max_size:
                continue
            if any(
                (sid := base.sessions.get(row.id_sessio)) is not None
                and not _espai_ok(base, sid, room)
                for row in rows.itertuples(index=False)
            ):
                continue
            staged = []
            feasible = True
            for row in rows.itertuples(index=False):
                start = minutes(row.h_ini)
                end = start + int(row.durada_min)
                date = row.data
                entries = by_date_room.get((date, room), ())
                if any(overlaps(start, end, old_start, old_end) for old_start, old_end, _ in entries):
                    feasible = False
                    break
                if any(d == date and overlaps(start, end, a, b) for d, a, b in staged):
                    feasible = False
                    break
                if not reserve_ok(date, start, end, room, staged):
                    feasible = False
                    break
                staged.append((date, start, end))
            if feasible:
                selected = room
                break

        if selected is None:
            impossible.append((key, group_name, max_size, len(rows)))
            for sid in rows["id_sessio"]:
                assigned[sid] = ""
            continue

        room_for_group[group_name] = selected
        for row in rows.itertuples(index=False):
            start = minutes(row.h_ini)
            end = start + int(row.durada_min)
            by_date_room[(row.data, selected)].append((start, end, row.id_sessio))
            assigned[row.id_sessio] = selected

    additions = pd.DataFrame([
        {column: {"id_sessio": row.id_sessio, "dia": row.dia, "h_ini": row.h_ini,
                  "aula": assigned[row.id_sessio]}.get(column, "")
         for column in proposal.columns}
        for row in new.itertuples(index=False)
    ], columns=proposal.columns)
    result = pd.concat([proposal, additions], ignore_index=True)
    output = Path(args.out).resolve()
    result.to_csv(output, index=False)

    print(f"Sessions del grau nou (C/2): {len(new)}")
    print(f"Sessions amb aula assignada: {sum(bool(v) for v in assigned.values())}")
    print(f"Activitats sense aula: {len(impossible)}")
    print(f"Proposta escrita a: {output}")
    if impossible:
        print("Activitats sense espai (activitat, grup, aforament, sessions):")
        for item in impossible:
            print("  ", *item)

    check_failed = False
    if args.check:
        command = [
            sys.executable, "-m", "horaris", "check", str(output), "--semestre", "2",
            "--escenari", str(scenario), "--referencia", str(proposal_path),
            "--json", str(output.with_name("informe-grau-nou.json")),
            "--violacions", str(output.with_name("violacions-grau-nou.csv")),
        ]
        relaxations = args.relaxacions
        if relaxations is None:
            default_relax = project / "relaxacions-5_2.csv"
            relaxations = default_relax if default_relax.is_file() else None
        if relaxations:
            command.extend(["--relaxacions", str(relaxations.resolve())])
        print("$", " ".join(command))
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            check_failed = True
            print(f"El verificador ha acabat amb codi {completed.returncode}.")

    return 1 if impossible or check_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
