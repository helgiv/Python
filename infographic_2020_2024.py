"""
Myndræn framsetning: Umframdauði á Íslandi 2020–2024.
Grunnlína (baseline) = meðaltal 2016–2019.
Heimild: Eurostat.
"""

from __future__ import annotations

import io
import gzip
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
import numpy as np

# Eurostat SDMX 2.1 API
EUROSTAT_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{code}"
    "?format=TSV&compressed=true"
)


@dataclass(frozen=True)
class EurostatFilter:
    geo: str = "IS"
    sex: str = "T"
    unit: str = "NR"


def download_data(code: str, timeout: int = 90) -> bytes:
    url = EUROSTAT_URL.format(code=code)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def parse_tsv_gz(data_gz: bytes) -> pd.DataFrame:
    raw = gzip.decompress(data_gz).decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(raw), sep="\t", dtype=str)
    first = df.columns[0]
    df = df.rename(columns={first: "series_key"})
    df["series_key"] = df["series_key"].str.replace(r"\\TIME_PERIOD$", "", regex=True)
    df["series_key"] = df["series_key"].str.replace(r"\\time$", "", regex=True)
    return df


def split_series_key(df: pd.DataFrame) -> pd.DataFrame:
    parts = df["series_key"].str.split(",", expand=True)
    n = parts.shape[1]
    if n == 5:
        df["freq"] = parts[0]
        df["age"] = parts[1]
        df["sex"] = parts[2]
        df["unit"] = parts[3]
        df["geo"] = parts[4]
    elif n == 4:
        df["unit"] = parts[0]
        df["sex"] = parts[1]
        df["age"] = parts[2]
        df["geo"] = parts[3]
    else:
        df["unit"] = parts[0]
        df["sex"] = parts[1]
        df["geo"] = parts[2]
        df["age"] = "TOTAL"
    df = df.drop(columns=["series_key"])
    return df


