import React from "react";
import { C } from "./theme";

// Light canvas with a subtle dotted grid. Static on purpose: the content moves, the paper doesn't.
export const ExplainerBackground: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: C.bg, overflow: "hidden" }}>
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundImage: `radial-gradient(${C.dot} 2.6px, transparent 3px)`,
        backgroundSize: "46px 46px",
        backgroundPosition: "11px 11px",
      }}
    />
  </div>
);
