const {useEffect,useRef,useState}=React;
const h=React.createElement;
const API="/api/bihar-live";

function Dashboard(){
  const [health,setHealth]=useState(null);
  const [fusion,setFusion]=useState(null);
  const [evaluation,setEvaluation]=useState(null);
  const [sources,setSources]=useState([]);
  const [district,setDistrict]=useState("patna");
  const [lead,setLead]=useState(3);
  const [error,setError]=useState("");
  const mapRef=useRef(null), mapObj=useRef(null), chartRef=useRef(null), chartObj=useRef(null);

  async function load(){
    try{
      setError("");
      const responses=await Promise.all([
        fetch(API+"/health",{cache:"no-store"}),
        fetch(API+"/fusion?lead="+lead,{cache:"no-store"}),
        fetch(API+"/model/evaluation",{cache:"no-store"}),
        fetch(API+"/sources",{cache:"no-store"})
      ]);
      const data=await Promise.all(responses.map(r=>r.json()));
      if(responses.some(r=>!r.ok)) throw new Error(data.find(x=>x.error)?.error||"JalDrishti API request failed");
      setHealth(data[0]);setFusion(data[1]);setEvaluation(data[2]);setSources(data[3].sources||[]);
    }catch(err){setError(err.message);setHealth(null)}
  }

  useEffect(()=>{load();const timer=setInterval(load,15000);return()=>clearInterval(timer)},[lead]);

  useEffect(()=>{
    if(!mapRef.current||mapObj.current||!window.L)return;
    mapObj.current=L.map(mapRef.current).setView([25.85,85.25],8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:18,attribution:"© OpenStreetMap contributors"}).addTo(mapObj.current);
    [[25.5941,85.1376,"Patna"],[26.1209,85.3647,"Muzaffarpur"]].forEach(([lat,lon,name])=>{
      L.circleMarker([lat,lon],{radius:8,weight:2,fillOpacity:.85}).addTo(mapObj.current).bindPopup("<b>"+name+"</b><br>JalDrishti monitoring point");
    });
  },[]);

  useEffect(()=>{
    if(!chartRef.current||!window.Chart||!evaluation)return;
    if(chartObj.current)chartObj.current.destroy();
    chartObj.current=new Chart(chartRef.current,{type:"bar",data:{
      labels:["MAE","RMSE"],datasets:[{label:"Synthetic test error",data:[evaluation.mae,evaluation.rmse],borderWidth:1}]
    },options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#8ca7af"},grid:{color:"#18343f"}},y:{beginAtZero:true,ticks:{color:"#8ca7af"},grid:{color:"#18343f"}}}}});
  },[evaluation]);

  const weights=(fusion&&fusion.weights)||{};
  return h("div",{className:"jl-app"},
    h("header",{className:"jl-header"},
      h("div",null,h("strong",null,"JalDrishti"),h("span",null," Bihar Integrated Early Warning")),
      h("div",{id:"data-badge",className:"jl-badge"},health?health.badge:"System unavailable")
    ),
    h("main",{className:"jl-main"},
      h("div",{className:"jl-toolbar"},
        h("div",null,
          h("button",{className:district==="patna"?"active":"",onClick:()=>setDistrict("patna")},"Patna"),
          h("button",{className:district==="muzaffarpur"?"active":"",onClick:()=>setDistrict("muzaffarpur")},"Muzaffarpur")
        ),
        h("span",{className:"jl-muted"},health?"Auto-refresh 15s":"API unavailable")
      ),
      h("h1",null,district==="patna"?"Patna":"Muzaffarpur"),
      h("p",{className:"jl-muted"},"72-hour rainfall and inundation decision-support prototype."),
      error&&h("div",{className:"jl-error"},"API error: "+error),
      h("section",{className:"jl-grid"},
        h("article",{className:"jl-card"},
          h("h2",null,"MULTI-SOURCE RAINFALL FUSION"),
          h("div",{className:"jl-metric"},fusion?fusion.estimate_mm+" mm":"—"),
          h("p",{className:"jl-muted"},"Fused rainfall estimate · lead "+lead+"h"),
          h("div",{className:"jl-leadrow"},h("span",null,"Forecast lead"),h("b",null,lead+"h")),
          h("input",{className:"jl-slider",type:"range",min:"1",max:"72",value:lead,onChange:e=>setLead(Number(e.target.value))}),
          h("div",{className:"jl-weights"},Object.entries(weights).map(([name,value])=>
            h("div",{key:name},h("small",null,name),h("b",null,Math.round(value*100)+"%"))
          ))
        ),
        h("article",{className:"jl-card"},
          h("h2",null,"BASELINE EVALUATION"),
          h("div",{className:"jl-stats"},
            h("div",null,h("b",null,evaluation?evaluation.mae.toFixed(2):"—"),h("small",null,"MAE")),
            h("div",null,h("b",null,evaluation?evaluation.rmse.toFixed(2):"—"),h("small",null,"RMSE"))
          ),
          h("p",{className:"jl-muted"},evaluation?"Chronological split · "+evaluation.data_mode+" · "+evaluation.backend:"Waiting for API"),
          h("div",{className:"jl-chart"},h("canvas",{ref:chartRef}))
        )
      ),
      h("section",{className:"jl-map"},h("div",{ref:mapRef})),
      h("section",{className:"jl-card jl-source-card"},
        h("h2",null,"DATA SOURCES"),
        h("div",{className:"jl-sources"},sources.map(source=>
          h("div",{key:source.name},h("span",null,source.name),h("b",null,source.status))
        ))
      ),
      h("p",{className:"jl-foot"},"Synthetic demo data is explicitly labeled. Fusion weights are an engineering baseline, not learned accuracy weights. Real mode fails closed when provider data is unavailable.")
    )
  );
}
ReactDOM.createRoot(document.getElementById("root")).render(h(Dashboard));
