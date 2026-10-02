"use client";

import { useEffect, useRef, useState } from "react";
import { RotateCcw, Upload } from "lucide-react";
import type { GLViewer } from "3dmol";

export function ProteinViewer({ pdb }: { pdb?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const viewer = useRef<GLViewer | null>(null);
  const [structure, setStructure] = useState<{ text: string; format: string; name: string } | null>(null);
  const [style, setStyle] = useState("cartoon");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [atoms, setAtoms] = useState(0);

  useEffect(() => {
    const element = container.current;
    let disposed = false;
    let resize: ResizeObserver | undefined;
    import("3dmol").then(mol => {
      if (disposed || !element) return;
      viewer.current = mol.createViewer(element, { backgroundColor: "#fafafa", antialias: true });
      resize = new ResizeObserver(() => { viewer.current?.resize(); viewer.current?.render(); });
      resize.observe(element);
      setReady(true);
    }).catch(() => { if (!disposed) setError("The 3D viewer could not start. Check that WebGL is enabled."); });
    return () => { disposed = true; resize?.disconnect(); viewer.current?.clear(); viewer.current = null; element?.replaceChildren(); };
  }, []);

  useEffect(() => {
    const input = pdb ? { text: pdb, format: "pdb", name: "Predicted structure" } : structure;
    if (!ready || !input || !viewer.current) return;
    try {
      const view = viewer.current;
      view.removeAllModels();
      const model = view.addModel(input.text, input.format);
      const count = model.selectedAtoms({}).length;
      if (!count) throw new Error("No atoms found. Choose a valid PDB or mmCIF structure.");
      setAtoms(count);
      setError("");
      view.setStyle({}, { cartoon: { color: "spectrum" }, stick: { radius: .12 } });
      view.zoomTo(); view.render();
    } catch (error) { setAtoms(0); setError(error instanceof Error ? error.message : "Could not load this structure."); }
  }, [structure, ready, pdb]);

  useEffect(() => {
    const view = viewer.current;
    if (!view || !atoms) return;
    const styles = { cartoon: { cartoon: { color: "spectrum" }, stick: { radius: .12 } }, sticks: { stick: { radius: .2 } }, spheres: { sphere: { scale: .7 } } };
    view.setStyle({}, styles[style as keyof typeof styles]); view.render();
  }, [style, atoms]);

  async function load(file?: File) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError("Choose a structure smaller than 10 MB."); return; }
    const format = /\.(cif|mmcif)$/i.test(file.name) ? "cif" : /\.pdb$/i.test(file.name) ? "pdb" : "";
    if (!format) { setError("Choose a PDB or mmCIF file."); return; }
    try { setStructure({ text: await file.text(), format, name: file.name }); }
    catch { setError("Could not read this file."); }
  }

  return <section className="protein-viewer-section">
    <header><h2>3D structure</h2><div className="protein-viewer-tools"><select aria-label="Structure display style" value={style} onChange={event => setStyle(event.target.value)}><option value="cartoon">Ribbon + sticks</option><option value="sticks">Sticks</option><option value="spheres">Spheres</option></select><button onClick={() => { viewer.current?.zoomTo(); viewer.current?.render(); }} aria-label="Reset camera"><RotateCcw size={15} /></button><label><Upload size={15} />Load structure<input type="file" accept=".pdb,.cif,.mmcif" onChange={event => { void load(event.target.files?.[0]); event.target.value = ""; }} /></label></div></header>
    <div className="protein-viewer-frame"><div ref={container} className="protein-viewer-canvas" aria-label="Interactive 3D protein structure" />{!atoms && <div className="protein-viewer-empty">Predict from a sequence below, or load a PDB / mmCIF file.</div>}</div>
    <div className="protein-viewer-footer"><span>{structure && atoms ? `${structure.name} · ${atoms.toLocaleString()} atoms` : "Files stay in your browser"}</span><span>Drag to rotate · Scroll to zoom</span></div>
    {error && <p className="medical-error" role="alert">{error}</p>}
  </section>;
}
