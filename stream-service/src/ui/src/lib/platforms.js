// 플랫폼 대표 색은 각 서비스의 브랜드 컬러를 참고했다
// chzzk #00F889(치지직 그린), soop #00BEFF(SOOP 블루), cime #9048F0(ci.me 퍼플),
// pandalive #FE695D(코랄 레드 계열), popkon #F0B400(팝콘TV 골드)
export const PLATFORM_META = {
  chzzk: { label: '치지직', dot: 'bg-[#00F889]', text: 'text-[#00F889]', border: 'border-[#00F889]/25', chip: 'bg-[#00F889]/10' },
  soop: { label: 'SOOP', dot: 'bg-[#00BEFF]', text: 'text-[#00BEFF]', border: 'border-[#00BEFF]/25', chip: 'bg-[#00BEFF]/10' },
  cime: { label: 'ci.me', dot: 'bg-[#9048F0]', text: 'text-[#A968FF]', border: 'border-[#9048F0]/30', chip: 'bg-[#9048F0]/15' },
  pandalive: { label: '팬더라이브', dot: 'bg-[#FE695D]', text: 'text-[#FE695D]', border: 'border-[#FE695D]/25', chip: 'bg-[#FE695D]/10' },
  popkon: { label: '팝콘TV', dot: 'bg-[#F0B400]', text: 'text-[#F0B400]', border: 'border-[#F0B400]/25', chip: 'bg-[#F0B400]/10' },
};

export function platformMeta(platform) {
  return PLATFORM_META[platform] || { label: platform, dot: 'bg-zinc-500', text: 'text-zinc-300', border: 'border-zinc-500/20', chip: 'bg-zinc-500/10' };
}

export function formatViewers(viewers) {
  if (viewers === null || viewers === undefined || viewers === '') return null;
  return Number(viewers).toLocaleString('ko-KR');
}

export function formatDateTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
