import { platformMeta } from '../lib/platforms.js';

export default function PlatformChip({ platform, size = 'sm' }) {
  const meta = platformMeta(platform);
  const cls = size === 'xs'
    ? 'px-1.5 py-px text-[9px]'
    : 'px-2 py-0.5 text-[10px] sm:text-xs';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border font-semibold shrink-0 ${cls} ${meta.chip} ${meta.border} ${meta.text}`}
    >
      <span className={`w-1 h-1 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}
