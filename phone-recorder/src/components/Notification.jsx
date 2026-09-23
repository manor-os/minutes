import React, { useEffect } from 'react';
import { CheckCircleIcon, AlertCircleIcon } from './Icons';
import './Notification.css';

function Notification({ message, type = 'success', onClose, onAction, actionLabel = 'View Meeting', duration = 5000 }) {
  useEffect(() => {
    // Auto-close after specified duration (default 5 seconds)
    const timer = setTimeout(() => {
      if (onClose) {
        onClose();
      }
    }, duration);

    return () => clearTimeout(timer);
  }, [onClose, duration]);

  return (
    <div className={`notification notification-${type}`}>
      <div className="notification-content">
        <div className="notification-icon">
          {type === 'success' && <CheckCircleIcon size={16} />}
          {type === 'error' && <AlertCircleIcon size={16} />}
          {type === 'info' && <AlertCircleIcon size={16} />}
        </div>
        <div className="notification-message">{message}</div>
        {onAction && (
          <button className="notification-action" onClick={onAction}>
            {actionLabel}
          </button>
        )}
        <button className="notification-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
    </div>
  );
}

export default Notification;
