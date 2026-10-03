"""Generuje SOURCES.md (rejestr zrodel dla jury) z sources.yaml.   python -m pipeline.make_sources_doc"""
from __future__ import annotations

import yaml

from pipeline.common import ROOT

FIELDS = [("used_for", "Do czego używamy"), ("publisher", "Wydawca"), ("license", "Licencja / warunki"),
          ("attribution", "Oznaczenie źródła"), ("commercial_use", "Użycie komercyjne"), ("currency", "Aktualność"),
          ("verification", "Jak weryfikujemy"), ("limitations", "Ograniczenia")]
STATUS = {"potwierdzona": "warunki sprawdzone", "do_potwierdzenia": "DO POTWIERDZENIA"}


def main() -> None:
    d = yaml.safe_load((ROOT / "sources.yaml").read_text("utf-8"))
    out = ["# Rejestr źródeł danych", "",
           "Dla każdego źródła: pochodzenie, warunki wykorzystania, aktualność i sposób weryfikacji. "
           "Plik generowany z `sources.yaml`.", "", "## Źródła użyte w rozwiązaniu", ""]
    for s in d["used"]:
        out.append(f"### {s['name']}")
        if s.get("url"):
            out.append(f"Adres: {s['url']}")
        out.append(f"Status licencji: **{STATUS[s['license_status']]}**")
        out.append("")
        for k, label in FIELDS:
            out.append(f"- **{label}:** {s[k]}")
        out.append("")
    out += ["## Źródła rozważone, jeszcze nieużyte", ""]
    for s in d["considered_not_used"]:
        out.append(f"- **{s['name']}** ({s['url']}): {s['note']}")
    (ROOT / "SOURCES.md").write_text("\n".join(out) + "\n", "utf-8")
    print("zapisano SOURCES.md")


if __name__ == "__main__":
    main()
