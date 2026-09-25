import { FormEvent, useState } from 'react';
import { generateCode, GenerateCodeResponse } from '../services/api';

interface RegistrationCodeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function RegistrationCodeModal({
  isOpen,
  onClose,
}: RegistrationCodeModalProps) {
  const [childName, setChildName] = useState('');
  const [codeResult, setCodeResult] = useState<GenerateCodeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  async function handleGenerate(e: FormEvent) {
    e.preventDefault();
    if (!childName.trim()) return;

    setLoading(true);
    setError('');

    try {
      const result = await generateCode(childName.trim());
      setCodeResult(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to generate code.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!codeResult) return;
    try {
      await navigator.clipboard.writeText(codeResult.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select the code text
      const el = document.querySelector('.code-display');
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    }
  }

  function handleClose() {
    setChildName('');
    setCodeResult(null);
    setError('');
    setCopied(false);
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{codeResult ? 'Registration Code' : 'Add Child'}</h3>
          <button className="modal-close" onClick={handleClose}>
            &times;
          </button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        {!codeResult ? (
          <form onSubmit={handleGenerate} className="modal-body">
            <p className="modal-description">
              Enter your child&apos;s name to generate a registration code. They will
              use this code on their device to connect with you.
            </p>
            <div className="form-group">
              <label htmlFor="childName">Child&apos;s Name</label>
              <input
                id="childName"
                type="text"
                value={childName}
                onChange={(e) => setChildName(e.target.value)}
                placeholder="e.g. Alex"
                required
                autoFocus
              />
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading || !childName.trim()}
              >
                {loading ? 'Generating...' : 'Generate Code'}
              </button>
            </div>
          </form>
        ) : (
          <div className="modal-body">
            <p className="modal-description">
              Share this code with your child. Enter it on their device to complete
              registration.
            </p>
            <div className="code-display">{codeResult.code}</div>
            <p className="code-expiry">
              Expires: {new Date(codeResult.expiresAt).toLocaleString()}
            </p>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={handleCopy}>
                {copied ? 'Copied!' : 'Copy Code'}
              </button>
              <button className="btn btn-primary" onClick={handleClose}>
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
