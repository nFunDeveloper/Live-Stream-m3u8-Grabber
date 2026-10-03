export const PLATFORM_META = {
  chzzk: { label: '치지직', dot: 'bg-violet-500', text: 'text-violet-300', border: 'border-violet-500/20', chip: 'bg-violet-500/10' },
  soop: { label: 'SOOP', dot: 'bg-orange-500', text: 'text-orange-300', border: 'border-orange-500/20', chip: 'bg-orange-500/10' },
  cime: { label: 'ci.me', dot: 'bg-cyan-400', text: 'text-cyan-300', border: 'border-cyan-400/20', chip: 'bg-cyan-400/10' },
  pandalive: { label: '팬더라이브', dot: 'bg-rose-500', text: 'text-rose-300', border: 'border-rose-500/20', chip: 'bg-rose-500/10' },
  popkon: { label: '팝콘TV', dot: 'bg-emerald-500', text: 'text-emerald-300', border: 'border-emerald-500/20', chip: 'bg-emerald-500/10' },
};

export function platformMeta(platform) {
  return PLATFORM_META[platform] || { label: platform, dot: 'bg-zinc-500', text: 'text-zinc-300', border: 'border-zinc-500/20', chip: 'bg-zinc-500/10' };
}

export function formatViewers(viewers) {
  if (viewers === null || viewers === undefined || viewers === '') return null;
  return Number(viewers).toLocaleString('ko-KR');
}
