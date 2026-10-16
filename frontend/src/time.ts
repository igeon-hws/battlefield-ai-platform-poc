export function formatTime(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false }) + ' KST';
}
