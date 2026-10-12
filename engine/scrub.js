/* engine/scrub.js — extraido TAL CUAL de utec-motos-landing/pack-scroll (commit 972b233, ORDEN BA1),
   sin cambiar logica, via ORDEN KIT1. initEscena()+initMotor()+LUT_MOTOR puros: no hay invocacion
   aqui adentro — las llamadas (stage/canvas/n/dir por animacion) viven en config.json y las dispara
   el bootstrap del template (ver template/index.html). */

/* despiece (moto grande + escenas chicas motor/carburador/freno/embrague/horquilla):
   - Precarga TEMPRANA: arranca a ~1.5 viewports de distancia (no 600px fijos) y pide TODOS
     los frames de una, esperando su decode() real (no solo el onload de red).
   - No anima hasta tener TODOS los frames decodificados: mientras faltan, se queda fijo en
     el cuadro 1 (nunca pinta un cuadro a medias ni salta lejos por frames que no llegaron).
   - Animación con "persecución" (lerp 0.14) en vez de salto directo: cada frame el dibujado
     avanza hacia el cuadro objetivo por rAF continuo, estilo Apple.
   - Dibujado FRACCIONAL: entre el cuadro i e i+1 se hace crossfade según la fracción.
   - Si cfg.track viene (carril alto dp-scrub con el stage sticky adentro), el progreso 0→1
     se mide sobre ESE carril (no sobre el stage, que ya no se mueve mientras está pegado).
     cfg.n ya viene recortado al tramo con movimiento real (medido cuadro a cuadro); los
     cuadros finales "congelados" de cada clip fuente no se cargan ni se mapean.
   - Liberar memoria SOLO a >3 viewports de distancia (nunca la escena actual ni las vecinas
     inmediatas): soltarla apenas sale de pantalla recargaba ~150 imágenes de golpe al volver
     a entrar y eso es lo que se sentía como scroll "trabado". */
