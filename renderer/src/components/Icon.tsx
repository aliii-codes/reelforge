import React from "react";

// Small code-drawn icon set used by scene layouts. Names are chosen by the Python planner.
export const ICON_NAMES = [
  "chip",
  "brain",
  "phone",
  "bolt",
  "book",
  "chart",
  "bulb",
  "warning",
  "share",
  "layers",
  "globe",
  "scale",
] as const;

export const Icon: React.FC<{ name: string; size: number; color: string; accent: string }> = ({ name, size, color, accent }) => {
  const s = { stroke: color, strokeWidth: 6, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  let body: React.ReactNode;
  switch (name) {
    case "brain":
      body = (
        <>
          <path {...s} d="M50 20 C34 18 22 30 26 44 C14 50 16 68 30 72 C30 84 44 90 50 82 C56 90 70 84 70 72 C84 68 86 50 74 44 C78 30 66 18 50 20 Z" />
          <path {...s} d="M50 22 L50 82 M36 40 C42 42 46 46 46 52 M64 40 C58 42 54 46 54 52" stroke={accent} />
        </>
      );
      break;
    case "phone":
      body = (
        <>
          <rect {...s} x={30} y={12} width={40} height={76} rx={8} />
          <path {...s} d="M44 78 L56 78" stroke={accent} />
          <rect x={38} y={24} width={24} height={40} rx={3} fill={accent} opacity={0.35} />
        </>
      );
      break;
    case "bolt":
      body = <path {...s} d="M56 10 L28 56 L48 56 L42 90 L72 42 L52 42 Z" stroke={accent} />;
      break;
    case "book":
      body = (
        <>
          <path {...s} d="M50 26 C40 18 24 18 14 22 L14 80 C24 76 40 76 50 84 C60 76 76 76 86 80 L86 22 C76 18 60 18 50 26 Z" />
          <path {...s} d="M50 26 L50 84" stroke={accent} />
        </>
      );
      break;
    case "chart":
      body = (
        <>
          <path {...s} d="M14 86 L86 86" />
          <rect x={22} y={56} width={14} height={26} rx={3} fill={color} />
          <rect x={43} y={38} width={14} height={44} rx={3} fill={color} />
          <rect x={64} y={18} width={14} height={64} rx={3} fill={accent} />
        </>
      );
      break;
    case "bulb":
      body = (
        <>
          <path {...s} d="M36 62 C22 52 22 26 40 16 C56 8 78 18 78 40 C78 52 70 58 64 62 L64 72 L36 72 Z" />
          <path {...s} d="M40 82 L60 82 M44 90 L56 90" stroke={accent} />
        </>
      );
      break;
    case "warning":
      body = (
        <>
          <path {...s} d="M50 12 L90 84 L10 84 Z" />
          <path {...s} d="M50 38 L50 60 M50 72 L50 73" stroke={accent} strokeWidth={8} />
        </>
      );
      break;
    case "share":
      body = (
        <>
          <path {...s} d="M30 50 L70 26 M30 50 L70 74" />
          <circle cx={28} cy={50} r={11} fill={accent} />
          <circle cx={72} cy={24} r={11} fill={color} />
          <circle cx={72} cy={76} r={11} fill={color} />
        </>
      );
      break;
    case "layers":
      body = (
        <>
          <path {...s} d="M50 14 L88 34 L50 54 L12 34 Z" stroke={accent} />
          <path {...s} d="M12 50 L50 70 L88 50 M12 66 L50 86 L88 66" />
        </>
      );
      break;
    case "globe":
      body = (
        <>
          <circle {...s} cx={50} cy={50} r={36} />
          <path {...s} d="M14 50 L86 50 M50 14 C34 30 34 70 50 86 C66 70 66 30 50 14" stroke={accent} />
        </>
      );
      break;
    case "scale":
      body = (
        <>
          <path {...s} d="M50 14 L50 86 M30 86 L70 86 M18 28 L82 28" />
          <path {...s} d="M18 28 L8 56 L28 56 Z M82 28 L72 56 L92 56 Z" stroke={accent} />
        </>
      );
      break;
    case "chip":
    default:
      body = (
        <>
          <rect {...s} x={24} y={24} width={52} height={52} rx={8} />
          <rect x={38} y={38} width={24} height={24} rx={4} fill={accent} />
          <path {...s} d="M36 10 L36 22 M50 10 L50 22 M64 10 L64 22 M36 78 L36 90 M50 78 L50 90 M64 78 L64 90 M10 36 L22 36 M10 50 L22 50 M10 64 L22 64 M78 36 L90 36 M78 50 L90 50 M78 64 L90 64" />
        </>
      );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 100 100">
      {body}
    </svg>
  );
};
