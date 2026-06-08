# Entwickelt im Rahmen von DLBDSOOFPP01_D
# Florian Wilkemeyer | Matrikelnummer: 14097437

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import uuid

import altair as alt
alt.renderers.set_embed_options(renderer="canvas", actions=False)
import pandas as pd
import streamlit as st


# ============================================================
# Domänenschicht — fachliche Klassen gemäß UML-Modell
# Bilden die reale Struktur des Studienablaufs ab.
# ============================================================

@dataclass
class Pruefungsleistung:
    """
    Repräsentiert das Ergebnis einer Prüfung zu einem Modul.
    Die Note ist optional, da ein Modul auch ohne benotete
    Leistung als bestanden markiert werden kann.
    """
    bestanden: bool = False
    note: Optional[float] = None

    @property
    def ist_bestanden(self) -> bool:
        """Gibt zurück, ob die Prüfung bestanden wurde."""
        return self.bestanden


@dataclass
class Modul:
    """
    Ein einzelner Kurs im Studienplan.
    Enthält alle relevanten Informationen zu einem Modul
    sowie optional die zugehörige Prüfungsleistung.
    """
    modul_id: str
    titel: str
    kuerzel: str
    ects: int
    druckskript_abgestellt: bool = False
    pruefungsleistung: Optional[Pruefungsleistung] = None

    @property
    def ist_abgeschlossen(self) -> bool:
        """Ein Modul gilt als abgeschlossen, wenn die Prüfung bestanden wurde."""
        return self.pruefungsleistung is not None and self.pruefungsleistung.ist_bestanden

    @property
    def beitrag_ects(self) -> int:
        """Liefert die ECTS-Punkte des Moduls — aber nur wenn es abgeschlossen ist."""
        return int(self.ects) if self.ist_abgeschlossen else 0


@dataclass
class Semester:
    """
    Fasst alle Module eines Semesters zusammen.
    Start- und Enddatum werden als ISO-String gespeichert,
    da JSON kein natives Date-Format kennt.
    """
    nr: int
    start: Optional[str] = None   # ISO-Format: YYYY-MM-DD
    ende: Optional[str] = None    # ISO-Format: YYYY-MM-DD
    module: List[Modul] = field(default_factory=list)

    def ects_summe(self) -> int:
        """Addiert die ECTS aller Module in diesem Semester — unabhängig vom Bestehen."""
        return sum(int(m.ects) for m in self.module)


@dataclass
class Studiengang:
    """
    Der Studiengang als übergeordnete Struktur.
    Enthält alle Semester und damit indirekt alle Module.
    """
    name: str
    regelstudienzeit_jahre: int
    gesamt_ects: int
    semester: List[Semester] = field(default_factory=list)


@dataclass
class Studienplan:
    """
    Enthält die persönlichen Studienziele wie Startdatum,
    geplante Dauer und angestrebten Notendurchschnitt.
    Das Startdatum wird als ISO-String gespeichert.
    """
    startdatum: str   # ISO-Format: YYYY-MM-DD
    studiendauer_jahre: int
    zielnote: float = 2.0

    def berechne_soll_fortschritt(self, stichtag: date) -> float:
        """
        Berechnet wie weit der Studierende am Stichtag planmäßig
        sein sollte — als Wert zwischen 0.0 und 1.0.
        """
        start = date.fromisoformat(self.startdatum)
        end = start + timedelta(days=int(self.studiendauer_jahre * 365))
        if stichtag <= start:
            return 0.0
        if stichtag >= end:
            return 1.0
        return (stichtag - start).days / (end - start).days

    def verbleibende_tage(self, stichtag: date) -> int:
        """Gibt an wie viele Tage bis zum geplanten Studienende noch verbleiben."""
        start = date.fromisoformat(self.startdatum)
        end = start + timedelta(days=int(self.studiendauer_jahre * 365))
        return max(0, (end - stichtag).days)


