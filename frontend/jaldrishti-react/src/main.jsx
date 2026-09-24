import React,{useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const API="/api/bihar-live";
function App(){
 const [health,setHealth]=useState(null),[fusion,setFusion]=useState(null),[evaluation,setEvaluation]=useState(null),[district,setDistrict]=useState("patna"),[lead,setLead]=useState(3);
 useEffect(()=>{let alive=true; const load=async()=>{try{const [h,f,e]=await Promise.all([fetch(API+"/health"),fetch(API+"/fusion?lead="+lead),fetch(API+"/model/evaluation")]); const data=await Promise.all([h.json(),f.json(),e.json()]); if(alive){setHealth(data[0]);setFusion(data[1]);setEvaluation(data[2]);}}catch(err){if(alive)setHealth({error:err.message})}}; load(); const timer=setInterval(load,15000); return()=>{alive=false;clearInterval(timer)}},[lead]);
 return <div className="app"><header><div><b>JalDrishti</b><span> Bihar Integrated Early Warning</span></div><div className="badge">{health?.badge||"Loading..."}</div></header>
 <nav><button className={district==="patna"?"active":""} onClick={()=>setDistrict("patna")}>Patna</button><button className={district==="muzaffarpur"?"active":""} onClick={()=>setDistrict("muzaffarpur")}>Muzaffarpur</button></nav>
 <main><section className="hero"><div><small>CONTROL ROOM</small><h1>{district==="patna"?"Patna":"Muzaffarpur"}</h1><p>72-hour rainfall and inundation decision-support prototype.</p></div><div className="metric"><strong>{fusion?.estimate_mm??"—"}</strong><span>fused rain mm</span></div></section>
 <section className="grid"><article><h2>Forecast lead</h2><input type="range" min="1" max="72" value={lead} onChange={e=>setLead(e.target.value)}/><strong>{lead}h</strong><div className="weights">{Object.entries(fusion?.weights||{}).map(([k,v])=><div key={k}><span>{k}</span><b>{Math.round(v*100)}%</b></div>)}</div></article>
 <article><h2>Baseline evaluation</h2><div className="numbers"><div><b>{evaluation?.mae?.toFixed(2)??"—"}</b><span>MAE</span></div><div><b>{evaluation?.rmse?.toFixed(2)??"—"}</b><span>RMSE</span></div></div><p className="muted">Chronological test split · {evaluation?.data_mode||"—"} · {evaluation?.backend||"—"}</p></article></section>
 <section className="map"><div className="mapbox"><div className="pin p1">PATNA</div><div className="pin p2">MUZAFFARPUR</div><div className="maplabel">Bihar live monitoring map</div></div></section>
 <footer>Source confidence is model/input confidence, not forecast accuracy. Real mode never falls back to synthetic data.</footer>
 </main></div>
}
createRoot(document.getElementById("root")).render(<App/>);