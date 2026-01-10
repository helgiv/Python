#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Myndræn framsetning: Umframdauði á Íslandi – samanburður 2016–2019 og 2020–2024.
Hönnuð fyrir birtingu í Morgunblaðinu.
Allur texti á íslensku. Heimild: Eurostat.
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


def load_iceland_weekly() -> pd.DataFrame:
    """Load and process Iceland weekly deaths by age from Eurostat."""
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

    return long


def compute_period_stats(
    long: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compute excess mortality stats for periods 2016-2019 and 2020-2024."""
    bins = ["0-14", "15-64", "65-74", "75-84", "85+"]
    df = long[long["age_bin"].isin(bins)].copy()

    # Aggregate deaths by age_bin, year, week
    weekly = df.groupby(["age_bin", "year", "week"], as_index=False)["deaths"].sum()

    # Add TOTAL
    total = weekly.groupby(["year", "week"], as_index=False)["deaths"].sum()
    total["age_bin"] = "TOTAL"
    weekly = pd.concat([weekly, total], ignore_index=True)

    # Baseline = mean 2016-2019 per (age_bin, week)
    baseline = weekly[weekly["year"].between(2016, 2019)].copy()
    expected = baseline.groupby(["age_bin", "week"], as_index=False)["deaths"].mean()
    expected = expected.rename(columns={"deaths": "expected"})

    # Merge expected
    weekly = weekly.merge(expected, on=["age_bin", "week"], how="left")
    weekly = weekly.dropna(subset=["expected"])
    weekly["excess"] = weekly["deaths"] - weekly["expected"]

    # Annual aggregation
    annual = weekly.groupby(["age_bin", "year"], as_index=False).agg(
        deaths=("deaths", "sum"),
        expected=("expected", "sum"),
        excess=("excess", "sum"),
    )
    annual["excess_pct"] = (annual["excess"] / annual["expected"]) * 100

    # Period aggregation
    def period_label(y):
        if 2016 <= y <= 2019:
            return "2016–2019"
        elif 2020 <= y <= 2024:
            return "2020–2024"
        return None

    annual["period"] = annual["year"].map(period_label)
    annual = annual.dropna(subset=["period"])

    periods = annual.groupby(["age_bin", "period"], as_index=False).agg(
        deaths=("deaths", "sum"),
        expected=("expected", "sum"),
        excess=("excess", "sum"),
        n_years=("year", "count"),
    )
    periods["avg_deaths"] = periods["deaths"] / periods["n_years"]
    periods["avg_expected"] = periods["expected"] / periods["n_years"]
    periods["avg_excess"] = periods["excess"] / periods["n_years"]
    periods["excess_pct"] = (periods["excess"] / periods["expected"]) * 100

    return annual, periods


def create_infographic(
    annual: pd.DataFrame, periods: pd.DataFrame, outpath: str
) -> None:
    """Create a visually striking infographic in Icelandic."""

    # Color scheme - modern, professional
    COLOR_PERIOD1 = "#3498db"  # Blue for 2016-2019
    COLOR_PERIOD2 = "#e74c3c"  # Red for 2020-2024
    COLOR_BG = "#f8f9fa"
    COLOR_TEXT = "#2c3e50"
    COLOR_ACCENT = "#7f8c8d"

    # Icelandic age group labels
    AGE_LABELS_IS = {
        "TOTAL": "Samtals",
        "0-14": "0–14 ára",
        "15-64": "15–64 ára",
        "65-74": "65–74 ára",
        "75-84": "75–84 ára",
        "85+": "85+ ára",
    }

    # Setup figure
    fig = plt.figure(figsize=(14, 10), facecolor=COLOR_BG)
    gs = GridSpec(3, 2, height_ratios=[0.8, 2.5, 0.5], hspace=0.25, wspace=0.25)

    # =========================================================================
    # Title area
    # =========================================================================
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.set_facecolor(COLOR_BG)
    ax_title.axis("off")
    ax_title.text(
        0.5,
        0.7,
        "Umframdauði á Íslandi",
        fontsize=32,
        fontweight="bold",
        ha="center",
        va="center",
        color=COLOR_TEXT,
        transform=ax_title.transAxes,
    )
    ax_title.text(
        0.5,
        0.25,
        "Samanburður tímabila: 2016–2019 og 2020–2024",
        fontsize=18,
        ha="center",
        va="center",
        color=COLOR_ACCENT,
        transform=ax_title.transAxes,
    )

    # =========================================================================
    # Left plot: Bar chart comparing periods by age group
    # =========================================================================
    ax_bars = fig.add_subplot(gs[1, 0])
    ax_bars.set_facecolor(COLOR_BG)

    age_order = ["TOTAL", "0-14", "15-64", "65-74", "75-84", "85+"]
    x = np.arange(len(age_order))
    width = 0.35

    p1_data = periods[periods["period"] == "2016–2019"].set_index("age_bin")
    p2_data = periods[periods["period"] == "2020–2024"].set_index("age_bin")

    vals1 = [
        p1_data.loc[a, "excess_pct"] if a in p1_data.index else 0 for a in age_order
    ]
    vals2 = [
        p2_data.loc[a, "excess_pct"] if a in p2_data.index else 0 for a in age_order
    ]

    bars1 = ax_bars.bar(
        x - width / 2,
        vals1,
        width,
        label="2016–2019",
        color=COLOR_PERIOD1,
        edgecolor="white",
        linewidth=1.5,
    )
    bars2 = ax_bars.bar(
        x + width / 2,
        vals2,
        width,
        label="2020–2024",
        color=COLOR_PERIOD2,
        edgecolor="white",
        linewidth=1.5,
    )

    ax_bars.axhline(0, color=COLOR_TEXT, linewidth=0.8, linestyle="-")
    ax_bars.set_ylabel("Umframdauði (%)", fontsize=12, color=COLOR_TEXT)
    ax_bars.set_xticks(x)
    ax_bars.set_xticklabels(
        [AGE_LABELS_IS[a] for a in age_order], fontsize=11, color=COLOR_TEXT
    )
    ax_bars.tick_params(axis="y", colors=COLOR_TEXT)
    ax_bars.set_title(
        "Umframdauði eftir aldurshópum",
        fontsize=14,
        fontweight="bold",
        color=COLOR_TEXT,
        pad=15,
    )
    ax_bars.legend(loc="upper left", fontsize=11, framealpha=0.9)
    ax_bars.spines["top"].set_visible(False)
    ax_bars.spines["right"].set_visible(False)
    ax_bars.spines["left"].set_color(COLOR_ACCENT)
    ax_bars.spines["bottom"].set_color(COLOR_ACCENT)

    # Add value labels on bars
    for bar, val in zip(bars1, vals1):
        ypos = bar.get_height()
        offset = 0.3 if ypos >= 0 else -0.8
        va = "bottom" if ypos >= 0 else "top"
        ax_bars.text(
            bar.get_x() + bar.get_width() / 2,
            ypos + offset,
            f"{val:.1f}%",
            ha="center",
            va=va,
            fontsize=9,
            color=COLOR_PERIOD1,
        )
    for bar, val in zip(bars2, vals2):
        ypos = bar.get_height()
        offset = 0.3 if ypos >= 0 else -0.8
        va = "bottom" if ypos >= 0 else "top"
        ax_bars.text(
            bar.get_x() + bar.get_width() / 2,
            ypos + offset,
            f"{val:.1f}%",
            ha="center",
            va=va,
            fontsize=9,
            color=COLOR_PERIOD2,
            fontweight="bold",
        )

    # =========================================================================
    # Right plot: Annual trend for TOTAL
    # =========================================================================
    ax_trend = fig.add_subplot(gs[1, 1])
    ax_trend.set_facecolor(COLOR_BG)

    total_annual = annual[annual["age_bin"] == "TOTAL"].sort_values("year")
    years_p1 = total_annual[total_annual["year"].between(2016, 2019)]
    years_p2 = total_annual[total_annual["year"].between(2020, 2024)]

    ax_trend.bar(
        years_p1["year"],
        years_p1["excess_pct"],
        color=COLOR_PERIOD1,
        edgecolor="white",
        linewidth=1.5,
        label="2016–2019",
    )
    ax_trend.bar(
        years_p2["year"],
        years_p2["excess_pct"],
        color=COLOR_PERIOD2,
        edgecolor="white",
        linewidth=1.5,
        label="2020–2024",
    )

    ax_trend.axhline(0, color=COLOR_TEXT, linewidth=0.8)

    # Add horizontal lines for period averages
    avg_p1 = years_p1["excess_pct"].mean()
    avg_p2 = years_p2["excess_pct"].mean()
    ax_trend.axhline(
        avg_p1, color=COLOR_PERIOD1, linewidth=2, linestyle="--", alpha=0.7
    )
    ax_trend.axhline(
        avg_p2, color=COLOR_PERIOD2, linewidth=2, linestyle="--", alpha=0.7
    )

    # Annotate averages
    ax_trend.text(
        2019.5,
        avg_p1 + 0.5,
        f"Meðaltal: {avg_p1:.1f}%",
        fontsize=10,
        color=COLOR_PERIOD1,
        ha="right",
        fontweight="bold",
    )
    ax_trend.text(
        2024.5,
        avg_p2 + 0.5,
        f"Meðaltal: {avg_p2:.1f}%",
        fontsize=10,
        color=COLOR_PERIOD2,
        ha="right",
        fontweight="bold",
    )

    ax_trend.set_ylabel("Umframdauði (%)", fontsize=12, color=COLOR_TEXT)
    ax_trend.set_xlabel("Ár", fontsize=12, color=COLOR_TEXT)
    ax_trend.set_title(
        "Umframdauði eftir árum (samtals)",
        fontsize=14,
        fontweight="bold",
        color=COLOR_TEXT,
        pad=15,
    )
    ax_trend.tick_params(axis="both", colors=COLOR_TEXT)
    ax_trend.set_xticks([2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024])
    ax_trend.legend(loc="upper left", fontsize=11, framealpha=0.9)
    ax_trend.spines["top"].set_visible(False)
    ax_trend.spines["right"].set_visible(False)
    ax_trend.spines["left"].set_color(COLOR_ACCENT)
    ax_trend.spines["bottom"].set_color(COLOR_ACCENT)

    # Add value labels on trend bars
    for _, row in total_annual.iterrows():
        ypos = row["excess_pct"]
        color = COLOR_PERIOD1 if row["year"] <= 2019 else COLOR_PERIOD2
        va = "bottom" if ypos >= 0 else "top"
        offset = 0.4 if ypos >= 0 else -0.4
        ax_trend.text(
            row["year"],
            ypos + offset,
            f"{ypos:.1f}%",
            ha="center",
            va=va,
            fontsize=9,
            color=color,
            fontweight="bold",
        )

    # =========================================================================
    # Bottom area: Key stats and source
    # =========================================================================
    ax_bottom = fig.add_subplot(gs[2, :])
    ax_bottom.set_facecolor(COLOR_BG)
    ax_bottom.axis("off")

    # Key statistics
    diff_pct = avg_p2 - avg_p1
    total_excess_p2 = periods[
        (periods["period"] == "2020–2024") & (periods["age_bin"] == "TOTAL")
    ]["excess"].values[0]

    stats_text = (
        f"Lykilniðurstöður:  •  Meðalumframdauði 2016–2019: {avg_p1:.2f}%  "
        f"•  Meðalumframdauði 2020–2024: {avg_p2:.1f}%  "
        f"•  Munur: +{diff_pct:.1f} prósentustig  "
        f"•  Heildarumframdauði 2020–2024: {int(total_excess_p2):,} manns".replace(
            ",", "."
        )
    )

    ax_bottom.text(
        0.5,
        0.7,
        stats_text,
        fontsize=11,
        ha="center",
        va="center",
        color=COLOR_TEXT,
        transform=ax_bottom.transAxes,
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="white",
            edgecolor=COLOR_ACCENT,
            alpha=0.9,
        ),
    )

    # Source attribution (bottom left)
    ax_bottom.text(
        0.01,
        0.1,
        "Heimild: Eurostat (demo_r_mwk_05) – Vikudauðsföll eftir aldri",
        fontsize=9,
        ha="left",
        va="bottom",
        color=COLOR_ACCENT,
        transform=ax_bottom.transAxes,
        style="italic",
    )

    # Date (bottom right)
    ax_bottom.text(
        0.99,
        0.1,
        f"Unnið - HÖV: {datetime.now().strftime('%d.%m.%Y')}",
        fontsize=9,
        ha="right",
        va="bottom",
        color=COLOR_ACCENT,
        transform=ax_bottom.transAxes,
        style="italic",
    )

    plt.savefig(outpath, dpi=200, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close()
    print(f"Infographic saved: {outpath}")


def main() -> None:
    os.makedirs("out", exist_ok=True)

    print("Sæki gögn frá Eurostat...")
    long = load_iceland_weekly()

    print("Reikna umframdauða...")
    annual, periods = compute_period_stats(long)

    # Save data
    annual.to_csv("out/infographic_annual.csv", index=False)
    periods.to_csv("out/infographic_periods.csv", index=False)

    print("Bý til myndræna framsetningu...")
    create_infographic(annual, periods, "out/island_umframdaudi_infographic.png")

    # Print summary
    print("\n" + "=" * 60)
    print("SAMANTEKT – Umframdauði á Íslandi")
    print("=" * 60)
    for period in ["2016–2019", "2020–2024"]:
        p = periods[(periods["period"] == period) & (periods["age_bin"] == "TOTAL")]
        if not p.empty:
            row = p.iloc[0]
            print(f"\n{period}:")
            print(
                f"  Heildarfjöldi dauðsfalla: {int(row['deaths']):,}".replace(",", ".")
            )
            print(
                f"  Væntanlegur fjöldi:       {int(row['expected']):,}".replace(
                    ",", "."
                )
            )
            print(
                f"  Umframdauði (fjöldi):     {int(row['excess']):+,}".replace(",", ".")
            )
            print(f"  Umframdauði (%):          {row['excess_pct']:+.2f}%")


if __name__ == "__main__":
    main()