class Leistungsprofil:
    """
    Analyseklasse, die lesend auf den Studiengang zugreift
    und daraus Kennzahlen wie ECTS-Fortschritt und Notendurchschnitt berechnet.
    Verändert keine Daten — nur Auswertung.
    """

    def __init__(self, studiengang: Studiengang):
        self.sg = studiengang

    def _all_module(self) -> List[Modul]:
        """Hilfsmethode: sammelt alle Module aus allen Semestern."""
        return [m for s in self.sg.semester for m in s.module]

    def abgeschlossene_ects(self) -> int:
        """Gibt die Summe der ECTS aller bestandenen Module zurück."""
        return sum(m.beitrag_ects for m in self._all_module())

    def aktueller_notendurchschnitt(self) -> Optional[float]:
        """
        Berechnet den Notendurchschnitt über alle bestandenen Module mit Note.
        Gibt None zurück, wenn noch keine benoteten Leistungen vorliegen.
        """
        noten = []
        for m in self._all_module():
            if (m.pruefungsleistung
                    and m.pruefungsleistung.note is not None
                    and m.pruefungsleistung.ist_bestanden):
                noten.append(m.pruefungsleistung.note)
        return None if not noten else float(pd.Series(noten).mean())

    def fortschritt_prozent(self, stichtag: date) -> float:
        """
        Gibt den IST-Fortschritt in Prozent zurück, bezogen auf
        die Gesamtzahl der ECTS im Studiengang.
        """
        all_module = self._all_module()
        total_ects = sum(m.ects for m in all_module) or self.sg.gesamt_ects
        done = self.abgeschlossene_ects()
        if total_ects == 0:
            return 0.0
        return (done / total_ects) * 100.0


class Nachhaltigkeit:
    """
    Berechnet den Nachhaltigkeitsindikator des Studierenden.
    Pro fünf abbestellte Druckskripte wird symbolisch ein Baum gepflanzt.
    """

    def __init__(self, studiengang: Studiengang):
        self.sg = studiengang

    def _all_module(self) -> List[Modul]:
        """Hilfsmethode: sammelt alle Module aus allen Semestern."""
        return [m for s in self.sg.semester for m in s.module]

    def abbestellte_skripte(self) -> int:
        """Gibt die Anzahl der Module zurück, bei denen das Druckskript abbestellt wurde."""
        return sum(1 for m in self._all_module() if m.druckskript_abgestellt)

    def gepflanzte_baeume(self) -> int:
        """Für je fünf abbestellte Skripte wird ein Baum gezählt."""
        return self.abbestellte_skripte() // 5


# ============================================================
# Persistenzschicht — Datenhaltung über JSON-Datei
# ============================================================