def clean_cell(x: str) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == ":" or s == "":
        return None
    m = re.match(r"^-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def parse_week_time(t: str) -> Tuple[int, int]:
    s = t.strip().replace("-", "")
    year = int(s[0:4])
    week = int(s.split("W")[1]) if "W" in s else int(s[4:6])
    return year, week


def age_to_bin(age_code: str) -> str:
    a = str(age_code).upper()
    if a in ("TOTAL", "Y_TOTAL", "T", "ALL"):
        return "TOTAL"
    a = a.replace(" ", "")
    if "LT" in a:
        start = 0
    elif "GE" in a:
        m = re.search(r"GE(\d+)", a)
        start = int(m.group(1)) if m else 85
    elif "+" in a:
        m = re.search(r"(\d+)\+", a)
        start = int(m.group(1)) if m else 85
    elif "-" in a:
        m = re.search(r"(\d+)-(\d+)", a)
        start = int(m.group(1)) if m else 0
    else:
        m = re.search(r"(\d+)", a)
        start = int(m.group(1)) if m else -1
    if start < 0:
        return "OTHER"
    if start <= 14:
        return "0-14"
    if start <= 64:
        return "15-64"
    if start <= 74:
        return "65-74"
    if start <= 84:
        return "75-84"
    return "85+"


def load_and_process_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Hlaða vikulegum dánartölum á Íslandi og reikna umframdauða fyrir 2020-2024."""
    gz = download_data("demo_r_mwk_05")
    wide = parse_tsv_gz(gz)
    wide = split_series_key(wide)

    filt = EurostatFilter()
    sub = wide[
        (wide["geo"] == filt.geo)
        & (wide["sex"] == filt.sex)
        & (wide["unit"] == filt.unit)
    ].copy()

    id_cols = ["geo", "sex", "unit", "age"]
    if "freq" in sub.columns:
        id_cols.append("freq")
    time_cols = [c for c in sub.columns if c not in id_cols]

    long = sub.melt(
        id_vars=id_cols, value_vars=time_cols, var_name="time", value_name="raw"
    )
    long["deaths"] = long["raw"].map(clean_cell)
    long = long.dropna(subset=["deaths"]).copy()

    years, weeks = zip(*[parse_week_time(t) for t in long["time"]])
    long["year"] = list(years)
    long["week"] = list(weeks)
    long["age_bin"] = long["age"].map(age_to_bin)

    # Filter to relevant age bins
    bins = ["0-14", "15-64", "65-74", "75-84", "85+"]
    df = long[long["age_bin"].isin(bins)].copy()

    # Weekly aggregation by age_bin
    weekly = df.groupby(["age_bin", "year", "week"], as_index=False)["deaths"].sum()

    # Add TOTAL
    total = weekly.groupby(["year", "week"], as_index=False)["deaths"].sum()
    total["age_bin"] = "TOTAL"
    weekly = pd.concat([weekly, total], ignore_index=True)

    # Baseline = mean 2016-2019
    baseline = weekly[weekly["year"].between(2016, 2019)].copy()
    expected = baseline.groupby(["age_bin", "week"], as_index=False)["deaths"].mean()
    expected = expected.rename(columns={"deaths": "expected"})

    # Merge and compute excess
    weekly = weekly.merge(expected, on=["age_bin", "week"], how="left")
    weekly = weekly.dropna(subset=["expected"])
    weekly["excess"] = weekly["deaths"] - weekly["expected"]

    # Annual stats
    annual = weekly.groupby(["age_bin", "year"], as_index=False).agg(
        deaths=("deaths", "sum"),
        expected=("expected", "sum"),
        excess=("excess", "sum"),
    )
    annual["excess_pct"] = (annual["excess"] / annual["expected"]) * 100

    # Filter to 2020-2024 only
    annual_2020_2024 = annual[annual["year"].between(2020, 2024)].copy()

    # Summary stats for the period
    summary = annual_2020_2024.groupby("age_bin", as_index=False).agg(
        total_deaths=("deaths", "sum"),
        total_expected=("expected", "sum"),
        total_excess=("excess", "sum"),
    )
    summary["excess_pct"] = (summary["total_excess"] / summary["total_expected"]) * 100
    summary["avg_annual_excess"] = summary["total_excess"] / 5

    return annual_2020_2024, summary


def create_infographic(
    annual: pd.DataFrame, summary: pd.DataFrame, outpath: str
) -> None:
    """Create a striking infographic focused on 2020-2024 excess mortality."""

    # Nútíma dökk litapalletta
    COLORS = {
        "bg": "#1a1a2e",  # Dökk blár bakgrunnur
        "card": "#16213e",  # Smá ljósari bakgrunnur korts
        "accent1": "#e94560",  # Líflegur rauður/bleikur
        "accent2": "#0f3460",  # Djúpblár
        "highlight": "#f39c12",  # Appelsínugulur fyrir áherslur
        "text": "#eef0f2",  # Ljós texti
        "text_muted": "#8892a0",  # Daufur texti
        "positive": "#e74c3c",  # Rauður fyrir umfram
        "negative": "#27ae60",  # Grænn fyrir skort
        "bar_2020": "#3498db",
        "bar_2021": "#9b59b6",
        "bar_2022": "#e74c3c",
        "bar_2023": "#e67e22",
        "bar_2024": "#f1c40f",
    }

    YEAR_COLORS = {
        2020: "#3498db",
        2021: "#9b59b6",
        2022: "#e74c3c",
        2023: "#e67e22",
        2024: "#f1c40f",
    }

    AGE_LABELS_IS = {
        "TOTAL": "Samtals",
        "0-14": "0–14 ára",
        "15-64": "15–64 ára",
        "65-74": "65–74 ára",
        "75-84": "75–84 ára",
        "85+": "85+ ára",
    }

    # Sækja grunn tölur
    total_summary = summary[summary["age_bin"] == "TOTAL"].iloc[0]
    total_excess = int(total_summary["total_excess"])
    total_excess_pct = total_summary["excess_pct"]
    avg_annual = total_summary["avg_annual_excess"]

    # Setup figure
    fig = plt.figure(figsize=(16, 12), facecolor=COLORS["bg"])

    # Custom grid
    gs = GridSpec(
        4,
        3,
        height_ratios=[1.2, 2.5, 2.5, 0.6],
        width_ratios=[1, 1, 1],
        hspace=0.3,
        wspace=0.25,
        left=0.06,
        right=0.94,
        top=0.95,
        bottom=0.05,
    )

    # =========================================================================
    # Haus - Fyrirsögn og lykiltölur
    # =========================================================================
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.set_facecolor(COLORS["bg"])
    ax_header.axis("off")

    # Aðal fyrirsögn
    ax_header.text(
        0.5,
        0.85,
        "UMFRAMDAUÐI Á ÍSLANDI",
        fontsize=36,
        fontweight="bold",
        ha="center",
        va="top",
        color=COLORS["text"],
        transform=ax_header.transAxes,
        fontfamily="sans-serif",
    )

    ax_header.text(
        0.5,
        0.55,
        "2020–2024",
        fontsize=28,
        ha="center",
        va="top",
        color=COLORS["accent1"],
        transform=ax_header.transAxes,
        fontweight="bold",
    )

    ax_header.text(
        0.5,
        0.25,
        "miðað við grunnlínu (meðaltal 2016–2019)",
        fontsize=14,
        ha="center",
        va="top",
        color=COLORS["text_muted"],
        transform=ax_header.transAxes,
        style="italic",
    )

    # =========================================================================
    # Lína 2: Rammar með stórum tölum
    # =========================================================================
    # Card 1: Total excess deaths
    ax_card1 = fig.add_subplot(gs[1, 0])
    ax_card1.set_facecolor(COLORS["card"])
    ax_card1.axis("off")
    for spine in ax_card1.spines.values():
        spine.set_visible(False)

    # Teikna rúnaðan rétthyrningsbakgrunn
    rect1 = FancyBboxPatch(
        (0.05, 0.05),
        0.9,
        0.9,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=COLORS["card"],
        edgecolor=COLORS["accent1"],
        linewidth=3,
        transform=ax_card1.transAxes,
        clip_on=False,
    )
    ax_card1.add_patch(rect1)

    ax_card1.text(
        0.5,
        0.75,
        f"+{total_excess:,}".replace(",", "."),
        fontsize=48,
        fontweight="bold",
        ha="center",
        va="center",
        color=COLORS["accent1"],
        transform=ax_card1.transAxes,
    )
    ax_card1.text(
        0.5,
        0.4,
        "umframdauðsföll",
        fontsize=16,
        ha="center",
        va="center",
        color=COLORS["text"],
        transform=ax_card1.transAxes,
    )
    ax_card1.text(
        0.5,
        0.2,
        "á 5 árum (2020–2024)",
        fontsize=12,
        ha="center",
        va="center",
        color=COLORS["text_muted"],
        transform=ax_card1.transAxes,
    )

    # Rammi 2: Prósenta umframdauða
    ax_card2 = fig.add_subplot(gs[1, 1])
    ax_card2.set_facecolor(COLORS["card"])
    ax_card2.axis("off")

    rect2 = FancyBboxPatch(
        (0.05, 0.05),
        0.9,
        0.9,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=COLORS["card"],
        edgecolor=COLORS["highlight"],
        linewidth=3,
        transform=ax_card2.transAxes,
        clip_on=False,
    )
    ax_card2.add_patch(rect2)

    ax_card2.text(
        0.5,
        0.75,
        f"+{total_excess_pct:.1f}%",
        fontsize=48,
        fontweight="bold",
        ha="center",
        va="center",
        color=COLORS["highlight"],
        transform=ax_card2.transAxes,
    )
    ax_card2.text(
        0.5,
        0.4,
        "umframdauði",
        fontsize=16,
        ha="center",
        va="center",
        color=COLORS["text"],
        transform=ax_card2.transAxes,
    )
    ax_card2.text(
        0.5,
        0.2,
        "meðaltal tímabilsins",
        fontsize=12,
        ha="center",
        va="center",
        color=COLORS["text_muted"],
        transform=ax_card2.transAxes,
    )

    # Rammi 3: Meðaltal á ári
    ax_card3 = fig.add_subplot(gs[1, 2])
    ax_card3.set_facecolor(COLORS["card"])
    ax_card3.axis("off")

    rect3 = FancyBboxPatch(
        (0.05, 0.05),
        0.9,
        0.9,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=COLORS["card"],
        edgecolor="#3498db",
        linewidth=3,
        transform=ax_card3.transAxes,
        clip_on=False,
    )
    ax_card3.add_patch(rect3)

    ax_card3.text(
        0.5,
        0.75,
        f"+{int(avg_annual):,}".replace(",", "."),
        fontsize=48,
        fontweight="bold",
        ha="center",
        va="center",
        color="#3498db",
        transform=ax_card3.transAxes,
    )
    ax_card3.text(
        0.5,
        0.4,
        "á ári að meðaltali",
        fontsize=16,
        ha="center",
        va="center",
        color=COLORS["text"],
        transform=ax_card3.transAxes,
    )
    ax_card3.text(
        0.5,
        0.2,
        "umfram væntanlegan fjölda",
        fontsize=12,
        ha="center",
        va="center",
        color=COLORS["text_muted"],
        transform=ax_card3.transAxes,
    )

    # =========================================================================
    # Lína 3, vinstra megin: Súlurit eftir árum
    # =========================================================================
    ax_years = fig.add_subplot(gs[2, :2])
    ax_years.set_facecolor(COLORS["card"])

    total_annual = annual[annual["age_bin"] == "TOTAL"].sort_values("year")
    years = total_annual["year"].values
    excess_pcts = total_annual["excess_pct"].values
    excess_counts = total_annual["excess"].values

    bars = ax_years.bar(
        years,
        excess_pcts,
        color=[YEAR_COLORS[y] for y in years],
        edgecolor="white",
        linewidth=2,
        width=0.7,
    )

    ax_years.axhline(0, color=COLORS["text_muted"], linewidth=1, linestyle="-")

    # Bæta við merkjum á súlur
    for bar, pct, cnt, yr in zip(bars, excess_pcts, excess_counts, years):
        height = bar.get_height()
        # Prósenta ofan á súlu
        ax_years.text(
            bar.get_x() + bar.get_width() / 2,
            height + 0.8,
            f"{pct:+.1f}%",
            ha="center",
            va="bottom",
            fontsize=14,
            fontweight="bold",
            color=YEAR_COLORS[yr],
        )
        # Fjöldi inni í súlu
        ax_years.text(
            bar.get_x() + bar.get_width() / 2,
            height / 2,
            f"+{int(cnt)}",
            ha="center",
            va="center",
            fontsize=11,
            color="white",
            fontweight="bold",
        )

    ax_years.set_ylabel(
        "Umframdauði (%)", fontsize=13, color=COLORS["text"], labelpad=10
    )
    ax_years.set_xlabel("", fontsize=12)
    ax_years.set_title(
        "Umframdauði eftir árum",
        fontsize=16,
        fontweight="bold",
        color=COLORS["text"],
        pad=15,
    )
    ax_years.set_xticks(years)
    ax_years.set_xticklabels([str(y) for y in years], fontsize=13, color=COLORS["text"])
    ax_years.tick_params(axis="y", colors=COLORS["text"], labelsize=11)
    ax_years.set_ylim(bottom=-2, top=max(excess_pcts) + 4)

    for spine in ax_years.spines.values():
        spine.set_color(COLORS["text_muted"])
        spine.set_linewidth(0.5)
    ax_years.spines["top"].set_visible(False)
    ax_years.spines["right"].set_visible(False)

    # =========================================================================
    # Lína 3, hægra megin: Eftir aldurshópum (láréttar súlur)
    # =========================================================================
    ax_age = fig.add_subplot(gs[2, 2])
    ax_age.set_facecolor(COLORS["card"])

    age_order = ["85+", "75-84", "65-74", "15-64", "0-14"]
    age_summary = summary[summary["age_bin"].isin(age_order)].set_index("age_bin")

    y_pos = np.arange(len(age_order))
    age_pcts = [age_summary.loc[a, "excess_pct"] for a in age_order]
    age_excess = [int(age_summary.loc[a, "total_excess"]) for a in age_order]

    # Litir súlur byggðar á jákvæðum/neikvæðum gildum
    bar_colors = [COLORS["positive"] if p > 0 else COLORS["negative"] for p in age_pcts]

    bars_h = ax_age.barh(
        y_pos, age_pcts, color=bar_colors, edgecolor="white", linewidth=1.5, height=0.65
    )

    ax_age.axvline(0, color=COLORS["text_muted"], linewidth=1)

    # Merki
    for i, (bar, pct, cnt) in enumerate(zip(bars_h, age_pcts, age_excess)):
        width = bar.get_width()
        label_x = width + 0.5 if width > 0 else width - 0.5
        ha = "left" if width > 0 else "right"
        sign = "+" if cnt > 0 else ""
        ax_age.text(
            label_x,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:+.1f}% ({sign}{cnt})",
            ha=ha,
            va="center",
            fontsize=10,
            color=COLORS["text"],
            fontweight="bold",
        )

    ax_age.set_yticks(y_pos)
    ax_age.set_yticklabels(
        [AGE_LABELS_IS[a] for a in age_order], fontsize=11, color=COLORS["text"]
    )
    ax_age.set_xlabel("Umframdauði (%)", fontsize=11, color=COLORS["text"])
    ax_age.set_title(
        "Eftir aldurshópum\n(2020–2024 samtals)",
        fontsize=14,
        fontweight="bold",
        color=COLORS["text"],
        pad=10,
    )
    ax_age.tick_params(axis="x", colors=COLORS["text"], labelsize=10)

    for spine in ax_age.spines.values():
        spine.set_color(COLORS["text_muted"])
        spine.set_linewidth(0.5)
    ax_age.spines["top"].set_visible(False)
    ax_age.spines["right"].set_visible(False)

    # =========================================================================
    # Fótur
    # =========================================================================
    ax_footer = fig.add_subplot(gs[3, :])
    ax_footer.set_facecolor(COLORS["bg"])
    ax_footer.axis("off")

    # Útskýringatexti (miðja)
    ax_footer.text(
        0.5,
        0.7,
        "Umframdauði = raunverulegur fjöldi dauðsfalla – væntanlegur fjöldi (meðaltal 2016–2019 eftir viku og aldri)",
        fontsize=10,
        ha="center",
        va="center",
        color=COLORS["text_muted"],
        transform=ax_footer.transAxes,
        style="italic",
    )

    # Heimild (neðst vinstra megin)
    ax_footer.text(
        0.0,
        0.15,
        "Heimild: Eurostat (demo_r_mwk_05)",
        fontsize=10,
        ha="left",
        va="bottom",
        color=COLORS["text_muted"],
        transform=ax_footer.transAxes,
    )

    # Dagsetning (neðst hægra megin)
    ax_footer.text(
        1.0,
        0.15,
        f"Unnið - HÖV: {datetime.now().strftime('%d.%m.%Y')}",
        fontsize=10,
        ha="right",
        va="bottom",
        color=COLORS["text_muted"],
        transform=ax_footer.transAxes,
    )

    plt.savefig(outpath, dpi=220, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close()
    print(f"Myndræn framsetning vistuð: {outpath}")


def main() -> None:
    os.makedirs("out", exist_ok=True)

    print("Sæki gögn frá Eurostat...")
    annual, summary = load_and_process_data()

    # Geymum gögnin í csv skrám fyrir frekari vinnslu
    print("Vistuð gögn í CSV skrám...")
    annual.to_csv("out/excess_2020_2024_annual.csv", index=False)
    summary.to_csv("out/excess_2020_2024_summary.csv", index=False)

    print("Bý til myndræna framsetningu...")
    create_infographic(annual, summary, "out/iceland_umframdaudi_2020_2024.png")

    # Samantekt í textaformi
    print("\n" + "=" * 65)
    print("  UMFRAMDAUÐI Á ÍSLANDI 2020–2024 (grunnlína: 2016–2019)")
    print("=" * 65)

    total = summary[summary["age_bin"] == "TOTAL"].iloc[0]
    print(
        f"\n  Heildarumframdauði:     +{int(total['total_excess']):,} manns".replace(
            ",", "."
        )
    )
    print(f"  Umframdauði (%):        +{total['excess_pct']:.1f}%")
    print(f"  Að meðaltali á ári:     +{int(total['avg_annual_excess'])} manns")

    print("\n  Eftir árum:")
    print("  " + "-" * 40)
    total_annual = annual[annual["age_bin"] == "TOTAL"].sort_values("year")
    for _, row in total_annual.iterrows():
        print(
            f"    {int(row['year'])}: {row['excess_pct']:+6.1f}%  ({int(row['excess']):+4} manns)"
        )

    print("\n  Eftir aldurshópum (2020–2024 samtals):")
    print("  " + "-" * 40)
    for age in ["0-14", "15-64", "65-74", "75-84", "85+"]:
        row = summary[summary["age_bin"] == age].iloc[0]
        print(
            f"    {age:>6} ára: {row['excess_pct']:+6.1f}%  ({int(row['total_excess']):+5} manns)"
        )

    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
