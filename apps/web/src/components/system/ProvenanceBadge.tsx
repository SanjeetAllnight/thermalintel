'use client';

import React from 'react';
import { ProvenanceRecord } from '../../types/provenance';
import { getFreshnessMeta, formatTimestamp } from '../../lib/formatters';
import { ShieldCheck, Info } from 'lucide-react';

interface ProvenanceBadgeProps {
  provenance: ProvenanceRecord;
  className?: string;
  onClick?: () => void;
}

export const ProvenanceBadge: React.FC<ProvenanceBadgeProps> = ({
  provenance,
  className = '',
  onClick,
}) => {
  const meta = getFreshnessMeta(provenance.freshness_state);

  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center space-x-1.5 px-2 py-0.5 rounded text-[10px] font-mono border transition-all ${
        onClick ? 'hover:bg-slate-800 cursor-pointer' : 'cursor-default'
      } ${meta.badgeBg} ${className}`}
      title={`Source: ${provenance.provider} (${provenance.product}) • Observed: ${
        provenance.observed_at_utc ? formatTimestamp(provenance.observed_at_utc) : 'N/A'
      }`}
    >
      <ShieldCheck className="w-3 h-3 shrink-0" />
      <span className="font-semibold text-white/90">{provenance.provider}</span>
      <span className="text-white/60">/</span>
      <span className="text-white/80">{provenance.product.split('_')[0]}</span>
      <span
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${meta.dotColor}`}
        aria-hidden="true"
      />
      <span className="font-bold">{meta.label}</span>
      {onClick && <Info className="w-2.5 h-2.5 opacity-60 ml-0.5" />}
    </button>
  );
};

export default ProvenanceBadge;
