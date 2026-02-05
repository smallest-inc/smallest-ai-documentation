import React from 'react';

export const CapabilityCard = ({
    title,
    description,
    href,
    icon = null
}) => {
    const CardWrapper = href ? 'a' : 'div';

    return (
        <CardWrapper
            href={href}
            className="capability-card"
            style={{ textDecoration: 'none' }}
        >
            {icon && <div className="capability-icon">{icon}</div>}
            <h4 className="capability-title">{title}</h4>
            <p className="capability-description">{description}</p>
            <style jsx>{`
        .capability-card {
          display: block;
          padding: 24px;
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          transition: all 0.2s ease;
        }
        .capability-card:hover {
          border-color: #217D80;
          box-shadow: 0 4px 12px rgba(33, 125, 128, 0.1);
        }
        .capability-icon {
          font-size: 24px;
          margin-bottom: 12px;
        }
        .capability-title {
          font-size: 16px;
          font-weight: 600;
          color: #111827;
          margin: 0 0 8px 0;
        }
        .capability-description {
          font-size: 14px;
          color: #6b7280;
          margin: 0;
          line-height: 1.5;
        }
        :global(.dark) .capability-card {
          background: #1f2937;
          border-color: #374151;
        }
        :global(.dark) .capability-card:hover {
          border-color: #0d9488;
        }
        :global(.dark) .capability-title {
          color: #f9fafb;
        }
        :global(.dark) .capability-description {
          color: #9ca3af;
        }
      `}</style>
        </CardWrapper>
    );
};

export const CapabilityGrid = ({ children, cols = 3 }) => {
    return (
        <div className="capability-grid">
            {children}
            <style jsx>{`
        .capability-grid {
          display: grid;
          grid-template-columns: repeat(${cols}, 1fr);
          gap: 16px;
          margin: 24px 0;
        }
        @media (max-width: 900px) {
          .capability-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
        @media (max-width: 600px) {
          .capability-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
        </div>
    );
};

export default CapabilityCard;