function initEscena(cfg){
  var stage=document.getElementById(cfg.stage), canvas=document.getElementById(cfg.canvas), bar=cfg.bar?document.getElementById(cfg.bar):null;
  var track=cfg.track?document.getElementById(cfg.track):null;
  if(!stage||!canvas) return;
  var ctx=canvas.getContext('2d'), N=cfg.n, W=canvas.width, H=canvas.height;
  var dir = window.matchMedia('(max-width:720px)').matches ? cfg.dirMob : cfg.dirDesk;
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var imgs=[], ok=[], loadedCount=0, allReady=false, want=1, cur=1, started=false, running=false, gen=0;
  var stickyTopPx=window.innerHeight*0.10, lastWidth=window.innerWidth;
  var READY_FRAC=0.9, READY_TIMEOUT_MS=4000; /* ORDEN AZ5: no esperar el 100% de los N cuadros */
  function src(i){ return dir+'f_'+String(i).padStart(3,'0')+'.webp'; }
  /* ORDEN AZ5: si el cuadro exacto no está listo (hueco por decode() que nunca resolvió o
     que todavía no llegó), usar el cuadro cargado más cercano en vez de dejar el canvas
     congelado en la posición vieja o, peor, en blanco. */
  function nearestLoaded(i){
    if(ok[i]) return i;
    for(var d=1; d<N; d++){
      if(i-d>=1 && ok[i-d]) return i-d;
      if(i+d<=N && ok[i+d]) return i+d;
    }
    return null;
  }
  function draw(pos){
    if(!started || !imgs.length) return;
    if(!allReady) pos=1;
    var i0=Math.floor(pos), frac=pos-i0, i1=i0+1;
    if(i0<1){ i0=1; i1=1; frac=0; } if(i1>N){ i1=N; if(i0>N) i0=N; }
    if(!imgs[i0] || !ok[i0]){
      i0=nearestLoaded(i0);
      if(i0==null) return; /* todavía no cargó ni un solo cuadro: nada que pintar */
      i1=i0; frac=0;
    }
    ctx.clearRect(0,0,W,H);
    ctx.globalAlpha=1; ctx.drawImage(imgs[i0],0,0,W,H);
    if(i1!==i0 && frac>0.004 && imgs[i1] && ok[i1]){ ctx.globalAlpha=frac; ctx.drawImage(imgs[i1],0,0,W,H); ctx.globalAlpha=1; }
  }
  function checkReady(){
    if(allReady) return;
    if(loadedCount>=Math.ceil(N*READY_FRAC)){ allReady=true; draw(cur); }
  }
  function load(i){
    if(imgs[i]) return;
    var im=new Image(); im.decoding='async'; im.src=src(i); imgs[i]=im;
    var mark=function(){
      if(imgs[i]!==im) return; ok[i]=true; loadedCount++;
      if(i===1) draw(cur); /* ORDEN AZ5: cuadro 1 visible en cuanto él esté listo, sin esperar a los demás */
      checkReady();
      if(!allReady && Math.abs(cur-i)<1) draw(cur);
    };
    /* ORDEN AZ5: decode() puede rechazar de forma intermitente en WebKit/iOS aun con el
       recurso bien cargado (presión de memoria/decodes concurrentes) — tratar el rechazo
       igual que el éxito (como ya hace initMotor) en vez de un no-op que deja el cuadro
       fantasma para siempre y nunca llega a loadedCount>=N. */
    if(im.decode){ im.decode().then(mark, mark); } else { im.onload=mark; im.onerror=mark; }
  }
  function startLoad(){
    if(started) return; started=true;
    gen++; var myGen=gen;
    if(reduced){ load(N); want=N; cur=N; if(bar) bar.style.setProperty('--t',1); return; }
    /* en tandas chicas (no las ~150 de una) para no saturar conexiones/decode de golpe */
    var i=1;
    function chunk(){
      if(!started || gen!==myGen) return;
      var end=Math.min(N,i+9);
      for(; i<=end; i++) load(i);
      if(i<=N) setTimeout(chunk,60);
    }
    chunk();
    /* ORDEN AZ5: red/decode lentos no deben trabar la animación para siempre — a los 4s se
       anima con lo que haya, rellenando huecos con el cuadro cargado más cercano (ver draw()). */
    setTimeout(function(){
      if(gen!==myGen || allReady) return;
      if(started){ allReady=true; draw(cur); }
    }, READY_TIMEOUT_MS);
  }
  function anim(){
    if(!started){ running=false; return; }
    var d=want-cur;
    if(Math.abs(d)<0.01){ cur=want; draw(cur); running=false; return; }
    cur+=d*0.14;
    draw(cur);
    requestAnimationFrame(anim);
  }
  function kick(){ if(!running){ running=true; requestAnimationFrame(anim); } }
  function tick(){
    var vh=window.innerHeight, p;
    if(track){
      /* progreso del carril sticky: 0 cuando el carril empieza a pegarse, 1 cuando se despega */
      var tr=track.getBoundingClientRect(), stageH=stage.getBoundingClientRect().height;
      var range=Math.max(1, tr.height - stageH);
      p=(stickyTopPx - tr.top)/range;
    } else {
      var r=stage.getBoundingClientRect();
      /* p=0 cuando el stage asoma por abajo; p=1 cuando su centro llega al 45% de la pantalla */
      var start=vh, end=vh*0.45 - r.height/2;
      p=(start - r.top)/(start - end);
    }
    p=Math.max(0,Math.min(1,p));
    if(bar) bar.style.setProperty('--t',p.toFixed(3));
    want=1+p*(N-1);
    kick();
  }
  function onResize(){
    var w=window.innerWidth;
    if(w===lastWidth) return; /* iOS cambia innerHeight al mostrar/ocultar la barra de direcciones sin cambiar el ancho: ignorar ese resize */
    lastWidth=w;
    stickyTopPx=window.innerHeight*0.10;
    tick();
  }
  function activar(){
    startLoad();
    if(reduced) return;
    window.addEventListener('scroll',tick,{passive:true});
    window.addEventListener('resize',onResize);
    tick();
  }
  function liberar(){
    if(!started) return;
    gen++; /* invalida el setTimeout de READY_TIMEOUT_MS de esta tanda si todavía estaba pendiente */
    window.removeEventListener('scroll',tick);
    window.removeEventListener('resize',onResize);
    imgs=[]; ok=[]; loadedCount=0; allReady=false; started=false; running=false; want=1; cur=1;
    ctx.clearRect(0,0,W,H);
  }
  var ioTarget=track||stage;
  if('IntersectionObserver' in window){
    var lead=Math.round(window.innerHeight*1.5)+'px';
    var io=new IntersectionObserver(function(es){
      es.forEach(function(e){ if(e.isIntersecting && !started) activar(); });
    },{rootMargin:lead+' 0px '+lead+' 0px'});
    io.observe(ioTarget);
    var farLead=Math.round(window.innerHeight*3)+'px';
    var ioFar=new IntersectionObserver(function(es){
      es.forEach(function(e){ if(!e.isIntersecting) liberar(); });
    },{rootMargin:farLead+' 0px '+farLead+' 0px'});
    ioFar.observe(ioTarget);
  } else { activar(); }
}

