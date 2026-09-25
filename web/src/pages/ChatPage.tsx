import { useEffect, useRef, useState, KeyboardEvent } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getMessages,
  sendMessage,
  requestScreenshot,
  getScreenshot,
  getChildren,
  Message,
  Child,
  ScreenshotRequest,
} from '../services/api';
import MessageBubble from '../components/MessageBubble';
import { useAuth } from '../App';

export default function ChatPage() {
  const { childId } = useParams<{ childId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [child, setChild] = useState<Child | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [screenshotLoading, setScreenshotLoading] = useState(false);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const screenshotPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch child info
  useEffect(() => {
    if (!childId) return;

    getChildren()
      .then((children) => {
        const found = children.find((c) => c.childId === childId);
        if (found) setChild(found);
      })
      .catch(() => {});
  }, [childId]);

  // Fetch messages and poll
  useEffect(() => {
    if (!childId) return;

    async function fetchMessages() {
      try {
        const data = await getMessages(childId!);
        setMessages(data);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to load messages.';
        setError(message);
      }
    }

    fetchMessages();
    pollRef.current = setInterval(fetchMessages, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [childId]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Cleanup screenshot poll
  useEffect(() => {
    return () => {
      if (screenshotPollRef.current) clearInterval(screenshotPollRef.current);
    };
  }, []);

  async function handleSend() {
    if (!input.trim() || !childId || sending) return;

    const content = input.trim();
    setInput('');
    setSending(true);

    try {
      const result = await sendMessage(childId, content);
      // Optimistically add the full message to the list
      const optimistic: Message = {
        conversationId: result.conversationId,
        timestamp: result.messageId,
        senderId: parentId,
        senderType: 'parent',
        content,
      };
      setMessages((prev) => [...prev, optimistic]);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to send message.';
      setError(message);
      setInput(content);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleRequestScreenshot() {
    if (!childId || screenshotLoading) return;

    setScreenshotLoading(true);
    setScreenshotUrl(null);

    try {
      const req: ScreenshotRequest = await requestScreenshot(childId);

      screenshotPollRef.current = setInterval(async () => {
        try {
          const result = await getScreenshot(req.requestId, childId);
          if (result.status === 'completed' && result.url) {
            setScreenshotUrl(result.url);
            setScreenshotLoading(false);
            if (screenshotPollRef.current) {
              clearInterval(screenshotPollRef.current);
              screenshotPollRef.current = null;
            }
          } else if (result.status === 'failed') {
            setError('Screenshot request failed.');
            setScreenshotLoading(false);
            if (screenshotPollRef.current) {
              clearInterval(screenshotPollRef.current);
              screenshotPollRef.current = null;
            }
          }
        } catch {
          // keep polling
        }
      }, 2000);

      // Timeout after 30 seconds
      setTimeout(() => {
        if (screenshotPollRef.current) {
          clearInterval(screenshotPollRef.current);
          screenshotPollRef.current = null;
          setScreenshotLoading(false);
          setError('Screenshot request timed out.');
        }
      }, 30000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to request screenshot.';
      setError(message);
      setScreenshotLoading(false);
    }
  }

  const parentId = user?.userId ?? '';

  return (
    <div className="chat-layout">
      {/* Chat header */}
      <header className="chat-header">
        <button className="btn-back" onClick={() => navigate('/chat')}>
          &larr; Back
        </button>
        <div className="chat-header-info">
          <h2>{child?.displayName ?? 'Chat'}</h2>
        </div>
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleRequestScreenshot}
          disabled={screenshotLoading}
        >
          {screenshotLoading ? 'Requesting...' : 'Request Screenshot'}
        </button>
      </header>

      {/* Error banner */}
      {error && (
        <div className="chat-error">
          {error}
          <button className="chat-error-dismiss" onClick={() => setError('')}>
            &times;
          </button>
        </div>
      )}

      {/* Screenshot preview */}
      {screenshotUrl && (
        <div className="screenshot-preview">
          <div className="screenshot-preview-header">
            <span>Screenshot</span>
            <button onClick={() => setScreenshotUrl(null)}>&times;</button>
          </div>
          <img src={screenshotUrl} alt="Child device screenshot" />
        </div>
      )}

      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>No messages yet. Say hello!</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={`${msg.conversationId}-${msg.timestamp}-${i}`}
            message={msg}
            isParent={msg.senderId === parentId || msg.senderType === 'parent'}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="chat-input-area">
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          rows={1}
          disabled={sending}
        />
        <button
          className="btn btn-primary btn-send"
          onClick={handleSend}
          disabled={!input.trim() || sending}
        >
          {sending ? '...' : 'Send'}
        </button>
      </div>
    </div>
  );
}
