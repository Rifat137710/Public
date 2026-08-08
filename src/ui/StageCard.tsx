/**
 * The narrative overlay: a stage brief before a run, a reveal after it.
 *
 * It covers the screen because each of these is a beat the learner is meant to stop
 * and read, and because the reveal has to land before they start fiddling with
 * controls again. Dismissing is always one obvious button or the Escape key.
 */

import { useEffect, useRef } from 'react';

interface Props {
  eyebrow: string;
  title: string;
  paragraphs: string[];
  actionLabel: string;
  onAction: () => void;
  /** Shown under the action, e.g. skip to the sandbox. */
  secondary?: { label: string; onClick: () => void };
  tone?: 'brief' | 'reveal';
}

export function StageCard({
  eyebrow,
  title,
  paragraphs,
  actionLabel,
  onAction,
  secondary,
  tone = 'brief',
}: Props) {
  const actionRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    actionRef.current?.focus();
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Enter' || event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onAction();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onAction]);

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="card" data-tone={tone}>
        <p className="card-eyebrow">{eyebrow}</p>
        <h1 className="card-title">{title}</h1>
        {paragraphs.map((text, i) => (
          <p key={i} className="card-body">
            {text}
          </p>
        ))}
        <div className="card-actions">
          <button ref={actionRef} className="ctl primary" onClick={onAction}>
            {actionLabel}
          </button>
          {secondary && (
            <button className="ctl quiet" onClick={secondary.onClick}>
              {secondary.label}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
