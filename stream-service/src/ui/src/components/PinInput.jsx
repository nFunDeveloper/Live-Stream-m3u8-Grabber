import { useEffect, useRef } from 'react';
import { Check } from 'lucide-react';

export const PIN_LENGTH = 4;

// 숫자를 넣은 칸만 짧게 튀어오르게 한다. 매번 클래스를 다시 붙일 필요 없이
// Web Animations API 를 쓰면 재실행도 자연스럽다.
function popBox(el) {
  if (!el?.animate) return;
  el.animate(
    [
      { transform: 'scale(1)' },
      { transform: 'scale(1.18)' },
      { transform: 'scale(1)' },
    ],
    { duration: 260, easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)' }
  );
  el.animate(
    [
      { boxShadow: '0 0 0 0 rgba(255,255,255,0)' },
      { boxShadow: '0 0 20px 3px rgba(255,255,255,0.16)' },
      { boxShadow: '0 0 0 0 rgba(255,255,255,0)' },
    ],
    { duration: 380, easing: 'ease-out' }
  );
}

// 숫자 4자리를 한 칸씩 나누어 받는 일반적인 인증폼.
// 한 칸에 숫자를 넣으면 자동으로 다음 칸으로 넘어가고, 지우면 앞 칸으로 돌아간다.
export default function PinInput({ boxes, onBoxesChange, disabled, onComplete, opened = false }) {
  const refs = useRef([]);
  const filledRef = useRef(false);

  // 첫 칸에 바로 입력할 수 있게 포커스를 넘긴다
  useEffect(() => {
    if (!disabled) refs.current[0]?.focus();
  }, [disabled]);

  // 네 칸이 모두 차면 서버로 보낸다. 한 번만 건다.
  const isComplete = boxes.every((box) => box !== '');
  useEffect(() => {
    if (isComplete && !filledRef.current) {
      filledRef.current = true;
      onComplete(boxes.join(''));
    } else if (!isComplete) {
      filledRef.current = false;
    }
  }, [isComplete, boxes, onComplete]);

  const focusBox = (index) => {
    const target = Math.min(Math.max(index, 0), PIN_LENGTH - 1);
    refs.current[target]?.focus();
    refs.current[target]?.select();
  };

  const write = (index, digits) => {
    const next = [...boxes];
    let cursor = index;
    const touched = [];
    // 붙여넣기나 자동완성으로 여러 자리가 한 번에 들어올 수 있다.
    for (const digit of digits) {
      if (cursor >= PIN_LENGTH) break;
      if (next[cursor] !== digit) touched.push(cursor);
      next[cursor] = digit;
      cursor += 1;
    }
    onBoxesChange(next);
    focusBox(cursor);
    touched.forEach((i) => popBox(refs.current[i]));
  };

  const onChange = (index, event) => {
    const raw = event.target.value.replace(/\D/g, '');
    if (!raw) {
      // 지운 경우. 앞 칸을 당겨오지 않고 그 칸만 비운다.
      const next = [...boxes];
      next[index] = '';
      onBoxesChange(next);
      return;
    }
    write(index, raw);
  };

  const onKeyDown = (index, event) => {
    if (event.key === 'Backspace') {
      // 이미 빈 칸에서 지우면 앞 칸을 함께 지운다
      if (boxes[index] === '' && index > 0) {
        event.preventDefault();
        const next = [...boxes];
        next[index - 1] = '';
        onBoxesChange(next);
        focusBox(index - 1);
      }
      return;
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      focusBox(index - 1);
      return;
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      focusBox(index + 1);
    }
  };

  const onPaste = (index, event) => {
    event.preventDefault();
    const digits = event.clipboardData.getData('text').replace(/\D/g, '');
    if (digits) write(index, digits);
  };

  return (
    <div className="relative">
      <div className="flex items-center justify-center gap-2 sm:gap-3">
        {boxes.map((box, index) => (
          <input
            key={index}
            ref={(el) => {
              refs.current[index] = el;
            }}
            value={box}
            onChange={(e) => onChange(index, e)}
            onKeyDown={(e) => onKeyDown(index, e)}
            onPaste={(e) => onPaste(index, e)}
            onFocus={(e) => e.target.select()}
            disabled={disabled}
            // 인증번호가 그대로 화면에 남지 않도록 마스킹한다. 숫자 키패드는
            // inputMode 로 그대로 유지된다.
            type="password"
            inputMode="numeric"
            // 문자 OTP가 오면 첫 칸에 통째로 들어오는데, 이를 각 칸에 나눠준다.
            autoComplete={index === 0 ? 'one-time-code' : 'off'}
            maxLength={PIN_LENGTH}
            aria-label={`${PIN_LENGTH}자리 인증번호 ${index + 1}번째 자리`}
            className={`pin-box-in w-12 h-14 sm:w-14 sm:h-16 text-center text-xl sm:text-2xl font-semibold
              bg-white/[0.03] border rounded-lg outline-none tabular-nums
              transition-[border-color,background-color,color,box-shadow] duration-200
              focus:border-white/40 focus:bg-white/[0.06] focus:shadow-[0_0_15px_rgba(255,255,255,0.07)]
              disabled:opacity-50 ${
                opened
                  ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300'
                  : box !== ''
                    ? 'border-white/20 text-white'
                    : 'border-white/10 text-white'
              }`}
            // 칸이 하나씩 늦게 나타난다
            style={{ animationDelay: `${index * 65}ms` }}
          />
        ))}
      </div>

      {opened && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-[#0A0A0C]/70 backdrop-blur-[2px] rounded-lg"
          aria-hidden="true"
        >
          <Check className="pin-check w-7 h-7 text-emerald-400" />
        </div>
      )}
    </div>
  );
}