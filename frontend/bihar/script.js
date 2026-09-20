const API_BASE='/api/bihar/v1';

function labelStatus(model) {
  if (model.status === 'trained_artifact_available') return 'Artifact available';
  if (model.status === 'model_not_trained') return 'Not trained';
  return model.status || 'Unknown';
}

async function loadStatus() {
  const el=document.getElementById('status');
  if(!el)return;
  const slug=location.pathname.toLowerCase().includes('muzaffarpur')?'muzaffarpur':'patna';
  try {
    const r=await fetch(`${API_BASE}/${slug}/status`,{cache:'no-store'});
    const d=await r.json();
    if(!r.ok) throw new Error(d.error || 'status request failed');
    el.textContent=`System status: ${d.operational_risk} · ${d.horizon_hours}-hour horizon · Live feeds: ${d.data_feeds.status}`;
    const rainfall=document.getElementById('rainfall-status');
    const flood=document.getElementById('flood-status');
    const inundation=document.getElementById('inundation-status');
    if(rainfall) rainfall.textContent=labelStatus(d.models.rainfall);
    if(flood) flood.textContent=labelStatus(d.models.flood);
    if(inundation) inundation.textContent=labelStatus(d.models.inundation);
  }catch(e){
    el.textContent='Bihar v1 API is not connected yet.';
  }
}
loadStatus();