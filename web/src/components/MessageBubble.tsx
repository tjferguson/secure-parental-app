import { Message } from '../services/api';

interface MessageBubbleProps {
  message: Message;
  isParent: boolean;
}

function formatTime(timestamp: string): string {
  // Timestamp format: "2026-03-09T17:16:08.001073+00:00_uuid" — strip the UUID suffix
  const isoStr = timestamp.replace(/_[0-9a-f-]+$/, '');
  const date = new Date(isoStr);
  if (isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function MessageBubble({ message, isParent }: MessageBubbleProps) {
  const alignment = isParent ? 'bubble-right' : 'bubble-left';
  const colorClass = isParent ? 'bubble-parent' : 'bubble-child';
  const label = isParent ? 'You' : 'Child';

  return (
    <div className={`message-row ${alignment}`}>
      <div className={`message-bubble ${colorClass}`}>
        <div className="bubble-sender">{label}</div>
        <div className="bubble-content">{message.content}</div>
        <div className="bubble-time">{formatTime(message.timestamp)}</div>
      </div>
    </div>
  );
}
