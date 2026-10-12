# landing-kit

Kit base reutilizable para landings de venta tipo pack-scroll, extraido de
`utec-motos-landing/pack-scroll` (commit `972b233`, ORDEN BA1) via ORDEN KIT1.

Ver tambien la sección **"LANDINGS: CLONAR, NO REHACER"** en el `CLAUDE.md` del taller:
toda landing nueva parte de una copia de este kit (o de la landing aprobada más reciente),
cambiando solo lo del producto nuevo.

## Estructura

- `config.json` — textos, precios, links de pago (placeholder), paleta, marcas, chips de
  cada animación. Es lo ÚNICO que cambia por producto nuevo. Trae de ejemplo los valores
  reales de motos (reproduce la landing original 1:1).
- `engine/scrub.js` — `initEscena()` + `initMotor()` + `LUT_MOTOR`, extraídos TAL CUAL
  (sin cambiar lógica). Componente probado: no se toca sin OK explícito de Esteban.
- `template/index.html` — el HTML de motos con los campos de `config.json` reemplazados
  por tokens `{{...}}`.
- `tools/build.py` — rellena `template/index.html` con `config.json` y escribe `index.html`
  en la raíz del kit.
- `tools/frames.sh` — video → frames `f_NNN.webp` (mob/desk) con los parámetros exactos de
  motos medidos del repo (resolución, cantidad de cuadros).
- `index.html`, `img/`, `vid/`, `vid-pack/`, `fonts/`, `favicon.ico` — el sitio ya armado
  con el `config.json` de ejemplo (motos), listo para servir o verificar.

## Uso para una landing nueva

1. Clonar este repo.
2. Editar `config.json` con los datos del producto nuevo (y reemplazar los assets en
   `img/`, `vid/`, `vid-pack/` que correspondan — usar `tools/frames.sh` para las
   animaciones scroll-scrub).
3. `python3 tools/build.py`
4. Servir/publicar la raíz del kit tal cual (mismo layout que `pack-scroll/`).

## Verificación hecha en KIT1

`tools/build.py` con el `config.json` de ejemplo reproduce `utec-motos-landing/pack-scroll`
sin diffs de DOM (título, meta, paleta, hero, chips de confianza, marcas, chips y atributos
de canvas de cada animación, precios) y visualmente igual en capturas Playwright a 390px y
1440px, incluyendo el canvas en movimiento de `escena-motor` servido desde `engine/scrub.js`.