/* ORDEN AY9: el motor queda como ÚNICO despiece chico, así que se le dedica un camino propio
   en vez de compartir initEscena con las otras 4 (que ya no cargan):
   - LUT de remuestreo por longitud de arco: medido el diff perceptual (gris, media de |Δ|)
     cuadro a cuadro de los 137 frames reales (mob), salía muy disparejo (CV=0.41: tramos casi
     quietos al inicio/fin, picos de hasta 12.8 en el medio). LUT[t] devuelve la posición de
     cuadro continua para que cada paso de scroll cueste el mismo cambio visual (CV 0.41->0.12,
     max 12.8->7.4, medido re-renderizando con el mismo crossfade que usa draw()). No hizo
     falta RIFE ni minterpolate: el crossfade ya existente entre cuadros vecinos alcanza para
     reespaciar sin generar frames nuevos ni perder nitidez.
   - Precarga total desde que abre la página (ya no hay otras 4 escenas compitiendo por ancho
     de banda/decode): decode() de los 137 cuadros de una, cuadro 1 fijo hasta que estén listos.
   - Canvas a resolución real de pantalla (devicePixelRatio, tope 2) en vez de al tamaño fijo
     784x1400 del HTML, recalculado si cambia el ancho.
   - Solo redibuja si la posición cambió (evita trabajo de GPU/CPU en frames idénticos) y ya
     no hace clearRect: el primer drawImage con alpha=1 ya cubre el canvas entero. */
