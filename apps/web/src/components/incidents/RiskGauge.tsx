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
          stroke="#1e293b"
          strokeWidth={strokeWidth}
          fill="transparent"
        />
        {/* Progress Arc */}
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
        />
      </svg>

      {/* Central Score Display */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-xl font-black font-mono leading-none" style={{ color: meta.fillHex }}>
          {Math.round(score)}
        </span>
        <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 mt-0.5">
          / 100
        </span>
      </div>
    </div>
  );
};

export default RiskGauge;
