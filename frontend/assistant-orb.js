/* Nebula-style WebGL assistant orb for the plain-JS VarshaGuard frontend. */
(() => {
  "use strict";

  const STATES = new Set(["idle", "connecting", "listening", "thinking", "speaking", "error", "disabled"]);
  const FROM = "#818cf8";
  const TO = "#22d3ee";
  let renderer, scene, camera, material, mesh, raf = 0, last = 0, elapsed = 0;
  let host, canvas, active = true, reduced = false, currentState = "disabled";
  let audioLevel = -1;

  const vertexShader = `
    uniform float uTime;
    uniform float uAudio;
    uniform float uDistort;
    varying float vNoise;
    varying vec3 vNormal;
    varying vec3 vViewDir;
    vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
    float snoise(vec3 v){
      const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
      vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
      vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g;
      vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
      vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+2.0*C.xxx; vec3 x3=x0-1.0+3.0*C.xxx;
      i=mod289(i); vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
      float n_=1.0/7.0; vec3 ns=n_*D.wyz-D.xzx; vec4 j=p-49.0*floor(p*ns.z*ns.z);
      vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_); vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy;
      vec4 h=1.0-abs(x)-abs(y); vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
      vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
      vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
      vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
      vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
      p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
      vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);m=m*m;
      return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
    }
    void main(){
      float n=snoise(position*1.7+vec3(uTime*0.12,uTime*0.21,uTime*0.08));
      vec3 displaced=position+normalize(position)*(n*(uDistort*0.45)+uAudio*0.18);
      vNoise=n; vNormal=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(displaced,1.0);
      vViewDir=normalize(-mv.xyz); gl_Position=projectionMatrix*mv;
    }`;

  const fragmentShader = `
    uniform vec3 uFrom;
    uniform vec3 uTo;
    uniform float uTime;
    uniform float uAudio;
    varying float vNoise;
    varying vec3 vNormal;
    varying vec3 vViewDir;
    void main(){
      vec3 N=normalize(vNormal); vec3 V=normalize(vViewDir);
      float mixAmt=clamp(0.5+vNoise*1.4+sin(uTime*0.7+vNoise)*0.12,0.0,1.0);
      vec3 col=mix(uFrom*0.36,uTo,smoothstep(0.08,0.92,mixAmt));
      float light=0.35+0.65*max(dot(N,normalize(vec3(0.6,0.8,0.5))),0.0);
      float rim=pow(1.0-max(dot(N,V),0.0),2.3);
      col=col*light+uTo*rim*(0.7+uAudio*0.65);
      col+=vec3(0.25,0.38,0.52)*pow(max(dot(N,normalize(vec3(-0.5,-0.3,0.7))),0.0),4.0)*0.18;
      col=col/(1.0+col*0.35);
      gl_FragColor=vec4(col,0.98);
    }`;

  function stateVisual(state) {
    const map = {
      idle:{glow:0.55, distort:0.23, scale:1},
      connecting:{glow:0.65, distort:0.3, scale:1},
      listening:{glow:0.9, distort:0.38, scale:1.03},
      thinking:{glow:0.72, distort:0.46, scale:0.99},
      speaking:{glow:1, distort:0.42, scale:1.06},
      error:{glow:0.75, distort:0.3, scale:1},
      disabled:{glow:0.2, distort:0.16, scale:0.92}
    };
    return map[state] || map.idle;
  }

  function color(hex) { return new THREE.Color(hex); }

  function ensureScene() {
    host = document.querySelector("#assistantNebulaOrb .nebula-canvas-host");
    if (!host || renderer || !window.THREE) return;
    try {
      scene = new THREE.Scene();
      camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
      camera.position.z = 4.2;
      renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, powerPreference:"low-power"});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
      renderer.setSize(Math.max(host.clientWidth, 1), Math.max(host.clientHeight, 1), false);
      renderer.setClearColor(0x000000, 0);
      canvas = renderer.domElement;
      canvas.setAttribute("aria-hidden", "true");
      host.appendChild(canvas);
      material = new THREE.ShaderMaterial({
        vertexShader, fragmentShader, transparent:true,
        uniforms:{
          uTime:{value:0}, uAudio:{value:0}, uDistort:{value:0.23},
          uFrom:{value:color(FROM)}, uTo:{value:color(TO)}
        }
      });
      mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(1.15, 5), material);
      scene.add(mesh);
      scene.add(new THREE.AmbientLight(0xffffff, 0.5));
      resize();
      window.addEventListener("resize", resize);
    } catch (error) {
      host.dataset.webglError = "true";
      console.error("VarshaGuard Nebula orb could not initialize:", error);
    }
  }

  function resize() {
    if (!renderer || !host) return;
    const width = Math.max(host.clientWidth, 1), height = Math.max(host.clientHeight, 1);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function draw(now) {
    raf = 0;
    if (!renderer || !material || !active || document.hidden) return;
    const dt = last ? Math.min((now-last)/1000, 0.05) : 0;
    last = now;
    if (!reduced) elapsed += dt;
    const visual = stateVisual(currentState);
    material.uniforms.uTime.value = elapsed * (reduced ? 0 : 1);
    material.uniforms.uAudio.value = audioLevel >= 0 ? audioLevel : (currentState === "disabled" ? 0.05 : visual.glow*(0.65+0.35*Math.sin(elapsed*(currentState==="thinking"?2.5:4))));
    material.uniforms.uDistort.value = visual.distort;
    material.uniforms.uFrom.value.set(currentState==="error" ? "#fb7185" : FROM);
    material.uniforms.uTo.value.set(currentState==="error" ? "#f43f5e" : TO);
    mesh.rotation.y += reduced ? 0 : dt*(currentState==="thinking" ? 0.42 : 0.16);
    mesh.rotation.x = reduced ? 0 : Math.sin(elapsed*0.55)*0.1;
    const pulse = reduced ? 1 : visual.scale*(1+Math.sin(elapsed*1.7)*0.018);
    mesh.scale.setScalar(pulse);
    renderer.render(scene,camera);
    if (!reduced) raf = requestAnimationFrame(draw);
  }

  function wake() {
    if (!renderer) ensureScene();
    if (renderer && !raf && active && !document.hidden) {
      if (reduced) { draw(performance.now()); }
      else raf = requestAnimationFrame(draw);
    }
  }

  function setState(state, global = true) {
    const next = STATES.has(state) ? state : "idle";
    currentState = next;
    const orb = document.getElementById("assistantNebulaOrb");
    if (orb) {
      orb.dataset.state = next;
      orb.setAttribute("aria-label", "VarshaGuard AI " + next);
    }
    const dialog = document.querySelector(".assistant-dialog");
    if (dialog) dialog.dataset.assistantState = next;
    const label = document.getElementById("assistantOrbState");
    if (label) label.textContent = ({
      idle:"Ready to listen", connecting:"Connecting…", listening:"Listening to you…",
      thinking:"Thinking through the dashboard…", speaking:"Speaking response",
      error:"Something went wrong", disabled:"Voice mode ready"
    })[next];
    if (material) material.uniforms.uDistort.value = stateVisual(next).distort;
    wake();
  }

  function init() {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reduced = mq.matches;
    mq.addEventListener?.("change", event => { reduced = event.matches; wake(); });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && raf) { cancelAnimationFrame(raf); raf=0; last=0; }
      else wake();
    });
    document.addEventListener("varshaguard:assistant-state", event => {
      setState(event.detail?.state || "idle", event.detail?.global !== false);
    });
    const voiceMode = document.getElementById("assistantVoiceMode");
    voiceMode?.addEventListener("click", () => {
      window.setTimeout(() => { ensureScene(); resize(); setState("disabled"); }, 60);
    });
    new MutationObserver(() => {
      const panel = document.getElementById("assistantOrbPanel");
      if (panel && !panel.classList.contains("hidden")) {
        ensureScene(); resize(); wake();
      } else if (raf) { cancelAnimationFrame(raf); raf=0; }
    }).observe(document.getElementById("assistantOrbPanel") || document.body,{attributes:true,attributeFilter:["class"],subtree:true});
    ensureScene();
    setState("disabled");
  }

  window.VarshaGuardOrb = {
    setState(state, global=true) {
      document.dispatchEvent(new CustomEvent("varshaguard:assistant-state",{detail:{state,global}}));
    },
    setAudioLevel(level) { audioLevel = Number.isFinite(level) ? Math.max(0,Math.min(1,level)) : -1; }
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",init,{once:true});
  else init();
})();