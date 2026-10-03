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
import { platformMeta } from '../lib/platforms.js';

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

function PlatformChip({ platform }) {
  const meta = platformMeta(platform);
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-px rounded border text-[9px] font-semibold shrink-0 ${meta.chip} ${meta.border} ${meta.text}`}
    >
      <span className={`w-1 h-1 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
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

function HistoryItem({ entry, onPick, onDelete, onCopyM3u8 }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onPick(entry)}
      onKeyDown={(e) => e.key === 'Enter' && onPick(entry)}
      className="group/item flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer hover:bg-white/[0.05] transition-colors"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <PlatformChip platform={entry.platform} />
          <span className="text-xs font-medium text-zinc-200 truncate group-hover/item:text-white">
            {entry.streamer_name || entry.streamer_id}
          </span>
        </div>
        <div className="text-[10px] text-zinc-500 truncate pl-0.5">
          {entry.title || '제목 정보 없음'}
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

function PlatformHistoryGroup({ platform, entries, open, onToggle, onPick, onDelete, onCopyM3u8 }) {
  const meta = platformMeta(platform);
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-white/[0.04] transition-colors"
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
        )}
        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
        <span className={`text-xs font-semibold ${meta.text}`}>{meta.label}</span>
        <span className="text-[10px] text-zinc-600 ml-auto">{entries.length}</span>
      </button>
      {open && (
        <div className="ml-3 pl-2 border-l border-white/5 flex flex-col gap-0.5">
          {entries.map((entry) => (
            <HistoryItem
              key={entry.key}
              entry={entry}
              onPick={onPick}
              onDelete={onDelete}
              onCopyM3u8={onCopyM3u8}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function GroupItem({ group, open, onToggle, onPick, onDeleteGroup, onDeleteMember, onDropMember, onCopyM3u8 }) {
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
      className={`rounded-lg transition-all ${
        dragOver ? 'ring-1 ring-purple-500/60 bg-purple-500/10' : ''
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
          <Layers className="w-3.5 h-3.5 text-purple-400" />
          <span className="text-xs font-semibold text-zinc-200 truncate">{group.name}</span>
          <span className="text-[10px] text-zinc-600 ml-auto">{group.members.length}</span>
        </button>
        <IconButton danger title="그룹 삭제" onClick={() => onDeleteGroup(group)}>
          <Trash2 className="w-3 h-3" />
        </IconButton>
      </div>
      {open && (
        <div className="ml-3 pl-2 border-l border-white/5 flex flex-col gap-0.5">
          {group.members.length === 0 && (
            <div className="px-2 py-1.5 text-[10px] text-zinc-600">
              추출된 방송 카드를 이 그룹으로 드래그해 저장하세요
            </div>
          )}
          {group.members.map((member) => (
            <div
              key={member.key}
              role="button"
              tabIndex={0}
              onClick={() => onPick(member)}
              onKeyDown={(e) => e.key === 'Enter' && onPick(member)}
              className="group/m flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer hover:bg-white/[0.05] transition-colors"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 min-w-0">
                  <PlatformChip platform={member.platform} />
                  <span className="text-xs font-medium text-zinc-200 truncate">
                    {member.streamer_name || member.streamer_id}
                  </span>
                </div>
                <div className="text-[10px] text-zinc-500 truncate pl-0.5">
                  {member.title || '제목 정보 없음'}
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
  const [openPlatforms, setOpenPlatforms] = useState({});
  const [openGroups, setOpenGroups] = useState({});
  const [creating, setCreating] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');

  const historyByPlatform = history.reduce((acc, entry) => {
    (acc[entry.platform] = acc[entry.platform] || []).push(entry);
    return acc;
  }, {});

  const toggle = (setter) => (key) =>
    setter((prev) => ({ ...prev, [key]: !prev[key] }));

  const submitNewGroup = () => {
    const name = newGroupName.trim();
    if (!name) return;
    onCreateGroup(name);
    setNewGroupName('');
    setCreating(false);
  };

  return (
    <div className="h-full flex flex-col">
      {/* 브랜드 */}
      <div className="flex items-center gap-2.5 px-4 h-14 shrink-0 border-b border-white/5">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center shadow-lg shadow-purple-500/25">
          <Radio className="w-4 h-4 text-white" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-tight">M3U8 Grabber</div>
          <div className="text-[9px] uppercase tracking-widest text-zinc-500">
            Live Stream Toolkit
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4 flex flex-col gap-6">
        {/* 검색 히스토리 */}
        <section>
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
            <div className="flex flex-col gap-0.5">
              {Object.entries(historyByPlatform).map(([platform, entries]) => (
                <PlatformHistoryGroup
                  key={platform}
                  platform={platform}
                  entries={entries}
                  open={openPlatforms[platform] ?? true}
                  onToggle={toggle(setOpenPlatforms)}
                  onPick={onPickHistory}
                  onDelete={onDeleteHistory}
                  onCopyM3u8={onCopyM3u8}
                />
              ))}
            </div>
          )}
        </section>

        {/* 그룹 */}
        <section>
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
                className="flex-1 min-w-0 bg-white/[0.04] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs outline-none focus:border-purple-500/60 placeholder:text-zinc-600"
              />
              <button
                type="button"
                onClick={submitNewGroup}
                className="px-2.5 rounded-lg bg-purple-600/80 hover:bg-purple-600 text-white text-xs font-semibold transition-colors"
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
            <div className="flex flex-col gap-0.5">
              {groups.map((group) => (
                <GroupItem
                  key={group.id}
                  group={group}
                  open={openGroups[group.id] ?? true}
                  onToggle={toggle(setOpenGroups)}
                  onPick={onPickMember}
                  onDeleteGroup={onDeleteGroup}
                  onDeleteMember={onDeleteMember}
                  onDropMember={onDropMember}
                  onCopyM3u8={onCopyM3u8}
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
