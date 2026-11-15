"""Draw the charts shown in the README from the exported marts.

Re-run every month by the pipeline, so the README always shows the latest data.
"""

import argparse
import csv
import json
import zipfile
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

NAVY = "#1F3A5F"
ORANGE = "#D9822B"
GREY = "#8A94A6"
LIGHT = "#C9D3E0"
STEEL = "#5C7FA8"
PALE = "#ECEFF3"
TOLL_START = date(2025, 1, 5)
SOURCE = "Data: NYC Taxi & Limousine Commission, yellow taxi trips"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def style(fig, ax, title: str, subtitle: str) -> None:
    fig.text(0.012, 0.965, title, fontsize=14, fontweight="bold", color="#1B2733", va="top")
    fig.text(0.012, 0.905, subtitle, fontsize=9.5, color=GREY, va="top")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LIGHT)
    ax.tick_params(colors="#4A5565", labelsize=9)


def footer(fig, last_month: str) -> None:
    fig.text(0.012, 0.012, f"{SOURCE}, Jan 2023 to {last_month}.", fontsize=8, color=GREY)
    fig.tight_layout(rect=(0, 0.035, 1, 0.84))


def chart_monthly_gap(exports: Path, out: Path, last_month: str, control: str) -> None:
    rows = [r for r in read_csv(exports / "mart_toll_effect_monthly.csv") if r["segment"] == "within_zone"]
    months = [date.fromisoformat(r["month_start"]) for r in rows]
    ratio = [float(r["speed_ratio"]) * 100 for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.axvspan(TOLL_START, max(months).replace(day=28), color=PALE, zorder=0)
    ax.plot(months, ratio, color=NAVY, linewidth=2, marker="o", markersize=3.5, zorder=3)

    # yearly averages, to make the change after the toll easy to read
    for year in sorted({m.year for m in months}):
        values = [v for m, v in zip(months, ratio) if m.year == year]
        start, end = date(year, 1, 1), max(m for m in months if m.year == year).replace(day=28)
        mean = sum(values) / len(values)
        color = ORANGE if year >= TOLL_START.year else GREY
        ax.hlines(mean, start, end, colors=color, linestyles="--", linewidth=1.2, zorder=2)
        label_x = start.replace(day=20) if year == TOLL_START.year else start
        ax.text(label_x, min(ratio) - 1.6, f"{year} average: {mean:.1f}%", fontsize=8.5, color=color,
                va="bottom", zorder=5)

    ax.axvline(TOLL_START, color=ORANGE, linewidth=1.5)
    ax.text(TOLL_START, max(ratio) + 0.8, "  Toll starts, 5 Jan 2025", color=ORANGE, fontsize=9, va="bottom")
    ax.set_ylim(min(ratio) - 2.2, max(ratio) + 3)
    ax.yaxis.set_major_locator(MultipleLocator(2))
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", color=PALE)
    style(fig, ax, "Taxis inside the toll zone vs the rest of the city",
          f"Monthly average speed of trips within the zone, as a % of the speed of the control group ({control})")
    footer(fig, last_month)
    fig.savefig(out / "speed_gap_monthly.png")
    plt.close(fig)


def chart_effects(exports: Path, out: Path, last_month: str) -> None:
    rows = read_csv(exports / "mart_toll_effect.csv")

    def find(comparison, scope, control=None):
        for r in rows:
            if (r["comparison"], r["scope"], r["segment"]) != (comparison, scope, "within_zone"):
                continue
            if (control is None and r["is_main_estimate"].lower() == "true") or r["control_group"] == control:
                return r
        return None

    def values(r):
        return tuple(float(r[k]) * 100 for k in ("speed_effect_pct", "ci95_low_pct", "ci95_high_pct"))

    def draw(y, r, color, hollow=False):
        mid, low, high = values(r)
        ax.plot([low, high], [y, y], color=color, linewidth=2.2, solid_capstyle="round", alpha=0.55 if hollow else 1)
        ax.plot(mid, y, "o", markersize=7, color=color, markerfacecolor="white" if hollow else color,
                markeredgewidth=1.8)
        ax.text(high + 0.3, y, f"{mid:+.1f}%", va="center", fontsize=8.5, color=color)

    r2026 = find("2026 vs 2024", "all hours")
    main_rows = [
        ("2025 vs 2024, all hours", find("2025 vs 2024", "all hours"), NAVY),
        ("2025 vs 2024, peak hours", find("2025 vs 2024", "peak hours"), NAVY),
        ("2025 vs 2024, overnight", find("2025 vs 2024", "overnight hours"), NAVY),
        (f"2026 vs 2024 ({r2026['months_compared']} months)" if r2026 else None, r2026, NAVY),
        ("Placebo: 2024 vs 2023 (no toll)", find("placebo: 2024 vs 2023", "all hours"), GREY),
    ]
    main_rows = [row for row in main_rows if row[0] and row[1]]
    other_controls = sorted({r["control_group"] for r in rows if r["is_main_estimate"].lower() != "true"})

    n = len(main_rows) + len(other_controls)
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
    labels, positions = [], []
    for i, (label, r, color) in enumerate(main_rows):
        y = n - i + 0.5
        draw(y, r, color)
        labels.append(label)
        positions.append(y)
    for j, control in enumerate(other_controls):
        y = n - len(main_rows) - j
        simple = find("2025 vs 2024", "all hours", control)
        adjusted = find("2025 vs 2024, trend-adjusted", "all hours", control)
        if simple:
            draw(y + 0.17, simple, STEEL)
        if adjusted:
            draw(y - 0.17, adjusted, STEEL, hollow=True)
        labels.append("2025, control: " + control.replace("outside the zone, ", "").replace(" outside the zone", ""))
        positions.append(y)

    ax.axvline(0, color="#4A5565", linewidth=1)
    ax.axhline(n - len(main_rows) + 0.75, color=LIGHT, linewidth=0.8)
    ax.set_yticks(positions, labels, fontsize=9)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
    ax.grid(axis="x", color=PALE)
    ax.set_xlim(ax.get_xlim()[0] - 0.5, ax.get_xlim()[1] + 1.5)
    style(fig, ax, "How much faster did taxis get inside the zone?",
          "Difference-in-differences on daily speeds, 95% confidence intervals. Top: main control group (short trips outside the zone).\n"
          "Bottom: other control groups, filled = simple estimate, hollow = adjusted for the 2023-2024 trend.")
    footer(fig, last_month)
    fig.savefig(out / "toll_effect.png")
    plt.close(fig)


def chart_zone_map(exports: Path, raw_dir: Path, out: Path) -> None:
    shapes_zip = raw_dir / "taxi_zones.zip"
    if not shapes_zip.exists():
        print("  taxi_zones.zip not found, map skipped")
        return
    import shapefile  # pyshp

    zones = {int(r["zone_id"]): r for r in read_csv(exports / "dim_zones.csv")}
    with zipfile.ZipFile(shapes_zip) as archive:
        shp_name = next(n for n in archive.namelist() if n.endswith(".shp"))
    reader = shapefile.Reader(f"{shapes_zip}/{shp_name}")
    fields = [f[0].lower() for f in reader.fields[1:]]

    fig, ax = plt.subplots(figsize=(6.5, 8), dpi=150)
    manhattan_bounds = []
    for shape_record in reader.iterShapeRecords():
        record = dict(zip(fields, shape_record.record))
        zone = zones.get(int(record["locationid"]))
        if zone is None or not shape_record.shape.points:
            continue
        is_crz = zone["is_crz"].lower() == "true"
        if zone["borough"] == "Manhattan":
            manhattan_bounds.append(shape_record.shape.bbox)
        color = ORANGE if is_crz else (LIGHT if zone["borough"] == "Manhattan" else PALE)
        points, parts = shape_record.shape.points, list(shape_record.shape.parts) + [len(shape_record.shape.points)]
        vertices, codes = [], []
        for start, end in zip(parts[:-1], parts[1:]):
            ring = points[start:end]
            vertices += ring
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(ring) - 1)
        ax.add_patch(PathPatch(MplPath(vertices, codes), facecolor=color, edgecolor="white", linewidth=0.4))

    if manhattan_bounds:
        x0 = min(b[0] for b in manhattan_bounds)
        y0 = min(b[1] for b in manhattan_bounds)
        x1 = max(b[2] for b in manhattan_bounds)
        y1 = max(b[3] for b in manhattan_bounds)
        pad_x, pad_y = (x1 - x0) * 0.35, (y1 - y0) * 0.04
        ax.set_xlim(x0 - pad_x, x1 + pad_x)
        ax.set_ylim(y0 - pad_y, y1 + pad_y)
    ax.set_aspect("equal")
    ax.axis("off")
    n_crz = sum(1 for z in zones.values() if z["is_crz"].lower() == "true")
    fig.text(0.03, 0.975, "The toll zone, rebuilt from the data", fontsize=13, fontweight="bold",
             color="#1B2733", va="top")
    fig.text(0.03, 0.94, f"{n_crz} taxi zones (orange) where more than 90% of trips pay\n"
             "the $0.75 congestion fee. Light blue: rest of Manhattan.", fontsize=9, color=GREY, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(out / "toll_zone_map.png")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    summary = json.loads((args.exports / "summary.json").read_text(encoding="utf-8"))
    last_month = date.fromisoformat(summary["last_month"] + "-01").strftime("%b %Y")

    chart_monthly_gap(args.exports, args.out, last_month, summary["main_control_group"])
    chart_effects(args.exports, args.out, last_month)
    chart_zone_map(args.exports, args.raw_dir, args.out)
    print(f"  charts written to {args.out}")


if __name__ == "__main__":
    main()
