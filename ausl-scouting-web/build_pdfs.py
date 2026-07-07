#!/usr/bin/env python3
"""Generate polished AUSL team scouting PDFs from the shared static dataset."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.graphics import renderPDF
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from svglib.svglib import svg2rlg

ROOT = Path(__file__).resolve().parent
DATA_PATHS = (ROOT / "data" / "scouting-data.json", ROOT / "data" / "scouting-data-2025-2026.json")
OUTPUT_DIR = ROOT / "output" / "pdf"
LOGO_DIR = ROOT / "assets" / "logos"
FIELD_IMAGE = ROOT / "assets" / "field-clean-v2.svg"
COMPACT_LABEL_ANCHORS = {
    "Third Base": (304, 409),
    "Shortstop": (366, 361),
    "Second Base": (434, 361),
    "First Base": (496, 409),
}
PAGE_W, PAGE_H = landscape(letter)
MARGIN = 28
INK = colors.HexColor("#101820")
MUTED = colors.HexColor("#67747C")
LINE = colors.HexColor("#B8C0C5")
SOFT = colors.HexColor("#E8ECEE")


def value(number: Any, digits: int = 2, signed: bool = False) -> str:
    if number is None:
        return "-"
    parsed = float(number)
    prefix = "+" if signed and parsed > 0 else ""
    return f"{prefix}{parsed:.{digits}f}"


def rate(number: Any) -> str:
    if number is None:
        return "-"
    text = f"{float(number):.3f}"
    return text[1:] if text.startswith("0") else "-" + text[2:] if text.startswith("-0") else text


def percent(number: Any, digits: int = 1) -> str:
    return "-" if number is None else f"{float(number) * 100:.{digits}f}%"


def ordinal(number: int) -> str:
    if 11 <= number % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def logo_path(team: dict[str, Any]) -> Path | None:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = LOGO_DIR / f"{team['key']}.svg"
    try:
        if not svg_path.exists():
            urllib.request.urlretrieve(team["logo"], svg_path)
        return svg_path
    except Exception:
        return svg_path if svg_path.exists() else None


class Report:
    def __init__(self, path: Path, team: dict[str, Any], data: dict[str, Any]):
        self.path = path
        self.team = team
        self.data = data
        self.players = {player["key"]: player for player in data["players"]}
        self.c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
        self.page = 0
        self.team_color = colors.HexColor(team["color"])

    def new_page(self, title: str | None = None, footer: bool = False):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.c.setFillColor(colors.white)
        self.c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        if title:
            self.c.setFillColor(INK)
            self.c.setFont("Helvetica-Bold", 18)
            self.c.drawCentredString(PAGE_W / 2, PAGE_H - 39, title)
            self.c.setStrokeColor(self.team_color)
            self.c.setLineWidth(3)
            self.c.line(MARGIN, PAGE_H - 52, PAGE_W - MARGIN, PAGE_H - 52)

    def draw_table(self, rows, x, y_top, width, col_widths=None, font_size=7, header=True, row_height=None, style=None):
        if not rows:
            return y_top
        if col_widths is None:
            col_widths = [width / len(rows[0])] * len(rows[0])
        table = Table(rows, colWidths=col_widths, rowHeights=row_height)
        commands = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", font_size),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", font_size)]
        if style:
            commands.extend(style)
        table.setStyle(TableStyle(commands))
        _, height = table.wrapOn(self.c, width, PAGE_H)
        table.drawOn(self.c, x, y_top - height)
        return y_top - height

    def cover(self):
        self.new_page(footer=False)
        self.c.setFillColor(colors.HexColor("#071B2B"))
        self.c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        self.c.setFillColor(self.team_color)
        self.c.rect(0, 0, 18, PAGE_H, fill=1, stroke=0)
        logo = logo_path(self.team)
        if logo:
            drawing = svg2rlg(str(logo))
            if drawing:
                scale = min(190 / drawing.width, 115 / drawing.height)
                drawing.scale(scale, scale)
                self.c.saveState()
                renderPDF.draw(drawing, self.c, 58, PAGE_H - 177)
                self.c.restoreState()
        self.c.setFillColor(colors.white)
        self.c.setFont("Helvetica-Bold", 12)
        self.c.drawString(58, PAGE_H - 220, "2026 AUSL")
        self.c.setFont("Helvetica-Bold", 31)
        self.c.drawString(58, PAGE_H - 258, "Scouting Report")
        self.c.setFont("Helvetica", 22)
        self.c.drawString(58, PAGE_H - 292, self.team["name"])
        self.c.setFillColor(colors.HexColor("#A9BBC7")); self.c.setFont("Helvetica-Bold",9)
        self.c.drawString(58,PAGE_H-316,f"PLAYER DATA: {self.data['meta']['periodLabel']}")

        summary = self.team["summary"]; ranks = self.team["rankings"]
        record = self.team["record"]
        cards = [
            ("Record", f"{record['wins']}-{record['losses']}", ranks["record"]),
            ("Runs/Game", value(summary["runsPerGame"]), ranks["runsPerGame"]),
            ("ERA", value(summary["ERA"]), ranks["ERA"]),
            ("OPS", rate(summary["OPS"]), ranks["OPS"]),
        ]
        card_x, card_y, card_w, card_h = 385, PAGE_H - 184, 165, 91
        for index, (label, stat, rank) in enumerate(cards):
            x = card_x + (index % 2) * (card_w + 12); y = card_y - (index // 2) * (card_h + 12)
            self.c.setFillColor(colors.HexColor("#102A3D")); self.c.roundRect(x, y, card_w, card_h, 4, fill=1, stroke=0)
            self.c.setFillColor(colors.HexColor("#A9BBC7")); self.c.setFont("Helvetica-Bold", 8); self.c.drawString(x + 13, y + 66, label.upper())
            self.c.setFillColor(colors.white); self.c.setFont("Helvetica-Bold", 24); self.c.drawString(x + 13, y + 31, stat)
            self.c.setFillColor(self.team_color); self.c.setFont("Helvetica-Bold", 8); self.c.drawRightString(x + card_w - 13, y + 67, f"{ordinal(rank)} OF 6")

    def hitting_summary(self, hitters):
        self.new_page("Hitting Summary")
        headers = ["Player","PA","AB","H","HR","XBH","SBA","Bunt","BA","OBP","SLG","OPS","K%","BB%","GB%","wOBA","wRAA","Off WAR","BsR"]
        rows = [headers]
        for player in hitters:
            s = player["hitting"]; a = player.get("advancedHitting") or {}
            rows.append([player["name"],s["PA"],s["AB"],s["H"],s["HR"],s["XBH"],s["SBA"],s["Bunts"],rate(s["BA"]),rate(s["OBP"]),rate(s["SLG"]),rate(s["OPS"]),percent(s["K_pct"]),percent(s["BB_pct"]),percent(s["GB_pct"]),rate(a.get("wOBA")),value(a.get("wRAA"),1,True),value(a.get("offensive_war"),2,True),value(a.get("baserunning_runs"),1,True)])
        widths = [83] + [27] * 7 + [32] * 8 + [34,38,32]
        table_width = sum(widths)
        self.draw_table(rows, (PAGE_W-table_width)/2, PAGE_H - 70, table_width, widths, 5.4, row_height=18)

    def pitching_summary(self, pitchers):
        self.new_page("Pitching Summary")
        rows = [["Pitcher","App","IP","ERA","FIP","WHIP","SO/7","BB/7","S%","WAR"]]
        for player in pitchers:
            s = player["pitching"]; a = player.get("advancedPitching") or {}
            rows.append([player["name"],s["App"],value(s["IP"],1),value(s["ERA"]),value(a.get("FIP")),value(s["WHIP"]),value(s["SO7"]),value(s["BB7"]),percent(s["S_pct"]),value(a.get("pitcher_war"),2,True)])
        widths = [150,48,52,58,58,58,58,58,58,70]
        table_width = sum(widths)
        self.draw_table(rows, (PAGE_W-table_width)/2, PAGE_H - 82, table_width, widths, 8, row_height=22)

    def fielding_summary(self, roster):
        self.new_page("Fielding Summary")
        rows = [["Player","Errors","Chances","Fielding %","Range Runs","Arm Runs","Def WAR"]]
        for player in roster:
            fielding = player.get("fielding") or {}; advanced = player.get("advancedHitting") or {}
            if fielding.get("totalChances"):
                rows.append([player["name"],fielding.get("errors",0),fielding.get("totalChances",0),rate(fielding.get("fieldingPct")),value(advanced.get("range_runs"),1,True),value(advanced.get("throwing_runs"),1,True),value(advanced.get("defensive_war"),2,True)])
        widths = [170,65,70,80,76,76,70]
        table_width = sum(widths)
        self.draw_table(rows, (PAGE_W-table_width)/2, PAGE_H - 82, table_width, widths, 8, row_height=22)

    def draw_spray(self, player, x, y, width, height, labels=True):
        counts = player["spray"]["counts"]; total = player["spray"]["total"]
        field_width, field_height = self.data["field"]["width"], self.data["field"]["height"]
        sx, sy = width / field_width, height / field_height
        self.c.setFillColor(colors.white); self.c.rect(x, y, width, height, fill=1, stroke=0)
        self.c.saveState()
        self.c.setStrokeColor(colors.HexColor("#3F464A")); self.c.setLineWidth(.45)
        label_positions = []
        for location, points in self.data["field"]["zones"].items():
            share = counts.get(location,0) / total if total else 0
            fill = colors.HexColor("#075B2A") if share > .30 else colors.HexColor("#4D9348") if share > .20 else colors.HexColor("#ACD276") if share > .10 else colors.white
            self.c.setFillColor(fill)
            path = self.c.beginPath(); path.moveTo(x + points[0][0]*sx, y + height - points[0][1]*sy)
            for px, py in points[1:]: path.lineTo(x + px*sx, y + height - py*sy)
            path.close(); self.c.drawPath(path, fill=1, stroke=1)
            if labels and counts.get(location,0):
                anchor = COMPACT_LABEL_ANCHORS.get(location) or self.data["field"].get("labelAnchors", {}).get(location)
                cx = x + (anchor[0] if anchor else sum(p[0] for p in points)/len(points))*sx
                cy = y + height - (anchor[1] if anchor else sum(p[1] for p in points)/len(points))*sy
                label_positions.append((cx, cy, share))
        self.c.restoreState()

        drawing = svg2rlg(str(FIELD_IMAGE))
        if drawing:
            self.c.saveState(); self.c.translate(x, y); self.c.scale(width/drawing.width, height/drawing.height)
            renderPDF.draw(drawing, self.c, 0, 0); self.c.restoreState()

        for cx, cy, share in label_positions:
            font_size = 5 if width < 230 else 7
            self.c.setFillColor(colors.white if share > .20 else INK)
            self.c.setFont("Helvetica-Bold",font_size); self.c.drawCentredString(cx,cy-font_size*.33,percent(share,0))
        pc = counts.get("Pitcher",0) + counts.get("Catcher",0); pc_share = pc/total if total else 0
        pc_width, pc_height, pc_font = (62, 11, 4.4) if width < 230 else (74, 14, 5.2)
        self.c.setFillColor(INK); self.c.roundRect(x+width/2-pc_width/2,y+4,pc_width,pc_height,pc_height/2,fill=1,stroke=0)
        self.c.setFillColor(colors.white); self.c.setFont("Helvetica-Bold",pc_font); self.c.drawCentredString(x+width/2,y+4+pc_height*.33,f"Pitcher/Catcher {percent(pc_share,0)}")

    def spray_overview(self, hitters):
        for start in range(0, min(12, len(hitters)), 6):
            self.new_page("Top Player Spray Charts")
            for index, player in enumerate(hitters[start:start+6]):
                col, row = index % 3, index // 3
                x = 32 + col * 248; top = PAGE_H - 72 - row * 258
                self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",9); self.c.drawCentredString(x+110,top,player["name"])
                self.c.setFillColor(MUTED); self.c.setFont("Helvetica",6.5); self.c.drawCentredString(x+110,top-12,f"{player['hitting']['PA']} PA | {rate(player['hitting']['OPS'])} OPS")
                self.draw_spray(player,x+2,top-221,216,184,True)

    def colored_stat_block(self, labels, values, x, y_top, width, columns=4):
        rows = []
        for start in range(0,len(labels),columns):
            label_row = labels[start:start+columns]; value_row = values[start:start+columns]
            while len(label_row)<columns: label_row.append(""); value_row.append("")
            rows.extend([label_row,value_row])
        styles = []
        for row in range(0,len(rows),2):
            styles += [("BACKGROUND",(0,row),(-1,row),self.team_color),("TEXTCOLOR",(0,row),(-1,row),colors.white),("FONT",(0,row),(-1,row),"Helvetica-Bold",6.5)]
        return self.draw_table(rows,x,y_top,width,[width/columns]*columns,7,header=False,row_height=18,style=styles)

    def percentile_rows(self, player, x, y_top, width):
        contexts = player["percentiles"].get("hitting")
        if not contexts:
            return False
        y = y_top
        for label, context in contexts.items():
            raw = context["value"]
            display = rate(raw) if label == "wOBA" else percent(raw) if label in {"BB%","K%","HR rate"} else value(raw,1,True) if label in {"Baserunning","Range","Arm"} else value(raw,2,True)
            display_label = "WAR" if label in {"Position WAR", "Pitcher WAR"} else label
            self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",7); self.c.drawString(x,y,f"{display_label}  {display}")
            bx=x+92; bw=112; self.c.setFillColor(colors.HexColor("#DDE3E6")); self.c.roundRect(bx,y-2,bw,8,4,fill=1,stroke=0)
            self.c.setFillColor(colors.HexColor("#D94C3D") if context["percentile"]>=50 else colors.HexColor("#3978B9")); self.c.circle(bx+bw*context["percentile"]/100,y+2,7,fill=1,stroke=0)
            self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",6.5); self.c.drawRightString(x+width,y+2,f"{context['percentile']}th percentile")
            self.c.setFillColor(MUTED); self.c.setFont("Helvetica",5.7); self.c.drawRightString(x+width,y-7,f"Rank {ordinal(context['rank'])} of {context['of']}")
            y-=20
        return True

    def draw_swing_grid(self, player, x, y_top, width):
        league = {row["count"]: row for row in self.data["leagueApproach"]}
        label_width, gap, cell_height = 28, 3, 40
        cell_width = (width - label_width - gap * 3) / 3
        self.c.setFillColor(MUTED); self.c.setFont("Helvetica-Bold",5.5)
        for strikes in range(3):
            cell_x = x + label_width + gap + strikes * (cell_width + gap)
            self.c.drawCentredString(cell_x + cell_width/2, y_top - 7, f"{strikes} STRIKE{'S' if strikes != 1 else ''}")
        grid_top = y_top - 14
        for balls in range(4):
            cell_y = grid_top - cell_height - balls * (cell_height + gap)
            self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",8)
            self.c.drawCentredString(x + label_width/2, cell_y + 21, str(balls))
            self.c.setFillColor(MUTED); self.c.setFont("Helvetica-Bold",4.5)
            self.c.drawCentredString(x + label_width/2, cell_y + 14, "BALLS")
            for strikes in range(3):
                count = f"{balls}-{strikes}"
                row = next(item for item in player["approach"] if item["count"] == count)
                avg = league[count]
                cell_x = x + label_width + gap + strikes * (cell_width + gap)
                self.c.setFillColor(colors.HexColor("#F6F8F9")); self.c.setStrokeColor(LINE); self.c.setLineWidth(.45)
                self.c.rect(cell_x, cell_y, cell_width, cell_height, fill=1, stroke=1)
                self.c.setFillColor(colors.HexColor("#071B2B")); self.c.rect(cell_x, cell_y + cell_height - 2, cell_width, 2, fill=1, stroke=0)
                self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",6.5); self.c.drawString(cell_x+4,cell_y+cell_height-10,count)
                self.c.setFillColor(MUTED); self.c.setFont("Helvetica",4.5); self.c.drawRightString(cell_x+cell_width-4,cell_y+cell_height-9,f"n={row['pitches']}")
                for index, (label, player_value, league_value) in enumerate((("SWING",row.get("swingPct"),avg.get("swingPct")),("TAKE K",row.get("calledStrikePct"),avg.get("calledStrikePct")))):
                    baseline = cell_y + 18 - index * 11
                    delta = None if player_value is None or league_value is None else (player_value-league_value)*100
                    self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",5.2); self.c.drawString(cell_x+4,baseline,f"{label} {percent(player_value,0)}")
                    self.c.setFillColor(MUTED); self.c.setFont("Helvetica",4.6); self.c.drawCentredString(cell_x+cell_width*.72,baseline,f"Lg {percent(league_value,0)}")
                    delta_color = colors.HexColor("#B33F26") if delta is not None and delta > 2.5 else colors.HexColor("#245E98") if delta is not None and delta < -2.5 else MUTED
                    self.c.setFillColor(delta_color); self.c.setFont("Helvetica-Bold",4.8); self.c.drawRightString(cell_x+cell_width-4,baseline,value(delta,0,True))

    def player_page(self, player):
        self.new_page()
        self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",20)
        prefix=f"#{player['jersey']}  " if player.get("jersey") else ""
        self.c.drawString(32,PAGE_H-39,prefix+player["name"])
        self.c.setFillColor(self.team_color); self.c.rect(32,PAGE_H-51,PAGE_W-150,3,fill=1,stroke=0)
        headshot = ROOT / str(player.get("headshot") or "")
        if player.get("headshot") and headshot.is_file():
            self.c.setFillColor(colors.white); self.c.roundRect(PAGE_W-91,PAGE_H-49,50,47,4,fill=1,stroke=0)
            self.c.drawImage(ImageReader(str(headshot)),PAGE_W-89,PAGE_H-48,46,45,preserveAspectRatio=True,anchor="c",mask="auto")
        self.draw_spray(player,30,PAGE_H-340,315,272,True)
        s=player["hitting"]; a=player.get("advancedHitting") or {}; b=player["baserunning"]
        self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",12); self.c.drawString(375,PAGE_H-75,"Stats")
        standard_labels=["PA","AB","H","K","BB","HR","XBH","SBA","Bunts","HBP","BA","OBP","SLG","OPS","K%","BB%","GB%"]
        standard_values=[s["PA"],s["AB"],s["H"],s["K"],s["BB"],s["HR"],s["XBH"],s["SBA"],s["Bunts"],s["HBP"],rate(s["BA"]),rate(s["OBP"]),rate(s["SLG"]),rate(s["OPS"]),percent(s["K_pct"]),percent(s["BB_pct"]),percent(s["GB_pct"])]
        bottom=self.colored_stat_block(standard_labels,standard_values,375,PAGE_H-86,370,5)
        self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",12); self.c.drawString(375,bottom-27,"Advanced Stats")
        advanced_labels=["wOBA","wRAA","Off WAR","Def WAR","WAR","Range Runs","Arm Runs","BsR","Extra Bases","1st-3rd","2nd-Home","1st-Home"]
        advanced_values=[rate(a.get("wOBA")),value(a.get("wRAA"),1,True),value(a.get("offensive_war"),2,True),value(a.get("defensive_war"),2,True),value(a.get("position_war"),2,True),value(a.get("range_runs"),1,True),value(a.get("throwing_runs"),1,True),value(b.get("runs"),1,True),b.get("extraBasesTaken"),b.get("firstToThird"),b.get("secondToHome"),b.get("firstToHome")]
        bottom=self.colored_stat_block(advanced_labels,advanced_values,375,bottom-38,370,4)
        if player["percentiles"].get("hitting"):
            self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",12); self.c.drawString(32,228,"League Percentiles")
            self.percentile_rows(player,32,209,315)
        self.c.setFillColor(INK); self.c.setFont("Helvetica-Bold",12); self.c.drawString(375,bottom-27,"Swing Decisions")
        self.draw_swing_grid(player,375,bottom-38,370)

    def save(self):
        self.c.save()


def generate_team(team: dict[str, Any], data: dict[str, Any]):
    players={player["key"]:player for player in data["players"]}
    roster=[players[key] for key in team["roster"]]
    hitters=sorted([p for p in roster if p.get("hitting")],key=lambda p:-p["hitting"]["PA"])
    pitchers=sorted([p for p in roster if p.get("pitching")],key=lambda p:-p["pitching"]["IP"])
    output=ROOT/team["pdf"]
    report=Report(output,team,data)
    report.cover(); report.hitting_summary(hitters); report.pitching_summary(pitchers); report.fielding_summary(roster); report.spray_overview(hitters)
    for player in hitters: report.player_page(player)
    report.save(); return output


def main():
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True); outputs=[]
    for path in DATA_PATHS:
        data=json.loads(path.read_text(encoding="utf-8"))
        outputs.extend(generate_team(team,data) for team in data["teams"])
    print(f"Generated {len(outputs)} team PDFs in {OUTPUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
