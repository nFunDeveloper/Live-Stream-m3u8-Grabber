import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Input, Spinner } from '@heroui/react';
import { Loader2, Minus, MonitorSmartphone, Plus, X } from 'lucide-react';
import { agentFetch } from './agent.js';
import { BASE_PORT, MAX_SLOTS, MIN_SLOTS, emptySlot, grabLive, looksLikeM3u8, withPorts } from './slots.js';
import StreamSlot from './StreamSlot.jsx';
import LogPanel from './LogPanel.jsx';
import { recordHistory } from '../../lib/storage.js';
import { detectPlatform } from '../../lib/qualities.js';

const STATUS_POLL_MS = 2500;
// 에이전트가 아직 빈 상태일 때 보여줄 기본 슬롯 수
const SEED_SLOTS = 4;

// 원격 제어 패널. 메인 페이지 오른쪽 드로어 안에서 렌더되며,
// 왼쪽에 이미 있는 메인 사이드바(검색·히스토리)를 그대로 드래그 소스로 쓴다.
// 모든 변경은 저장 버튼 없이 즉시 PUT /agent/config로 에이전트에 반영한다.
export default function RemoteDashboard({ agentInfo, onClose }) {
  const [slots, setSlots] = useState(null); // null = 로딩 중
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState('');
  const [busyPort, setBusyPort] = useState(null);
  const [resolving, setResolving] = useState(false);
  const [pasteUrl, setPasteUrl] = useState('');
  const [toastMessage, setToastMessage] = useState('');
  const toastTimerRef = useRef(null);
  // 변경 직후 상태와 PUT 사이에 틈이 없도록 ref를 진실 원천으로 쓴다(빠른 연타 대응)
  const slotsRef = useRef(null);
  const putChainRef = useRef(Promise.resolve());
  // 자동 재생 판단에 최신 세션 상태가 필요 — 폴링 결과를 ref에 미러링한다
  const statusRef = useRef(null);

  const showToast = useCallback((message) => {
    setToastMessage(message);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToastMessage(''), 1800);
  }, []);

  useEffect(() => () => clearTimeout(toastTimerRef.current), []);

  // 초기 로드: 슬롯이 비어 있으면 기본 슬롯을 만들어 에이전트에 알린다
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await agentFetch('/agent/config');
        if (cancelled) return;
        let next = withPorts(data.slots || []);
        if (next.length === 0) {
          next = withPorts(Array.from({ length: SEED_SLOTS }, emptySlot));
        }
        slotsRef.current = next;
        setSlots(next);
      } catch (err) {
        if (cancelled) return;
        showToast(`슬롯을 불러오지 못했습니다: ${err.message}`);
        const next = withPorts(Array.from({ length: SEED_SLOTS }, emptySlot));
        slotsRef.current = next;
        setSlots(next);
      }
    })();
    return () => { cancelled = true; };
  }, [showToast]);

  // 상태 폴링
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await agentFetch('/agent/status', { timeout: 3000 });
        if (cancelled) return;
        statusRef.current = data;
        setStatus(data);
        setStatusError('');
      } catch (err) {
        if (cancelled) return;
        setStatusError(err.message);
      }
    };
    poll();
    const timer = setInterval(poll, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  // 슬롯 변경 + 즉시 PUT (체인 직렬화로 연타/경합 방지)
  const mutateSlots = useCallback((fn) => {
    const next = withPorts(fn(slotsRef.current || []));
    slotsRef.current = next;
    setSlots(next);
    putChainRef.current = putChainRef.current
      .then(() => agentFetch('/agent/config', { method: 'PUT', body: { slots: next }, timeout: 8000 }))
      .catch((err) => showToast(`에이전트 저장 실패: ${err.message}`));
    return next;
  }, [showToast]);

  const firstEmptyIndex = () =>
    (slotsRef.current || []).findIndex((slot) => !slot.m3u8_url);

  // 슬롯에 새 스트림이 들어가면 자동으로 재생한다.
  // PUT 체인 뒤에 붙여 "설정 반영 → 시작/재시작" 순서를 보장하고,
  // 실행 중이면 재시작(새 m3u8 적용), 정지/오류면 시작, 시작 중이면 건너뛴다.
  const ensurePlaying = useCallback((port) => {
    const session = statusRef.current?.sessions?.find((s) => s.port === port);
    let action = 'start';
    if (session) {
      if (session.state === 'starting') return; // 이미 올라오는 중
      action = (session.state === 'running' || session.state === 'waiting') ? 'restart' : 'start';
    }
    putChainRef.current = putChainRef.current
      .then(() => agentFetch(
        `/agent/sessions/${encodeURIComponent(String(port))}/${action}`,
        { method: 'POST', timeout: 8000 }
      ))
      .then(() => agentFetch('/agent/status', { timeout: 3000 }))
      .then((data) => {
        statusRef.current = data;
        setStatus(data);
        showToast(action === 'restart'
          ? `포트 ${port} 새 스트림으로 재시작`
          : `포트 ${port} 재생 시작`);
      })
      .catch((err) => showToast(`포트 ${port} 자동 재생 실패: ${err.message}`));
  }, [showToast]);

  // 슬롯에 방송 배정 — page_url이 있으면 grab으로 m3u8을 새로 뽑는다.
  // grab이 실패해도 히스토리에 저장된 m3u8이 있으면 그것을 쓴다(토큰 만료 가능성 안내).
  const assignToSlot = useCallback(async (index, payload) => {
    setResolving(true);
    try {
      const pageUrl = payload.url || payload.page_url || '';
      const storedM3u8 = payload.m3u8_url || payload.m3u8 || '';
      let m3u8 = storedM3u8;
      let grabbed = null;
      let grabError = null;
      if (pageUrl) {
        try {
          grabbed = await grabLive(pageUrl, payload.quality || 'auto');
          m3u8 = grabbed.m3u8_url;
        } catch (err) {
          grabError = err;
          if (!storedM3u8) throw err;
        }
      }
      if (!m3u8) throw new Error('m3u8 주소를 찾지 못했습니다');
      mutateSlots((current) => current.map((slot, i) => (i === index ? {
        ...slot,
        page_url: pageUrl,
        m3u8_url: m3u8,
        quality: grabbed?.quality || payload.quality || 'auto',
        platform: grabbed?.platform || payload.platform || '',
        streamer_name: grabbed?.streamer_name || payload.streamer_name || '',
        title: grabbed?.title || payload.title || '',
      } : slot)));
      if (grabbed) {
        recordHistory(grabbed, pageUrl);
      }
      const name = grabbed?.streamer_name || payload.streamer_name || '방송';
      if (grabError) {
        showToast(`${name} → 포트 ${BASE_PORT + index} (저장된 m3u8 사용 — 추출 실패: ${grabError.message})`);
      } else {
        showToast(`${name} → 포트 ${BASE_PORT + index} 배정 완료`);
      }
      // 배정이 PUT 에 반영되면 이어서 자동 재생까지
      ensurePlaying(BASE_PORT + index);
    } catch (err) {
      showToast(`배정 실패: ${err.message}`);
    } finally {
      setResolving(false);
    }
  }, [mutateSlots, ensurePlaying, showToast]);

  // 슬롯 드롭 (메인 사이드바 히스토리 / 외부 드래그)
  const handleDropPayload = useCallback((index, payload) => {
    assignToSlot(index, payload);
  }, [assignToSlot]);

  // URL 붙여넣기 → 첫 빈 슬롯에 배정 (m3u8이면 그대로, 방송 페이지면 grab)
  const handlePaste = useCallback(() => {
    const value = pasteUrl.trim();
    if (!value) return;
    const index = firstEmptyIndex();
    if (index < 0) {
      showToast('빈 슬롯이 없습니다 — 상단의 + 로 슬롯을 늘려주세요');
      return;
    }
    if (looksLikeM3u8(value)) {
      assignToSlot(index, { m3u8_url: value });
      setPasteUrl('');
      return;
    }
    if (!detectPlatform(value)) {
      showToast('지원하지 않는 주소입니다 (방송 페이지 또는 m3u8 주소)');
      return;
    }
    assignToSlot(index, { url: value }).finally(() => setPasteUrl(''));
  }, [pasteUrl, assignToSlot, showToast]);

  // 슬롯 수 조절 — 포트는 항상 9001부터 증가
  const handleCount = useCallback((delta) => {
    const current = slotsRef.current || [];
    const target = Math.min(MAX_SLOTS, Math.max(MIN_SLOTS, current.length + delta));
    if (target === current.length) return;
    if (delta < 0) {
      const removed = current.slice(target);
      mutateSlots((cur) => cur.slice(0, target));
      if (removed.some((slot) => slot.m3u8_url)) {
        showToast(`슬롯 ${target + 1}번 이후가 제거되었습니다`);
      }
      return;
    }
    mutateSlots((cur) => [...cur, ...Array.from({ length: target - cur.length }, emptySlot)]);
  }, [mutateSlots, showToast]);

  const handleRefresh = useCallback(async (index) => {
    const slot = (slotsRef.current || [])[index];
    if (!slot?.page_url) return;
    setResolving(true);
    try {
      const grabbed = await grabLive(slot.page_url, slot.quality || 'auto');
      mutateSlots((current) => current.map((item, i) => (i === index ? {
        ...item,
        m3u8_url: grabbed.m3u8_url,
        streamer_name: grabbed.streamer_name || item.streamer_name,
        title: grabbed.title || item.title,
      } : item)));
      recordHistory(grabbed, slot.page_url);
      showToast(`포트 ${slot.port} 스트림 재등록 완료`);
      // 싱크 밀림·오류 복구 작업의 완성: 새 URL 반영 후 세션까지 재시작
      ensurePlaying(slot.port);
    } catch (err) {
      showToast(`갱신 실패: ${err.message}`);
    } finally {
      setResolving(false);
    }
  }, [mutateSlots, ensurePlaying, showToast]);

  const handleRemove = useCallback((index) => {
    const slot = (slotsRef.current || [])[index];
    mutateSlots((current) => current.map((item, i) => (i === index ? { ...item, page_url: '', m3u8_url: '', platform: '', streamer_name: '', title: '' } : item)));
    showToast(`포트 ${slot?.port} 슬롯을 비웠습니다`);
  }, [mutateSlots, showToast]);

  const handleSessionAction = useCallback(async (port, action) => {
    setBusyPort(port);
    try {
      await agentFetch(`/agent/sessions/${encodeURIComponent(String(port))}/${action}`, {
        method: 'POST',
        timeout: 8000,
      });
      showToast(
        action === 'start' ? `포트 ${port} 시작` :
        action === 'stop' ? `포트 ${port} 중지` :
        `포트 ${port} 재시작`
      );
      try {
        const data = await agentFetch('/agent/status', { timeout: 3000 });
        statusRef.current = data;
        setStatus(data);
      } catch {
        // 다음 폴링이 알아서 채운다
      }
    } catch (err) {
      showToast(`실패: ${err.message}`);
    } finally {
      setBusyPort(null);
    }
  }, [showToast]);

  const sessionByPort = new Map((status?.sessions || []).map((s) => [s.port, s]));
  const vmixByPort = new Map((status?.vmix_ports || []).map((item) => [item.port, item]));
  const count = slots?.length ?? 0;

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* 헤더: 닫기 + 제목 + 슬롯 수 조절 + 연결 상태 */}
      <header className="flex items-center gap-2.5 px-4 sm:px-5 py-3 border-b border-white/10 shrink-0">
        <button
          type="button"
          onClick={onClose}
          aria-label="원격 제어 닫기"
          className="w-8 h-8 rounded-xl border border-white/10 bg-white/[0.04] flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/10 transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
            <MonitorSmartphone className="w-4 h-4 text-zinc-400" />
            원격 제어
          </h2>
          <p className="text-[10px] text-zinc-500 truncate">
            {agentInfo.name} v{agentInfo.version} · 127.0.0.1:17300
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* SRT 스트림 수 조절 */}
          <div className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-2 py-1.5">
            <span className="text-[11px] text-zinc-400 font-semibold hidden sm:inline">SRT 스트림</span>
            <Button
              size="sm"
              isDisabled={count <= MIN_SLOTS || slots === null}
              onPress={() => handleCount(-1)}
              aria-label="스트림 수 줄이기"
              className="h-6 w-6 min-w-0 rounded-lg bg-white/5 text-zinc-300 p-0"
            >
              <Minus className="w-3 h-3" />
            </Button>
            <span className="text-xs font-bold text-white font-mono min-w-[6rem] text-center">
              {count}개 · {BASE_PORT}~{BASE_PORT + Math.max(0, count - 1)}
            </span>
            <Button
              size="sm"
              isDisabled={count >= MAX_SLOTS || slots === null}
              onPress={() => handleCount(1)}
              aria-label="스트림 수 늘리기"
              className="h-6 w-6 min-w-0 rounded-lg bg-white/5 text-zinc-300 p-0"
            >
              <Plus className="w-3 h-3" />
            </Button>
          </div>

          <span
            className={`inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-1 rounded-full border shrink-0 ${
              statusError
                ? 'border-red-500/25 bg-red-500/10 text-red-400'
                : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${statusError ? 'bg-red-400' : 'bg-emerald-400 animate-pulse'}`} />
            {statusError ? '끊김' : '연결됨'}
          </span>
        </div>
      </header>

      {/* 본문 */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-5 py-4 flex flex-col gap-3">
        {statusError && (
          <p className="text-[11px] text-amber-400/90 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2 shrink-0">
            상태 폴링 실패: {statusError} — 자동 재시도 중입니다
          </p>
        )}

        {/* URL 붙여넣기 — 첫 빈 슬롯에 배정. HeroUI Input은 onKeyDown을 안 넘겨주므로
            메인 앱과 같은 form/submit 패턴으로 Enter를 처리한다 */}
        <form
          className="flex items-center gap-2 shrink-0"
          onSubmit={(e) => { e.preventDefault(); handlePaste(); }}
          onKeyDown={(e) => {
            // 암시적 form 제출에 기대지 않고 키다운 자체를 잡는다(입력 중계 라이브러리 차단 대비)
            if (e.key === 'Enter') {
              e.preventDefault();
              handlePaste();
            }
          }}
        >
          <Input
            size="sm"
            value={pasteUrl}
            onChange={(e) => setPasteUrl(e.target.value)}
            placeholder="방송 URL 또는 m3u8 주소 붙여넣기 — Enter로 첫 빈 슬롯에 배정"
            className="flex-1 h-9 rounded-lg text-xs"
            classNames={{ inputWrapper: 'h-9 rounded-lg bg-white/[0.04] border-white/10' }}
          />
          <Button
            size="sm"
            type="submit"
            isDisabled={resolving || !pasteUrl.trim()}
            className="h-9 rounded-lg bg-white/10 text-zinc-200 text-xs font-semibold"
          >
            {resolving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '배정'}
          </Button>
        </form>

        {/* 슬롯 그리드 — 사이드바 히스토리를 끌어다 놓는 곳 */}
        {slots === null ? (
          <div className="py-16 flex justify-center shrink-0">
            <Spinner size="sm" color="white" />
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2.5 items-start">
            {slots.map((slot, index) => (
              <StreamSlot
                key={slot.id}
                slot={slot}
                index={index}
                session={sessionByPort.get(slot.port)}
                vmixAlive={vmixByPort.get(slot.port)?.alive}
                busy={busyPort === slot.port}
                resolving={resolving}
                onDropPayload={handleDropPayload}
                onRefresh={handleRefresh}
                onRemove={handleRemove}
                onAction={handleSessionAction}
              />
            ))}
          </div>
        )}
      </div>

      {/* 로그는 슬롯 영역과 달리 스크롤되지 않게 드로어 하단에 고정 */}
      <div className="shrink-0 border-t border-white/10 px-4 sm:px-5 py-3 bg-[#08080a]">
        <LogPanel sessions={status?.sessions || []} />
      </div>

      {/* 토스트 */}
      {toastMessage && (
        <div className="pointer-events-none fixed inset-x-0 bottom-8 z-[60] flex justify-center px-4">
          <div className="flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm font-semibold text-white shadow-2xl backdrop-blur-xl">
            <span>{toastMessage}</span>
          </div>
        </div>
      )}
    </div>
  );
}
