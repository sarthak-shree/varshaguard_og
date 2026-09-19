const API_BASE="";
let map,layer,state={rows:[],stations:[]};
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function getJson(url){const r=await fetch(url,{cache:"no-store"});let d={};try{d=await r.json()}catch{}if(!r.ok||d.success===false)throw Error(d.error||("HTTP "+r.status));return d}
function setHealth(id,value,good=true){$(id).textContent=value;$(id).style.color=good?"var(--green)":"var(--amber)"}
function riskClass(r){return String(r||"LOW").toLowerCase()}
function render(){
 const selected=$("districtSelect").value;
 const rows=state.rows.filter(r=>!selected||r.district===selected);
 $("selectedDistrict").textContent=selected||"All Bihar";
 const top=rows.reduce((a,b)=>!a||Number(b.flood_probability)>Number(a.flood_probability)?b:a,null);
 if(top){const pct=Number(top.flood_probability_percent)||0;$("riskLevel").textContent=top.risk;$("probability").textContent=pct.toFixed(1)+"%";$("probabilityFill").style.width=Math.max(0,Math.min(100,pct))+"%";$("riskCard").className="risk-card "+riskClass(top.risk);$("riskNote").textContent=top.river_confirmation+" river confirmation • integrated alert state";$("updated").textContent=top.data_timestamp||"—"}else{$("riskLevel").textContent="UNKNOWN";$("probability").textContent="--%";$("probabilityFill").style.width="0";$("riskNote").textContent="No current district prediction available."}
 const ds=[...new Set(state.rows.map(r=>r.district))].sort(),old=selected;$("districtSelect").innerHTML='<option value="">All Bihar</option>'+ds.map(d=>'<option>'+esc(d)+"</option>").join("");$("districtSelect").value=old;
 $("districtCount").textContent=rows.length;$("highCount").textContent=rows.filter(r=>r.risk==="HIGH").length;$("mediumCount").textContent=rows.filter(r=>r.risk==="MEDIUM").length;$("stationCount").textContent=state.stations.length+" stations";$("stationMetric").textContent=state.stations.length;
 $("riskBody").innerHTML=rows.map(r=>'<tr><td><b>'+esc(r.district)+'</b></td><td><span class="badge '+riskClass(r.risk)+'">'+esc(r.risk)+'</span></td><td>'+Number(r.flood_probability_percent).toFixed(2)+'%</td><td>'+esc(r.river_confirmation)+'</td><td>'+r.rainfall_24h_mm+' mm</td><td>'+r.rainfall_72h_mm+' mm</td><td>'+(r.river_level_max_m??"—")+' m</td><td>'+(r.river_mean_rise_1h_m??"—")+'</td><td>'+(r.inundation?.available?r.inundation.extent_percent+"% / "+r.inundation.depth_m+"m":"—")+'</td></tr>').join("")||'<tr><td colspan="9">No district data.</td></tr>';
 $("riverBody").innerHTML=state.stations.map(s=>{const l=Number(s.water_level_m),w=Number(s.warning_level_m),d=Number(s.danger_level_m);const st=Number.isFinite(d)&&l>=d?"DANGER":Number.isFinite(w)&&l>=w?"WARNING":"NORMAL";return '<tr><td><b>'+esc(s.station)+'</b></td><td>'+esc(s.district)+'</td><td>'+esc(s.river)+'</td><td>'+ (Number.isFinite(l)?l.toFixed(2):"—")+' m</td><td>'+ (Number.isFinite(w)?w.toFixed(2):"—")+'</td><td>'+ (Number.isFinite(d)?d.toFixed(2):"—")+'</td><td>'+st+'</td><td>'+(Number(s.rise_1h_m)>0?"↑ rising":Number(s.rise_1h_m)<0?"↓ falling":"→ steady")+'</td></tr>'}).join("")||'<tr><td colspan="8">No live observations.</td></tr>';
 const r=top||{};$("rainBars").innerHTML=top? [["24H",r.rainfall_24h_mm,"r24"],["72H",r.rainfall_72h_mm,"r72"],["7D",r.rainfall_7d_mm,"r7"],["14D",r.rainfall_14d_mm,"r14"]].map(x=>'<div class="bar-col"><div class="bar-stack"><div class="bar '+x[2]+'" style="height:'+Math.max(2,Math.min(100,(Number(x[1])||0)/Math.max(1,Number(r.rainfall_14d_mm)||1)*100))+'%"></div></div><div class="bar-value">'+(x[1]??"—")+' mm</div><div class="bar-label">'+x[0]+'</div></div>').join(""):'<div class="empty">No rainfall data.</div>';
 layer.clearLayers();state.stations.forEach(s=>{const lat=Number(s.latitude),lon=Number(s.longitude);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;const l=Number(s.water_level_m),w=Number(s.warning_level_m),d=Number(s.danger_level_m);const st=Number.isFinite(d)&&l>=d?"DANGER":Number.isFinite(w)&&l>=w?"WARNING":"NORMAL";L.circleMarker([lat,lon],{radius:7,weight:2,color:"#dbe7ef",fillColor:st==="DANGER"?"#ff5f6d":st==="WARNING"?"#f2a93b":"#38d39f",fillOpacity:.9}).bindPopup("<b>"+esc(s.station)+"</b><br>"+esc(s.district)+"<br>Level: "+(Number.isFinite(l)?l.toFixed(2):"—")+" m<br>Status: "+st).addTo(layer)});
}
async function refresh(){
 try{
  const [risk,river]=await Promise.all([getJson("/api/bihar-live/ml-risk"),getJson("/api/bihar-live/stations")]);
  state.rows=risk.districts||[];state.stations=river.stations||[];
  setHealth("rainStatus",risk.rainfall_failures?.length?"PARTIAL":"ONLINE",!risk.rainfall_failures?.length);setHealth("riverStatus","LIVE");setHealth("modelStatus",risk.model?.name||"LOADED");setHealth("inundationStatus",state.rows.some(r=>r.inundation?.available)?"PROXY":"LIMITED",false);
  $("modelName").textContent=risk.model?.name||"—";$("modelScope").textContent=risk.model?.target||"Calibrated Bihar flood-event probability";$("horizon").textContent=(risk.prediction_horizon_hours||24)+"h";$("calibration").textContent=risk.model?.calibration_method||"—";$("rainSource").textContent=risk.rainfall_source||"—";$("riverSource").textContent=risk.river_source||"—";
  const feats=risk.model?.features||[];$("features").innerHTML=feats.map(f=>'<div class="feature"><span>MODEL FEATURE</span><b>'+esc(f)+'</b></div>').join("");
  $("lastSync").textContent="SYNC "+new Date().toLocaleTimeString("en-IN",{hour12:false})+" IST";render();$("message").classList.add("hidden");
 }catch(e){$("message").textContent="Bihar Live unavailable: "+e.message;$("message").classList.remove("hidden");setHealth("rainStatus","ERROR",false);setHealth("riverStatus","ERROR",false);setHealth("modelStatus","ERROR",false)}
}
function init(){map=L.map("map").setView([25.9,85.3],7);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:18,attribution:"© OpenStreetMap contributors"}).addTo(map);layer=L.layerGroup().addTo(map);$("districtSelect").addEventListener("change",render);$("refreshBtn").addEventListener("click",refresh);refresh();setInterval(refresh,300000);setInterval(()=>{$("clock").textContent=new Date().toLocaleTimeString("en-IN",{hour12:false})+" IST"},1000)}
document.addEventListener("DOMContentLoaded",init);
