import { useState } from 'react';
import { Button, Spinner } from '@heroui/react';
import { Play, RefreshCw, RotateCw, Square, Trash2 } from 'lucide-react';
import { platformMeta } from '../../lib/platforms.js';
import { HISTORY_DRAG_TYPE } from './slots.js';

// 세션 상태 → 점/배지 색. SrtRelay의 상태머신(stopped/running/waiting)과 매핑된다.
const STATE_META = {
  running: { label: '실행', dot: 'bg-emerald-400', text: 'text-emerald-400' },
  starting: { label: '시작 중', dot: 'bg-sky-400', text: 'text-sky-400' },
  waiting: { label: '대기', dot: 'bg-amber-400', text: 'text-amber-400' },
  error: { label: '오류', dot: 'bg-red-400', text: 'text-red-400' },
  stopped: { label: '정지', dot: 'bg-zinc-600', text: 'text-zinc-500' },
};

// 슬롯 하나 = SRT 하나(포트). 한 화면에 12~16개가 보여야 하므로 카드는 컴팩트하다.
// 드롭 대상이자 세션 제어 지점.
export default function StreamSlot({ slot, index, session, vmixAlive, busy, resolving, onDropPayload, onRefresh, onRemove, onAction }) {
  const [dragOver, setDragOver] = useState(false);
  const occupied = Boolean(slot.m3u8_url);
  const state = session?.state || 'stopped';
  const meta = STATE_META[state] || STATE_META.stopped;
  const platform = slot.platform ? platformMeta(slot.platform) : null;

  const canStart = state === 'stopped' || state === 'error';
  const canStop = state === 'running' || state === 'waiting' || state === 'starting';
  const canRestart = state === 'running' || state === 'waiting' || state === 'error';

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    let raw = e.dataTransfer.getData(HISTORY_DRAG_TYPE) || e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
    raw = (raw || '').split(/\r?\n/).map((s) => s.trim()).find((s) => s && !s.startsWith('#')) || '';
    if (!raw) return;
    let payload;
    if (raw.startsWith('{')) {
      try {
        payload = JSON.parse(raw);
      } catch {
        payload = { url: raw };
      }
    } else {
      payload = { url: raw };
    }
    onDropPayload(index, payload);
  };

  // 비활성 상태가 한눈에 보이게 (HeroUI 기본 opacity만으로는 구분이 약하다)
  const iconBtn = 'h-7 w-7 min-w-0 rounded-lg bg-white/[0.06] text-zinc-300 p-0';
  const dim = (enabled) => (enabled ? '' : ' opacity-30 saturate-50');

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        // 그룹 멤버 드래그는 effectAllowed='move'라서 무조건 'copy'로 쓰면
        // 브라우저가 드롭을 불허한다 — 소스의 effectAllowed에 맞춰준다
        e.dataTransfer.dropEffect = e.dataTransfer.effectAllowed === 'move' ? 'move' : 'copy';
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      title={occupied ? (slot.page_url || slot.m3u8_url) : undefined}
      className={`rounded-xl border p-2.5 flex flex-col gap-1.5 min-h-[5.75rem] transition-colors ${
        dragOver
          ? 'border-emerald-400/60 bg-emerald-500/[0.07]'
          : occupied
            ? 'border-white/10 bg-white/[0.02]'
            : 'border-dashed border-white/15 bg-white/[0.01]'
      }`}
    >
      {/* 줄 1: 포트 + 상태 */}
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-bold font-mono text-zinc-200 bg-white/[0.07] border border-white/10 rounded px-1.5 py-0.5 shrink-0">
          :{slot.port}
        </span>
        <span className={`flex items-center gap-1 text-[10px] font-semibold ${meta.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
        {session?.last_error && (
          <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" title={session.last_error} />
        )}
        {busy && <Spinner size="sm" color="white" className="ml-auto scale-75" />}
      </div>

      {/* 줄 2: 방송 이름 */}
      <div className="flex items-center gap-1.5 min-w-0 h-4">
        {occupied ? (
          <>
            {platform && <span className={`w-1.5 h-1.5 rounded-full ${platform.dot} shrink-0`} />}
            <span className="text-xs font-semibold text-white truncate">
              {slot.streamer_name || slot.title || '이름 없음'}
            </span>
          </>
        ) : (
          <span className="text-[11px] text-zinc-600 truncate">
            {dragOver ? '여기에 놓으면 배정' : resolving ? 'm3u8 추출 중…' : '빈 슬롯 — 드롭 대상'}
          </span>
        )}
      </div>

      {/* 줄 3: vMix + 슬롯 번호 */}
      <div className="flex items-center gap-1 text-[10px] text-zinc-600">
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            vmixAlive == null ? 'bg-zinc-700' : vmixAlive ? 'bg-emerald-400/80' : 'bg-red-400/80'
          }`}
        />
        vMix
        <span className="ml-auto">#{index + 1}</span>
      </div>

      {/* 줄 4: 제어 버튼 (빈 슬롯이면 드롭 안내) */}
      <div className="flex items-center gap-1 h-7">
        {!occupied ? (
          <span className="text-[10px] text-zinc-600 w-full text-center">
            {resolving ? '…' : '방송을 여기로 끌어다 놓으세요'}
          </span>
        ) : busy ? (
          <div className="w-full flex justify-center">
            <Spinner size="sm" color="white" />
          </div>
        ) : (
          <>
            <Button
              size="sm"
              isDisabled={!canStart}
              onPress={() => onAction(slot.port, 'start')}
              aria-label={`재생 — 포트 ${slot.port}`}
              title={canStart ? '재생' : '이미 재생 중입니다'}
              className={`${iconBtn} text-emerald-400${dim(canStart)}`}
            >
              <Play className="w-3 h-3" />
            </Button>
            <Button
              size="sm"
              isDisabled={!canStop}
              onPress={() => onAction(slot.port, 'stop')}
              aria-label={`중지 — 포트 ${slot.port}`}
              title={canStop ? '중지' : '이미 정지 상태입니다'}
              className={iconBtn + dim(canStop)}
            >
              <Square className="w-3 h-3" />
            </Button>
            <Button
              size="sm"
              isDisabled={!canRestart}
              onPress={() => onAction(slot.port, 'restart')}
              aria-label={`재시작 — 포트 ${slot.port}`}
              title="재시작"
              className={iconBtn + dim(canRestart)}
            >
              <RotateCw className="w-3 h-3" />
            </Button>
            {slot.page_url && (
              <Button
                size="sm"
                onPress={() => onRefresh(index)}
                aria-label={`새로고침 — 포트 ${slot.port}`}
                title="새로고침 — 새 m3u8로 다시 따서 세션을 재등록합니다 (싱크 밀림·오류 복구)"
                className={iconBtn}
              >
                <RefreshCw className="w-3 h-3" />
              </Button>
            )}
            <Button
              size="sm"
              onPress={() => onRemove(index)}
              aria-label={`슬롯 비우기 — 포트 ${slot.port}`}
              title="슬롯 비우기"
              className="h-7 w-7 min-w-0 rounded-lg bg-red-500/10 text-red-400 p-0"
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
