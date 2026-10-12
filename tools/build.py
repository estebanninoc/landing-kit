#!/usr/bin/env python3
"""
tools/build.py — rellena template/index.html con config.json y escribe el index.html
final en la raiz del kit (al lado de img/, vid/, vid-pack/, fonts/, engine/).

Uso:
  python3 tools/build.py                       # lee ./config.json, escribe ./index.html
  python3 tools/build.py --config otro.json --out otro/index.html
"""
import argparse
import html
import json
import os

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def esc(s):
    return html.escape(str(s), quote=True)


def chips_html(items):
    return "".join(f"<li>{esc(x)}</li>" for x in items)


def trust_chips_html(items):
    return "".join(f'<span class="trust-chip">{esc(x)}</span>' for x in items)


def cinta_group_html(marcas, visible):
    out = []
    for m in marcas:
        alt = esc(m["name"]) if visible else ""
        out.append(
            f'<span class="cinta-it"><img src="{esc(m["logo"])}" alt="{alt}" '
            f'width="{int(m["w"])}" height="{int(m["h"])}" decoding="async"></span>'
        )
    return "".join(out)


def cinta_row_html(marcas, extra_class=""):
    grp = cinta_group_html(marcas, visible=True)
    grp_hidden = cinta_group_html(marcas, visible=False)
    cls = "cinta" + (" " + extra_class if extra_class else "")
    return (
        f'<div class="{cls}"><div class="cinta-track">'
        f'<span class="cinta-grp">{grp}</span>'
        f'<span class="cinta-grp" aria-hidden="true">{grp_hidden}</span>'
        f"</div></div>"
    )


def js_obj(d):
    """Objeto JS de un nivel con valores string, en el mismo formato compacto del original."""
    parts = ",".join(f"{k}:'{v}'" for k, v in d.items())
    return "{" + parts + "}"


def engine_bootstrap_js(animaciones):
    """Genera las llamadas initEscena()/initMotor() que antes estaban hardcodeadas en motos,
    ahora armadas desde config.json. Misma forma de llamada que el original, sin cambiar
    initEscena()/initMotor() (eso vive intacto en engine/scrub.js)."""
    lines = []
    for a in animaciones:
        cfg = {
            "stage": a["stage"],
            "canvas": a["canvas"],
            "n": a["n"],
            "dirMob": a["dirMob"],
            "dirDesk": a["dirDesk"],
        }
        if "bar" in a:
            cfg["bar"] = a["bar"]
        if "track" in a:
            cfg["track"] = a["track"]
        fn = "initMotor" if "lutRef" in a else "initEscena"
        obj_parts = []
        for k, v in cfg.items():
            if isinstance(v, str):
                obj_parts.append(f"{k}:'{v}'")
            else:
                obj_parts.append(f"{k}:{json.dumps(v)}")
        if "lutRef" in a:
            obj_parts.append(f"lut:{a['lutRef']}")
        lines.append(f"{fn}({{{','.join(obj_parts)}}});")
    return "\n".join(lines)


def build(config_path, out_path):
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    template_path = os.path.join(KIT_ROOT, "template", "index.html")
    with open(template_path, encoding="utf-8") as f:
        tpl = f.read()

    textos = cfg["textos"]
    precios = cfg["precios"]
    links = cfg["links_pago"]
    paleta = cfg["paleta"]
    marcas = cfg["marcas"]
    animaciones = {a["id"]: a for a in cfg["animaciones"]}
    despiece = animaciones["despiece"]
    motor = animaciones["motor-mini"]

    replacements = {
        "{{META_TITLE}}": cfg["meta"]["title"],
        "{{META_DESC}}": cfg["meta"]["description"],
        "{{OG_DESC}}": cfg["meta"]["og_description"],
        "{{PAL_BG}}": paleta["bg"],
        "{{PAL_PANEL}}": paleta["panel"],
        "{{PAL_PANEL2}}": paleta["panel2"],
        "{{PAL_LINE}}": paleta["line"],
        "{{PAL_TX}}": paleta["tx"],
        "{{PAL_MUT}}": paleta["mut"],
        "{{PAL_DIM}}": paleta["dim"],
        "{{PAL_RED}}": paleta["red"],
        "{{PAL_RED_TX}}": paleta["red_tx"],
        "{{PAL_BLUE}}": paleta["blue"],
        "{{PILL}}": textos["pill"],
        "{{HERO_TITLE_HTML}}": textos["hero_title_html"],
        "{{HERO_SUB_HTML}}": textos["hero_sub_html"],
        "{{CTA_HERO}}": textos["cta_hero"],
        "{{CTA_NOTE}}": textos["cta_note"],
        "{{TRUST_CHIPS_HTML}}": trust_chips_html(textos["trust_chips"]),
        "{{MARCAS_LABEL}}": textos["marcas_label"],
        "{{MARCAS_ROW1_HTML}}": cinta_row_html(marcas["row1"]),
        "{{MARCAS_ROW2_HTML}}": cinta_row_html(marcas["row2"], extra_class="cinta-rev"),
        "{{DESPIECE_EYEBROW}}": textos["despiece_eyebrow"],
        "{{DESPIECE_TITLE}}": textos["despiece_title"],
        "{{DESPIECE_LEAD}}": textos["despiece_lead"],
        "{{DESPIECE_W}}": str(despiece["w"]),
        "{{DESPIECE_H}}": str(despiece["h"]),
        "{{DESPIECE_ARIA}}": despiece["aria_label"],
        "{{DESPIECE_CHIPS_HTML}}": chips_html(despiece["chips"]),
        "{{PACK_INTRO_EYEBROW}}": textos["pack_intro_eyebrow"],
        "{{PACK_INTRO_TITLE}}": textos["pack_intro_title"],
        "{{PACK_INTRO_LEAD}}": textos["pack_intro_lead"],
        "{{MOTOR_W}}": str(motor["w"]),
        "{{MOTOR_H}}": str(motor["h"]),
        "{{MOTOR_ARIA}}": motor["aria_label"],
        "{{MOTOR_CHIPS_HTML}}": chips_html(motor["chips"]),
        "{{LINKS_JS}}": js_obj(links),
        "{{PRECIOS_JS}}": js_obj(
            {k: precios[k] for k in ("base", "a", "b", "ab")}
        ),
        "{{ANTES_JS}}": js_obj({"base": precios["antes_base"]}),
        "{{ENGINE_BOOTSTRAP_JS}}": engine_bootstrap_js(cfg["animaciones"]),
    }

    out = tpl
    missing = []
    for token, value in replacements.items():
        if token not in out:
            missing.append(token)
        out = out.replace(token, value)

    leftover = [t for t in replacements if t in out]
    if missing:
        raise SystemExit(f"tokens no encontrados en template: {missing}")
    if leftover:
        raise SystemExit(f"tokens sin reemplazar en el resultado: {leftover}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"escrito {out_path} ({len(out)} bytes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(KIT_ROOT, "config.json"))
    ap.add_argument("--out", default=os.path.join(KIT_ROOT, "index.html"))
    args = ap.parse_args()
    build(args.config, args.out)
