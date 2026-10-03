import { useState } from 'react';
import {
  History,
  Layers,
  Trash2,
  Plus,
  ChevronDown,
  ChevronRight,
  X,
  Copy,
  Radio,
} from 'lucide-react';
import PlatformChip from './PlatformChip.jsx';
import { formatDateTime, formatViewers } from '../lib/platforms.js';

function LiveDot({ statusKey, statuses }) {
  const status = statuses[statusKey];
  if (!status || status.is_live === null || status.is_live === undefined) return null;
  const title = status.is_live
    ? `방송 중${formatViewers(status.viewers) ? ` (${formatViewers(status.viewers)}명)` : ''}`
    : '오프라인';
  return (
    <span
      title={title}
      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
        status.is_live ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-700'
      }`}
    />
  );
}

function SectionHeader({ icon: Icon, title, actions }) {
  return (
    <div className="flex items-center justify-between px-2 mb-2">
      <div className="flex items-center gap-1.5 text-zinc-400">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-[10px] font-bold uppercase tracking-widest">{title}</span>
      </div>
      <div className="flex items-center gap-1">{actions}</div>
    </div>
  );
}

function IconButton({ onClick, title, danger, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`p-1 rounded-md transition-colors ${
        danger
          ? 'text-zinc-500 hover:text-red-400 hover:bg-red-500/10'
          : 'text-zinc-500 hover:text-white hover:bg-white/10'
      }`}
    >
      {children}
    </button>
  );
}

function CopyM3u8Button({ onClick }) {
  return (
    <button
      type="button"
      title="M3U8 URL 복사"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="p-1 rounded-md bg-transparent text-zinc-500 hover:text-white hover:bg-white/10 transition-colors shrink-0"
    >
      <Copy className="w-3 h-3" />
    </button>
  );
}

function HistoryItem({ entry, onPick, onDelete, onCopyM3u8, statuses }) {
  // 히스토리 항목을 사이드바 그룹으로 드래그할 수 있도록 페이로드 실기
  const handleDragStart = (e) => {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('application/json', JSON.stringify(entry));
  };

  const secondary = [
    formatDateTime(entry.searchedAt),
    entry.quality ? entry.quality : null,
  ].filter(Boolean).join(' · ');

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      title="드래그하여 그룹에 추가"
      onClick={() => onPick(entry)}
      className="group/item flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-grab active:cursor-grabbing hover:bg-white/[0.05] transition-colors min-w-0"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <PlatformChip platform={entry.platform} size="xs" />
          <span className="text-xs font-medium text-zinc-200 truncate group-hover/item:text-white">
            {entry.streamer_name || entry.streamer_id}
          </span>
          <LiveDot statusKey={entry.key} statuses={statuses} />
        </div>
        <div className="text-[10px] text-zinc-500 truncate pl-0.5">
          {secondary}
        </div>
      </div>
      <div className="hidden group-hover/item:flex items-center gap-0.5 shrink-0">
        <CopyM3u8Button onClick={() => onCopyM3u8(entry)} />
        <IconButton danger title="히스토리에서 삭제" onClick={() => onDelete(entry.key)}>
          <X className="w-3 h-3" />
        </IconButton>
      </div>
    </div>
  );
}

function GroupItem({ group, open, onToggle, onPick, onDeleteGroup, onDeleteMember, onDropMember, onCopyM3u8, statuses }) {
  const [dragOver, setDragOver] = useState(false);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    if (!dragOver) setDragOver(true);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    try {
      const payload = JSON.parse(e.dataTransfer.getData('application/json'));
      if (payload?.platform && payload?.streamer_id) {
        onDropMember(group, payload);
      }
    } catch {
      // 드래그 페이로드가 아니면 무시
    }
  };

  return (
    <div
      data-testid="group-item"
      onDragOver={handleDragOver}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`rounded-lg transition-all min-w-0 ${
        dragOver ? 'ring-1 ring-white/50 bg-white/10' : ''
      }`}
    >
      <div className="flex items-center group/g">
        <button
          type="button"
          onClick={onToggle}
          className="flex-1 min-w-0 flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-white/[0.04] transition-colors"
        >
          {open ? (
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
          )}
          <Layers className="w-3.5 h-3.5 text-zinc-400" />
          <span className="text-xs font-semibold text-zinc-200 truncate">{group.name}</span>
          <span className="text-[10px] text-zinc-600 ml-auto">{group.members.length}</span>
        </button>
        <IconButton danger title="그룹 삭제" onClick={() => onDeleteGroup(group)}>
          <Trash2 className="w-3 h-3" />
        </IconButton>
      </div>
      {open && (
        <div className="ml-3 pl-2 border-l border-white/5 flex flex-col gap-0.5 min-w-0">
          {group.members.length === 0 && (
            <div className="px-2 py-1.5 text-[10px] text-zinc-600">
              히스토리 항목을 이 그룹으로 드래그해 저장하세요
            </div>
          )}
          {group.members.map((member) => (
            <div
              key={member.key}
              role="button"
              tabIndex={0}
              onClick={() => onPick(member)}
              onKeyDown={(e) => e.key === 'Enter' && onPick(member)}
              className="group/m flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer hover:bg-white/[0.05] transition-colors min-w-0"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 min-w-0">
                  <PlatformChip platform={member.platform} size="xs" />
                  <span className="text-xs font-medium text-zinc-200 truncate">
                    {member.streamer_name || member.streamer_id}
                  </span>
                  <LiveDot statusKey={member.key} statuses={statuses} />
                </div>
                <div className="text-[10px] text-zinc-500 truncate pl-0.5">
                  {member.title || '제목 정보 없음'}{member.quality ? ` · ${member.quality}` : ''}
                </div>
              </div>
              <div className="hidden group-hover/m:flex items-center gap-0.5 shrink-0">
                <CopyM3u8Button onClick={() => onCopyM3u8(member)} />
                <IconButton danger title="그룹에서 제거" onClick={() => onDeleteMember(group, member)}>
                  <X className="w-3 h-3" />
                </IconButton>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar({
  history,
  groups,
  statuses = {},
  onPickHistory,
  onDeleteHistory,
  onClearHistory,
  onCreateGroup,
  onDeleteGroup,
  onPickMember,
  onDeleteMember,
  onDropMember,
  onCopyM3u8,
}) {
  const [openGroups, setOpenGroups] = useState({});
  const [creating, setCreating] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');

  const toggle = (key) => setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));

  const submitNewGroup = () => {
    const name = newGroupName.trim();
    if (!name) return;
    onCreateGroup(name);
    setNewGroupName('');
    setCreating(false);
  };

  return (
    <div className="h-full w-full min-w-0 flex flex-col">
      {/* 브랜드 */}
      <div className="flex items-center gap-2.5 px-4 h-14 shrink-0 border-b border-white/5">
        <div className="w-7 h-7 rounded-lg bg-white flex items-center justify-center">
          <Radio className="w-4 h-4 text-black" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-tight text-white">M3U8 Grabber</div>
          <div className="text-[9px] uppercase tracking-widest text-zinc-500">
            Live Stream Toolkit
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4 flex flex-col gap-6 min-w-0">
        {/* 그룹 (최상단) */}
        <section className="min-w-0">
          <SectionHeader
            icon={Layers}
            title="그룹"
            actions={
              <IconButton title="그룹 추가" onClick={() => setCreating((v) => !v)}>
                <Plus className="w-3.5 h-3.5" />
              </IconButton>
            }
          />
          {creating && (
            <div className="flex gap-1.5 mb-2">
              <input
                autoFocus
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') submitNewGroup();
                  if (e.key === 'Escape') {
                    setCreating(false);
                    setNewGroupName('');
                  }
                }}
                placeholder="그룹 이름"
                className="flex-1 min-w-0 bg-white/[0.04] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs outline-none focus:border-white/40 placeholder:text-zinc-600"
              />
              <button
                type="button"
                onClick={submitNewGroup}
                className="px-2.5 rounded-lg bg-white hover:bg-zinc-200 text-black text-xs font-semibold transition-colors"
              >
                추가
              </button>
            </div>
          )}
          {groups.length === 0 ? (
            <p className="px-2 text-[11px] text-zinc-600 leading-relaxed">
              그룹을 만들어 자주 보는 방송인을 모아두면 클릭 한 번으로 다시 조회할 수 있습니다.
            </p>
          ) : (
            <div className="flex flex-col gap-0.5 min-w-0">
              {groups.map((group) => (
                <GroupItem
                  key={group.id}
                  group={group}
                  open={openGroups[group.id] ?? true}
                  onToggle={toggle}
                  onPick={onPickMember}
                  onDeleteGroup={onDeleteGroup}
                  onDeleteMember={onDeleteMember}
                  onDropMember={onDropMember}
                  onCopyM3u8={onCopyM3u8}
                  statuses={statuses}
                />
              ))}
            </div>
          )}
        </section>

        {/* 검색 히스토리 */}
        <section className="min-w-0">
          <SectionHeader
            icon={History}
            title="검색 히스토리"
            actions={
              history.length > 0 ? (
                <IconButton danger title="전체 삭제" onClick={onClearHistory}>
                  <Trash2 className="w-3 h-3" />
                </IconButton>
              ) : null
            }
          />
          {history.length === 0 ? (
            <p className="px-2 text-[11px] text-zinc-600 leading-relaxed">
              아직 검색 기록이 없습니다. 방송 URL을 추출하면 이곳에 쌓입니다.
            </p>
          ) : (
            <div className="flex flex-col gap-0.5 min-w-0">
              {history.map((entry) => (
                <HistoryItem
                  key={entry.key}
                  entry={entry}
                  onPick={onPickHistory}
                  onDelete={onDeleteHistory}
                  onCopyM3u8={onCopyM3u8}
                  statuses={statuses}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      <div className="px-4 py-3 shrink-0 border-t border-white/5">
        <p className="text-[9px] text-zinc-600">
          히스토리·그룹은 이 브라우저에만 저장됩니다
        </p>
      </div>
    </div>
  );
}