class Repository:
    """
    Kapselt alle Lese- und Schreibzugriffe auf die JSON-Datei.
    Domänen- und UI-Klassen müssen sich nicht um Dateipfade
    oder Serialisierung kümmern.
    """

    def __init__(self, path: Path):
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        """
        Legt die JSON-Datei mit einem leeren Studiengang an,
        falls sie noch nicht existiert oder leer ist.
        """
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if (not self.path.exists()) or self.path.stat().st_size == 0:
            sg = Studiengang(
                name="Mein Studiengang",
                regelstudienzeit_jahre=4,
                gesamt_ects=180,
                semester=[Semester(nr=i + 1) for i in range(8)]
            )
            plan = Studienplan(
                startdatum=date.today().replace(month=1, day=1).isoformat(),
                studiendauer_jahre=4,
                zielnote=2.0
            )
            self.save(sg, plan)

    def load(self) -> Tuple[Studiengang, Studienplan]:
        """
        Liest die JSON-Datei und baut daraus die vollständigen
        Domänenobjekte wieder auf.
        """
        data = json.loads(self.path.read_text(encoding="utf-8"))
        sg_raw = data["studiengang"]
        plan_raw = data["studienplan"]

        semester: List[Semester] = []
        for s in sg_raw["semester"]:
            module: List[Modul] = []
            for m in s["module"]:
                pl = None
                if m["pruefungsleistung"] is not None:
                    plr = m["pruefungsleistung"]
                    pl = Pruefungsleistung(
                        bestanden=bool(plr.get("bestanden", False)),
                        note=(None if plr.get("note") is None else float(plr.get("note")))
                    )
                module.append(Modul(
                    modul_id=str(m["modul_id"]),
                    titel=str(m["titel"]),
                    kuerzel=str(m["kuerzel"]),
                    ects=int(m["ects"]),
                    druckskript_abgestellt=bool(m.get("druckskript_abgestellt", False)),
                    pruefungsleistung=pl
                ))
            semester.append(Semester(
                nr=int(s["nr"]),
                start=s.get("start"),
                ende=s.get("ende"),
                module=module
            ))

        sg = Studiengang(
            name=str(sg_raw["name"]),
            regelstudienzeit_jahre=int(sg_raw["regelstudienzeit_jahre"]),
            gesamt_ects=int(sg_raw["gesamt_ects"]),
            semester=semester
        )
        plan = Studienplan(
            startdatum=str(plan_raw["startdatum"]),
            studiendauer_jahre=int(plan_raw["studiendauer_jahre"]),
            zielnote=float(plan_raw.get("zielnote", 2.0))
        )
        return sg, plan

    def save(self, sg: Studiengang, plan: Studienplan) -> None:
        """
        Serialisiert den Studiengang und den Studienplan in JSON
        und schreibt sie sicher über eine temporäre Datei.
        Das verhindert Datenverlust bei einem Absturz während des Speicherns.
        """
        def mod_to_dict(m: Modul) -> Dict:
            """Wandelt ein Modul-Objekt in ein JSON-kompatibles Dictionary um."""
            d: Dict = {
                "modul_id": m.modul_id,
                "titel": m.titel,
                "kuerzel": m.kuerzel,
                "ects": int(m.ects),
                "druckskript_abgestellt": bool(m.druckskript_abgestellt),
            }
            if m.pruefungsleistung:
                d["pruefungsleistung"] = {
                    "bestanden": bool(m.pruefungsleistung.bestanden),
                    "note": (None if m.pruefungsleistung.note is None
                             else float(m.pruefungsleistung.note))
                }
            else:
                d["pruefungsleistung"] = None
            return d

        data = {
            "studiengang": {
                "name": sg.name,
                "regelstudienzeit_jahre": sg.regelstudienzeit_jahre,
                "gesamt_ects": sg.gesamt_ects,
                "semester": [
                    {
                        "nr": s.nr,
                        "start": s.start,
                        "ende": s.ende,
                        "module": [mod_to_dict(m) for m in s.module],
                    }
                    for s in sg.semester
                ],
            },
            "studienplan": {
                "startdatum": plan.startdatum,
                "studiendauer_jahre": plan.studiendauer_jahre,
                "zielnote": plan.zielnote,
            },
        }
        # Erst in eine temporäre Datei schreiben, dann atomar ersetzen
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


# ============================================================
# Visualisierungsschicht — Altair-Diagramme
# ============================================================

class Chart:
    """
    Zentralisiert die Erzeugung aller Diagramme.
    Durch die Auslagerung bleibt die DashboardApp übersichtlich
    und Diagramme lassen sich unabhängig anpassen.
    """

    @staticmethod
    def bullet_progress(actual_ratio: float, plan_ratio: float) -> None:
        """
        Zeigt einen Plan-Ist-Vergleich als Bullet-Chart.
        Der grüne Balken zeigt den IST-Fortschritt,
        die rote Markierung den SOLL-Wert zum aktuellen Stichtag.
        """
        a = max(0.0, min(1.0, float(actual_ratio)))
        p = max(0.0, min(1.0, float(plan_ratio)))

        # Datenvorbereitung für die einzelnen Chart-Ebenen
        df_track = pd.DataFrame([{"Kategorie": "Fortschritt", "Wert": 100}])
        df_ist   = pd.DataFrame([{"Kategorie": "Fortschritt", "Wert": a * 100}])
        df_sollx = pd.DataFrame([{"x": p * 100, "Kategorie": "Fortschritt"}])
        df_txt_i = pd.DataFrame([{"Kategorie": "Fortschritt", "x": a * 100, "label": f"{a*100:.1f}%"}])
        df_txt_s = pd.DataFrame([{"Kategorie": "Fortschritt", "x": p * 100, "label": f"SOLL {p*100:.1f}%"}])

        # Hintergrundbalken (volle Breite, transparent)
        track = alt.Chart(df_track).mark_bar(height=18, opacity=0.22).encode(
            x=alt.X("Wert:Q", scale=alt.Scale(domain=[0, 100]), title=""),
            y=alt.Y("Kategorie:N", axis=None)
        )
        # IST-Balken (grün)
        ist = alt.Chart(df_ist).mark_bar(height=18, color="#22c55e", opacity=1.0).encode(
            x="Wert:Q", y=alt.Y("Kategorie:N", axis=None)
        )
        # SOLL-Linie (rot, gestrichelt)
        soll_rule = alt.Chart(df_sollx).mark_rule(
            color="#ef4444", size=2.5, strokeDash=[6, 3], clip=False
        ).encode(x="x:Q")
        # SOLL-Dreieck als Marker
        soll_marker = alt.Chart(df_sollx).mark_point(
            shape="triangle-down", size=90, color="#ef4444", filled=True, clip=False
        ).encode(x="x:Q", y=alt.Y("Kategorie:N", axis=None))
        # Beschriftungen
        txt_ist = alt.Chart(df_txt_i).mark_text(
            dx=-6, baseline="middle", align="right", fontWeight="bold",
            color="#ffffff", size=12, clip=False
        ).encode(x="x:Q", y=alt.Y("Kategorie:N", axis=None), text="label:N")
        txt_soll = alt.Chart(df_txt_s).mark_text(
            dy=-22, fontWeight="bold", fontStyle="italic", color="#ef4444",
            size=12, stroke="#000000", strokeWidth=0.6, strokeOpacity=0.6, clip=False
        ).encode(x="x:Q", y=alt.Y("Kategorie:N", axis=None), text="label:N")

        chart = alt.layer(
            track, ist, soll_rule, soll_marker, txt_ist, txt_soll
        ).properties(
            height=92, padding={"top": 30, "right": 0, "bottom": 8, "left": 0}
        ).configure_view(clip=False, strokeWidth=0)

        st.altair_chart(chart, width="stretch", key=f"chart_{uuid.uuid4()}", theme="streamlit")