var LUT_MOTOR=[1.0,4.168,6.397,8.38,10.254,11.749,13.379,14.753,16.028,17.361,18.801,20.104,21.459,23.046,24.414,25.801,27.491,28.881,30.27,31.9,33.2,34.329,35.512,36.829,38.075,39.114,40.532,41.975,43.454,44.616,45.737,46.735,47.613,48.439,49.279,50.194,51.148,52.007,52.743,53.545,54.402,55.236,55.972,56.753,57.489,58.216,58.976,59.773,60.526,61.233,61.888,62.525,63.17,63.847,64.536,65.215,65.869,66.472,67.066,67.702,68.363,69.04,69.638,70.254,70.9,71.486,72.067,72.686,73.318,73.964,74.597,75.215,75.811,76.409,77.008,77.643,78.287,78.941,79.577,80.199,80.798,81.438,82.095,82.731,83.428,84.152,84.818,85.453,86.086,86.785,87.511,88.236,88.935,89.604,90.278,90.964,91.716,92.494,93.273,94.03,94.714,95.447,96.216,96.983,97.875,98.702,99.459,100.21,101.05,102.022,102.87,103.666,104.451,105.262,106.142,107.062,107.963,108.789,109.682,110.571,111.56,112.582,113.484,114.412,115.531,116.616,117.718,118.823,120.097,121.594,122.9,124.249,126.05,127.702,129.935,132.279,137.0];
function initMotor(cfg){
  var stage=document.getElementById(cfg.stage), canvas=document.getElementById(cfg.canvas);
  if(!stage||!canvas) return;
  var ctx=canvas.getContext('2d'), N=cfg.n, LUT=cfg.lut;
  var dir = window.matchMedia('(max-width:720px)').matches ? cfg.dirMob : cfg.dirDesk;
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* want/cur viven en progreso de scroll 0..1 (t); draw()/LUT trabajan en posición de cuadro 1..N */
  var imgs=[], ok=[], loadedCount=0, allReady=false, want=0, cur=0, drawnPos=-1, running=false;
  var W=0, H=0, lastWidth=window.innerWidth;
  function src(i){ return dir+'f_'+String(i).padStart(3,'0')+'.webp'; }
  function lutPos(p){
    var x=Math.max(0,Math.min(1,p))*(LUT.length-1), i0=Math.floor(x), frac=x-i0;
    if(i0>=LUT.length-1) return LUT[LUT.length-1];
    return LUT[i0]*(1-frac)+LUT[i0+1]*frac;
  }
  function sizeCanvas(){
    var rect=canvas.getBoundingClientRect();
    if(!rect.width||!rect.height) return;
    var dpr=Math.min(window.devicePixelRatio||1,2);
    var w=Math.max(1,Math.round(rect.width*dpr)), h=Math.max(1,Math.round(rect.height*dpr));
    if(w===W && h===H) return;
    W=w; H=h; canvas.width=W; canvas.height=H; drawnPos=-1; draw(lutPos(cur),true);
  }
  function draw(pos,force){
    if(!imgs.length || !W || !H) return;
    if(!allReady) pos=1;
    if(!force && Math.abs(pos-drawnPos)<0.01) return; /* dibujar SOLO cuando cambia el cuadro */
    var i0=Math.floor(pos), frac=pos-i0, i1=i0+1;
    if(i0<1){ i0=1; i1=1; frac=0; } if(i1>N){ i1=N; if(i0>N) i0=N; }
    if(!imgs[i0] || !ok[i0]) return;
    drawnPos=pos;
    ctx.drawImage(imgs[i0],0,0,W,H); /* cubre el canvas entero: no hace falta clearRect antes */
    if(i1!==i0 && frac>0.004 && imgs[i1] && ok[i1]){ ctx.globalAlpha=frac; ctx.drawImage(imgs[i1],0,0,W,H); ctx.globalAlpha=1; }
  }
  function load(i){
    if(imgs[i]) return;
    var im=new Image(); im.decoding='async'; im.src=src(i); imgs[i]=im;
    var mark=function(){
      if(imgs[i]!==im) return; ok[i]=true; loadedCount++;
      if(i===1) draw(1,true); /* cuadro 1 visible en cuanto él esté listo, aunque falten los demás */
      if(loadedCount>=N){ allReady=true; draw(lutPos(cur),true); }
    };
    if(im.decode){ im.decode().then(mark, mark); } else { im.onload=mark; }
  }
  function preloadAll(){ for(var i=1;i<=N;i++) load(i); }
  function anim(){
    var d=want-cur;
    if(Math.abs(d)<0.0015){ cur=want; draw(lutPos(cur),false); running=false; return; }
    cur+=d*0.14;
    draw(lutPos(cur),false);
    requestAnimationFrame(anim);
  }
  function kick(){ if(!running){ running=true; requestAnimationFrame(anim); } }
  function tick(){
    /* ORDEN AZ2: sin carril/pin — mismo criterio que la moto grande (initEscena sin track):
       p=0 cuando el TOPE del stage asoma por abajo de la pantalla (top=100vh), p=1 cuando
       su CENTRO llega al 38% de la pantalla (ya completamente abierto antes de salir). */
    var vh=window.innerHeight, r=stage.getBoundingClientRect();
    var start=vh, end=vh*0.38 - r.height/2;
    var p=(start - r.top)/(start - end);
    p=Math.max(0,Math.min(1,p));
    want=p;
    kick();
  }
  function onResize(){
    var w=window.innerWidth;
    if(w===lastWidth){ sizeCanvas(); return; } /* iOS cambia innerHeight sin cambiar el ancho */
    lastWidth=w;
    sizeCanvas();
    tick();
  }
  sizeCanvas();
  draw(1,true); /* cuadro 1 visible desde ya, mientras decodifican los 137 */
  preloadAll(); /* precarga TOTAL desde que abre la página: ya no compite con otras escenas */
  if(reduced){ want=1; cur=1; return; } /* draw(1,true) + el gancho de mark() al quedar allReady ya muestran el cuadro final */
  window.addEventListener('scroll',tick,{passive:true});
  window.addEventListener('resize',onResize);
  tick();
}
