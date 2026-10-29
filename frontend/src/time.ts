export function formatTime(value?: string | null): string {
  if (!value) return '정보 없음';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false }) + ' KST';
}
