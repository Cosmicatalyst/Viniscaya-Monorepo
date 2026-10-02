"use client";
import { useEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { CloudBoxPicker } from "@/components/cloud-box-picker";
import { medicalApi } from "@/lib/medical-api";

type Stats = {threads: number; resources: number; analyses: number; activity: {date: string; analyses: number; threads: number}[]; specialties: {name: string; count: number}[]};
export function Home({ navigate }: { navigate: (destination: string) => void }) {
  const [stats, setStats] = useState<Stats>();
  const [error, setError] = useState("");
  useEffect(() => { let alive = true; medicalApi("v1/stats").then(data => {if (alive) setStats(data);}).catch(e => {if (alive) setError(e.message);}); return () => {alive = false;}; }, []);
  const maximum = Math.max(1, ...(stats?.activity.map(day => Math.max(day.analyses, day.threads)) || []));
  const specialtyMax = Math.max(1, ...(stats?.specialties.map(item => item.count) || []));
  const hasActivity = stats?.activity.some(day => day.analyses || day.threads);
  return <div className="home-minimal">
    <div className="minimal-heading"><h1>Overview</h1><div className="home-heading-tools"><span>Last 7 days</span><CloudBoxPicker/></div></div>
    <div className="minimal-stats">
      <button onClick={() => navigate("Threads")}><span>Threads</span><strong>{stats?.threads ?? "—"}</strong><ArrowUpRight size={15} /></button>
      <button onClick={() => navigate("Library")}><span>Saved analyses</span><strong>{stats?.resources ?? "—"}</strong><ArrowUpRight size={15} /></button>
      <button onClick={() => navigate("General")}><span>Analyses run</span><strong>{stats?.analyses ?? "—"}</strong><ArrowUpRight size={15} /></button>
    </div>
    {error && <p className="medical-error" role="alert">{error}</p>}
    <div className="minimal-charts">
      <section className="minimal-chart">
        <header><h2>Activity</h2><span>Conversations · Analyses</span></header>
        <div className="activity-plot"><div className="plot-lines">{[1,2,3,4].map(n => <div key={n}/>)}</div>
          {!hasActivity ? <div className="plot-empty"><span>{stats ? "No activity yet" : "Loading activity…"}</span></div> : <div className="activity-bars">{stats?.activity.map(day => <div key={day.date}><i title={`${day.date}: ${day.threads} conversations`} style={{height: `${day.threads / maximum * 100}%`}}/><b title={`${day.date}: ${day.analyses} analyses`} style={{height: `${day.analyses / maximum * 100}%`}}/></div>)}</div>}
        </div>
        <div className="plot-days">{stats?.activity.map(day => <span key={day.date}>{new Date(day.date + "T00:00:00").toLocaleDateString(undefined,{weekday: "short"})}</span>)}</div>
      </section>
      <section className="minimal-chart specialty-chart"><header><h2>By specialty</h2><span>Completed analyses</span></header><div className="specialty-bars">{(stats?.specialties || ["Cancer","Proteins","Radiology","Neurology","Cardiac","General"].map(name => ({name,count:0}))).map(item => <button className="specialty-bar-row" key={item.name} onClick={() => navigate(item.name)}><span>{item.name}</span><div className="specialty-bar-track"><i style={{width: `${item.count / specialtyMax * 100}%`}}/></div><span>{stats ? item.count : "—"}</span></button>)}</div></section>
    </div>
  </div>;
}
