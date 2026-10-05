// 잠글 때 사용하는 신호.
//
// 잠금 상태는 PasswordGate 가 갖고 있고, 잠그라는 버튼은 앱 안쪽(App 헤더)에
// 있다. 두 곳을 prop 으로 이어주기보다 창에 신호를 쏘는 편이 단순하고,
// 사이드바처럼 다른 자식에서도 그대로 쓸 수 있다.
export const LOCK_EVENT = 'm3u8-grabber:lock';

export function requestLock() {
  window.dispatchEvent(new CustomEvent(LOCK_EVENT));
}