# ============================================================
# Controller-Schicht — Streamlit-UI und Anwendungssteuerung
# ============================================================

class DashboardApp:
    """
    Zentrale Steuerkomponente der Anwendung.
    Verbindet Repository, Chart und alle Domänenobjekte
    und steuert den Ablauf der Streamlit-Oberfläche.

    Die privaten Hilfsmethoden (_add_modul, _find_semester etc.)
    kapseln die Modulverwaltungslogik und sind bewusst nicht im UML
    modelliert, da sie interne Implementierungsdetails des Controllers sind.
    """

    def __init__(self, repo: Repository):
        self.repo = repo
        # Daten nur beim ersten Aufruf laden — Streamlit behält den Zustand
        if "sg" not in st.session_state or "plan" not in st.session_state:
            st.session_state.sg, st.session_state.plan = self.repo.load()
        self.sg: Studiengang   = st.session_state.sg
        self.plan: Studienplan = st.session_state.plan
        self.lp = Leistungsprofil(self.sg)
        self.nh = Nachhaltigkeit(self.sg)

    # ----------------------------------------------------------
    # Private Hilfsmethoden für den Zugriff auf Domänenobjekte
    # ----------------------------------------------------------

    def _all_module(self) -> List[Modul]:
        """Gibt alle Module aus allen Semestern als flache Liste zurück."""
        return [m for s in self.sg.semester for m in s.module]

    def _total_ects(self) -> int:
        """
        Summiert die ECTS aller vorhandenen Module.
        Fällt auf den Planwert zurück, solange noch keine Module eingetragen sind.
        """
        total = sum(m.ects for m in self._all_module())
        return total if total > 0 else self.sg.gesamt_ects

    def _find_semester(self, nr: int) -> Optional[Semester]:
        """Sucht ein Semester anhand seiner Nummer."""
        return next((s for s in self.sg.semester if s.nr == nr), None)

    def _add_modul(self, semester_nr: int, modul: Modul) -> Optional[str]:
        """
        Validiert ein neues Modul und fügt es dem angegebenen Semester hinzu.
        Gibt eine Fehlermeldung zurück, wenn die Eingabe ungültig ist,
        oder None bei Erfolg.
        """
        if not modul.titel.strip() or not modul.kuerzel.strip():
            return "Bitte Titel und Kürzel angeben."
        if any(m.kuerzel == modul.kuerzel for m in self._all_module()):
            return f"Kürzel '{modul.kuerzel}' existiert bereits."
        sem = self._find_semester(semester_nr)
        if not sem:
            return f"Semester {semester_nr} existiert nicht."
        sem.module.append(modul)
        return None

    def _remove_modul(self, modul_id: str) -> None:
        """Entfernt ein Modul anhand seiner ID aus dem jeweiligen Semester."""
        for s in self.sg.semester:
            s.module = [m for m in s.module if m.modul_id != modul_id]

    def _update_modul(self, sem_nr: int, updated: Modul) -> None:
        """Ersetzt ein bestehendes Modul durch die aktualisierte Version."""
        sem = self._find_semester(sem_nr)
        if sem:
            for i, m in enumerate(sem.module):
                if m.modul_id == updated.modul_id:
                    sem.module[i] = updated
                    return

    # ----------------------------------------------------------
    # Öffentliche Render-Methoden
    # ----------------------------------------------------------

    def render_top_metrics(self):
        """Zeigt die drei wichtigsten Kennzahlen oben im Dashboard an."""
        modules = self._all_module()
        total = len(modules)
        done  = sum(1 for m in modules if m.ist_abgeschlossen)

        unsub = self.nh.abbestellte_skripte()
        trees = self.nh.gepflanzte_baeume()

        remainder = unsub % 5
        to_next = 0 if (remainder == 0 and unsub > 0) else (5 if unsub == 0 else 5 - remainder)
        delta_text = "1 Baum geschafft 🎉" if (trees >= 1 and remainder == 0) else f"noch {to_next} Skripte bis 1 Baum"

        c1, c2, c3 = st.columns(3)
        c1.metric("📚 Kurse gesamt",        total)
        c2.metric("✅ Abgeschlossene Kurse", done)
        c3.metric("🌳 Bäume gepflanzt",      trees, delta=delta_text)

    def render_plan_and_progress(self):
        """
        Zeigt die Planungsparameter und den Gesamt-Fortschritt.
        Änderungen an Startdatum, Studiendauer oder Zielnote
        werden sofort gespeichert.
        """
        st.subheader("Planung")
        row = st.columns([2, 1, 1, 1.2])
        start        = row[0].date_input("Startdatum", value=date.fromisoformat(self.plan.startdatum))
        target_years = row[1].number_input("Ziel (Jahre)", 1, 10, self.plan.studiendauer_jahre)
        today        = row[2].date_input("Stichtag", value=date.today())
        zielnote     = row[3].number_input("Ziel-Notendurchschnitt", 0.7, 6.0, float(self.plan.zielnote), step=0.1)

        if (
            start.isoformat() != self.plan.startdatum
            or int(target_years) != self.plan.studiendauer_jahre
            or float(zielnote) != self.plan.zielnote
        ):
            self.plan.startdatum         = start.isoformat()
            self.plan.studiendauer_jahre = int(target_years)
            self.plan.zielnote           = float(zielnote)
            self.repo.save(self.sg, self.plan)
            st.toast("Plan gespeichert", icon="✅")

        total_ects = self._total_ects()
        done_ects  = self.lp.abgeschlossene_ects()
        plan_ratio = self.plan.berechne_soll_fortschritt(today)
        act_ratio  = 0.0 if total_ects == 0 else done_ects / total_ects
        plan_ects  = round(total_ects * plan_ratio, 1)
        delta_ects = round(done_ects - plan_ects, 1)
        delta_pct  = (act_ratio - plan_ratio) * 100

        st.subheader("Gesamt-Fortschritt")
        k1, k2, k3, k4, k5 = st.columns([1, 1, 1, 1, 1.2])
        k1.metric("Geplant (ECTS)",     f"{plan_ects:.1f}")
        k2.metric("Tatsächlich (ECTS)", f"{done_ects}")
        k3.metric("Abweichung (ECTS)",  f"{delta_ects:+.1f}")
        k4.metric("Abweichung (%)",     f"{delta_pct:+.1f}%")

        cur_avg = self.lp.aktueller_notendurchschnitt()
        if cur_avg is None:
            k5.metric("Ø Note aktuell", "–", delta="keine Noten", delta_color="off")
        else:
            k5.metric(
                "Ø Note aktuell", f"{cur_avg:.2f}",
                delta=f"{(cur_avg - float(self.plan.zielnote)):+.2f} ggü. Ziel",
                delta_color="inverse",
            )

        Chart.bullet_progress(act_ratio, plan_ratio)
        st.caption(
            f"Gesamt-ECTS: **{total_ects}** · Plananteil heute: **{plan_ratio*100:.1f}%** · "
            f"Resttage: **{self.plan.verbleibende_tage(today)}**"
        )

    def render_filters(self) -> Tuple[str, Tuple[float, float], str, str, bool]:
        """
        Zeigt Filter- und Sortieroptionen für die Modulliste.
        Gibt die gewählten Filterparameter als Tuple zurück.
        """
        with st.expander("🔎 Filter & Sortierung", expanded=True):
            ca, cb, cc, cd, ce = st.columns([2, 2, 2, 2, 2])
            search    = ca.text_input("Suche (Titel/Kürzel)", "")
            all_mods  = self._all_module()
            ects_vals = sorted(set(float(m.ects) for m in all_mods)) or [0.0, 10.0]

            # Sonderfall: nur ein ECTS-Wert vorhanden — minimalen Bereich aufspannen
            if len(ects_vals) == 1:
                v = ects_vals[0]
                options = [v, v + 0.01]
            else:
                options = ects_vals
            e_min, e_max = cb.select_slider("ECTS-Bereich", options=options, value=(options[0], options[-1]))

            status  = cc.selectbox("Status",         ["Alle", "Abgeschlossen", "Offen"])
            sort_by = cd.selectbox("Sortieren nach", ["titel", "kuerzel", "ects"])
            desc    = ce.checkbox("Absteigend", False)

        return search, (e_min, e_max), status, sort_by, desc

    def render_add_form(self):
        """Formular zum Hinzufügen eines neuen Moduls."""
        with st.expander("➕ Neues Modul hinzufügen"):
            with st.form("add_mod", clear_on_submit=True):
                r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns([3, 1.2, 1.2, 1, 1.2])
                titel     = r1c1.text_input("Titel*")
                kuerzel   = r1c2.text_input("Kürzel*")
                ects      = r1c3.number_input("ECTS*", 0, 60, 5)
                sem       = r1c4.selectbox("Semester*", [s.nr for s in self.sg.semester])
                skr       = r1c5.checkbox("Druckskript abbestellt")
                bestanden = r1c5.checkbox("Bestanden", value=False, key="add_bestanden")
                note      = r1c5.number_input("Note", 0.7, 6.0, 2.0, step=0.1, key="add_note")

                if st.form_submit_button("Hinzufügen"):
                    pl = None
                    if bestanden:
                        pl = Pruefungsleistung(bestanden=True, note=(float(note) if note is not None else None))
                    err = self._add_modul(int(sem), Modul(
                        modul_id=str(uuid.uuid4()), titel=titel.strip(), kuerzel=kuerzel.strip(),
                        ects=int(ects), druckskript_abgestellt=bool(skr), pruefungsleistung=pl
                    ))
                    if err:
                        st.error(err)
                    else:
                        self.repo.save(self.sg, self.plan)
                        st.success(f"Modul '{titel}' angelegt.")
                        st.rerun()

    def render_module_cards(self, view: List[Tuple[int, Modul]]):
        """
        Zeigt alle gefilterten Module als bearbeitbare Zeilen an.
        Änderungen werden automatisch erkannt und gespeichert.
        Ein Modulwechsel in ein anderes Semester wird ebenfalls unterstützt.
        """
        if not view:
            st.info("Keine Module im aktuellen Filter.")
            return

        def pl_to_dict(pl: Optional[Pruefungsleistung]) -> Optional[dict]:
            """Hilfsfunktion für den Vorher-Nachher-Vergleich von Prüfungsleistungen."""
            if pl is None:
                return None
            return {"bestanden": bool(pl.bestanden), "note": (None if pl.note is None else float(pl.note))}

        def modul_snapshot(sem_nr: int, m: Modul) -> dict:
            """Erstellt einen Schnappschuss des aktuellen Modulzustands zum Vergleich."""
            return {
                "sem":     int(sem_nr),
                "titel":   m.titel.strip(),
                "kuerzel": m.kuerzel.strip(),
                "ects":    int(m.ects),
                "skr":     bool(m.druckskript_abgestellt),
                "pl":      pl_to_dict(m.pruefungsleistung),
            }

        for sem_nr, m in view:
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([3, 1.2, 1, 1.2, 1.2, 1.0, 1.0, 0.6])
            titel_in      = c1.text_input("Titel",   m.titel,   key=f"t{m.modul_id}")
            kuerzel_in    = c2.text_input("Kürzel",  m.kuerzel, key=f"k{m.modul_id}")
            ects_in       = c3.number_input("ECTS",  0, 60, int(m.ects), key=f"e{m.modul_id}")
            sem_sel       = c4.selectbox("Semester", [s.nr for s in self.sg.semester], index=sem_nr - 1, key=f"s{m.modul_id}")
            skr_in        = c5.toggle("Skript abbestellt", m.druckskript_abgestellt, key=f"r{m.modul_id}")
            cur_bestanden = m.pruefungsleistung.bestanden if m.pruefungsleistung else False
            bestanden_in  = c6.checkbox("Bestanden", value=cur_bestanden, key=f"b{m.modul_id}")
            note_init     = (m.pruefungsleistung.note if (m.pruefungsleistung and m.pruefungsleistung.note is not None) else 2.0)
            note_in       = c7.number_input("Note", 0.7, 6.0, float(note_init), step=0.1, disabled=(not bestanden_in), key=f"gn{m.modul_id}")

            if c8.button("🗑️", key=f"x{m.modul_id}"):
                self._remove_modul(m.modul_id)
                self.repo.save(self.sg, self.plan)
                st.success("Modul gelöscht.")
                st.rerun()

            st.divider()

            pl_new = None
            if bestanden_in:
                pl_new = Pruefungsleistung(bestanden=True, note=(float(note_in) if note_in is not None else None))

            updated = Modul(
                modul_id=m.modul_id,
                titel=titel_in.strip(), kuerzel=kuerzel_in.strip(),
                ects=int(ects_in), druckskript_abgestellt=bool(skr_in),
                pruefungsleistung=pl_new,
            )

            before = modul_snapshot(sem_nr, m)
            after  = {
                "sem":     int(sem_sel),
                "titel":   updated.titel,
                "kuerzel": updated.kuerzel,
                "ects":    updated.ects,
                "skr":     updated.druckskript_abgestellt,
                "pl":      pl_to_dict(updated.pruefungsleistung),
            }

            if before != after:
                # Kürzel darf nicht doppelt vergeben sein
                other = [x for x in self._all_module() if x.modul_id != updated.modul_id]
                if any(x.kuerzel == updated.kuerzel for x in other):
                    st.error(f"Doppeltes Kürzel: {updated.kuerzel}")
                    continue

                if after["sem"] != before["sem"]:
                    # Modul in ein anderes Semester verschieben
                    self._remove_modul(updated.modul_id)
                    tgt = self._find_semester(after["sem"])
                    if tgt:
                        tgt.module.append(updated)
                else:
                    self._update_modul(sem_nr, updated)

                self.repo.save(self.sg, self.plan)
                st.toast("Änderungen gespeichert", icon="✅")
                st.rerun()

    def run(self):
        """
        Einstiegspunkt der Anwendung.
        Baut die Seite auf und koordiniert alle Render-Methoden.
        """
        st.set_page_config(page_title="Kurs-Fortschritt", layout="wide")
        st.title("Kurs-Fortschritt & Nachhaltigkeit")

        self.render_top_metrics()
        st.divider()
        self.render_plan_and_progress()
        st.divider()

        search, (e_min, e_max), status, sort_by, desc = self.render_filters()

        # Module anhand der Filterkriterien zusammenstellen
        pairs: List[Tuple[int, Modul]] = []
        for s in self.sg.semester:
            for m in s.module:
                if search and (search.lower() not in m.titel.lower() and search.lower() not in m.kuerzel.lower()):
                    continue
                if not (e_min <= float(m.ects) <= e_max):
                    continue
                if status == "Abgeschlossen" and not m.ist_abgeschlossen:
                    continue
                if status == "Offen" and m.ist_abgeschlossen:
                    continue
                pairs.append((s.nr, m))

        pairs = sorted(pairs, key=lambda p: getattr(p[1], sort_by), reverse=desc)

        st.caption(
            f"Gefundene Module: **{len(pairs)}**"
            + (f" | ECTS gesamt: **{self._total_ects()}**" if pairs else "")
            + f" | Abgeschlossen (ECTS): **{self.lp.abgeschlossene_ects()}**"
        )

        self.render_add_form()
        st.subheader("Modulliste (bearbeitbar)")
        self.render_module_cards(pairs)


# ============================================================
# Anwendungsstart
# ============================================================

def main():
    """Erstellt das Repository und startet die Anwendung."""
    repo = Repository(Path("data/studium.json"))
    DashboardApp(repo).run()


if __name__ == "__main__":
    main()
