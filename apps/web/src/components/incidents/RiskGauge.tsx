'use client';

import React from 'react';
import { getRiskLevelMeta } from '../../lib/formatters';
import { RiskLevel } from '../../types/api';

interface RiskGaugeProps {
  score: number;
  level: RiskLevel;
  size?: number;
}

export const RiskGauge: React.FC<RiskGaugeProps> = ({
  score,
  level,
  size = 96,
}) => {
  const meta = getRiskLevelMeta(level);
  const strokeWidth = 8;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const clampedScore = Math.max(0, Math.min(100, score));
  const strokeDashoffset = circumference - (clampedScore / 100) * circumference;

  return (
    <div
      className="relative flex items-center justify-center select-none"
      style={{ width: size, height: size }}
    >
      <svg className="w-full h-full -rotate-90" viewBox={`0 0 ${size} ${size}`}>
        {/* Background Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#151922"
          strokeWidth={strokeWidth}
          fill="transparent"
        />
        {/* Progress Arc with Neon Glow */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={meta.fillHex}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          fill="transparent"
          className="transition-all duration-1000 ease-out"
          style={{
            filter: `drop-shadow(0 0 6px ${meta.fillHex}80)`,
          }}
        />
      </svg>

      {/* Central Score Display */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-xl font-black font-mono leading-none tracking-tight" style={{ color: meta.fillHex, textShadow: `0 0 10px ${meta.fillHex}60` }}>
          {Math.round(score)}
        </span>
        <span className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-400 mt-0.5">
          RISK
        </span>
      </div>
    </div>
  );
};

export default RiskGauge;
