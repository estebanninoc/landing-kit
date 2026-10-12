#!/usr/bin/env python3
"""QA automatico de landings scroll-scrub (ORDEN KIT2).

Uso:
  tools/qa_calidad.py <ruta-landing>
  tools/qa_calidad.py <ruta-landing> --estandar tools/estandar.json --ref-js tools/scrub-referencia.js

Falla (exit 1) si alguna animacion scroll-scrub detectada en el HTML tiene:
  1. < 90% de los frames (o KB/frame o resolucion) del estandar en estandar.json.
  2. El motor JS (engine/scrub.js o el <script> de scrub embebido) difiere del kit
     sin una marca "// OK-ESTEBAN:<fecha>" en el mismo archivo.
  3. Algun frame/asset referenciado por una llamada initEscena()/initMotor() no existe.
Placeholders "[PENDIENTE]" solo generan warning (no fallan).

No depende de nada fuera de la stdlib (el tamano real de cada frame .webp se lee
parseando el header RIFF/VP8 a mano, sin Pillow).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------- estandar por repo (ORDEN CB1: motos vertical y carros horizontal son formatos
# legitimos distintos, no una desviacion a forzar a un unico tamano) ----------

def detect_repo_name(landing_path):
    """Nombre del repo git que contiene landing_path (ultimo segmento del remote 'origin'),
    o el nombre del directorio si no hay remote/.git."""
    d = os.path.abspath(landing_path)
    while True:
        if os.path.isdir(os.path.join(d, '.git')):
            try:
                url = subprocess.check_output(
                    ['git', '-C', d, 'remote', 'get-url', 'origin'],
                    stderr=subprocess.DEVNULL, text=True).strip()
                name = url.rstrip('/').rsplit('/', 1)[-1]
                return name[:-4] if name.endswith('.git') else name
            except (subprocess.CalledProcessError, OSError):
                return os.path.basename(d)
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.basename(os.path.abspath(landing_path))
        d = parent


def seleccionar_estandar(estandar, repo_name, notas):
    """Si estandar.json tiene 'repos', usa SOLO la seccion del repo detectado (cada repo
    tiene su propio formato de frames/resolucion). Si el repo no esta registrado, fusiona
    todas las secciones conocidas (permisivo, con nota) en vez de fallar. Formato viejo
    (estandar.json plano, sin 'repos') se respeta tal cual para no romper otros usos."""
    if 'repos' not in estandar:
        return estandar
    sel = estandar['repos'].get(repo_name)
    if sel is not None:
        return sel
    fusion = {}
    for r in estandar['repos'].values():
        fusion.update(r.get('animaciones', {}))
    notas.append(
        "repo '%s' no tiene seccion propia en estandar.json: se usa la union de todos los "
        "repos conocidos (%s)" % (repo_name, ', '.join(estandar['repos'].keys())))
    return {'animaciones': fusion}


# ---------- utilidades de texto ----------

def strip_js_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    return src


def normalize_js(code):
    return re.sub(r'\s+', ' ', strip_js_comments(code)).strip()


def extract_balanced_function(src, func_name):
    """Devuelve 'function NAME(...){...}' completo (conteo de llaves) o None."""
    m = re.search(r'function\s+' + re.escape(func_name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return None
    depth = 0
    for i in range(m.end() - 1, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
    return None


# ---------- tamano real de un .webp sin Pillow ----------

def webp_dimensions(path):
    """Lee w,h del header RIFF/WEBP (VP8/VP8L/VP8X). None si no se puede parsear."""
    try:
        with open(path, 'rb') as f:
            data = f.read(64)
    except OSError:
        return None
    if data[0:4] != b'RIFF' or data[8:12] != b'WEBP':
        return None
    fmt = data[12:16]
    try:
        if fmt == b'VP8 ':
            w = (data[26] | (data[27] << 8)) & 0x3fff
            h = (data[28] | (data[29] << 8)) & 0x3fff
            return w, h
        if fmt == b'VP8L':
            b0, b1, b2, b3, b4 = data[21:26]
            w = 1 + (((b1 & 0x3f) << 8) | b0)
            h = 1 + (((b3 & 0xf) << 10) | (b2 << 2) | ((b1 & 0xc0) >> 6))
            return w, h
        if fmt == b'VP8X':
            b0, b1, b2 = data[24:27]
            w = 1 + (b0 | (b1 << 8) | (b2 << 16))
            b0, b1, b2 = data[27:30]
            h = 1 + (b0 | (b1 << 8) | (b2 << 16))
            return w, h
    except (ValueError, IndexError):
        return None
    return None


# ---------- localizar HTML / engine JS de la landing ----------

def find_index_html(landing_path):
    for rel in ('index.html', os.path.join('pack-scroll', 'index.html'),
                os.path.join('template', 'index.html')):
        c = os.path.join(landing_path, rel)
        if os.path.isfile(c):
            return c
    return None


def find_engine_source(index_html_path, raw_html):
    """Si hay <script src=".../scrub.js">, usa ese archivo; si no, el propio HTML."""
    m = re.search(r'<script[^>]*\bsrc\s*=\s*["\']([^"\']*scrub\.js)["\']', raw_html)
    if m:
        engine_path = os.path.normpath(os.path.join(os.path.dirname(index_html_path), m.group(1)))
        if os.path.isfile(engine_path):
            with open(engine_path, encoding='utf-8', errors='replace') as f:
                return engine_path, f.read()
    return index_html_path, raw_html


# ---------- llamadas initEscena()/initMotor() activas (sin comentarios) ----------

def parse_init_calls(src_no_comments):
    calls = []
    for fn in ('initEscena', 'initMotor'):
        for m in re.finditer(fn + r'\(\{(.*?)\}\)\s*;', src_no_comments, flags=re.S):
            body = m.group(1)

            def get(key):
                mm = re.search(re.escape(key) + r"\s*:\s*'([^']*)'", body)
                if mm:
                    return mm.group(1)
                mm = re.search(re.escape(key) + r"\s*:\s*([0-9]+)", body)
                if mm:
                    return mm.group(1)
                return None

            n_raw = get('n')
            dir_mob = get('dirMob')
            dir_desk = get('dirDesk')
            if n_raw is None or dir_mob is None or dir_desk is None:
                continue  # n viene de una variable (p.ej. placeholder sin terminar), no evaluable estaticamente
            calls.append({
                'fn': fn,
                'id': get('stage') or get('canvas') or fn,
                'n': int(n_raw),
                'dirMob': dir_mob,
                'dirDesk': dir_desk,
            })
    return calls


# ---------- checks ----------

def check_frames_y_resolucion(landing_path, call, estandar, fallas, advertencias, animaciones_out):
    base_desk = os.path.join(landing_path, call['dirDesk'])
    base_mob = os.path.join(landing_path, call['dirMob'])
    n = call['n']

    def listar(base):
        existentes, faltantes, tamanos = [], [], []
        for i in range(1, n + 1):
            p = os.path.join(base, 'f_%03d.webp' % i)
            if os.path.isfile(p):
                existentes.append(p)
                tamanos.append(os.path.getsize(p))
            else:
                faltantes.append(p)
        return existentes, faltantes, tamanos

    desk_ok, desk_missing, desk_sizes = listar(base_desk)
    mob_ok, mob_missing, mob_sizes = listar(base_mob)

    item = {
        'id': call['id'], 'fn': call['fn'], 'n_declarado': n,
        'frames_desk_encontrados': len(desk_ok), 'frames_mob_encontrados': len(mob_ok),
        'tipo': None, 'ok': True, 'detalle': [],
    }

    # (3) assets faltantes: zero-tolerancia
    faltantes = desk_missing + mob_missing
    if faltantes:
        item['ok'] = False
        muestra = faltantes[:5]
        extra = '' if len(faltantes) <= 5 else ' (+%d mas)' % (len(faltantes) - 5)
        msg = '%s: %d frame(s) referenciados no existen: %s%s' % (
            call['id'], len(faltantes), ', '.join(os.path.relpath(p, landing_path) for p in muestra), extra)
        fallas.append(msg)
        item['detalle'].append(msg)

    if not desk_ok:
        animaciones_out.append(item)
        return  # nada mas que medir

    dims_desk = webp_dimensions(desk_ok[0])
    dims_mob = webp_dimensions(mob_ok[0]) if mob_ok else None

    # clasificar por resolucion desk contra el estandar
    tipo, spec = None, None
    for nombre, s in estandar['animaciones'].items():
        if dims_desk and tuple(dims_desk) == (s['resolucion']['desk']['w'], s['resolucion']['desk']['h']):
            tipo, spec = nombre, s
            break
    item['tipo'] = tipo or '(sin estandar)'

    if spec is None:
        opciones = ', '.join(
            '%s=%dx%d' % (nom, s['resolucion']['desk']['w'], s['resolucion']['desk']['h'])
            for nom, s in estandar['animaciones'].items())
        msg = '%s: resolucion desk %s no coincide con ningun estandar (%s)' % (
            call['id'], ('%dx%d' % dims_desk if dims_desk else '?'), opciones)
        item['ok'] = False
        fallas.append(msg)
        item['detalle'].append(msg)
        animaciones_out.append(item)
        return

    # resolucion mob tambien debe calzar exacto
    exp_desk = (spec['resolucion']['desk']['w'], spec['resolucion']['desk']['h'])
    exp_mob = (spec['resolucion']['mob']['w'], spec['resolucion']['mob']['h'])
    if dims_mob and tuple(dims_mob) != exp_mob:
        msg = '%s (%s): resolucion mob %dx%d != estandar %dx%d' % (
            call['id'], tipo, dims_mob[0], dims_mob[1], exp_mob[0], exp_mob[1])
        item['ok'] = False
        fallas.append(msg)
        item['detalle'].append(msg)

    # (1a) % de frames contra el estandar
    esperados = spec['frames_esperados']
    min_pct = spec['min_frames_pct']
    for nombre_lado, encontrados in (('desk', len(desk_ok)), ('mob', len(mob_ok))):
        pct = encontrados / esperados
        item['pct_%s' % nombre_lado] = round(pct, 3)
        if pct < min_pct:
            msg = '%s (%s): %d/%d frames %s (%.0f%%) < %.0f%% del estandar' % (
                call['id'], tipo, encontrados, esperados, nombre_lado, pct * 100, min_pct * 100)
            item['ok'] = False
            fallas.append(msg)
            item['detalle'].append(msg)

    # (1b) KB/frame contra el estandar (con tolerancia)
    for nombre_lado, sizes in (('desk', desk_sizes), ('mob', mob_sizes)):
        if not sizes:
            continue
        avg_kb = (sum(sizes) / len(sizes)) / 1024.0
        esperado = spec['kb_por_frame'][nombre_lado]['avg']
        tol = spec['kb_por_frame'][nombre_lado]['tolerancia_pct']
        item['kb_frame_%s' % nombre_lado] = round(avg_kb, 1)
        lo, hi = esperado * (1 - tol), esperado * (1 + tol)
        if not (lo <= avg_kb <= hi):
            msg = '%s (%s): %.1f KB/frame %s fuera de %.1f-%.1f KB (estandar %.1f +-%.0f%%)' % (
                call['id'], tipo, avg_kb, nombre_lado, lo, hi, esperado, tol * 100)
            item['ok'] = False
            fallas.append(msg)
            item['detalle'].append(msg)

    animaciones_out.append(item)


def check_motor_js(index_html_path, raw_html, ref_js_path, fallas, advertencias, notas):
    engine_path, engine_src = find_engine_source(index_html_path, raw_html)
    with open(ref_js_path, encoding='utf-8') as f:
        ref_src = f.read()

    marker = re.search(r'OK-ESTEBAN\s*:\s*(\S+)', engine_src)

    for fn in ('initEscena', 'initMotor'):
        ref_body = extract_balanced_function(strip_js_comments(ref_src), fn)
        tgt_body = extract_balanced_function(strip_js_comments(engine_src), fn)
        if tgt_body is None or ref_body is None:
            continue  # esta landing no usa esa funcion (o la referencia no la tiene)
        if normalize_js(tgt_body) != normalize_js(ref_body):
            rel = os.path.relpath(engine_path, os.path.dirname(index_html_path))
            if marker:
                notas.append('%s en %s difiere del kit pero esta autorizado (OK-ESTEBAN:%s)' % (
                    fn, rel, marker.group(1)))
            else:
                fallas.append(
                    '%s en %s difiere del motor del kit (%s) sin marca // OK-ESTEBAN:<fecha>' % (
                        fn, rel, os.path.relpath(ref_js_path)))


def check_placeholders(landing_path, advertencias):
    exts = ('.html', '.js', '.json', '.md')
    total = 0
    for root, dirs, files in os.walk(landing_path):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in files:
            if not name.lower().endswith(exts):
                continue
            p = os.path.join(root, name)
            try:
                with open(p, encoding='utf-8', errors='ignore') as f:
                    n = len(re.findall(r'\[PENDIENTE\]', f.read(), flags=re.I))
            except OSError:
                n = 0
            if n:
                total += n
                advertencias.append('%s: %d placeholder(es) [PENDIENTE]' % (os.path.relpath(p, landing_path), n))
    return total


# ---------- salida ----------

def imprimir_tabla(animaciones):
    if not animaciones:
        print('(sin animaciones scroll-scrub activas detectadas)')
        return
    cols = ['id', 'tipo', 'n', 'desk', 'mob', 'KB/f desk', 'KB/f mob', 'OK']
    filas = []
    for a in animaciones:
        filas.append([
            a['id'], a.get('tipo') or '-', str(a['n_declarado']),
            str(a['frames_desk_encontrados']), str(a['frames_mob_encontrados']),
            str(a.get('kb_frame_desk', '-')), str(a.get('kb_frame_mob', '-')),
            'si' if a['ok'] else 'NO',
        ])
    widths = [max(len(cols[i]), *(len(f[i]) for f in filas)) for i in range(len(cols))]
    def fila(vals):
        return '  '.join(v.ljust(widths[i]) for i, v in enumerate(vals))
    print(fila(cols))
    print(fila(['-' * w for w in widths]))
    for f in filas:
        print(fila(f))


def main():
    ap = argparse.ArgumentParser(description='QA de calidad para landings scroll-scrub (ORDEN KIT2)')
    ap.add_argument('landing', help='ruta de la landing (o del repo) a revisar')
    ap.add_argument('--estandar', default=os.path.join(SCRIPT_DIR, 'estandar.json'))
    ap.add_argument('--ref-js', default=os.path.join(SCRIPT_DIR, 'scrub-referencia.js'))
    ap.add_argument('--out', default='qa-report.json', help='ruta del JSON de salida')
    args = ap.parse_args()

    landing_path = os.path.abspath(args.landing)
    index_html_path = find_index_html(landing_path)
    if not index_html_path:
        print('ERROR: no se encontro index.html (ni en pack-scroll/ ni en template/) bajo %s' % landing_path,
              file=sys.stderr)
        sys.exit(1)

    with open(index_html_path, encoding='utf-8', errors='replace') as f:
        raw_html = f.read()
    with open(args.estandar, encoding='utf-8') as f:
        estandar = json.load(f)

    fallas, advertencias, notas, animaciones = [], [], [], []

    repo_name = detect_repo_name(landing_path)
    estandar_repo = seleccionar_estandar(estandar, repo_name, notas)
    if 'repos' in estandar:
        notas.append("estandar por repo: '%s'" % repo_name)

    html_sin_comentarios = re.sub(r'<!--.*?-->', '', strip_js_comments(raw_html), flags=re.S)
    calls = parse_init_calls(html_sin_comentarios)
    for call in calls:
        check_frames_y_resolucion(os.path.dirname(index_html_path), call, estandar_repo, fallas, advertencias, animaciones)

    check_motor_js(index_html_path, raw_html, args.ref_js, fallas, advertencias, notas)
    n_placeholders = check_placeholders(landing_path, advertencias)

    ok = len(fallas) == 0
    reporte = {
        'landing': landing_path,
        'index_html': os.path.relpath(index_html_path, landing_path),
        'ok': ok,
        'animaciones': animaciones,
        'fallas': fallas,
        'advertencias': advertencias,
        'notas': notas,
    }

    print('=== QA calidad: %s ===' % landing_path)
    imprimir_tabla(animaciones)
    print()
    if notas:
        for n in notas:
            print('NOTA: %s' % n)
    if advertencias:
        for a in advertencias:
            print('WARNING: %s' % a)
    if fallas:
        print()
        print('FALLAS (%d):' % len(fallas))
        for f in fallas:
            print('  - %s' % f)
    print()
    print('RESULTADO: %s' % ('PASA' if ok else 'FALLA'))

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)
    print('reporte: %s' % os.path.abspath(args.out))

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
